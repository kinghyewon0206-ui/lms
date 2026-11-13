# ECONOVA

UN 지속가능발전목표(SDG)와 연결해 경제를 배우는 고등학생 **자기주도 학습 플랫폼**.
강좌 9개(각 레슨 3개, 난이도 하·중·상), 진단평가, 형성 퀴즈·최종 평가, 경제 시뮬레이션, AI 튜터·토론, 학습 보고서, SDG 캡스톤.
Flask + (로컬: sqlite3 / 배포: Firebase Firestore). 이전 LMS(대학 공개 강의·AI 커리큘럼)는 2026-11 에 없앴다
(그 시절 코드는 Git 기록과 `legacy-lms-v1` 태그에만 남아 있다).

## 로컬에서 실행

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # 처음 한 번. 필요한 값만 채운다
.venv/bin/python app.py       # http://localhost:5000 (PORT 로 바꿀 수 있다). 실행할 때 로컬 sqlite 를 준비한다
```

`flask` 명령으로 실행할 때는 DB 를 먼저 준비한다. 앱을 import 하기만 해서는 DB 를 만들거나 바꾸지 않는다.

```bash
.venv/bin/flask --app app init-db   # sqlite 테이블 생성·마이그레이션 (여러 번 실행해도 같다)
.venv/bin/flask --app app run
```

AI 기능은 기본으로 꺼져 있다 (`ECONOVA_AI_PROVIDER=off`). 로컬에서 키 없이 보려면 `ECONOVA_AI_PROVIDER=mock`.
공개된 실제 강좌가 아직 없으므로 수강 화면을 보려면 `ECONOVA_DEV_FIXTURES=1` (개발용 가짜 강좌, 운영에서는 켤 수 없음).

## 개발 환경과 운영 환경

어느 저장소를 쓸지는 **`DB_BACKEND`** 로만 정한다. Firebase 키가 있다는 이유만으로 Firestore 를 쓰지 않는다.

| | 로컬 개발·테스트 | 운영 (Render) |
|---|---|---|
| `DB_BACKEND` | `sqlite` (안 적으면 sqlite) | `firestore` (안 적으면 **기동 거부**) |
| 데이터 | `lms.db` 또는 `SQLITE_PATH` | Firebase Firestore |
| `FIREBASE_CREDENTIALS_JSON` | 넣지 않는다 (넣어도 sqlite 모드면 접속 안 함) | 운영 서비스 계정 키 |

- 운영 환경 판단: Render 가 넣어 주는 `RENDER` 환경변수, 또는 `APP_ENV=production`.
- Firebase 프로젝트는 `econova-dev` 하나를 쓴다 (2026-11 결정, 나중에 운영으로 쓸 수 있음). Firestore 는 스키마가 없어
  `init-db` 가 할 일이 없다. 실제 연동 시험은 `integration_tests/` (아래 Phase 8B-2).

## 테스트

```bash
.venv/bin/python -m pytest
```

- 실제 `.env` 를 읽지 않고, Firebase 와 외부 네트워크(OpenAI 등)를 부르면 실패하도록 막아 둔 상태로 실행된다.
- 대부분의 화면·저장 테스트는 sqlite 와 **가짜 Firestore**(`tests/fake_firestore.py`, 시각은 실제처럼 `DatetimeWithNanoseconds`)
  양쪽에서 돈다. 실제 Firestore 확인은 `integration_tests/` 로 `econova-dev` 에서 한다.

## ECONOVA 강좌 콘텐츠

> **English-only:** ECONOVA's user-facing text (UI, admin screens, course content, assessments, simulations, AI prompts and output)
> must be English. New courses (c04–c09) and features are written in English from the start. Rules:
> `docs/content/english-only-guidelines.md`; enforced by `tests/test_english_only.py`.

강좌·레슨의 정본은 Git 으로 관리하는 JSON 이다. 앱은 시작할 때 한 번 읽고 형식을 검사한다
(잘못되면 파일 이름과 이유가 담긴 `ContentError`). JSON 을 고친 뒤에는 서버를 다시 시작한다.

| 위치 | 내용 |
|---|---|
| `content/catalog.json` | 실제 강좌 순서 (c01~c09) |
| `content/courses/cNN.json` | 강좌 1개 + 레슨 3개. `status`, 레슨별 `requirements`, 자료·퀴즈 승인 상태 |
| `content/dev_fixtures/` | 개발·자동 테스트 전용 가짜 강좌. `ECONOVA_DEV_FIXTURES=1` 일 때만 보인다 (운영에서는 켤 수 없음) |
| `content/sdgs.json` | SDG 번호·이름·색 |

- 공개(`published`)는 강좌 정보가 있는지와 별개다. 모든 레슨의 필수 자료와 퀴즈가 `approved` 여야만 `published` 로 둘 수 있고,
  그렇지 않으면 로더가 거절한다. 지금 실제 강좌 9개는 모두 `coming_soon` 이다.
- 레슨 완료 = 레슨의 `requirements` 를 모두 마침 (기본: 필수 자료 확인 + 필수 퀴즈 제출). 퀴즈가 없으면 통과로 치지 않는다.
- 공개된 실제 강좌가 아직 없으므로, 로컬에서 수강·진도 화면을 보려면 `.env` 에 `ECONOVA_DEV_FIXTURES=1` 을 넣는다.

### 학습자료와 검토 절차 (Phase 3)

| 위치 | 내용 |
|---|---|
| `content/lessons/<lesson>.json` | 레슨 학습자료: 핵심 개념, 하·중·상 설명, 풀이 예제, 그래프 명세, 실제 사례, SDG 사례와 정책 상충관계, 핵심 정리, 출처 |
| `content/sources.json` | 출처 레지스트리: 제목·저자·날짜·URL·관련 개념·레슨·이용 조건·확인 상태(verified / unverified) |
| `content/diagnostic.json` | 경제 기초 진단평가 12문항과 임시 추천 기준 |

- 검토 상태: `draft → in_review → approved → published`. 강좌 JSON 의 `material.status` 는 자료 파일의 `review.status` 와 같아야 한다.
- `approved`·`published` 에는 교사 검토자(`reviewer.role = "teacher"`)와 승인 시각, 그 상태로 바뀐 기록이 있어야 하고,
  AI 가 승인한 기록은 로더가 거절한다. AI 가 쓴 자료는 항상 `draft` 로 시작한다.
- 승인된 자료는 `verified` 출처만 인용할 수 있다. 예제의 계산과 그래프 균형점은 로더가 다시 계산해 확인한다.
- 학생 화면에는 `approved`·`published` 자료만 나온다. 초안은 개발 환경에서 `ECONOVA_CONTENT_PREVIEW=1` 일 때
  `/preview/<course>/<lesson>` 로만 볼 수 있다 (운영에서 켜면 앱이 시작되지 않음).
- 진단평가(`/diagnostic`)는 정해진 규칙으로만 채점하고, 추천 난이도는 참고용이다. 응시 기록은 추가만 하고 다시 계산하지 않는다.

### 형성 퀴즈·최종 평가 (Phase 4)

- 평가 JSON: `content/assessments/<id>.json` (개발용은 `content/dev_fixtures/assessments/`). 강좌 JSON 의
  `lessons[].quiz` 와 `final_assessment` 가 `assessment_id` 로 가리키고, 상태는 파일의 검토 상태와 같아야 한다.
- 문항은 레슨·학습목표 번호·핵심 개념·난이도·버전·문항 검토 상태를 갖는다. 승인된 평가에는 승인된 문항만 들어갈 수 있다.
- 채점은 `econova/grading.py` 의 규칙으로만 한다 (AI 채점 없음). 정답은 서버에만 있고 화면에는 보내지 않는다.
- 레슨 완료 = 자료 확인 + 형성 퀴즈 **제출** (점수 무관). 퀴즈 점수는 최고 점수만 따로 기록한다.
- 최종 평가는 레슨을 모두 끝내야 열린다. 합격 기준(`passing.status`)이 `approved` 일 때만 수료를 인정한다.
  `proposed` 는 미승인 제안값, `dev_provisional` 은 개발용 fixture 전용(테스트 수료로 표시).
- 제출 화면을 열 때 일회용 토큰을 발급해 같은 제출이 두 번 저장되지 않게 한다. 응시 기록은 고칠 수 없다.
- 교사용 검토 문서(정답 포함, 학생 화면으로 제공하지 않음):
  `.venv/bin/flask --app app review-package c02` (기본 위치는 저장소 밖 비공개 폴더 — 아래 "평가 정답 키" 참고)

### 경제 시뮬레이션 (Phase 5)

- `/lab` 경제 실험실: 수요·공급(`/lab/supply-demand`), 탄소세(`/lab/carbon-tax`). 로그인한 학생이면 누구나 쓸 수 있고,
  레슨 JSON 의 `simulations: ["supply-demand"]` 로 레슨 안에도 넣는다 (레슨에 들어갈 수 있는 학생에게만 보인다).
- 모형: 선형 수요 Qd = a − bP, 공급 Qs = c + dP. 탄소세는 공급자에게 단위당 t 를 매기는 모형으로, 세금 부담 귀착·세수·
  사적 시장의 사중손실 ½·t·(Q0 − Qt) 를 계산한다. 단위당 외부 피해 md 를 가정값으로 넣었을 때만 사회적 후생 변화
  (회피한 피해 − 사중손실)를 보여준다. 탄소세가 항상 후생을 줄인다고 표시하지 않는다.
- 모든 값은 가상의 모형 계산이며 실제 통계가 아니다. 화면에도 그렇게 적혀 있다.
- 계산은 `econova/simulations.py`(서버, 기준)와 `static/js/econova-sim.js`(화면 즉시 반응)가 같은 공식·같은 반올림
  (소수 6자리)·같은 입력 검사로 한다. `tests/test_simulations.py` 가 Node 로 JS 를 돌려 두 결과를 비교한다
  (`node` 가 없으면 이 비교만 건너뛴다).
- 저장할 때 서버는 **입력값만** 받아 다시 계산한다. 브라우저가 보낸 결과 값은 쓰지 않는다. 저장 기록(`/lab/saved`)은
  본인만 볼 수 있고, 계산 버전(`calc_version`)을 함께 남긴다. sqlite 마이그레이션 5 가 `econ_simulation_runs` 를 추가한다.

### 평가 정답 키 (Phase 6)

저장소가 **공개(public)** 이므로 정답은 저장소에 두지 않는다. Flask 가 파일을 내려주지 않아도, 커밋하면 누구나 볼 수 있다.

- 공개 파일(`content/assessments/*.json`, `content/diagnostic.json`): 문항·선택지(정답 표시 없음)·학습목표·난이도·배점만.
- 비공개 정답 키(`<ECONOVA_PRIVATE_CONTENT_DIR>/<평가 id>.answers.json`): 정답·허용오차·해설·검증식. 서버에서만 합친다.
  키에는 공개 문항의 지문(`public_sha256`)과 버전이 있어, 문항이 바뀌었는데 키가 그대로면 그 평가는 **열리지 않는다**.
  키가 없을 때도 마찬가지로 닫히고(`평가를 지금 열 수 없어요`, 503), 다른 값으로 대신 채점하지 않는다.
  이미 저장된 응시 기록·결과 화면·같은 토큰 재제출 복구는 키 없이도 동작한다 (다시 채점하지 않으므로).
- 폴더 설정
  - 개발: 비워 두면 `~/econova-private` (저장소 밖). 저장소 안을 가리키면 앱이 시작되지 않는다.
  - 운영(Render): Render **Secret Files** 에 `*.answers.json` 을 올리고 `ECONOVA_PRIVATE_CONTENT_DIR=/etc/secrets`.
    (Secret Files 는 하위 폴더가 없어서 키 파일을 평평하게 둔다.) 아직 설정하지 않았다 — 사람이 결정·설정해야 한다.
- 개발용 fixture 의 키는 가짜(합성) 값이라 `content/dev_fixtures/private/` 에 두고 `"synthetic": true` 로 표시한다.
  자동 테스트는 실제 키를 읽지 않는다 (빈 임시 폴더 + 합성 데이터). 실제 키 정합성 확인:
  `ECONOVA_REAL_PRIVATE_CONTENT_DIR=~/econova-private .venv/bin/python -m pytest tests/test_private_content.py`
- 교사용 검토 문서: `.venv/bin/flask --app app review-package c02` → 기본 위치 `<비공개 폴더>/review/c02-review-package.md`.
  저장소 안의 커밋될 수 있는 위치에는 쓰지 않는다. 정답 키가 없으면 만들지 않는다.
- 커밋 전 점검: `.venv/bin/flask --app app check-public-files` (또는 `python -m econova.public_safety --staged`).
  정답 키 파일, 정답이 든 평가 JSON, 교사용 검토 문서, API 키처럼 보이는 문자열을 찾으면 실패한다.
  pre-commit 훅으로 켜기(각자 컴퓨터에서 한 번): `git config core.hooksPath tools/git-hooks`.
  `.gitignore` 가 `*.answers.json`, `docs/review/` 를 막는다.

### AI 튜터·오답 설명·토론·추천 (Phase 6)

- 공급자: `ECONOVA_AI_PROVIDER=off`(기본) | `mock`(네트워크 없는 모의 응답, 개발·테스트 전용, 운영에서는 시작 거부) |
  `openai`(서버의 `OPENAI_API_KEY`, Chat Completions + strict JSON 스키마 응답, `gpt-4o-mini` 로 실제 확인). 키는 화면·JS 로 가지 않는다.
- AI 튜터(`POST /api/tutor`, 레슨 화면): 서버가 **승인된 학습자료**와 **확인된 출처의 목록 정보**(제목·저자·발행처)로 맥락을 만든다.
  초안·미확인 출처·출처 본문(제3자 저작물)·평가 정답은 보내지 않는다. 답의 출처 id 는 서버 목록과 대조해 없는 것은 지우고 알린다.
  답은 `AI 생성` 표시, 근거 수준(자료 근거/일부/부족), 자료 밖 추가 설명, 한계를 나눠 보여준다. 대화는 서버에 저장(본인만).
- 오답 설명(결과 화면): 틀린 문항의 정답·승인된 해설을 공급자에게 보내야 하므로 **기본 꺼짐** (`ECONOVA_AI_FEEDBACK=off`,
  2026-11 결정). 켜면 본인 응시 기록 + 같은 평가·같은 버전·승인됨·정답 키 있음일 때만 쓰고, AI 는 점수·진도·수료를 바꾸지 않는다.
  꺼져 있으면 규칙으로 정리한 '다시 볼 내용'과 승인된 해설만 보여준다.
- 경제 토론(`/discuss/<강좌>`): 공개·수강 중 강좌의 **승인된 주제**만. 관점 여러 개, 모형·근거·가정·가치 판단·상충관계 구분.
  학생 의견은 항상 저장되고, AI 를 못 쓰면 주제에 적힌 안내 질문·자동 정리로 이어 간다. 실제 강좌 주제는 아직 없다(개발용만).
- 학습 추천(대시보드): `econova/recommendations.py` 가 퀴즈·평가의 개념별 정오로 **결정적으로** 계산한다 (문항 3개 미만 → 잠정).
  AI 는 그 결과를 쉬운 말로 풀어 쓰기만 하고, 분석에 없는 백분율을 쓰면 표시하지 않는다. 수강·난이도는 자동으로 바뀌지 않는다.
- 한도(`ECONOVA_AI_*`, 기본: 학생 하루 20회, 전체 하루 300회, 입력 600자, 이전 메시지 6개, 출력 700토큰, 20초): 저장소(sqlite·Firestore)에
  기록하므로 여러 gunicorn 워커·인스턴스가 같은 한도를 공유한다. 학생별 동시 요청 1개, 방금 성공한 같은 요청은 다시 받지 않는다.
  실패한 요청도 횟수에 들어간다(남용 방지). 메모리 한도는 쓰지 않는다.
- 개인정보: 프롬프트에 이메일·이름을 넣지 않고, 공급자 사용자 식별값은 `SECRET_KEY` 로 만든 가명이다. 로그에는 기능·결과 코드·토큰 수만.
  AI 대화는 `ECONOVA_AI_RETENTION_DAYS`(기본 30일) 뒤 `flask --app app ai-purge` 로 지운다 (운영에서는 매일 실행하도록 설정 필요).
- sqlite 마이그레이션 6 이 `econ_ai_conversations`, `econ_ai_messages`, `econ_ai_usage`, `econ_ai_usage_global`, `econ_ai_locks` 를 추가한다.

### 자기주도 학습 플랫폼: 역할·콘텐츠 관리·보고서·캡스톤 (Phase 7)

ECONOVA 는 학교·교사가 학생을 관리하는 LMS 가 아니라 **자기주도 학습 플랫폼**이다. 교사 대시보드·학급·출석·학생 감독 기능은 없다.

- **역할**: `student`(기본, 회원가입) / `admin`(플랫폼 관리자). 관리자는 `users.role='admin'` 이면서 취소되지 않은 부여 기록
  (`econ_admin_grants`)이 있어야 한다. 부여는 서버 셸에서만: `flask --app app admin-grant <email> --operator ... --verification ...`
  (이메일 재입력 확인, 운영에서는 `ECONOVA_ALLOW_ADMIN_BOOTSTRAP=1` 필요). 예전 `teacher` 값은 보존되며 특별한 권한이 없다.
- **콘텐츠 관리**(`/admin/content`, 관리자 전용): 강좌별 공개 준비 상태와 막힌 이유, 검사 오류, 검토 대기, 운영 집계(숫자만).
  검토 결정(검토 시작·승인·수정 요청·다시 검토)은 DB 감사 기록(`econ_content_reviews`)으로 남고 내용 지문에 묶인다.
  **웹은 정본 JSON 을 바꾸지 않는다.** 릴리스 준비에서 계획 JSON 을 내려받아 개발 환경에서
  `flask --app app content-release-apply plan.json [--dry-run]` 으로 반영한다. 반영된 승인(`reviewer.role=admin`)은
  `review_id`·`content_digest` 를 가지며, 승인 뒤 내용을 고치면 검사기가 거부한다. 예전 `role=teacher` 승인 기록은 그대로 인정한다.
- **내 학습 보고서**(`/report`): 진도, 평가 점수 추세(SVG + 표), 재응시 변화, 개념별 결과(잠정·강점·복습), 추천, 활동 기록.
  모두 저장된 기록에서 결정적으로 계산하며 '숙달도' 같은 추정 퍼센트는 만들지 않는다. 본인만 볼 수 있다.
- **SDG 캡스톤**(`/capstone/<강좌>`): `content/capstone/c09.json` (초안, 루브릭 임시). 9단계 작성 → 버전 저장 → 자기평가 → 제출.
  완료 = 레슨 모두 완료 + 필수 칸을 채운 제출 버전 + 그 버전의 자기평가 + 되돌아보기 (AI 의견과 무관). 실제 강좌는 캡스톤 정의와
  루브릭이 사람 승인을 받아야 수료로 기록한다. 수료는 자기주도 제출 기록이며 공식 학업 성취·자격 인증이 아니다.
  최종 평가 대신 캡스톤으로 마치는 강좌는 강좌 JSON 의 `"capstone": {"status", "file"}` 로 지정한다 (c09).
  개발용 강좌 `dev-f3` 로 시험한다. AI 코치(선택)는 질문·빠진 관점·가정·구성 제안만 하고 점수·출처를 만들지 않는다.
- **보안**: 운영 `SECRET_KEY` 32자 이상 필수, 세션 쿠키 HttpOnly·SameSite=Lax·(운영) Secure, 로그인 실패 15분 10회 제한.
- sqlite 마이그레이션 7. 운영 준비 절차는 `docs/operations-readiness.md`.
- Phase 8A: 보안 점검 수정(응시 횟수 동시 제출, 재응시가 남은 최종 평가의 정답 비공개, 다시 검토된 승인의 반영 차단, 서명된 릴리스 계획,
  `content-verify-approvals`, 스테이지 내용 검사, 보안 헤더). 준비 문서: `docs/content-readiness.md`, `docs/integration-test-plans.md`,
  `docs/release-checklist-8b.md`, `docs/release/commit-plan.md`.
- Phase 8B-1: `ECONOVA_AI_PROVIDER` 하나로 모든 AI 제어(off 면 외부 AI 요청 0), 로그인 제한(계정+IP·계정·IP, 신뢰 프록시만
  `X-Forwarded-For` 사용, 성공한 기기 쿠키), 학생 저장 한도(`econova/quotas.py`), 권한 취소된 관리자의 승인 반영 차단, 마이그레이션 8.
  8B-2 준비: `docs/phase-8b2-prerequisites.md`, 학생용 변경 요약: `docs/release/student-summary.md`.
- Phase 8B-2: 실제 Firestore·OpenAI 연동 시험 도구 `integration_tests/` (기본은 가짜 백엔드로 외부 접속 없음,
  `.venv/bin/python -m pytest integration_tests`). 실제 연동은 개발 전용 자원·승인 확인값이 모두 있어야만 시작하고, 아니면 접속 전에
  멈춘다. 프록시 홉 수 측정용 관리자 진단 화면(`ECONOVA_PROXY_DIAGNOSTICS=1` 일 때만). 절차: `docs/phase-8b2-integration.md`,
  다음 승인 점검표: `docs/release/readiness-8b2.md`. 이 저장소는 pre-commit 훅(`core.hooksPath=tools/git-hooks`)을 켜 두었다.
  실제 연동 결과: `econova-dev` Firestore 15 통과(시각 처리 결함 1건 수정), OpenAI `gpt-4o-mini` 요청 6회 통과.
- 이전 LMS 제거 (2026-11): 대학 공개 강의·영상·AI 커리큘럼 화면과 코드, 강의 목록 시드를 없앴다. sqlite 마이그레이션 9 가
  그 테이블을 지운다 (`users` 는 그대로). 배포 계획: `docs/deployment-econova.md`.

### 콘텐츠 검사와 오류 처리

```bash
.venv/bin/flask --app app check-content   # 실제 강좌 + 개발용 테스트 강좌 JSON 전체 검사. 문제가 있으면 종료 코드 1
```

- 강좌 JSON 을 고쳤으면 커밋·배포 전에 위 명령을 실행한다 (배포 파이프라인에 넣는 것을 권장).
- 강좌 JSON 이 깨져 있어도 앱은 시작되고, 로그인·회원가입은 정상 동작한다.
  ECONOVA 화면(대시보드·강좌·레슨)만 "강좌 정보를 불러올 수 없어요"(503) 안내를 보여주고, 원인은 서버 로그에만 남긴다.
  파일을 고치면 서버를 다시 시작하지 않아도 다음 요청부터 정상으로 돌아온다 (실패한 읽기는 캐시하지 않음).
- 반대로 보안과 관련된 설정 오류(운영 환경인데 `DB_BACKEND` 가 없거나, 운영에서 `ECONOVA_DEV_FIXTURES=1`)는
  앱 시작 단계에서 멈춘다.

### 알려진 제약

- sqlite 의 레슨 진도 저장(`update_lesson_progress`)은 자체 트랜잭션(`BEGIN IMMEDIATE`)으로 실행된다.
  같은 DB 연결에 커밋하지 않은 다른 쓰기가 남아 있으면, 그 쓰기를 지우지 않고 `RuntimeError` 로 멈춘다.
  지금 있는 화면 흐름에서는 생기지 않는다. 새 코드에서 진도를 저장하기 전에는 앞선 쓰기를 커밋해야 한다.
- `econ_lesson_progress.course_id` 는 수강 정보의 강좌를 복사해 둔 값이다. 읽을 때는 항상 `econ_enrollments.course_id` 를 쓴다.

## 코드 구조

| 위치 | 역할 |
|---|---|
| `app.py` | Flask 앱 설정·시작 전 안전 검사, 첫 화면·회원가입·로그인·대시보드, 오류 화면, 관리 CLI (`gunicorn app:app`) |
| `econova/web.py` | ECONOVA 화면: `/courses`, `/courses/<id>`, 수강 신청, 난이도, `/learn/<course>/<lesson>` |
| `econova/learning.py` | 학습 규칙: 공개 강좌만 수강, 레슨 접근 권한, 진도 이벤트, 대시보드 요약 |
| `econova/simulations.py`, `static/js/econova-sim*.js` | 경제 시뮬레이션 계산(서버·브라우저 동일 공식)과 화면 |
| `econova/private_content.py`, `econova/public_safety.py` | 정답 키 분리·합치기, 커밋 전 공개 자료 점검 |
| `econova/ai/`, `econova/ai_web.py`, `econova/recommendations.py`, `econova/debates.py` | AI 튜터·오답 설명·토론·추천 설명, 결정적 학습 추천, 토론 주제 |
| `econova/content.py` | 강좌 JSON 로더와 형식 검사 |
| `econova/progress.py` | 진도 계산 (저장소와 무관한 순수 함수) |
| `econova/config.py` | 환경 설정, `DB_BACKEND` 선택 규칙, 개발용 테스트 강좌 스위치 |
| `econova/storage.py` | 저장소 계층 (sqlite / Firestore), sqlite 마이그레이션, 수강·진도 저장 |
| `tests/` | pytest 테스트 |
| `integration_tests/` | 실제 연동 시험 (기본 fake, live 는 승인 뒤) |

sqlite 스키마를 바꿀 때는 `econova/storage.py` 의 `SQLITE_MIGRATIONS` 에 새 번호를 추가한다.
이미 있는 번호는 고치지 않고, ECONOVA 사용자 데이터가 있는 테이블은 DROP 하지 않는다 (9번은 없앤 이전 LMS 테이블만 지움).

## 배포 (Render)

기존 Render 웹 서비스 `lms` 를 그대로 써서 ECONOVA 로 교체한다 (`render.yaml`). 교체 순서·환경변수·주의 사항은
`docs/deployment-econova.md`. 요약:

| 이름 | 값 |
|---|---|
| `DB_BACKEND` | `firestore` (필수. 없으면 앱이 시작되지 않는다) |
| `FIREBASE_CREDENTIALS_JSON` | `econova-dev` 의 최소 권한 서비스 계정 키(JSON 전체) |
| `SECRET_KEY` | 32자 이상 (짧으면 시작 거부) |
| `ECONOVA_AI_PROVIDER`, `OPENAI_API_KEY`, `ECONOVA_AI_MODEL` | `openai`, 학원 제공 키, `gpt-4o-mini` |
| `ECONOVA_AI_DAILY_REQUESTS` / `ECONOVA_AI_GLOBAL_DAILY_REQUESTS` | `20` / `300` (잠정) |
| `ECONOVA_AI_FEEDBACK` | 넣지 않음 (기본 off: 정답·해설을 외부로 보내지 않음) |
| `ECONOVA_TRUSTED_PROXY_HOPS` | 운영에서 측정하기 전에는 `0` |
| `ECONOVA_PRIVATE_CONTENT_DIR` | 승인된 평가의 정답 키를 Secret Files 로 올린 뒤 `/etc/secrets` |

Render 무료 플랜은 재배포할 때마다 디스크가 초기화되므로, 회원 데이터는 Firestore 에 저장한다.
