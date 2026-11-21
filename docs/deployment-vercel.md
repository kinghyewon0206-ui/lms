# ECONOVA Vercel 배포 계획 (대회용, 2026-11-21)

> 내부 문서. **이 문서는 배포 실행 기록이 아니다.** 아직 Vercel 프로젝트는 만들지 않았고, 아무것도 배포하지 않았다.
> 근거: Vercel·Google 공식 문서(2026-11-21 열람). 확인하지 못한 항목은 "미확인"으로 적었다.
> Render 계획(`docs/deployment-econova.md`)은 대회용으로는 이 문서로 대체한다. Render 자동 배포를 건드리지 않는다.

## 1. 결론
- Flask/Jinja 를 그대로 Vercel Python 런타임에 올릴 수 있다. Vercel 은 `app.py` 의 Flask 인스턴스 `app` 을 설정 없이 찾는다.
  앱 전체가 Function 하나가 된다 (Fluid compute 기본).
- 런타임에 디스크에 쓰는 코드는 CLI 명령(`content-release-apply`, `review-package`)뿐이고, 웹 요청 경로에는 없다.
  운영 데이터는 Firestore(`DB_BACKEND=firestore`)에만 저장한다. sqlite 는 로컬 개발 전용이고, 운영에서는 시작이 거부된다.
- 정답 키 폴더(`~/econova-private`)는 Vercel 에 없다. 그래서 **정답 키 묶음**(gzip+base64 JSON 한 개)을
  Secret Manager(권장) 또는 Sensitive 환경변수로 넣는 경로를 추가했다 (`econova/private_content.py`).
- Hobby(무료) 플랜 약관은 "개인적 또는 비상업적 사용"만 허용한다. 비상업 학교 대회는 이 조건에 맞아 보이지만, 약관이 "commercial" 을 정의하지 않으므로 법적 판단은 아니다.

## 2. 호환성 점검표
| 항목 | 상태 | 조치 |
|---|---|---|
| 진입점 | OK | `app.py` 의 `app` (zero-config). `.python-version` = 3.12 (Vercel 기본 3.12, 로컬 .venv 3.12.4) |
| 의존성 | OK | `requirements.txt` (Flask, gunicorn, firebase-admin). google-auth·requests 는 firebase-admin 이 함께 설치하므로 새 패키지 없음 |
| 파일 쓰기 | OK | 읽기 전용 파일시스템(쓰기는 `/tmp` 500 MB, 인스턴스마다 따로, 사라짐). 웹 경로에서 쓰지 않음 |
| sqlite | 운영 금지 | `VERCEL_ENV=production/preview` 면 운영으로 판단 → `DB_BACKEND` 필수, sqlite 거부 |
| 세션 | OK | 서명 쿠키(Flask). 인스턴스 간 공유 상태 없음. 운영에서 `SECRET_KEY` 32자 이상 필수, Secure 쿠키 |
| 정적 파일 | 동작함, 최적화는 나중 | Vercel 문서는 `public/**` 사용을 권장한다(CDN). 지금은 Flask 가 `static/` 을 함수로 제공한다. 첫 미리보기 배포에서 응답 시간을 재 보고, 필요하면 빌드 때 `public/static` 으로 복사한다 |
| 함수 시간 | OK | Hobby 기본·최대 300초. `vercel.json` 에서 60초로 제한 (OpenAI 호출 타임아웃보다 김) |
| 요청 크기 | OK | 4.5 MB 제한. 업로드 기능 없음 |
| 백그라운드 작업 | 바꿈 | 없음. `ai-purge` 는 하루 1회 Vercel Cron → `/internal/cron/daily-cleanup` (`CRON_SECRET` Bearer 필수, 없으면 404). Hobby Cron 은 하루 1회, ±59분 오차, 중복·누락 가능 → 여러 번 실행해도 안전하게 만듦 |
| 클라이언트 IP | 설정값 1개 | Vercel 은 `X-Forwarded-For` 를 덮어써서 위조 값을 전달하지 않는다 → `ECONOVA_TRUSTED_PROXY_HOPS=1` |
| Firestore | OK | 서비스 계정 JSON(`FIREBASE_CREDENTIALS_JSON`, Sensitive). OIDC 방식은 4장 |
| OpenAI | OK | urllib, 타임아웃 있음. `OPENAI_API_KEY` Sensitive |
| 개발 기능 | 차단됨 | 운영에서 `ECONOVA_DEV_FIXTURES=1`·`ECONOVA_CONTENT_PREVIEW=1` 은 시작 실패. `.vercelignore` 로 `content/dev_fixtures/` 를 올리지 않음 |
| 콜드 스타트 | 측정 필요 | 6장 |

## 3. 정답 키 보호
정답 키 36개는 Git·공개 정적 파일에 절대 넣지 않는다 (`.gitignore`, `.vercelignore`, `check-public-files`, `tests/test_vercel_compat.py`).

| 방법 | 크기 한도 | 장점 | 단점 |
|---|---|---|---|
| **A. Google Secret Manager (권장)** | 버전당 64 KiB | 키가 Vercel 에 없음. 접근 기록(감사 로그). 회전 쉬움. 무료 등급: 활성 버전 6개, 접근 10,000회/월 (결제 계정 기준) | 결제 계정이 연결된 프로젝트 필요 (무료 등급 안이면 0원, 유료 요금은 공식 가격 페이지를 끝까지 읽지 못해 미확인). 서비스 계정에 이 비밀 하나에 대한 `roles/secretmanager.secretAccessor` 추가 |
| B. Vercel Sensitive 환경변수 | 배포당 모든 변수 합계 64 KB | 추가 클라우드 설정 없음 | 지금 묶음 54,820자 → 다른 변수와 합쳐 64 KB 에 근접 (여유 약 9 KB). 평가가 늘면 넘침 |
| C. Git 에 암호화해 넣기 | — | — | 공개 저장소이므로 **사용 안 함** |

- 묶음 만들기 (저장소 밖에만 쓸 수 있음): `flask --app app private-keys-bundle --output ~/econova-private/vercel/keys-bundle.b64`
  → 공개 문항과 맞지 않는 키가 하나라도 있으면 만들지 않는다. 화면에는 개수·크기·지문만 출력한다.
- A: 비밀 값으로 업로드 → `ECONOVA_PRIVATE_KEYS_SECRET=projects/<PROJECT>/secrets/<NAME>/versions/<N>` (버전 번호 고정 권장).
  인스턴스마다 처음 한 번만 읽고 메모리에 둔다.
- B: `ECONOVA_PRIVATE_KEYS_BUNDLE` 에 파일 내용 전체 (Sensitive, Production 환경에만).
- 대회에서는 **승인·공개된 평가의 키만** 넣어도 된다 (나머지 평가는 어차피 열리지 않는다). 그러면 크기도 줄어든다.

## 4. Vercel OIDC → Google Cloud (Workload Identity Federation)
- 모든 플랜에서 쓸 수 있다. 함수 요청 헤더 `x-vercel-oidc-token`(유효 2시간)으로 토큰을 받는다. 발급자는 `https://oidc.vercel.com/<team>`, 주체는 `owner:<team>:project:<project>:environment:production`.
- Python 은 `google.auth.identity_pool.Credentials` + 요청 헤더에서 토큰을 읽는 supplier 로 구현할 수 있다 (약 30줄).
  그러면 서비스 계정 JSON 키가 필요 없다.
- Google Cloud 쪽 자원 약 5개(풀, 공급자, 서비스 계정, 권한 2개)가 필요하다. Firestore 클라이언트는 시작할 때 한 번 만들어지고 토큰은 요청마다 오므로 구조를 바꿔야 한다.
- **판단: 대회 출시를 막는 요소가 아니다. 출시 후 보안 강화 단계로 둔다.** 대회에서는 최소 권한 서비스 계정 키(`roles/datastore.user` + 이 비밀 하나에 대한 accessor)를 Sensitive 환경변수로 쓴다.

## 5. 브랜치 안전장치 (이전 LMS 가 ECONOVA 로 배포되지 않게)
`vercel.json` 은 **빌드되는 커밋의 파일**이 읽히는 것으로 보인다 (공식 문서로 확인하지 못함). main 에는 이 파일이 없으므로 `vercel.json` 만으로는 막을 수 없다. 대시보드에서 다음을 반드시 설정한다.
1. **Project Settings → Environments → Production → Branch Tracking**: `feature/econova-lms-renewal` (또는 대회용 릴리스 브랜치). 기본값은 `main` 이므로 프로젝트를 만들 때 바로 바꾼다.
2. **Project Settings → Git → Ignored Build Step** (대시보드 설정이라 모든 커밋에 적용됨):
   `if [ "$VERCEL_GIT_COMMIT_REF" = "feature/econova-lms-renewal" ]; then exit 1; else exit 0; fi`
   (exit 1 = 빌드, exit 0 = 건너뜀. "Automatically Expose System Environment Variables" 켜기)
3. `vercel.json` 의 `git.deploymentEnabled: {"main": false, "master": false}` 는 이 브랜치 쪽의 이중 방어다.
4. 첫 배포 전에 **Deployment Protection = Vercel Authentication, "All Deployments"** (Hobby 가능)로 두면 소유자만 볼 수 있다. 공개(심사위원 접근)는 소유자 승인 뒤에만 "Standard Protection" 으로 내린다. 비밀번호 보호는 Hobby 에서 쓸 수 없다 (Pro 유료 추가 기능).
5. Hobby 는 GitHub **조직** 소유 비공개 저장소를 배포할 수 없다. `kinghyewon0206-ui/lms` 는 개인 계정의 공개 저장소이므로 해당 없음. Hobby 에서는 소유자 본인 커밋만 배포된다.
6. Render 는 건드리지 않는다. main 병합 없음.

## 6. 콜드 스타트 측정
- 공개된 Python 콜드 스타트 수치는 없다. 2주(운영)·3일(미리보기) 동안 호출이 없으면 함수가 보관되고, 다음 첫 호출에 최소 1초가 더 걸린다.
- 측정용 헤더: `ECONOVA_TIMING_HEADERS=1` 이면 응답에 `Server-Timing: app;dur=<ms>` 와 `X-Econova-Instance: cold|warm; age=..; served=..` 가 붙는다 (측정이 끝나면 끈다).
- 방법:
  1. 미리보기 배포에서 `curl -s -o /dev/null -D - -w 'total=%{time_total}\n' https://<배포주소>/login` 을 10분 이상 쉬었다가 1회(콜드), 바로 이어서 5회(웜) 실행한다.
  2. `X-Econova-Instance`, `Server-Timing`, `x-vercel-id`(실행 지역), 전체 시간을 기록한다.
- 지역: 기본 `iad1`(미국 동부). Firestore 위치와 가까운 지역으로 함수 지역을 맞출지는 측정 뒤 결정한다.
- 대회 당일에는 시작 10분 전에 주요 화면을 한 번씩 열어 데운다.

## 7. Hobby 한도 (대회 규모 판단)
- 월간: Active CPU 4시간, 프로비전 메모리 360 GB-시간, 함수 호출 100만, Fast Data Transfer 100 GB. 넘으면 대부분 30일을 기다려야 한다 → 대회 기간 직전에 사용량 대시보드를 확인한다.
- 메모리 2 GB 고정, 번들 500 MB(Python), 런타임 로그 보존 1시간, 하루 배포 100회.

## 8. 환경변수 목록 (Vercel → Settings → Environment Variables)
| 변수 | 환경 | Sensitive | 값 / 메모 |
|---|---|---|---|
| `SECRET_KEY` | Production, Preview(따로) | 예 | 64자 무작위. 환경마다 다르게 |
| `DB_BACKEND` | Production, Preview | 아니오 | `firestore` |
| `FIREBASE_CREDENTIALS_JSON` | Production (Preview 는 개발 프로젝트용 별도 계정) | 예 | 최소 권한 서비스 계정 JSON. 지금 있는 시험용 관리자 키는 쓰지 않는다 |
| `ECONOVA_PRIVATE_KEYS_SECRET` 또는 `ECONOVA_PRIVATE_KEYS_BUNDLE` | Production | 예 | 3장 |
| `ECONOVA_TRUSTED_PROXY_HOPS` | 모두 | 아니오 | `1` |
| `OPENAI_API_KEY` | Production | 예 | 없으면 AI 기능이 꺼진 채로 동작. 사용 한도는 OpenAI 쪽에서 설정 |
| `ECONOVA_AI_PROVIDER` | Production | 아니오 | `openai` (Preview 는 `mock` 권장) |
| `ECONOVA_AI_MODEL` | Production | 아니오 | 사용할 모델 이름 (소유자 결정). `OPENAI_MODEL` 은 쓰지 않는다 |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Production | 비밀만 예 | `docs/google-sign-in-setup.md` |
| `GOOGLE_OAUTH_REDIRECT_URI` | Production | 아니오 | `https://<운영 도메인>/auth/google/callback` (Google 에 등록한 값과 완전히 같게) |
| `CRON_SECRET` | Production | 예 | 32자 이상 무작위. Vercel 이 Cron 요청에 Bearer 로 붙인다 |
| `ECONOVA_RELEASE_SIGNING_KEY` | (Vercel 에 넣지 않음) | — | 릴리스 계획 서명은 로컬에서만 |
| `ECONOVA_TIMING_HEADERS` | 측정할 때만 | 아니오 | `1` |
| 넣지 않는 변수 | — | — | `ECONOVA_DEV_FIXTURES`, `ECONOVA_CONTENT_PREVIEW`, `ECONOVA_PRIVATE_CONTENT_DIR`, `SQLITE_PATH`, `ECONOVA_ALLOW_ADMIN_BOOTSTRAP`, `ECONOVA_PROXY_DIAGNOSTICS`, `APP_ENV`(VERCEL_ENV 로 대체) |

## 9. 첫 배포 순서 (소유자 승인 후에만)
1. Vercel 계정(Hobby)에서 GitHub `kinghyewon0206-ui/lms` 가져오기 → **배포 전에** 5장 1·2·4 설정.
2. 환경변수 입력(8장). Preview 는 개발용 Firestore 프로젝트·mock AI.
3. 미리보기 배포 → `/login` 200, 정답 키 확인(관리자 화면의 평가 상태), Google 로그인(콜백 주소 등록 후), 6장 측정.
4. 공개 범위 결정(`docs/competition-demo-plan.md`) → 소유자 승인 → 보호 단계 조정.
