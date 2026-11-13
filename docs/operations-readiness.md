# ECONOVA 운영 준비 문서 (Phase 7)

> 이 문서는 **배포 전 준비 사항**을 정리한 것이다. 이 문서를 쓰는 동안 운영 자격 증명, 예약 작업, 외부 서비스는 설정하지 않았다.
> 실제 적용은 사람이 결정하고 수행한다. 명령은 모두 저장소 루트에서 실행한다.

## 1. 비공개 평가 콘텐츠 (정답 키)

| 항목 | 내용 |
|---|---|
| 위치 | `ECONOVA_PRIVATE_CONTENT_DIR` (저장소 밖이어야 함. 저장소 안을 가리키면 앱이 시작되지 않음) |
| 개발 기본값 | `~/econova-private` |
| 운영 기본값 | 없음 → 설정하지 않으면 정답 키가 필요한 평가는 **열리지 않음** (fail closed, 503 "평가를 지금 열 수 없어요") |
| 파일 | `<평가 id>.answers.json` (평평한 폴더. 하위 폴더 없음) |

**Render Secret Files 준비 (사람이 할 일)**
1. 개발 PC 의 `~/econova-private/*.answers.json` 을 확인한다 (`review/` 폴더는 올리지 않는다 — 교사용 문서).
2. Render 대시보드 → 서비스 → Environment → Secret Files 에 파일 이름 그대로 각각 올린다 (`/etc/secrets/<이름>` 으로 보임).
3. 환경변수 `ECONOVA_PRIVATE_CONTENT_DIR=/etc/secrets` 를 추가한다.
4. 배포 뒤 `flask --app app check-content` 결과의 "정답 키 확인" 줄에서 열 수 없는 평가가 없는지 본다.

**동작 확인 포인트**
- 공개 문항이 바뀌었는데 키를 갱신하지 않으면 그 평가만 닫힌다(지문 `public_sha256` 불일치). 키를 다시 만들어 올려야 한다.
- 키가 없어도: 이미 저장된 응시 기록·결과 화면·같은 토큰 재제출 복구는 동작한다(다시 채점하지 않음).

**백업과 복구**
- 정답 키는 Git 에 없으므로 **별도 백업이 유일한 복구 수단**이다. 암호화된 저장소(예: 학교 계정의 비공개 드라이브)에 사본 2곳 이상.
- 키를 만든 원본(정답이 든 예전 평가 JSON)은 `.git/econova-snapshots/`(로컬 전용)와 `~/lms-project-backups/`(저장소 밖)에 있다.
  **이 스냅샷·백업은 절대 저장소에 복사하거나 커밋하지 않는다.**

**민감한 Git 이력 피하기**
- `.gitignore` 가 `*.answers.json`, `docs/review/`, `econova-private/` 를 막는다 (개발용 합성 키 `content/dev_fixtures/private/` 만 예외).
- 커밋 전 점검: `flask --app app check-public-files --staged` (또는 `git config core.hooksPath tools/git-hooks` 로 pre-commit 훅 사용).
- 정답이 든 예전 버전을 "중간 커밋"으로라도 넣지 않는다. 한 번 푸시하면 공개 저장소에서 지워도 사본이 남을 수 있다.

## 2. AI 공급자

| 설정 | 기본 | 설명 |
|---|---|---|
| `ECONOVA_AI_PROVIDER` | `off` | `off` / `mock`(개발 전용, 운영에서 시작 거부) / `openai` |
| `ECONOVA_AI_MODEL` | `gpt-4o-mini` | 2026-11 실제 연동 시험으로 strict 구조화 응답 호환 확인 |
| `OPENAI_API_KEY` | 없음 | 서버 환경변수로만. 화면·JS·로그에 나가지 않음 |
| 한도 | 학생 하루 20회, 전체 하루 300회, 입력 600자, 이전 메시지 6개, 출력 700토큰, 20초 | `ECONOVA_AI_*` |
| 앱 전체 스위치 (8B-1) | `ECONOVA_AI_PROVIDER` 하나로 모든 AI 기능을 제어 | `off` 면 `OPENAI_API_KEY` 가 있어도 외부 AI 요청 0 |
| `ECONOVA_AI_FEEDBACK` | `off` | AI 오답 설명. 틀린 문항의 정답·해설을 공급자에게 보내므로 정책으로 허용할 때만 `on` (2026-11 결정: 운영 off) |

### 학생 저장 한도 (8B-1, `econova/quotas.py`, `ECONOVA_QUOTA_<이름>`)
| 이름 | 기본 | 이유 |
|---|---|---|
| SIMULATION_RUNS | 200 | 실험 저장은 비교용 (레슨 27개 × 약 7회) |
| TUTOR_MESSAGES | 200 | 레슨 하나의 튜터 대화 100번 주고받기 (보존 기간 30일 뒤 정리) |
| FEEDBACK_REQUESTS | 10 | 응시 기록 하나에 대한 AI 오답 설명 |
| DEBATES_PER_TOPIC / DEBATES_TOTAL | 20 / 100 | 같은 주제를 다시 시작하는 횟수 / 전체 토론 |
| CAPSTONE_VERSIONS / CAPSTONE_FEEDBACK | 100 / 50 | 저장할 때마다 새 버전 / AI 코치 기록 |
| DIAGNOSTIC_ATTEMPTS | 50 | 진단평가 재응시 |
| QUIZ_ATTEMPTS | 100 | 재응시 무제한 형성 퀴즈 하나 (최종 평가는 원래 횟수 제한을 따름) |
한도에 닿으면 새 저장만 막고 한국어로 안내한다. 기존 기록은 지우지 않고, 학생 글은 자르지 않는다 (캡스톤은 입력 내용을 화면에 그대로 둠).

**개발용 API 검증 절차 (실제 키로 처음 확인할 때)**
1. 개발 전용 OpenAI 프로젝트·키를 만들고 **사용 한도(월 예산 알림·하드 리밋)** 를 공급자 콘솔에서 먼저 건다.
2. 로컬 격리 환경(임시 sqlite, `ECONOVA_DEV_FIXTURES=1`)에서 `ECONOVA_AI_PROVIDER=openai`, 낮은 한도(`ECONOVA_AI_DAILY_REQUESTS=5`)로 실행.
3. 개발용 강좌(dev-f1)에서 튜터 질문 2~3개, 오답 설명 1회, 토론 1회, 캡스톤 코치 1회만 시험한다.
4. 확인: 응답이 스키마를 통과하는지, 출처 id 가 서버 목록 밖이면 지워지는지, 사용량(`econ_ai_usage`)이 쌓이는지, 시간 초과 처리.
5. 실제 c02 초안 자료는 사람 승인 전이므로 AI 에 보내지 않는다 (튜터는 승인된 자료만 쓴다).

**비용 통제 (추정 방법)**
- 상한 비용 ≈ (하루 전체 요청 상한 300) × (요청당 입력 토큰 ≈ 3,000~6,000 + 출력 ≤ 700) × 모델 단가. 단가는 공급자 가격표로 확인.
- 2026-11 실제 시험: `gpt-4o-mini` 요청 5회(401 시험 제외)에 입력 4,395·출력 776 토큰 → 요청당 입력 약 900토큰.
- 운영 중 `econ_ai_usage_global` 의 날짜별 요청·토큰을 확인한다 (관리 화면에는 오늘 요청 수가 보임).

**실패 처리**: 공급자 오류·시간 초과·형식 오류 → 한국어 안내, 점수·진도·수료 변화 없음, 학생 글 보존, 비AI 학습 계속 가능.

## 3. 데이터베이스

- **마이그레이션**: sqlite `SQLITE_MIGRATIONS` 1~7, 모두 새 테이블 추가 방식(기존 테이블 DROP·변경 없음). `flask --app app init-db`.
  Firestore 는 스키마가 없어 마이그레이션이 없다 (문서 경로는 `econova/storage.py` 머리말 참고).
- **Firestore 색인**: 현재 쿼리는 하위 컬렉션 전체 읽기와 단일 필드 `==` 조건뿐이라 **복합 색인이 필요 없다**.
  (참고: `ai-purge` 와 관리 화면 집계는 사용자 컬렉션을 훑는다. 사용자가 많아지면 비용이 늘어나므로 그때 집계용 문서를 따로 두는 것을 검토.)
- **개발용 Firebase 검증**: 운영과 다른 Firebase 프로젝트를 만들고 그 서비스 계정 키로만 `DB_BACKEND=firestore` 를 시험한다.
  가입 → 수강 → 퀴즈 → 최종 평가 → 시뮬레이션 저장 → AI(mock) → 캡스톤 저장·제출 → 관리자 검토 기록 순서로 확인.
- **백업·롤백**: 배포 전 Firestore 내보내기(gcloud firestore export, 개발 프로젝트에서 먼저 연습). 롤백은 이전 Git 커밋 재배포 +
  필요 시 내보낸 데이터 가져오기. 새 코드가 만든 컬렉션은 이전 코드가 읽지 않으므로 롤백해도 기존 기능이 깨지지 않는다.

## 4. 인증과 보안

- `SECRET_KEY`: 운영에서 32자 이상 필수 (없거나 기본값이면 앱이 시작되지 않음). render.yaml 의 `generateValue: true` 사용.
- 세션 쿠키: HttpOnly, SameSite=Lax, 운영에서 Secure.
- 로그인 시도 제한 (Phase 8B-1, `econova/login_guard.py`): 15분 구간 카운터(지금+직전 구간), 실패만 센다.
  | 설정 | 기본 | 의미 |
  |---|---|---|
  | `ECONOVA_LOGIN_MAX_PER_ACCOUNT_IP` | 10 | 같은 곳에서 한 계정을 계속 틀림 |
  | `ECONOVA_LOGIN_MAX_PER_ACCOUNT` | 50 | 여러 곳에서 한 계정을 노림 — 이 브라우저로 로그인에 성공한 적이 있으면(서명 쿠키, 30일) 건너뜀 |
  | `ECONOVA_LOGIN_MAX_PER_IP` | 200 | 한 곳에서 여러 계정을 노림 — 학교·공공 네트워크 공유를 고려해 넉넉하게 |
  | `ECONOVA_TRUSTED_PROXY_HOPS` | 0 | 앞단 프록시 수. 0 이면 `X-Forwarded-For` 를 **무시**하고 직접 연결 주소를 쓴다 |
  **Render 주의**: Render 는 앞단 프록시를 거치므로 0 으로 두면 모든 사용자가 같은 IP 로 보여 IP 제한이 사이트 전체에 공유된다.
  홉 수는 **추측하지 않는다**. 운영과 분리된 Render 서비스에서 관리자 진단 화면(`/admin/diagnostics/request`,
  `ECONOVA_PROXY_DIAGNOSTICS=1` 일 때만)으로 실제 `X-Forwarded-For` 모양을 재고(절차: `docs/phase-8b2-integration.md` 4장), 그
  측정값만 설정한다. 확인 전에는 IP 제한 값을 더 크게 두는 것이 안전하다. 키는 해시라 이메일·IP 원문을 저장하지 않고, 만료 기록은 `ai-purge` 가 함께 지운다.
- 보안 헤더: X-Frame-Options SAMEORIGIN, X-Content-Type-Options nosniff, Referrer-Policy same-origin. 요청 본문 1MB 상한.
- 운영에서 진단평가는 사람 승인(approved) 전에는 열리지 않는다 (개발에서는 초안도 열림).
- CSRF: 모든 POST 에 세션 토큰(폼 `csrf_token` 또는 `X-CSRF-Token` 헤더) 필요.
- **관리자 부여**: 웹에서는 불가. 서버 셸에서
  `ECONOVA_ALLOW_ADMIN_BOOTSTRAP=1 flask --app app admin-grant <email> --operator "<운영자>" --verification "<본인 확인 방법>"`
  (이메일을 한 번 더 입력해 확인). 가입 이메일은 소유 확인을 하지 않으므로, 계정 주인을 다른 방법으로 확인한 뒤에만 부여한다.
  부여 뒤 `ECONOVA_ALLOW_ADMIN_BOOTSTRAP` 은 지운다. 취소: `flask --app app admin-revoke <email>`. 목록: `admin-list`.
- 예전 `teacher` 역할 값은 보존되며 특별한 권한이 없다 (자동으로 관리자가 되지 않음).
- **콘텐츠 공개 제한**: 관리 화면의 승인은 DB 감사 기록일 뿐 정본 JSON 을 바꾸지 않는다. 릴리스 계획을 내려받아 개발 환경에서
  `flask --app app content-release-apply plan.json --dry-run` → 반영 → `check-content`·테스트 → diff 검토 → 커밋 → 배포.
  관리자 승인(`role=admin`)은 내용 지문(`content_digest`)에 묶여, 승인 뒤 내용을 고치면 검사기가 거부한다.
  반영할 때 검토자·날짜·번호는 계획 파일이 아니라 DB 기록을 따르고, 승인 뒤 '다시 검토'·'수정 요청'이 기록됐으면 반영하지 않는다.
  운영 DB 의 기록이 없는 개발 환경에서는 `--trust-plan` 과 **유효한 서명**이 둘 다 있어야 한다: 운영 서버에
  `ECONOVA_RELEASE_SIGNING_KEY`(32자 이상)를 두면 내려받는 계획에 HMAC 서명이 붙고, 같은 키를 가진 릴리스 담당자만 반영할 수 있다.
  배포 직후 운영에서 `flask --app app content-verify-approvals` 로 정본 승인이 모두 운영 DB 기록과 맞는지 확인한다
  (기록 없음·지문 불일치·이후 다시 검토·예전 teacher 형식이면 실패).

## 5. AI 데이터 보존

- 기본 보존 기간: `ECONOVA_AI_RETENTION_DAYS=30`. 정리 명령: `flask --app app ai-purge` (메시지·빈 대화·90일 지난 사용량 기록 삭제,
  점수·진도·수강·캡스톤은 건드리지 않음).
- 제안: Render Cron Job 으로 매일 1회 실행 (예: `0 18 * * *` = 한국 시간 03:00). **아직 설정하지 않았다.**
- 모니터링: Render 로그에서 `econova.ai` 로거의 `ai fail task=... code=...` 비율, 전역 사용량, 503(평가 닫힘) 응답을 확인.
  로그에는 프롬프트·학생 글·답변·키가 남지 않는다.

## 6. 배포 직전 점검표

- [ ] `pytest` 전체 통과, `check-content` 통과, `check-public-files` 통과
- [ ] `SECRET_KEY`, `DB_BACKEND=firestore`, `FIREBASE_CREDENTIALS_JSON`(운영), `ECONOVA_PRIVATE_CONTENT_DIR=/etc/secrets` 설정
- [ ] `ECONOVA_DEV_FIXTURES`, `ECONOVA_CONTENT_PREVIEW` 가 비어 있음 (켜면 시작 거부)
- [ ] `ECONOVA_AI_PROVIDER` 결정 (`off` 로 시작 권장), 공급자 콘솔 예산 한도
- [ ] 관리자 계정 부여 절차 기록, Cron(ai-purge) 결정
- [ ] 공개할 강좌의 자료·평가·합격 기준·캡스톤이 사람 승인을 받았고 정본 JSON 에 반영됨
