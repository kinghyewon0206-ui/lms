# ECONOVA Vercel 배포 계획 (대회용, 2026-11-21 개정)

> 내부 문서. **배포 실행 기록이 아니다.** Vercel 프로젝트는 아직 없고 아무것도 배포하지 않았다.
> 근거: Vercel·Google 공식 문서(2026-11-21 열람). 공식 문서로 확인하지 못한 항목은 **미확인**으로 표시했다 — 첫 미리보기 배포에서 확인한다.
> Render 는 대회용으로 쓰지 않는다 (기존 Render 서비스는 건드리지 않음).

## 1. 결론
- Flask/Jinja 를 그대로 Vercel Python 런타임(3.12)에 올린다. Vercel 이 `app.py` 의 `app` 을 설정 없이 찾고, 앱 전체가 Function 하나가 된다 (Fluid compute 기본).
- **정적 파일은 `public/static/` 으로 옮겼다.** Vercel 문서: `app.static_folder` 는 Vercel 에서 정적 파일 제공에 쓰이지 않는다(무시된다), `public/**` 를 쓰라. 주소는 그대로 `/static/...` 이고, 로컬·테스트에서는 Flask 가 같은 폴더를 제공한다.
  `public/static/x.css → /static/x.css` 로 매핑되는지는 문서에 명시가 없어 **첫 배포에서 확인**한다 (안 되면 Flask 가 함수에서 계속 제공하므로 화면은 깨지지 않는다).
- 함수 지역을 **`icn1`(서울)** 로 지정했다 (`vercel.json`). Firestore(`econova-dev`)가 서울(asia-northeast3)에 있으므로, 기본값 `iad1`(미국 동부)에서는 Firestore 호출마다 태평양을 왕복한다. Hobby 도 지역 1개를 고를 수 있다. 지역 코드 목록 페이지는 열어 보지 못했으므로, 배포가 지역 오류로 실패하면 `hnd1`(도쿄)로 바꾼다.
- 운영 데이터는 Firestore 에만 저장한다. sqlite·디자인 시안·개발용 강좌·초안 미리보기·모의 AI 는 운영(`VERCEL_ENV=production/preview`)에서 켜면 앱이 시작하지 않는다.

## 2. 호환성 점검 (코드로 확인)
| 항목 | 결과 |
|---|---|
| 진입점·버전 | `app.py`/`app`, `.python-version` 3.12 (로컬 3.12.4) |
| 의존성 | `requirements.txt` 3개(Flask, gunicorn, firebase-admin). google-auth·requests 는 firebase-admin 이 설치. 로컬 site-packages 122 MB (한도 500 MB) |
| 파일 쓰기 | 웹 요청 경로에 없음 (CLI 만). Vercel 은 읽기 전용 + `/tmp` |
| 세션 | 서명 쿠키, HttpOnly·SameSite=Lax, 운영에서 Secure. Google 콜백(최상위 GET)은 Lax 쿠키를 받는다 |
| Firestore | 첫 사용 때 한 번 초기화(지연 연결). 선택 설정 `ECONOVA_FIRESTORE_DATABASE`(이름 있는 데이터베이스) 추가 — 4장 |
| OpenAI | urllib, 타임아웃 20초(설정 가능), 함수 제한 60초 |
| 정답 키 | 묶음(Secret Manager 또는 환경변수) — 3장 |
| Cron | `/internal/cron/daily-cleanup` 하루 1회, `CRON_SECRET` Bearer 필수(없으면 404). Hobby Cron 은 하루 1회·±59분·중복 가능 → 반복 실행해도 안전 |
| 클라이언트 IP | Vercel 이 `X-Forwarded-For` 를 덮어쓴다(위조 값 전달 안 함) → `ECONOVA_TRUSTED_PROXY_HOPS=1` (테스트로 확인) |
| 콜백 주소 | 운영에서는 `GOOGLE_OAUTH_REDIRECT_URI` 필수 (Vercel 뒤에서 `request.scheme` 이 http 일 수 있으므로 자동 생성 주소를 쓰지 않음) |

로컬 측정 (2026-11-21, 이 컴퓨터): `import app` 0.27~0.56초, 강좌 카탈로그 첫 로드 0.05초, 정답 키 묶음 해제 0.001초.
**Vercel 콜드 스타트는 측정 전이다** — 7장 절차로 첫 배포 뒤 잰다. 공식 문서에 Python 콜드 스타트 수치는 없고, Vercel 이 `.pyc` 를 미리 만들어 넣는다고만 되어 있다.

## 3. 정답 키 (36개) 보관
- 묶음 크기: **54,820 바이트** (ASCII base64, 정답 키 36개 gzip). `flask private-keys-bundle --output <저장소 밖 경로>` 로 만든다 (공개 문항과 하나라도 맞지 않으면 만들지 않음, 화면에는 개수·크기·지문만).
- 한도: Secret Manager 비밀 버전당 **64 KiB(65,536 바이트)** → 여유 약 10.7 KB. Vercel 환경변수는 **배포당 전체 합계 64 KB** → 다른 변수(서비스 계정 JSON 약 2.3 KB 등)와 합치면 여유가 거의 없다.
- **권장: Google Secret Manager + 그 비밀 하나에만 주는 최소 권한.**
  - 요금(공식 가격표): 무료 등급 월 활성 버전 6개·접근 10,000회·회전 알림 3회 (결제 계정 단위 합산). 초과 시 버전당 월 약 $0.06, 접근 1만 회당 $0.03. 결제 계정 연결이 필요해 보이나 명시 문구는 미확인.
  - 권한: `roles/secretmanager.secretAccessor` 를 **비밀 하나에만** 부여 (프로젝트 전체 아님).
  - 앱 동작: 인스턴스마다 처음 한 번 읽고 메모리에 둔다 (월 접근 수 ≈ 콜드 스타트 수). 읽기 실패·형식 오류면 그 평가는 열리지 않는다(fail closed). 로그·응답에 키 내용은 나가지 않는다.
  - 갱신: 새 버전 추가 → `ECONOVA_PRIVATE_KEYS_SECRET` 의 버전 번호 변경 → 재배포 (버전 고정으로 예기치 않은 변경 방지).
- 대안: Sensitive 환경변수 `ECONOVA_PRIVATE_KEYS_BUNDLE` (추가 클라우드 설정 없음, 크기 여유 부족).
- 대회용으로는 **공개(승인)할 강좌의 평가 키만** 묶어도 된다 → 크기·노출 범위 모두 줄어든다.
- Vercel OIDC → Google Cloud(Workload Identity Federation): 모든 플랜 가능. 풀·공급자·서비스 계정·바인딩 4가지 자원과 Vercel 변수 5개가 필요하다. 공식 예제는 TypeScript 뿐(Python 예제 없음). → **대회 뒤 보안 강화 단계**로 둔다. 대회에는 최소 권한 서비스 계정 키(Sensitive)를 쓴다.

## 4. 데이터 (Firestore)
- Firestore 무료 할당량은 **프로젝트당 데이터베이스 1개**(처음 만든 것)에만 적용된다. 추가 데이터베이스는 사용량만큼 과금.
- 권장: 기존 `econova-dev` 의 기본 데이터베이스를 대회용으로 쓴다. 로컬 검토 DB(`review.db`, sqlite)와는 처음부터 분리되어 있고, 실제 학생 기록은 없다. 연동 테스트가 남긴 표식 문서(`econova_it/marker`)만 있다.
- 새 프로젝트를 만들지 않는다. 다른 데이터베이스가 꼭 필요하면 `ECONOVA_FIRESTORE_DATABASE=<id>` 로 지정할 수 있다(유료 가능성 — 소유자 승인 필요).
- 저장되는 것: 계정, Google 연결(`econ_user_identities`), 수강, 진도, 평가 시도, 진단, AI 대화(30일 뒤 정리), 캡스톤. 대회 뒤 정리 정책은 소유자 결정.

## 5. 브랜치 안전 (이전 LMS 가 배포되지 않게)
`vercel.json` 은 빌드되는 커밋에서 읽히는 것으로 보이며(공식 명시 없음) main 에는 이 파일이 없다. 그래서 대시보드 설정이 진짜 방어선이다.

**권장 구성: 대회 전용 브랜치 `competition` 을 Production Branch 로 쓴다.**
- feature 브랜치에 푸시할 때마다 운영 사이트가 바뀌지 않고, 공개는 `competition` 으로 옮길 때만 일어난다 (소유자 승인 시점이 분명해짐).
- `competition` 브랜치는 소유자가 공개를 승인할 때 feature 브랜치에서 만든다 (지금 만들지 않음).

| 설정 | 위치 (Vercel 대시보드) | 값 |
|---|---|---|
| Production Branch | Project Settings → Environments → Production → Branch Tracking | `competition` (기본값 `main` 을 프로젝트 만들 때 바로 바꾼다) |
| Ignored Build Step | Project Settings → Build and Deployment → Ignored Build Step → Custom | `if [ "$VERCEL_GIT_COMMIT_REF" = "competition" ] \|\| [ "$VERCEL_GIT_COMMIT_REF" = "feature/econova-lms-renewal" ]; then exit 1; else exit 0; fi` (1 = 빌드, 0 = 취소. main·다른 브랜치는 빌드 안 함. 취소도 배포 횟수에 포함) |
| 시스템 변수 노출 | Project Settings → Environment Variables | "Automatically Expose System Environment Variables" 켜기 |
| Function Region | `vercel.json` `regions: ["icn1"]` (대시보드 Settings → Functions 에서도 가능) | 서울 |
| Deployment Protection | Project Settings → Deployment Protection | 처음: **All Deployments** (소유자만). 공개 승인 후: **Standard Protection** |
| 이중 방어 | `vercel.json` `git.deploymentEnabled` | `main`·`master` false |

- 완전히 멈추려면: Settings → Git → Disconnect (연결 해제).
- Hobby 는 GitHub 조직 소유 비공개 저장소를 배포할 수 없다. `kinghyewon0206-ui/lms` 는 개인 계정 공개 저장소라 해당 없음.

## 6. 공개 접근 (심사위원)
- **Standard Protection**: 운영 도메인을 제외한 모든 주소를 보호한다 → 미리보기 배포와 배포별 생성 주소(`…-hash.vercel.app`)는 Vercel 로그인 필요, **운영 도메인은 누구나 접속**. 심사위원은 Vercel 계정이 필요 없다.
- 프로젝트 기본 별칭 `<project>.vercel.app` 이 "운영 도메인"으로 취급되어 공개되는지는 문서에 명시가 없다(**미확인**) → 첫 배포 후 시크릿 창에서 확인. 공개되지 않으면 Domains 에 별칭을 운영 도메인으로 추가한다.
- Hobby 에서는 비밀번호 보호를 쓸 수 없다 (Pro 유료). 그래서 공개 사이트의 학습 기능 보호는 **ECONOVA 로그인**이 맡는다: 랜딩·로그인·가입만 공개, 나머지는 로그인 필요, 관리 화면은 관리자 권한(서버 검사, 그 외 404).
- 공개 전 확인: 공개된 강좌 범위(소유자 승인), 디자인 시안·초안 미리보기 꺼짐(운영에서 강제), 관리자 계정만 관리자.

## 7. 콜드 스타트 측정 (첫 미리보기 배포 뒤)
1. 미리보기에 `ECONOVA_TIMING_HEADERS=1` 임시 설정 → 재배포.
2. 15분 이상 아무도 접속하지 않은 뒤:
   `curl -s -o /dev/null -D - -w 'total=%{time_total}s ttfb=%{time_starttransfer}s\n' https://<주소>/login` (보호된 주소면 브라우저 개발자 도구 Network 탭에서 같은 값 확인)
3. 바로 이어서 5회 더 → 첫 번째(콜드)와 나머지(웜) 비교. 응답 헤더 `X-Econova-Instance`(cold/warm), `Server-Timing`(앱 처리 시간), `x-vercel-id`(실행 지역)를 기록.
4. 로그인한 상태로 `/dashboard` 도 같은 방식으로 (Firestore 첫 연결 포함 시간).
5. 측정이 끝나면 `ECONOVA_TIMING_HEADERS` 삭제.
대회 당일: 시작 10분 전에 랜딩·로그인·대시보드·레슨을 한 번씩 열어 데운다. (Hobby 에는 미리 데워 두는 인스턴스 기능이 없다.)

## 8. 환경변수 (Production)
| 변수 | Sensitive | 값 |
|---|---|---|
| `SECRET_KEY` | 예 | 64자 무작위 (Preview 와 다르게) |
| `DB_BACKEND` | 아니오 | `firestore` |
| `FIREBASE_CREDENTIALS_JSON` | 예 | 최소 권한 서비스 계정 (`roles/datastore.user` + 비밀 하나의 accessor). 지금 있는 시험용 관리자 키 사용 금지 |
| `ECONOVA_PRIVATE_KEYS_SECRET` | 아니오(이름만) | `projects/<PROJECT>/secrets/<NAME>/versions/<N>` |
| `ECONOVA_TRUSTED_PROXY_HOPS` | 아니오 | `1` |
| `GOOGLE_OAUTH_CLIENT_ID` | 아니오 | Google 클라이언트 ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | 예 | Google 클라이언트 비밀값 |
| `GOOGLE_OAUTH_REDIRECT_URI` | 아니오 | `https://<운영 도메인>/auth/google/callback` |
| `CRON_SECRET` | 예 | 32자 이상 무작위 |
| `ECONOVA_AI_PROVIDER` | 아니오 | `openai` (AI 튜터를 켤 때만, 소유자 승인 후) 또는 `off` |
| `OPENAI_API_KEY` | 예 | 기존 academy 키 (새 키 만들지 않음) |
| `ECONOVA_AI_MODEL` | 아니오 | `gpt-4o-mini` (2026-11-13 실제 연동 시험한 모델) |
| `ECONOVA_AI_DAILY_REQUESTS` / `ECONOVA_AI_GLOBAL_DAILY_REQUESTS` | 아니오 | 학생 1인 하루 20 / 전체 하루 300 (기본값) |
| 측정 때만 | 아니오 | `ECONOVA_TIMING_HEADERS=1` |
| **넣지 않음** | — | `ECONOVA_DEV_FIXTURES`, `ECONOVA_CONTENT_PREVIEW`, `ECONOVA_DESIGN_PROTOTYPES`, `ECONOVA_PRIVATE_CONTENT_DIR`, `SQLITE_PATH`, `ECONOVA_ALLOW_ADMIN_BOOTSTRAP`, `ECONOVA_PROXY_DIAGNOSTICS`, `ECONOVA_RELEASE_SIGNING_KEY`, `APP_ENV`, `OPENAI_MODEL` |

Preview 환경: 다른 `SECRET_KEY`, `ECONOVA_AI_PROVIDER=off`, Google 변수 없음(콜백 주소가 배포마다 바뀌어 등록 불가).

## 9. Hobby 한도 (대회 규모)
월 Active CPU 4시간, 메모리 360 GB-시간, 함수 호출 100만, Fast Data Transfer 100 GB. 넘으면 대부분 30일 대기 → 대회 직전에 Usage 화면 확인. 메모리 2 GB 고정, 런타임 로그 1시간 보관, 하루 배포 100회. 약관: Hobby 는 "개인적 또는 비상업적 사용" — 비상업 학교 대회는 맞아 보이나 법적 판단은 아니다.

## 10. 첫 배포 순서 (소유자 승인 후)
1. Vercel(Hobby)에서 `kinghyewon0206-ui/lms` 가져오기 → **첫 빌드 전에** 5장 표의 설정 (Production Branch, Ignored Build Step, All Deployments 보호).
2. Secret Manager 비밀 만들기 → 최소 권한 서비스 계정 → 8장 환경변수.
3. feature 브랜치 미리보기 배포 → 보호된 상태에서 `/login`, 정적 파일(`/static/style.css`), 정답 키 상태, 7장 측정.
4. Google 클라이언트에 운영 도메인 콜백 등록 (`docs/google-sign-in-setup.md`).
5. 공개 승인 → `competition` 브랜치 생성·푸시 → 운영 배포 확인 → Standard Protection 으로 전환 → 시크릿 창에서 공개 접근·Google 로그인 확인.

## 11. 프로젝트 생성 방법 (2026-11-21 공식 문서 재확인 → 계획 변경)
- 대시보드 "Import Git Repository" 는 **Deploy 를 누르는 즉시 첫 배포**를 만든다. **새 프로젝트의 첫 배포는 항상 Production** 이고, Production Branch 기본값은 `main` → **이전 LMS 가 운영으로 배포될 위험** → 대시보드 Import 를 쓰지 않는다.
- Ignored Build Step 은 배포를 막는 것이 아니라 빌드를 시작한 뒤 취소(CANCELED)한다 (배포 횟수에는 포함).
- **채택: Git 연결 없이 CLI 로만 배포한다.** 로컬 worktree(`feature/econova-lms-renewal`)에서 `vercel deploy` → `.vercelignore` 가 적용된 로컬 파일만 올라가고, main 은 Vercel 이 아예 보지 못한다. 자동 배포도 없다.
  1. `vercel login` (소유자 본인 계정, 터미널에서 직접)
  2. `vercel project create econova` (배포 없음)
  3. 대시보드 Settings → Deployment Protection → Vercel Authentication → **All Deployments** (Hobby 가능). 새 프로젝트 기본값은 Standard(운영 도메인 공개)이므로 첫 배포 전에 바꾼다.
  4. 환경변수(Secret 유형, Production) 입력 — 첫 배포는 Production 변수로 빌드된다.
  5. worktree 에서 `vercel link --yes --project econova` → `vercel deploy` (첫 배포 = Production 이지만 All Deployments 보호로 비공개)
  6. 공개 승인 후: Deployment Protection 을 Standard 로 내린다 (운영 도메인만 공개, 나머지 주소는 계속 보호).
- `icn1` = 서울(ap-northeast-2) 확인됨. Hobby 는 지역 1개 선택 가능.
- Vercel 의 "Sensitive" 환경변수는 현재 **Secret** 유형으로 이름이 바뀌었다 (저장 후 읽을 수 없음, 환경별 값 지정 가능).
- Google: openid/email/profile 만 요청하면 Testing 상태에서도 경고 화면·테스트 사용자 제한·7일 만료가 없다 (support.google.com/cloud/answer/15549945).
