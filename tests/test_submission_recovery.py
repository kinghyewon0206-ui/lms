"""Phase 4 안전 점검 B2: 응시 기록은 저장됐는데 진도(또는 수료) 반영이 실패한 뒤, 같은 제출 토큰으로 다시 제출하는 경우.
요구: 응시 기록은 하나뿐, 진도·수료는 결국 반영, 최고 점수는 내려가지 않음, 처음 제출 시각 유지, 반복해도 같은 결과.
sqlite 와 가짜 Firestore 양쪽에서 돈다."""
import re

import pytest

from econova import content, learning, storage
from tests.conftest import CSRF
from tests.test_assessments import _complete_lessons
from tests.test_econova_routes import _enroll, _post, _uid, take

pytestmark = pytest.mark.usefixtures("fixtures_on")
QUIZ_URL = "/learn/dev-f1/dev-f1-l1/quiz"


def _form(client, url, assessment, correct=True):
    token = re.search(r'name="submission_token" value="([^"]+)"', client.get(url).get_data(as_text=True)).group(1)
    answers = {f"q_{q['id']}": (q["answer"] if q["type"] == "mcq" else f"{q['answer']:g}") if correct
               else ("b" if q["type"] == "mcq" else "-1") for q in assessment.questions}
    return {"csrf_token": CSRF, "submission_token": token, **answers}


def _fail_once(monkeypatch, module, name):
    real = getattr(module, name)
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("일시적인 저장 실패 (테스트)")
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, flaky)
    return calls


def _quiz():
    return content.get_catalog().course("dev-f1").lesson("dev-f1-l1").quiz_assessment


def test_quiz_progress_recovers_on_retry_with_same_token(app, logged_in, monkeypatch):
    _enroll(logged_in, "dev-f1")
    _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    data = _form(logged_in, QUIZ_URL, _quiz())
    calls = _fail_once(monkeypatch, storage, "update_lesson_progress")

    # 1) 응시 기록은 저장되지만 2) 진도 반영이 실패한다
    with pytest.raises(RuntimeError):
        logged_in.post(QUIZ_URL, data=data)
    with app.app_context():
        uid = _uid(app)
        [attempt] = storage.list_assessment_attempts(uid)
        assert storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]["quiz_submitted"] is False

    # 3) 같은 토큰으로 다시 제출 → 4) 원래 결과로 이동하면서 진도가 복구된다
    res = logged_in.post(QUIZ_URL, data=data)
    assert res.status_code == 302 and res.headers["Location"].endswith(f"/assessments/attempts/{attempt['id']}")
    with app.app_context():
        attempts = storage.list_assessment_attempts(uid)
        rec = storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]
    assert len(attempts) == 1 and calls["n"] >= 2
    assert (rec["status"], rec["quiz_submitted"], rec["quiz_submission_id"], rec["quiz_score"]) == \
        ("completed", True, attempt["id"], 1.0)
    assert rec["quiz_submitted_at"] == attempt["created_at"].replace(microsecond=0) or \
        rec["quiz_submitted_at"] == attempt["created_at"]   # 처음 제출 시각 유지
    with app.app_context():
        assert learning.dashboard(uid)["completed_lessons"] == 1


def test_final_completion_recovers_on_retry(app, logged_in, monkeypatch):
    _enroll(logged_in, "dev-f2")
    _complete_lessons(logged_in, "dev-f2")
    final = content.get_catalog().course("dev-f2").final
    data = _form(logged_in, "/courses/dev-f2/final", final)
    _fail_once(monkeypatch, storage, "complete_enrollment")
    with pytest.raises(RuntimeError):
        logged_in.post("/courses/dev-f2/final", data=data)
    with app.app_context():
        uid = _uid(app)
        [attempt] = storage.list_assessment_attempts(uid, assessment_id=final.id)
        assert attempt["passed"] is True and storage.get_enrollment(uid, "dev-f2")["status"] == "active"
    logged_in.post("/courses/dev-f2/final", data=data)
    with app.app_context():
        e = storage.get_enrollment(uid, "dev-f2")
        assert len(storage.list_assessment_attempts(uid, assessment_id=final.id)) == 1
    assert (e["status"], e["completion_attempt_id"], e["completion_policy"]) == ("completed", attempt["id"], "dev_provisional")
    assert e["completed_at"] in (attempt["created_at"], attempt["created_at"].replace(microsecond=0))


def test_recovery_never_lowers_best_score_or_changes_first_submission(app, logged_in, monkeypatch):
    _enroll(logged_in, "dev-f1")
    _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    take(logged_in, QUIZ_URL, _quiz(), correct=True)
    with app.app_context():
        uid = _uid(app)
        before = storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]
    data = _form(logged_in, QUIZ_URL, _quiz(), correct=False)
    _fail_once(monkeypatch, storage, "update_lesson_progress")
    with pytest.raises(RuntimeError):
        logged_in.post(QUIZ_URL, data=data)
    logged_in.post(QUIZ_URL, data=data)
    with app.app_context():
        after = storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]
        assert len(storage.list_assessment_attempts(uid)) == 2
    assert after["quiz_score"] == 1.0                                   # 0점 재응시로 내려가지 않음
    assert after["quiz_submission_id"] == before["quiz_submission_id"]  # 처음 제출 기록 유지
    assert after["quiz_submitted_at"] == before["quiz_submitted_at"] and after["completed_at"] == before["completed_at"]


def test_reconciliation_is_idempotent(app, logged_in):
    _enroll(logged_in, "dev-f1")
    _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    take(logged_in, QUIZ_URL, _quiz())
    course = content.get_catalog().course("dev-f1")
    with app.app_context():
        uid = _uid(app)
        [attempt] = storage.list_assessment_attempts(uid)
        first = storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]
        for _ in range(3):
            learning.reconcile_attempt(uid, course, _quiz(), attempt, lesson=course.lesson("dev-f1-l1"))
        assert storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"] == first   # updated_at 까지 그대로
        assert learning.dashboard(uid)["completed_lessons"] == 1


def test_concurrent_duplicate_is_reconciled_not_duplicated(app, logged_in, monkeypatch):
    """두 요청이 동시에 '아직 기록 없음'을 보고 저장을 시도하는 경우: 저장소의 고유 제약이 두 번째를 막고,
    두 번째 요청은 진도 반영(멱등)만 하고 같은 기록을 가리킨다."""
    _enroll(logged_in, "dev-f1")
    course = content.get_catalog().course("dev-f1")
    lesson = course.lesson("dev-f1-l1")
    answers = {q["id"]: q["answer"] if q["type"] == "mcq" else f"{q['answer']:g}" for q in _quiz().questions}
    with app.app_context():
        uid = _uid(app)
        first_id, created = learning.submit_assessment(uid, course, _quiz(), answers, "race-token", lesson=lesson)
        assert created
        monkeypatch.setattr(storage, "find_attempt_by_token", lambda *a, **k: None)   # 경쟁 상황 흉내
        second_id, created2 = learning.submit_assessment(uid, course, _quiz(), answers, "race-token", lesson=lesson)
        assert (second_id, created2) == (first_id, False)
        assert len(storage.list_assessment_attempts(uid)) == 1
        assert storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]["quiz_submission_id"] == first_id


def test_token_from_another_assessment_has_no_effect(app, logged_in):
    _enroll(logged_in, "dev-f1")
    data = _form(logged_in, QUIZ_URL, _quiz())
    logged_in.post(QUIZ_URL, data=data)
    # 같은 토큰을 다른 레슨 퀴즈 주소로 보내도 그 레슨의 진도는 바뀌지 않는다
    res = logged_in.post("/learn/dev-f1/dev-f1-l2/quiz", data={"csrf_token": CSRF, "submission_token": data["submission_token"]})
    assert res.status_code == 302
    with app.app_context():
        assert "dev-f1-l2" not in storage.list_lesson_progress(_uid(app), "dev-f1")
        assert len(storage.list_assessment_attempts(_uid(app))) == 1
