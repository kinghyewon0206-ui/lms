"""Phase 8A 수정 회귀 테스트: 스테이지된 내용 검사, 릴리스 계획 서명·DB 기준 반영, 정본 승인 검증, 합격 기준 승인이
평가 승인을 무효로 만들지 않음, 보안 헤더."""
import copy
import json
import os
import shutil
import subprocess

import pytest

from econova import admin_content as ac
from econova import content, lesson_content, public_safety, storage
from tests.conftest import CSRF, ROOT
from tests.test_phase7 import DRAFT_TOPIC, _make_admin, _review, content_copy  # noqa: F401 (fixture 재사용)

pytestmark = pytest.mark.usefixtures("fixtures_on")
KEY = "k" * 40


def test_staged_scan_reads_index_not_worktree(tmp_path):
    """작업 트리에 없는(또는 다른) 내용이 인덱스에만 스테이지돼 있어도 찾아낸다 (git add -p, 스테이지 뒤 수정)."""
    index = tmp_path / "index"
    env = {**os.environ, "GIT_INDEX_FILE": str(index)}
    subprocess.run(["git", "read-tree", "HEAD"], cwd=ROOT, env=env, check=True)
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=ROOT, env=env, check=True, capture_output=True,
                          input=b'{"questions": [{"id": "q1", "answer": "a"}]}').stdout.decode().strip()
    subprocess.run(["git", "update-index", "--add", "--cacheinfo", f"100644,{blob},content/assessments/zz-planted.json"],
                   cwd=ROOT, env=env, check=True)
    assert not os.path.exists(os.path.join(ROOT, "content/assessments/zz-planted.json"))
    res = subprocess.run([os.path.join(ROOT, "tools/git-hooks/pre-commit")], cwd=ROOT, env=env, capture_output=True, text=True)
    assert res.returncode == 1 and "zz-planted.json" in res.stdout and "answer information" in res.stdout
    clean = tmp_path / "clean"
    env["GIT_INDEX_FILE"] = str(clean)
    subprocess.run(["git", "read-tree", "HEAD"], cwd=ROOT, env=env, check=True)
    assert subprocess.run([os.path.join(ROOT, "tools/git-hooks/pre-commit")], cwd=ROOT, env=env).returncode == 0


def test_plan_signature():
    plan = {"kind": "econova_release_plan", "items": [{"target_id": "x"}]}
    signed = ac.sign_plan(plan, KEY)
    assert ac.plan_signature_ok(signed, KEY)
    assert not ac.plan_signature_ok(signed, "x" * 40)              # 다른 키
    assert not ac.plan_signature_ok(plan, KEY)                     # 서명 없음
    assert not ac.plan_signature_ok(ac.sign_plan(plan, "short"), "short")   # 짧은 키는 쓰지 않음
    tampered = copy.deepcopy(signed)
    tampered["items"][0]["target_id"] = "y"
    assert not ac.plan_signature_ok(tampered, KEY)
    assert ac.sign_plan(plan, "") == plan


def _forged_plan(tmp_path, **override):
    target = ac.find_target("debate", DRAFT_TOPIC, include_fixtures=True)
    item = {"target_type": "debate", "target_id": DRAFT_TOPIC, "course_id": "dev-f1", "file": target.file,
            "content_version": "1", "content_digest": target.digest, "review_id": "999", "reviewer_name": "누군가",
            "comment": "", "approved_at": "2026-11-03", **override}
    return {"schema_version": 1, "kind": "econova_release_plan", "items": [item]}


def test_trust_plan_requires_valid_signature(app, client, content_copy, tmp_path, monkeypatch):  # noqa: F811
    runner = app.test_cli_runner()
    plan = _forged_plan(tmp_path)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    res = runner.invoke(args=["content-release-apply", str(path), "--trust-plan"])
    assert "Plan signature missing or invalid" in res.output                      # 서명 없는 계획 + --trust-plan → 거부
    monkeypatch.setenv("ECONOVA_RELEASE_SIGNING_KEY", KEY)
    tampered = ac.sign_plan(plan, KEY)
    tampered["items"][0]["reviewer_name"] = "바꾼 이름"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    assert "Plan signature missing or invalid" in runner.invoke(args=["content-release-apply", str(path), "--trust-plan"]).output
    topic = json.loads((content_copy / "dev_fixtures/debates/dev-f1.json").read_text(encoding="utf-8"))["topics"][2]
    assert topic["review"]["status"] == "draft"
    path.write_text(json.dumps(ac.sign_plan(plan, KEY)), encoding="utf-8")   # 운영 서버가 서명한 계획 (키 공유)
    res = runner.invoke(args=["content-release-apply", str(path), "--trust-plan"])
    assert "→ Applied" in res.output, res.output


def test_apply_uses_db_reviewer_not_plan_fields(app, client, content_copy, tmp_path):  # noqa: F811
    _make_admin(app, client)
    _review(client, "start_review")
    _review(client, "approve")
    plan = json.loads(client.get("/admin/content/release?download=1").get_data(as_text=True))
    plan["items"][0]["reviewer_name"] = "위조된 검토자"
    plan["items"][0]["approved_at"] = "2020-01-01"
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    res = app.test_cli_runner().invoke(args=["content-release-apply", str(path)])
    assert "→ Applied" in res.output, res.output
    review = json.loads((content_copy / "dev_fixtures/debates/dev-f1.json").read_text(encoding="utf-8"))["topics"][2]["review"]
    assert review["reviewer"]["name"] == "관리자 김" and review["approved_at"] != "2020-01-01"


def test_verify_canonical_approvals(app, client, content_copy, tmp_path):  # noqa: F811
    runner = app.test_cli_runner()
    assert runner.invoke(args=["content-verify-approvals"]).exit_code == 0      # 실제 강좌: 관리자 승인 없음
    _make_admin(app, client)
    _review(client, "start_review")
    _review(client, "approve")
    plan = json.loads(client.get("/admin/content/release?download=1").get_data(as_text=True))
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    runner.invoke(args=["content-release-apply", str(path)])
    res = runner.invoke(args=["content-verify-approvals", "--include-fixtures"])
    assert res.exit_code == 0 and "All 1 canonical admin approval(s) match" in res.output
    # 다른 DB(기록 없음)나 위조된 번호면 실패
    data = json.loads((content_copy / "dev_fixtures/debates/dev-f1.json").read_text(encoding="utf-8"))
    data["topics"][2]["review"]["reviewer"]["review_id"] = "424242"
    (content_copy / "dev_fixtures/debates/dev-f1.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    res = runner.invoke(args=["content-verify-approvals", "--include-fixtures"])
    assert res.exit_code != 0 and "Review record #424242 is not in the DB." in res.output
    assert "Canonical approvals not confirmed by DB review records" in client.get("/admin/content").get_data(as_text=True)


def test_passing_approval_does_not_invalidate_assessment_approval():
    data = {"id": "f", "version": 1, "questions": [], "passing": {"score_ratio": 0.7, "status": "proposed", "note": "제안"}}
    after = copy.deepcopy(data)
    after["passing"].update(status="approved", review_id="12", note="2026-11-10 관리자 승인 (검토 기록 #12)")
    assert lesson_content.assessment_digest(data) == lesson_content.assessment_digest(after)
    changed = copy.deepcopy(data)
    changed["passing"]["score_ratio"] = 0.8
    assert lesson_content.assessment_digest(changed) != lesson_content.assessment_digest(data)


def test_security_headers(client):
    res = client.get("/login")
    assert res.headers["X-Frame-Options"] == "SAMEORIGIN" and res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["Referrer-Policy"] == "same-origin"


# ------------------------------------------------------------- 독립 감사(Phase 8A) 지적 사항 수정
def test_reopened_approval_cannot_be_released_or_verified(app, client, content_copy, tmp_path):  # noqa: F811
    _make_admin(app, client)
    _review(client, "start_review")
    _review(client, "approve")
    plan = json.loads(client.get("/admin/content/release?download=1").get_data(as_text=True))
    _review(client, "reopen")                                          # 승인 뒤 '다시 검토'
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    res = app.test_cli_runner().invoke(args=["content-release-apply", str(path)])
    assert "'Reopen review' (#" in res.output and "was recorded after the approval" in res.output and "→ Applied" not in res.output
    topic = json.loads((content_copy / "dev_fixtures/debates/dev-f1.json").read_text(encoding="utf-8"))["topics"][2]
    assert topic["review"]["status"] == "draft"
    assert client.get("/admin/content/release?download=1").get_json()["items"] == []   # 새 계획에도 없다


def test_superseded_canonical_approval_is_flagged(app, client, content_copy, tmp_path):  # noqa: F811
    _make_admin(app, client)
    _review(client, "start_review")
    _review(client, "approve")
    plan = json.loads(client.get("/admin/content/release?download=1").get_data(as_text=True))
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    runner = app.test_cli_runner()
    runner.invoke(args=["content-release-apply", str(path)])
    assert runner.invoke(args=["content-verify-approvals", "--include-fixtures"]).exit_code == 0
    _review(client, "reopen")                                          # 정본 반영 뒤 '다시 검토'
    res = runner.invoke(args=["content-verify-approvals", "--include-fixtures"])
    assert res.exit_code != 0 and "this approval is no longer valid" in res.output


def test_legacy_teacher_approval_is_flagged(content_copy):  # noqa: F811
    path = content_copy / "dev_fixtures/debates/dev-f1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["topics"][2]["review"] = {"status": "approved", "reviewer": {"name": "김선생", "role": "teacher"},
                                   "approved_at": "2026-11-10", "history": [{"status": "approved", "at": "2026-11-10", "by": "김선생"}]}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    problems = ac.verify_canonical_approvals(lambda rid: None, include_fixtures=True)
    assert any("role=teacher" in why for _, why in problems)


def test_attempt_limit_is_enforced_at_save(app):
    from tests.test_econova_routes import _uid
    rec = {"course_id": "dev-f2", "lesson_id": None, "assessment_id": "dev-f2-final", "assessment_version": 1,
           "course_content_version": 1, "kind": "final", "score": 0, "max_score": 1, "ratio": 0.0, "passed": False,
           "answers": {}, "results": [], "passing": {}}
    with app.app_context():
        storage.create_user("lim@example.com", "L", "h")
        uid = storage.get_user_by_email("lim@example.com")["id"]
        storage.enroll_course(uid, "dev-f2", "beginner", 1)
        storage.save_assessment_attempt(uid, rec, "token-aaaaaaaaaaaaaaaa1", max_attempts=2)
        storage.save_assessment_attempt(uid, rec, "token-aaaaaaaaaaaaaaaa2", max_attempts=2)
        with pytest.raises(storage.AttemptLimitReached):
            storage.save_assessment_attempt(uid, rec, "token-aaaaaaaaaaaaaaaa3", max_attempts=2)
        with pytest.raises(storage.DuplicateSubmission):            # 같은 토큰 재전송은 한도와 무관하게 중복으로 처리
            storage.save_assessment_attempt(uid, rec, "token-aaaaaaaaaaaaaaaa2", max_attempts=2)
        assert len(storage.list_assessment_attempts(uid, assessment_id="dev-f2-final")) == 2


def test_attempt_limit_under_concurrent_threads(tmp_path):
    import threading
    import app as app_module
    flask_app = app_module.app
    old = flask_app.config["DATABASE"]
    flask_app.config["DATABASE"] = str(tmp_path / "race.db")
    rec = {"course_id": "dev-f2", "lesson_id": None, "assessment_id": "dev-f2-final", "assessment_version": 1,
           "course_content_version": 1, "kind": "final", "score": 0, "max_score": 1, "ratio": 0.0, "passed": False,
           "answers": {}, "results": [], "passing": {}}
    try:
        with flask_app.app_context():
            storage.init_db()
            storage.create_user("race@example.com", "R", "h")
            uid = storage.get_user_by_email("race@example.com")["id"]
            storage.enroll_course(uid, "dev-f2", "beginner", 1)
        def worker(i):
            with flask_app.app_context():
                try:
                    storage.save_assessment_attempt(uid, rec, f"token-concurrent-{i:04d}", max_attempts=3)
                except Exception:
                    pass
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        with flask_app.app_context():
            assert len(storage.list_assessment_attempts(uid, assessment_id="dev-f2-final")) <= 3
    finally:
        flask_app.config["DATABASE"] = old


def test_final_answers_hidden_while_retakes_remain(app, logged_in):
    from tests.test_econova_routes import _enroll, _post, take
    _enroll(logged_in, "dev-f2")
    course = content.get_catalog().course("dev-f2")
    for lesson in course.lessons:
        _post(logged_in, f"/learn/dev-f2/{lesson.id}/material-reviewed")
        if lesson.quiz_assessment:
            take(logged_in, f"/learn/dev-f2/{lesson.id}/quiz", lesson.quiz_assessment)
    url = take(logged_in, "/courses/dev-f2/final", course.final, correct=False)
    html = logged_in.get(url).get_data(as_text=True)
    assert "shown only after you pass or use all your attempts" in html
    assert all(q["explanation"] not in html for q in course.final.questions)
    res = logged_in.post(url + "/explain", data={"csrf_token": CSRF})
    assert "after you pass it or use all of your attempts" in logged_in.get(res.headers["Location"]).get_data(as_text=True)
    take(logged_in, "/courses/dev-f2/final", course.final, correct=True)
    html = logged_in.get(url).get_data(as_text=True)                    # 합격한 뒤에는 첫 응시의 해설도 볼 수 있다
    assert any(q["explanation"] in html for q in course.final.questions)


def test_diagnostic_served_when_answer_keys_exist_even_in_production(monkeypatch):
    """대회판 정책: 진단평가는 검토 상태와 무관하게 정답 키가 있으면 제공한다 (운영 환경 포함). 정답 키가 없으면 제공하지 않는다."""
    from econova import diagnostic
    test = diagnostic.load()
    assert test["review"]["status"] == "draft" and diagnostic.servable(test)   # 검토 기록은 draft 그대로
    monkeypatch.setenv("RENDER", "1")
    assert diagnostic.servable(test)
    assert not diagnostic.servable({**test, "answer_keys": False})


@pytest.mark.parametrize("token", ["..", "a/b/c", "short", "x" * 65, "tok en-aaaaaaaaaaaa"])
def test_submission_token_format(logged_in, token):
    from tests.test_econova_routes import _enroll, _post
    _enroll(logged_in, "dev-f1")
    _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    res = logged_in.post("/learn/dev-f1/dev-f1-l1/quiz", data={"csrf_token": CSRF, "submission_token": token})
    assert res.status_code == 400


def test_input_size_limits(client):
    from tests.conftest import set_csrf
    set_csrf(client)
    res = client.post("/signup", data={"csrf_token": CSRF, "name": "가" * 51, "email": "n@example.com",
                                       "password": "password123", "confirm": "password123"})
    assert "Your name must be 50 characters or fewer." in res.get_data(as_text=True)
    res = client.post("/signup", data={"csrf_token": CSRF, "name": "x", "email": "n@example.com",
                                       "password": "p" * 300, "confirm": "p" * 300})
    assert "256 characters max" in res.get_data(as_text=True)
    assert client.post("/login", data={"csrf_token": CSRF, "email": "a@b.c", "password": "x" * (1024 * 1024 + 10)}).status_code == 413


def test_passing_threshold_needs_approved_assessment_first(app, client):
    _make_admin(app, client)
    target = ("passing", "dev-f2-final")
    t = ac.find_target(*target, include_fixtures=True)
    assert t.refs["assessment_approved"]          # fixture 평가는 이미 승인 (순서 조건 충족)
    blocked = dataclasses_replace_refs(t, assessment_approved=False)
    state = {"state": "in_review"}
    with pytest.raises(ac.ReviewRefused, match=r"assessment first, then passing criteria"):
        ac.validate_decision(blocked, state, "approve", blocked.digest, "직접 확인했습니다", True, "관리자 김")


def dataclasses_replace_refs(t, **refs):
    import dataclasses
    return dataclasses.replace(t, refs={**t.refs, **refs})
