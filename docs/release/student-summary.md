# 변경 요약 (학생 검토용)

이 문서는 커밋하기 전에 학생이 무엇이 바뀌었는지 이해하고 검토할 수 있도록 정리한 것이다.
**코드는 Claude Code(AI)가 작성했다.** 학생이 직접 읽고 확인한 뒤에만 커밋한다 (아직 검토·커밋 전).

## 한눈에 보기
- 원래 프로젝트: 대학 무료 강의로 커리큘럼을 만들어 주는 LMS (지금은 '이전 LMS 보관함'으로 그대로 남아 있다)
- 바뀐 방향: **ECONOVA** — 고등학생이 스스로 공부하는 경제 학습 플랫폼 (UN SDG 연계, 교사 관리 기능 없음)
- 실제 강좌 9개는 모두 '준비 중'이다. 학생에게 공개된 실제 강좌는 아직 없다. 시험은 '개발용 테스트 강좌'로 한다.

## 단계별로 무엇이 생겼나
| 단계 | 생긴 것 | 볼 곳 |
|---|---|---|
| Phase 3 | c02(시장과 가격) 레슨 3개 학습자료 초안, 출처 목록, 경제 기초 진단평가(12문항) | `content/lessons/`, `content/sources.json`, `econova/lesson_content.py`, `econova/diagnostic.py` |
| Phase 4 | 형성 퀴즈·최종 평가, 정해진 규칙으로 채점(AI 아님), 수료 규칙 | `econova/assessments.py`, `econova/grading.py`, `econova/learning.py` |
| Phase 5 | 수요·공급, 탄소세 시뮬레이션 (서버 Python 과 화면 JavaScript 가 같은 공식) | `econova/simulations.py`, `static/js/econova-sim*.js` |
| Phase 6 | 정답 키를 저장소 밖으로 분리, AI 튜터·오답 설명·토론·학습 추천 (기본은 AI 꺼짐) | `econova/private_content.py`, `econova/ai/` |
| Phase 7 | 학생/관리자 역할, 콘텐츠 검토 기록, 내 학습 보고서, SDG 캡스톤 | `econova/roles.py`, `econova/admin_*.py`, `econova/report.py`, `econova/capstone.py` |
| Phase 8A | 보안 점검과 수정 (최종 평가 재응시 공정성, 응시 횟수 동시 제출, 릴리스 계획 서명 등) | `tests/test_phase8a.py` |
| Phase 8B-1 | AI 스위치 하나로 통일, 로그인 시도 제한 강화, 학생 저장 한도 | `econova/login_guard.py`, `econova/quotas.py` |
| Phase 8B-2 | 실제 Firebase·OpenAI 연동 시험 도구 (지금은 가짜로만 실행, 실제 접속은 승인 뒤), 프록시 확인용 관리자 진단 화면 | `integration_tests/`, `docs/phase-8b2-integration.md` |

## 꼭 알아야 할 안전 장치
1. **정답은 저장소에 없다.** 실제 정답 키는 컴퓨터의 저장소 밖 폴더(`~/econova-private`)에만 있다. 저장소의 `answers.json` 7개는 시험용 가짜다.
2. **커밋 전 점검**: 이 저장소에는 pre-commit 훅이 켜져 있어(`core.hooksPath=tools/git-hooks`) 정답·교사용 문서·API 키가
   스테이지되면 커밋이 막힌다. 직접 확인: `flask --app app check-public-files --staged`.
3. **AI 는 기본으로 꺼져 있다** (`ECONOVA_AI_PROVIDER=off`). 꺼져 있으면 OpenAI 로 아무 요청도 가지 않는다.
4. 점수·진도·수료는 AI 가 정하지 않는다. 모두 정해진 규칙으로 계산한다.
5. 관리자 권한은 웹에서 줄 수 없다. 서버 명령(`flask admin-grant`)과 본인 확인 기록이 필요하다.

## 학생이 확인할 것 (검토 체크리스트)
> 주제별 코드 안내와 질문 16개: `docs/release/student-review-guide.md`
> 짧은 순서: ① 앱 실행 → ② 아래 "꼭 읽을 파일" 5개 → ③ `pytest` 와 `pytest integration_tests` 직접 실행 → ④ 질문 정리 → ⑤ 커밋 승인 여부 결정

꼭 읽을 파일 (각 파일 맨 위 설명부터): `econova/learning.py`(수료 규칙), `econova/private_content.py`(정답 키 분리),
`econova/ai/usage.py`(AI 한도), `econova/login_guard.py`(로그인 제한), `integration_tests/guards.py`(실제 연동 전 확인 조건)

- [ ] 앱을 직접 실행해 학생 흐름(가입 → 진단평가 → 개발용 강좌 수강 → 퀴즈 → 최종 평가 → 시뮬레이션 → 보고서 → 캡스톤)을 해 보았다
- [ ] 이전 LMS 보관함(`/legacy`)과 내 커리큘럼이 그대로 동작한다
- [ ] 주요 파일(위 표의 '볼 곳')을 읽고 이해가 안 되는 부분을 질문했다
- [ ] `.venv/bin/python -m pytest` 와 `.venv/bin/python -m pytest integration_tests` 를 직접 실행해 결과를 봤다
- [ ] 커밋 메시지(`docs/release/commit-plan.md`)의 "AI 가 작성하고 학생이 검토했다" 가 사실이다
- [ ] 정답 키 폴더·`.env`·`lms.db` 가 커밋 목록에 없다

## 모르는 게 있으면
- 각 파일 맨 위의 설명(한국어 주석)에 그 파일의 역할과 규칙이 적혀 있다.
- 운영 관련: `docs/operations-readiness.md`, 콘텐츠 준비: `docs/content-readiness.md`.
