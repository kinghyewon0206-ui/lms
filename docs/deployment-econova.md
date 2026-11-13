# ECONOVA 배포 — 기존 Render 서비스 `lms` 를 ECONOVA 로 교체

> 2026-11 결정: 이전 LMS 는 폐기했다. 기록·사용자·호환성을 보존하지 않는다. 새 Render 서비스는 만들지 않고 `lms` 를 그대로 쓴다.
> Firebase 는 `econova-dev`, OpenAI 는 학원 제공 키를 쓴다. 이 문서의 명령은 그대로 복사해 실행하지 말고 한 줄씩 확인한다.

## 1. 지금 상태
- Render `lms`: `main` 브랜치를 배포한다 (마지막 배포 `039b48f` = 이전 LMS). 무료 플랜.
- ECONOVA 는 `feature/econova-lms-renewal` 에 있다. `main` 에 합쳐야 Render 가 ECONOVA 를 배포한다.
- **이전 LMS 코드는 시작할 때마다 `init_db()` 를 실행하고, `FIREBASE_CREDENTIALS_JSON` 이 있으면 그 Firebase 에 대학 강의 목록을
  쓴다.** 그래서 `econova-dev` 키를 먼저 넣고 이전 코드가 다시 시작되면 `econova-dev` 에 이전 LMS 데이터가 섞인다 → 3장 순서를 지킨다.

## 2. 운영 설정 (`render.yaml` 과 같음)
- Build `pip install -r requirements.txt` · Start `gunicorn app:app --bind 0.0.0.0:$PORT` · Health check `/login`
- 환경변수

| 이름 | 값 | 비고 |
|---|---|---|
| `PYTHON_VERSION` | `3.12.4` | 시험한 버전 |
| `DB_BACKEND` | `firestore` | 없으면 시작 거부 |
| `FIREBASE_CREDENTIALS_JSON` | `econova-dev` **최소 권한** 서비스 계정 JSON 전체 | 역할 `roles/datastore.user` 하나 (4장) |
| `SECRET_KEY` | 64자 무작위 | 32자 미만이면 시작 거부 |
| `ECONOVA_AI_PROVIDER` | `openai` | 운영에서 `mock` 은 시작 거부 |
| `OPENAI_API_KEY` | 학원 제공 키 | |
| `ECONOVA_AI_MODEL` | `gpt-4o-mini` | |
| `ECONOVA_AI_DAILY_REQUESTS` / `ECONOVA_AI_GLOBAL_DAILY_REQUESTS` | `20` / `300` | 잠정 |
| `ECONOVA_AI_FEEDBACK` | 넣지 않음 (기본 off) | 오답 설명은 정답·해설을 외부로 보내므로 끔 |
| `ECONOVA_TRUSTED_PROXY_HOPS` | `0` | 6장에서 측정한 뒤에만 바꾼다 |
| `ECONOVA_PRIVATE_CONTENT_DIR` | `/etc/secrets` | 승인된 평가의 `*.answers.json` 을 Secret Files 로 올린 뒤에만 |
| `OPENAI_MODEL` | **삭제** | 이전 LMS 전용 |

넣지 않는다: `ECONOVA_DEV_FIXTURES`, `ECONOVA_CONTENT_PREVIEW`, `ECONOVA_ALLOW_ADMIN_BOOTSTRAP`.
비밀 값은 채팅·문서에 붙여 넣지 않는다: `pbcopy < <파일>` → Render 값 칸에 붙여 넣기 → `pbcopy < /dev/null`.

## 3. 교체 순서 (각 단계는 사람의 승인 뒤)
1. 기능 브랜치를 `main` 으로 합치는 PR 을 만든다 (`main` ← `feature/econova-lms-renewal`).
2. Render `lms` → Settings → **Auto-Deploy 를 Off** (이 변경만으로는 배포되지 않는다).
3. PR 을 병합한다 (Auto-Deploy 가 꺼져 있어 아직 배포 안 됨).
4. Render 환경변수를 2장대로 바꾸고 **Save, rebuild, and deploy**. 이제 `main` 이 ECONOVA 라서 어떤 재시작도 ECONOVA 코드로 일어난다.
5. 배포 로그 확인. `ConfigError` 로 시작을 거부하면 그 메시지대로 값을 고친다 (실패한 배포는 기존 인스턴스를 대체하지 않는다).
6. 7장 확인 뒤 Auto-Deploy 를 다시 켠다.
- 되돌리기: Render Rollback 은 **ECONOVA 배포끼리만**. 이전 LMS 배포로 되돌리면 새 Firebase 키로 이전 코드가 돌아 `econova-dev` 가 오염된다.
- 이전 Firebase 프로젝트·데이터는 지우지 않는다 (더 쓰지 않을 뿐).

## 4. 운영용 Firebase 자격 증명 (공개 배포 전)
1. Google Cloud 콘솔에서 **`econova-dev` 프로젝트**를 선택 → IAM 및 관리자 → 서비스 계정 → 만들기 (예: `econova-web`).
2. 역할: **Cloud Datastore 사용자 (`roles/datastore.user`)** 하나만.
3. 키 → JSON 하나 → 저장소 밖 `~/econova-dev-secrets/econova-web.json` (`chmod 600`) → Render `FIREBASE_CREDENTIALS_JSON` 에 붙여 넣기.
4. 시험에 쓴 기본 관리자 키(`firebase-adminsdk-fbsvc`)는 시험이 끝나면 폐기한다.
5. Firestore: 삭제 보호 켜기, 보안 규칙 "모두 거부" 유지(서버만 접근), 백업 방법 결정(정기 내보내기는 유료 전환 필요).
6. 연동 시험 표식 문서 `econova_it/marker`: 실제 사용자가 생기면 시험 도구가 이 프로젝트를 자동으로 거부한다(의도된 동작).

## 5. 관리자 부여 (Render 무료에는 셸이 없음)
관리자 후보가 사이트에서 먼저 가입한다. 그다음 이 컴퓨터에서 **Firestore 로 직접** 부여한다 (로컬 `.env` 의 다른 값보다 환경변수가 우선):

```bash
env DB_BACKEND=firestore FIREBASE_CREDENTIALS_JSON="$(cat ~/econova-dev-secrets/econova-web.json)" .venv/bin/flask --app app admin-grant <관리자 이메일> --operator "<부여자>" --verification "<본인 확인 방법>"
```

이메일을 한 번 더 입력하라는 확인이 나온다. 취소는 `admin-revoke`. 로컬 `.env` 에 이전 LMS 의 Firebase 키가 남아 있으면 지운다.

## 6. 프록시 홉 수 (운영에서 측정)
`ECONOVA_PROXY_DIAGNOSTICS=1` → 관리자로 `/admin/diagnostics/request` → 두 네트워크에서, 위조 `X-Forwarded-For` 를 넣어도 같은
홉 수가 내 IP 를 가리키는지 확인 → `ECONOVA_TRUSTED_PROXY_HOPS` 설정 → 로그인 제한 확인 → 진단 변수 삭제.
절차: `docs/phase-8b2-integration.md` 4장. 추측한 값은 넣지 않는다.

## 7. 배포 직후 확인
- `/` 첫 화면, 회원가입·로그인, 대시보드, 강좌 카탈로그, 보안 헤더, 세션 쿠키 `Secure`.
- 없앤 주소(`/legacy`, `/curriculum`, `/course/…`)가 404.
- AI: 공개된 강좌가 없으면 튜터는 쓸 일이 없다 (승인된 학습자료가 있어야 동작).
- `ai-purge`(AI 대화 보존 기간 정리): Render Cron 은 유료 → 이 컴퓨터에서 주기적으로 실행하거나 다른 방법을 정한다.

## 8. 출시 전 콘텐츠
공개(`published`)된 실제 강좌가 없으면 카탈로그에는 '준비 중' 만 보인다. c02 부터 사람 검토·승인 → 릴리스 계획 반영 → 공개 커밋 →
정답 키 Secret Files 순서로 진행한다 (`docs/content-readiness.md`, `docs/content/c02-review.md`).
