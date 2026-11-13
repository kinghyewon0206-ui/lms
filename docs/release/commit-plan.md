# Phase 3~8B-2 안전 체크포인트 커밋 계획

## 상태: 완료 (2026-11-13)
- 체크포인트 커밋 `327f3397958f0c4e230621d51f53005eac97ee1b` (부모 `231cab5`), 작성자 `kimminjune` (저장소 설정의 학생 계정)
- 162개 파일 (새 파일 133, 수정 29, 삭제 0). 아래 2장의 파일 목록과 같다.
- 커밋 직전 확인: 작업 트리가 학생이 검토한 스냅샷과 바이트 단위로 같음, 전체 pytest 869 통과·1 건너뜀, `integration_tests` 27 통과,
  실제 정답 키 정합성 시험 3 통과, `check-public-files --staged`·pre-commit 훅 통과, 실제 정답 해설 34개·키 파일 5개와 대조 일치 0.
- 학생 검토: 선생님이 학생과 함께 검토·승인을 확인한 뒤 커밋했다.
- 실제 커밋 메시지는 아래 4장의 초안이 아니라 승인 때 정한 문구를 썼다 (제목 `feat(econova): expand self-directed economics
  learning platform`, 본문에 학생 검토·승인과 Claude Code 도움 표기, `Co-Authored-By` 한 줄).
- 푸시: 이 문서를 고친 시점에는 하지 않았다 (별도 승인).

> 아래는 커밋 전에 쓴 **계획 기록**이다. 내용은 고치지 않고 그대로 남긴다 ("아직 커밋하지 않았다" 등은 그때의 상태).

> (당시) **아직 커밋하지 않았다.** 학생이 `docs/release/student-review-guide.md` 로 검토를 실제로 마치고 명시적으로 승인한 뒤에만 실행한다.
> 푸시·PR 은 별도 승인. 학생용 요약: `docs/release/student-summary.md`

## 1. 방식: 정리된 현재 파일로 만드는 단일 체크포인트 커밋
- Phase 3~8B-2 의 코드가 같은 파일(예: `econova/storage.py` 의 마이그레이션 3~8, `app.py`, `econova/web.py`)에 섞여 있어,
  단계별로 나누면 각 중간 상태가 테스트를 통과한다는 보장이 없다.
- Phase 3·4 시점의 평가 파일에는 실제 정답이 있었다. 그 시점을 재현하는 커밋은 **만들지 않는다** (공개 저장소).
- 그래서 지금의 정리된 작업 트리 전체를 **커밋 하나**로 올린다. 단계별 대응은 커밋 본문과 학생용 요약으로 설명한다.

## 2. 커밋에 들어가는 파일 (162개: 새 파일 133, 수정 29, 삭제 0)
`.env`, `lms.db`, `.claude/`, 비공개 정답 키(저장소 밖), 비공개 검토 문서, 스냅샷·백업은 **들어가지 않는다**.
`content/dev_fixtures/private/*.answers.json` 7개는 개발용 **합성(가짜)** 키다 (`"synthetic": true`).

| 상태 | 파일 |
|---|---|
| M | `.env.example` |
| M | `.gitignore` |
| M | `README.md` |
| M | `app.py` |
| A | `content/assessments/c02-final.json` |
| A | `content/assessments/c02-l1-quiz.json` |
| A | `content/assessments/c02-l2-quiz.json` |
| A | `content/assessments/c02-l3-quiz.json` |
| A | `content/capstone/c09.json` |
| M | `content/courses/c02.json` |
| M | `content/courses/c03.json` |
| M | `content/courses/c09.json` |
| A | `content/dev_fixtures/assessments/dev-f1-final.json` |
| A | `content/dev_fixtures/assessments/dev-f1-l1-quiz.json` |
| A | `content/dev_fixtures/assessments/dev-f1-l2-quiz.json` |
| A | `content/dev_fixtures/assessments/dev-f1-l3-quiz.json` |
| A | `content/dev_fixtures/assessments/dev-f2-final.json` |
| A | `content/dev_fixtures/assessments/dev-f2-l1-quiz.json` |
| A | `content/dev_fixtures/capstone/dev-f3.json` |
| M | `content/dev_fixtures/catalog.json` |
| A | `content/dev_fixtures/debates/dev-f1.json` |
| M | `content/dev_fixtures/dev-f1.json` |
| M | `content/dev_fixtures/dev-f2.json` |
| A | `content/dev_fixtures/dev-f3.json` |
| A | `content/dev_fixtures/diagnostic.json` |
| A | `content/dev_fixtures/lessons/dev-f1-l1.json` |
| A | `content/dev_fixtures/lessons/dev-f1-l2.json` |
| A | `content/dev_fixtures/lessons/dev-f1-l3.json` |
| A | `content/dev_fixtures/lessons/dev-f2-l1.json` |
| A | `content/dev_fixtures/lessons/dev-f2-l2.json` |
| A | `content/dev_fixtures/lessons/dev-f3-l1.json` |
| A | `content/dev_fixtures/lessons/dev-f3-l2.json` |
| A | `content/dev_fixtures/lessons/dev-f3-l3.json` |
| A | `content/dev_fixtures/private/dev-diagnostic.answers.json` |
| A | `content/dev_fixtures/private/dev-f1-final.answers.json` |
| A | `content/dev_fixtures/private/dev-f1-l1-quiz.answers.json` |
| A | `content/dev_fixtures/private/dev-f1-l2-quiz.answers.json` |
| A | `content/dev_fixtures/private/dev-f1-l3-quiz.answers.json` |
| A | `content/dev_fixtures/private/dev-f2-final.answers.json` |
| A | `content/dev_fixtures/private/dev-f2-l1-quiz.answers.json` |
| A | `content/diagnostic.json` |
| A | `content/lessons/c02-l1.json` |
| A | `content/lessons/c02-l2.json` |
| A | `content/lessons/c02-l3.json` |
| A | `content/sources.json` |
| A | `docs/content-readiness.md` |
| A | `docs/integration-test-plans.md` |
| A | `docs/operations-readiness.md` |
| A | `docs/phase-8b2-integration.md` |
| A | `docs/phase-8b2-prerequisites.md` |
| A | `docs/release-checklist-8b.md` |
| A | `docs/release/commit-plan.md` |
| A | `docs/release/readiness-8b2.md` |
| A | `docs/release/student-review-guide.md` |
| A | `docs/release/student-summary.md` |
| A | `econova/admin_content.py` |
| A | `econova/admin_web.py` |
| A | `econova/ai/__init__.py` |
| A | `econova/ai/capstone.py` |
| A | `econova/ai/client.py` |
| A | `econova/ai/context.py` |
| A | `econova/ai/debate.py` |
| A | `econova/ai/feedback.py` |
| A | `econova/ai/legacy.py` |
| A | `econova/ai/recommendations.py` |
| A | `econova/ai/safety.py` |
| A | `econova/ai/tutor.py` |
| A | `econova/ai/usage.py` |
| A | `econova/ai_web.py` |
| A | `econova/assessments.py` |
| A | `econova/capstone.py` |
| M | `econova/config.py` |
| M | `econova/content.py` |
| A | `econova/debates.py` |
| A | `econova/diagnostic.py` |
| A | `econova/grading.py` |
| A | `econova/graphs.py` |
| M | `econova/learning.py` |
| A | `econova/lesson_content.py` |
| A | `econova/login_guard.py` |
| A | `econova/private_content.py` |
| M | `econova/progress.py` |
| A | `econova/public_safety.py` |
| A | `econova/quotas.py` |
| A | `econova/recommendations.py` |
| A | `econova/report.py` |
| A | `econova/review_package.py` |
| A | `econova/roles.py` |
| A | `econova/simulations.py` |
| M | `econova/storage.py` |
| A | `econova/student_web.py` |
| M | `econova/web.py` |
| A | `integration_tests/__init__.py` |
| A | `integration_tests/conftest.py` |
| A | `integration_tests/fake_backends.py` |
| A | `integration_tests/firestore_marker.py` |
| A | `integration_tests/guards.py` |
| A | `integration_tests/test_firestore_integration.py` |
| A | `integration_tests/test_openai_integration.py` |
| A | `integration_tests/transport.py` |
| A | `static/js/econova-ai.js` |
| A | `static/js/econova-sim-ui.js` |
| A | `static/js/econova-sim.js` |
| M | `static/style.css` |
| M | `templates/base.html` |
| A | `templates/econova/_graph.html` |
| A | `templates/econova/_lesson_body.html` |
| A | `templates/econova/_material.html` |
| A | `templates/econova/admin/content.html` |
| A | `templates/econova/admin/release.html` |
| A | `templates/econova/admin/request_diagnostics.html` |
| A | `templates/econova/admin/target.html` |
| A | `templates/econova/ai/_tutor.html` |
| A | `templates/econova/assessment/_explain.html` |
| A | `templates/econova/assessment/completion.html` |
| A | `templates/econova/assessment/history.html` |
| A | `templates/econova/assessment/result.html` |
| A | `templates/econova/assessment/take.html` |
| A | `templates/econova/capstone/edit.html` |
| A | `templates/econova/capstone/home.html` |
| A | `templates/econova/capstone/self_assessment.html` |
| A | `templates/econova/capstone/version.html` |
| M | `templates/econova/course_detail.html` |
| M | `templates/econova/dashboard.html` |
| A | `templates/econova/diagnostic/index.html` |
| A | `templates/econova/diagnostic/result.html` |
| A | `templates/econova/diagnostic/take.html` |
| A | `templates/econova/discuss/course.html` |
| A | `templates/econova/discuss/index.html` |
| A | `templates/econova/discuss/topic.html` |
| A | `templates/econova/lab/_widget.html` |
| A | `templates/econova/lab/index.html` |
| A | `templates/econova/lab/run.html` |
| A | `templates/econova/lab/saved.html` |
| A | `templates/econova/lab/sim.html` |
| M | `templates/econova/lesson.html` |
| A | `templates/econova/preview.html` |
| A | `templates/econova/report.html` |
| A | `templates/errors/assessment_unavailable.html` |
| M | `tests/conftest.py` |
| A | `tests/data/sim_vectors.json` |
| A | `tests/sim_node_runner.js` |
| A | `tests/synthetic_keys.py` |
| A | `tests/test_ai_features.py` |
| A | `tests/test_assessments.py` |
| A | `tests/test_diagnostic.py` |
| M | `tests/test_econova_content.py` |
| M | `tests/test_econova_progress.py` |
| M | `tests/test_econova_routes.py` |
| M | `tests/test_econova_storage.py` |
| M | `tests/test_lms.py` |
| A | `tests/test_phase3_content.py` |
| A | `tests/test_phase7.py` |
| A | `tests/test_phase8a.py` |
| A | `tests/test_phase8b1.py` |
| A | `tests/test_phase8b2.py` |
| A | `tests/test_private_content.py` |
| A | `tests/test_simulations.py` |
| M | `tests/test_stability.py` |
| M | `tests/test_storage.py` |
| A | `tests/test_submission_recovery.py` |
| A | `tools/git-hooks/pre-commit` |

## 3. 사전 점검 결과 (커밋하지 않고, 실제 인덱스는 쓰지 않음 — 임시 인덱스 `GIT_INDEX_FILE`)
| 점검 | 결과 |
|---|---|
| 실제 인덱스 | 점검 전 0개 → 점검 후 0개 |
| 후보 파일 | 162개 |
| 공개 저장소 점검 (pre-commit 훅, 스테이지된 내용 기준) | 종료 코드 0 — 공개 저장소 점검 통과: 162개 파일 |
| 제외해야 할 경로 (.env, DB, .claude/, 비공개 폴더, 스냅샷, docs/review/, 키 파일) | 0개 |
| 정답 키 파일 | 7개, 모두 합성: 예 |
| 실제 정답 키와 대조 | 실제 해설 34개·키 파일 5개 → 일치 0 |
| 비공개 검토 문서와 대조 | 긴 줄 41개 중 5줄이 2개 파일에서 일치 — 확인 결과 모두 공개 정보: `content/assessments/c02-l1-quiz.json` 의 **문항 지문(prompt)** 2줄(검토 문서가 공개 문항을 인용), `econova/review_package.py` 의 문서 생성 틀 문장 3줄. 정답·해설 줄 일치 0 |
| 재현성 (꺼낸 트리 = 작업 트리, 바이트 단위) | 다른 파일 0개 |
| 꺼낸 트리 전체 pytest | 4 failed, 865 passed, 1 skipped in 313.91s (0:05:13) |
| 꺼낸 트리 integration_tests (fake) | 27 passed in 15.30s |

꺼낸 트리 실패 시험: `tests/test_phase8a.py::test_staged_scan_reads_index_not_worktree`, `tests/test_private_content.py::test_cli_reports_closed_assessments_and_public_scan`, `tests/test_private_content.py::test_everything_git_add_would_include_is_clean`, `tests/test_private_content.py::test_gitignore_blocks_private_material` — 모두 `.git` 이 있어야 하는 시험
(꺼낸 폴더에는 `.git` 이 없음). 저장소 안에서는 통과한다.

## 4. 작성자와 AI 도움 기록
- 작성자: 저장소 설정의 학생 계정(바꾸지 않는다). 코드·테스트·문서는 Claude Code(AI)가 작성했다. 단계별 요구 사항은 선생님이 정했다.
- **학생 검토 기록을 지어내지 않는다.** 아래 메시지의 "reviewed by the student" 문장은 학생이 검토를 실제로 마쳤을 때만 남기고,
  아니면 지우거나 커밋하지 않는다. 학생이 직접 고친 부분이 있으면 본문에 따로 적는다.

### 커밋 메시지 초안 (계획 당시 — 실제로는 쓰지 않음, 맨 위 상태 참고)
```
feat(econova): add assessments, simulations, AI learning, admin review and capstone (Phase 3-8B-2)

Phase 3: c02 draft lesson materials, source registry, diagnostic (draft)
Phase 4: formative quizzes, final assessment, deterministic grading, completion rules
Phase 5: supply-demand and carbon-tax simulations (Python/JS parity)
Phase 6: private answer keys outside the repo, AI tutor/feedback/debate/recommendations
         (provider off by default), usage limits, retention
Phase 7: student/admin roles, content review audit and release plans,
         personal learning report, SDG capstone (c09 draft, dev-f3 fixture)
Phase 8A: security fixes (attempt-limit race, final answers hidden while retakes remain,
         superseded approvals not releasable, signed release plans, staged-content scan)
Phase 8B-1: single AI provider switch incl. legacy LMS, login abuse protection
         (account/IP/account+IP, trusted proxy hops, known-device cookie), student storage quotas,
         revoked-reviewer approvals not releasable, sqlite migration 8
Phase 8B-2: integration test harness for development Firestore and OpenAI (fake by default;
         live mode refuses to start without an identified dev project, key files outside the repo,
         request budget and explicit approval values), admin-only proxy diagnostics page (off by default),
         student review guide

All real courses remain coming_soon; c02 content and assessments remain unapproved drafts.
Real assessment answer keys are not in this repository.
Code was written by Claude Code (AI) and reviewed by the student before committing.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## 5. 학생이 승인한 뒤 실행할 순서 (참고 — 지금 실행하지 않음. 문서 속 명령을 그대로 복사·실행하지 말고 한 줄씩 확인)
1. 변경 목록 확인 (`git status`), 위 표와 같은지
2. 모든 변경을 스테이지
3. 스테이지 검사 `flask --app app check-public-files --staged` — 반드시 통과 (pre-commit 훅도 같은 검사를 한다)
4. 스테이지 통계가 위 표와 같은지 확인 (`.claude/`·`.env`·DB 가 없어야 함)
5. 메시지 파일로 커밋 (작성자는 저장소 설정의 학생 계정, `--no-verify` 금지)
6. 커밋 뒤 저장소 안에서 전체 테스트

pre-commit 훅은 이 저장소에서 켜져 있다 (저장소 로컬 설정 `core.hooksPath=tools/git-hooks`). 다른 컴퓨터에서 받으면 각자 한 번 켠다.
