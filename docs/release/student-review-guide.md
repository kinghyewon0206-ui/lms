# ECONOVA 코드 검토 안내 (학생용)

> 체크포인트 커밋을 승인하기 전에 읽는 문서다. 각 주제마다 **꼭 열어 볼 파일·함수**와 **답할 수 있어야 하는 질문**을 적었다.
> 줄 번호는 바뀔 수 있으니 함수 이름으로 찾는다 (편집기의 "기호로 이동" 또는 `grep -n "def 함수이름"`).
> 변경 요약: `docs/release/student-summary.md`, 커밋 계획: `docs/release/commit-plan.md`.

## 0. 누가 무엇을 만들었나 (사실 그대로)
| 범위 | 만든 사람 | 학생 검토 |
|---|---|---|
| 원래 LMS (2026-09-28 ~ 10-26 커밋 16개: 로그인, 강의 목록, AI 커리큘럼 상담, Firestore 저장, 마인드맵 UI 등) | 15개는 학생 계정, 1개(`67a6087`, 포트 설정)는 `1Kirl` 계정으로 커밋됨. 어떻게 작성했는지는 이 문서가 판단하지 않는다 | — |
| Phase 2-0 ~ 2.1 (커밋 8개, `2737f01`~`231cab5`) | **Claude Code(AI)가 작성**, 학생 계정으로 커밋. 메시지에 AI 작성과 Co-Authored-By 표기 | 커밋 당시 선생님을 통해 학생 확인을 받았다고 기록됨 |
| Phase 3 ~ 8B-2 (이번 체크포인트, 162개 파일) | **Claude Code(AI)가 작성** (코드·테스트·문서·c02 학습자료 초안 전부). 단계별 방향·요구 사항은 선생님(운영자)이 정함 | **아직 없음** |
| c02 학습자료·평가 문항·정답 | AI 초안. 사람 승인 0건 (모든 실제 강좌는 `coming_soon`) | 아직 없음 |

- 이번 체크포인트에서 학생이 직접 쓴 코드는 없다. "학생이 작성했다"고 적지 않는다.
- 커밋 메시지의 "reviewed by the student" 는 학생이 이 문서의 검토를 **실제로 마친 경우에만** 남긴다. 아니면 그 문장을 빼거나 커밋하지 않는다.
- 학생이 검토 중 고친 부분이 있으면 그 내용만 학생 기여로 따로 적는다.

## 1. Flask 앱 구조
- `app.py`: 앱을 만들고 설정(`SECRET_KEY`, 쿠키 보안, 요청 크기 1MB), 보안 헤더(`security_headers`), CSRF(`csrf_token`),
  회원가입·로그인(`signup`, `login`, `logout`), 이전 LMS 화면(`/legacy`…), 관리 CLI 명령(`admin-grant`, `check-content`,
  `content-release-apply` 등)을 둔다. ECONOVA 화면은 Blueprint `econova` 로 붙는다.
- `econova/web.py`(강좌·레슨·평가·시뮬레이션 화면), `student_web.py`(보고서·캡스톤), `ai_web.py`(AI·토론), `admin_web.py`(관리).
- 규칙은 화면 밖 모듈에: `learning.py`(수강·평가·수료), `progress.py`(진도, 순수 함수), `grading.py`(채점), `simulations.py`.
- 저장은 `storage.py` 하나로만: sqlite(개발·테스트)와 Firestore(운영)를 `config.db_backend()` 로 고른다. **`DB_BACKEND=firestore`
  라고 직접 적어야만** Firestore 를 쓴다 (`.env` 에 키만 있어도 운영 DB 를 건드리지 않게).
- 콘텐츠는 DB 가 아니라 Git 의 JSON (`content/`), 읽기는 `content.py` 의 `load_catalog`.

질문
1. 라우트 함수가 sqlite/Firestore 를 직접 부르지 않고 `storage` 를 거치는 이유는?
2. `DB_BACKEND` 를 비워 두고 로컬에서 실행하면 어느 저장소를 쓰나?

## 2. 인증과 수강 신청
- `app.py` `signup`: 비밀번호를 `generate_password_hash(…, "pbkdf2:sha256")` 로 저장 (원문 저장 안 함). `login`: `check_password_hash`,
  성공하면 `session.clear()` 후 새 세션 (세션 고정 방지). 모든 POST 는 CSRF 토큰 필요.
- `econova/login_guard.py` `blocked`·`record_failure`·`record_success`: 15분 구간으로 계정+IP 10회, 계정 50회, IP 200회.
  `client_ip` 는 `ECONOVA_TRUSTED_PROXY_HOPS` 가 0이면 `X-Forwarded-For` 를 믿지 않는다.
- `econova/roles.py` `is_admin`: `role == 'admin'` **그리고** 취소되지 않은 부여 기록이 있어야 관리자. 매 요청마다 DB 에서 다시 읽는다.
- 수강: `web.enroll` → `learning.enroll` → `storage.enroll_course` (Firestore 는 트랜잭션: 이미 있으면 그대로 두고 False).

질문
3. 다른 사람이 내 계정 비밀번호를 계속 틀려도 나는 로그인할 수 있는 이유는? (`known_device`)
4. 관리자 권한을 취소하면 왜 바로 관리 화면이 막히나?

## 3. 학습 진도와 퀴즈 채점
- `progress.py` `apply_event`·`lesson_status`: 레슨 완료 = 필수 활동(자료 확인 `material`, 퀴즈 **제출** `quiz`)을 모두 함.
  퀴즈 점수는 완료 조건이 아니고 최고 점수만 남긴다. 같은 이벤트를 여러 번 보내도 결과가 같다(멱등).
- `grading.py` `grade`·`is_correct`: 객관식은 선택지 id 가 정답과 같아야, 수치형은 `|입력 − 정답| ≤ 허용오차`. AI 는 채점하지 않는다.
- `learning.py` `submit_assessment`: 일회용 제출 토큰(같은 토큰 재전송 → 새 응시 없음), 응시 횟수(`attempts_left`), 채점, 저장
  (`storage.save_assessment_attempt` 가 횟수를 트랜잭션 안에서 다시 확인), `reconcile_attempt` 로 진도·수료 반영.
  최종 평가 합격 = `ratio ≥ passing.score_ratio` 이고 합격 기준이 사용 가능할 때만 수료 기록.
- `answers_revealable`: 최종 평가 정답·해설은 합격했거나 기회를 다 쓴 뒤에만 보인다.

질문
5. 퀴즈를 0점 맞아도 레슨이 "완료"되는 이유와, 그게 괜찮은지에 대한 내 생각은?
6. 같은 답안 화면을 두 번 제출하면 응시가 몇 개 생기나? 왜?

## 4. 평가 정답을 비공개로 두는 방법
- 공개 JSON(`content/assessments/*.json`, `content/diagnostic.json`)에는 문항만 있고 정답·해설·허용오차가 없다.
- 정답 키는 저장소 **밖** `ECONOVA_PRIVATE_CONTENT_DIR`(예: `~/econova-private/*.answers.json`)에만. 운영 기본값은 없음 → 키가 없으면
  응시를 막는다(fail closed, `learning.require_keys`).
- `private_content.py` `read_keys`·`merge`: 키의 `public_sha256`·문항 버전이 공개 파일과 맞아야 합친다 (문항이 바뀌었는데 옛 정답으로
  채점하는 일 방지). `split` 은 정답이 든 원본을 공개/비공개로 나눈다.
- `public_safety.py` + pre-commit 훅(`tools/git-hooks/pre-commit`): 정답·교사용 문서·API 키가 스테이지되면 커밋을 막는다.
  개발용 합성 키 7개(`content/dev_fixtures/private/`, `"synthetic": true`)만 예외.

질문
7. 저장소가 공개(public)인데 정답 파일을 `.gitignore` 에만 맡기면 안 되는 이유는?
8. 공개 문항을 고쳤는데 정답 키를 안 고치면 어떻게 되나?

## 5. AI 튜터와 사용 한도
- 스위치 `ECONOVA_AI_PROVIDER`: `off`(기본, 외부 요청 0) / `mock`(개발용 모의 답, 운영에서 거부) / `openai`. `ai/client.py` `settings`·`get_provider`.
- `ai/tutor.py` `ask`: 맥락은 서버가 **승인된 학습자료**로만 만든다(`ai/context.py` `lesson_context` — 출처 본문·정답·이메일 제외).
  공급자에게는 이메일 대신 가명(`ai/safety.py` `pseudonym`). 응답은 JSON 스키마로 검사(`client.validate`), 출처 id 는 서버 목록에
  있는 것만 남긴다(`safety.filter_source_ids` — 지어낸 출처 제거).
- `ai/usage.py` `run`: 학생별 동시 요청 잠금 → 하루 한도·전체 한도·같은 질문 반복 확인(`storage.reserve_ai_request`, 트랜잭션) →
  호출 → 검사 → 토큰 기록. 실패해도 학습 기록은 그대로.
- 저장 한도는 `quotas.py` `check` (예: 레슨당 튜터 메시지 200개). 한도에 닿으면 새 저장만 막고 기존 기록은 지우지 않는다.

질문
9. AI 가 지어낸 출처 id 를 답에 넣으면 화면에 어떻게 보이나?
10. AI 를 `off` 로 두면 어떤 기능이 계속 되고 어떤 기능이 멈추나?

## 6. 경제 시뮬레이션 계산
- `simulations.py` (파일 맨 위 설명에 공식): 수요 `Qd = a − bP`, 공급 `Qs = c + dP` → 균형 `P* = (a − c)/(b + d)`, `Q* = a − bP*`
  (`supply_demand`). 탄소세 t 는 생산자에게: 소비자 가격 `Pc = (a − c + d·t)/(b + d)`, 생산자 가격 `Pp = Pc − t`, 세수 `t·Qt`,
  사중손실 `½·t·(Q* − Qt)`, 외부 피해 md 를 넣으면 사회적 후생 변화 = 피한 피해 − 사중손실 (`carbon_tax`).
- 균형이 없거나 세금이 너무 크면 숫자 대신 `status` 와 이유를 돌려준다. 모든 값은 소수 6자리 반올림(`r6`).
- 화면의 `static/js/econova-sim.js` 가 같은 공식을 쓰고, 테스트가 Python 과 JS 결과가 같은지 확인한다. 저장할 때는 **입력만** 받아
  서버가 다시 계산한다(`web.lab_save`) — 화면이 보낸 결과 값은 무시.

질문
11. a=100, b=2, c=10, d=1 일 때 균형 가격과 거래량을 손으로 계산해 화면 값과 비교해 보자.
12. 세금의 부담이 소비자와 생산자에게 나뉘는 비율은 어떤 값에 따라 정해지나? (`consumer_share`)

## 7. 관리자 승인과 공개
- 관리자는 웹에서 만들 수 없다. 서버 셸 `flask admin-grant`(본인 확인 기록 필수), `admin-revoke`.
- `admin_content.py`: 검토 대상(학습자료·평가·합격 기준·진단평가·토론 주제·캡스톤)마다 내용 지문(digest). 상태 이동 `TRANSITIONS`
  (초안 → 검토 중 → 승인, 수정 요청, 다시 검토). `validate_decision` 은 지문이 지금 내용과 같고, 의견이 있고, 확인란을 체크해야 통과.
- 웹은 **콘텐츠 파일을 바꾸지 않는다**. `release_plan` 이 반영할 승인 목록을 만들고(서명 가능 `sign_plan`), 개발 환경에서
  `flask content-release-apply 계획.json` 으로 JSON 에 반영 → 테스트 → Git 커밋. 다시 검토됐거나 승인자 권한이 취소된 승인은 빠진다.
- 강좌 공개는 강좌 JSON 의 `status` 를 `published` 로 바꾸는 별도 커밋. 지금은 공개 0개.

질문
13. 관리자가 승인한 뒤 누군가 학습자료 파일을 고치면 그 승인은 어떻게 되나?
14. 왜 승인 버튼이 곧바로 강좌를 공개하지 않게 만들었을까?

## 8. 자기주도 SDG 캡스톤
- 정의: `content/capstone/c09.json`(실제, 초안), 개발용 `content/dev_fixtures/capstone/`. 읽기 `capstone.py` `parse_definition`.
- 화면 `student_web.py`: `capstone_edit`(저장할 때마다 새 버전, `storage.save_capstone_version` 트랜잭션으로 번호 증가),
  `capstone_self_assessment`(루브릭으로 스스로 평가), `capstone_submit`, `capstone_feedback`(AI 코치 — 질문·제안만, 점수 없음).
- 수료: `capstone.completion_state` — 모든 레슨 완료 + 제출 버전에 필수 칸 + 자기평가 + 성찰 글 최소 길이. AI 의견은 조건이 아니다.
  `completion_policy`: 실제 강좌는 캡스톤 정의·루브릭이 사람 승인을 받아야만 수료 기록.
- 교사 채점·감독 기능은 없다 (자기주도).

질문
15. 캡스톤 수료에 AI 피드백이 들어가지 않는 이유는?
16. 저장을 여러 번 하면 이전 내용은 어디에 남나?

## 9. 직접 해 볼 것 (승인 전)
1. 미리보기(격리 서버)에서 학생 흐름: 대시보드 → 진단평가 → 강좌 → 레슨 → 퀴즈 → 시뮬레이션 → 보고서 → 캡스톤.
2. 관리자 계정으로 콘텐츠 관리 화면에서 개발용 토론 주제를 "검토 시작 → 승인 → 다시 검토" 해 보고, 릴리스 계획에서 빠지는지 확인.
3. `.venv/bin/python -m pytest` 와 `.venv/bin/python -m pytest integration_tests` 를 직접 실행.
4. 위 질문 16개 중 답하지 못한 것을 정리해 질문한다. 이해하지 못한 채로 "검토했다"고 하지 않는다.
