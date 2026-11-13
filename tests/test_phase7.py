"""Phase 7: 역할(학생·플랫폼 관리자), 관리자 부여 CLI, 콘텐츠 검토·감사·릴리스, 개인 학습 보고서, SDG 캡스톤,
보안 설정, 마이그레이션 7·Firestore. 실제 OpenAI·Firebase 는 부르지 않는다.
화면·저장 테스트는 sqlite 와 가짜 Firestore 양쪽에서 돈다."""
import copy
import dataclasses
import datetime
import io
import json
import os
import shutil
import sqlite3
import urllib.request

import pytest

from econova import admin_content as ac
from econova import capstone as cap
from econova import config, content, lesson_content, roles, storage
from econova.ai import client
from econova.ai.safety import STUDENT_TAG
from tests.conftest import CSRF, ROOT, login, set_csrf, signup
from tests.test_econova_routes import _enroll, _post, _uid, take

pytestmark = pytest.mark.usefixtures("fixtures_on")
ADMIN = "admin@example.test"


def _user(app, email="student@example.com"):
    with app.app_context():
        return storage.get_user_by_email(email)


def _make_admin(app, client_, email=ADMIN, name="관리자 김"):
    signup(client_, email=email, name=name)
    with app.app_context():
        storage.grant_admin(storage.get_user_by_email(email)["id"], "테스트 운영자", "테스트에서 만든 가상 계정 확인")
    login(client_, email=email)
    set_csrf(client_)
    return client_


def _switch(client_, email):
    client_.post("/logout", data={"csrf_token": CSRF})
    signup(client_, email=email)
    login(client_, email=email)
    set_csrf(client_)


# ------------------------------------------------------------- 역할·권한
def test_signup_is_always_student_and_cannot_escalate(app, client):
    set_csrf(client)
    client.post("/signup", data={"name": "학생", "email": "x@example.com", "password": "password123", "confirm": "password123",
                                 "csrf_token": CSRF, "role": "admin"})
    login(client, email="x@example.com")
    set_csrf(client)
    user = _user(app, "x@example.com")
    assert roles.role_of(user) == "student"
    with app.app_context():
        assert not roles.is_admin(user)
    for path in ("/admin", "/admin/content", "/admin/content/release", "/admin/content/assessment/dev-f1-l1-quiz"):
        assert client.get(path).status_code == 404
    assert client.post("/admin/content/debate/dev-f1/draft-topic-hidden/review", data={"csrf_token": CSRF}).status_code == 404


def test_role_value_alone_or_legacy_teacher_grants_nothing(app, client, monkeypatch):
    signup(client)
    login(client)
    set_csrf(client)
    with app.app_context():
        uid = _uid(app)
        storage.set_user_role(uid, "admin")             # 부여 기록 없이 역할 값만 admin
        assert not roles.is_admin(storage.get_user_by_id(uid))
        if not storage.using_firestore():
            storage.get_db().execute("UPDATE users SET role = 'teacher' WHERE id = ?", (uid,))
            storage.get_db().commit()
            assert roles.role_of(storage.get_user_by_id(uid)) == "teacher"
            assert not roles.is_admin(storage.get_user_by_id(uid))
    assert client.get("/admin/content").status_code == 404
    monkeypatch.delenv("ECONOVA_CONTENT_PREVIEW", raising=False)
    assert client.get("/preview/c02/c02-l1").status_code == 404     # 초안 미리보기도 열리지 않는다


def test_admin_access_and_revocation(app, client):
    _make_admin(app, client)
    res = client.get("/admin/content")
    html = res.get_data(as_text=True)
    assert res.status_code == 200 and res.headers["Cache-Control"] == "no-store"
    assert "C02" in html and "C09" in html and "to resolve before publishing" in html and "Content admin" in html
    assert "student@example.com" not in html
    assert client.get("/preview/c02/c02-l1").status_code == 200        # 관리자는 검토용 미리보기 가능
    with app.app_context():
        storage.revoke_admin(_uid(app, ADMIN))
        assert storage.get_admin_grant(_uid(app, ADMIN)) is None
    assert client.get("/admin/content").status_code == 404


def test_no_admin_route_exposes_individual_students():
    import app as app_module
    admin_rules = [r.rule for r in app_module.app.url_map.iter_rules() if r.rule.startswith("/admin")]
    assert admin_rules and all("user" not in r and "student" not in r and "attempt" not in r for r in admin_rules)


def test_admin_grant_cli_requires_explicit_verification(app, client, monkeypatch):
    signup(client, email="future-admin@example.com")
    runner = app.test_cli_runner()
    base = ["admin-grant", "future-admin@example.com", "--operator", "운영자 박", "--verification", "대면으로 계정 주인 확인함"]
    assert runner.invoke(args=["admin-grant", "nobody@example.com", "--operator", "운영자", "--verification", "대면 확인 완료함"],
                         input="nobody@example.com\n").exit_code != 0
    res = runner.invoke(args=base, input="wrong@example.com\n")
    assert res.exit_code != 0 and "Nothing was changed." in res.output
    res = runner.invoke(args=base[:-1] + ["짧음"], input="future-admin@example.com\n")
    assert res.exit_code != 0
    with app.app_context():
        assert storage.get_admin_grant(_uid(app, "future-admin@example.com")) is None
    monkeypatch.setenv("RENDER", "1")
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    res = runner.invoke(args=base, input="future-admin@example.com\n")
    assert res.exit_code != 0 and "ECONOVA_ALLOW_ADMIN_BOOTSTRAP" in res.output
    monkeypatch.delenv("RENDER")
    res = runner.invoke(args=base, input="future-admin@example.com\n")
    assert res.exit_code == 0, res.output
    with app.app_context():
        grant = storage.get_admin_grant(_uid(app, "future-admin@example.com"))
    assert grant["granted_by"] == "운영자 박" and "대면" in grant["verification"]
    assert "future-admin@example.com" in runner.invoke(args=["admin-list"]).output
    assert runner.invoke(args=["admin-revoke", "future-admin@example.com"]).exit_code == 0


def test_admin_sees_answer_keys_only_in_admin_pages(app, client):
    _make_admin(app, client)
    html = client.get("/admin/content/assessment/dev-f1-l1-quiz").get_data(as_text=True)
    assert "← Correct answer" in html and "Admin-only page." in html
    html = client.get("/admin/content/assessment/c02-l1-quiz").get_data(as_text=True)
    assert "No answer key" in html and "← Correct answer" not in html            # 테스트에는 실제 키가 없다
    _switch(client, "plain@example.com")
    assert client.get("/admin/content/assessment/dev-f1-l1-quiz").status_code == 404


# ------------------------------------------------------------- 콘텐츠 검토 흐름
DRAFT_TOPIC = "dev-f1/draft-topic-hidden"


def _review(c, decision, digest=None, comment="내용을 직접 확인했습니다.", confirm=True, target=("debate", DRAFT_TOPIC)):
    if digest is None:
        digest = ac.find_target(*target, include_fixtures=True).digest
    data = {"csrf_token": CSRF, "decision": decision, "comment": comment, "content_digest": digest}
    if confirm:
        data["confirm_reviewed"] = "1"
    return c.post(f"/admin/content/{target[0]}/{target[1]}/review", data=data)


def _file_hash(rel):
    import hashlib
    return hashlib.sha256(open(os.path.join(content.CONTENT_DIR, rel), "rb").read()).hexdigest()


def test_review_transitions_are_audited_and_never_touch_files(app, client):
    _make_admin(app, client)
    before = _file_hash("dev_fixtures/debates/dev-f1.json")
    page = f"/admin/content/debate/{DRAFT_TOPIC}"
    assert "Start review" in client.get(page).get_data(as_text=True)
    _review(client, "approve")                                              # 초안에서 바로 승인 불가
    with app.app_context():
        assert storage.list_content_reviews("debate", DRAFT_TOPIC) == []
    assert _review(client, "start_review").status_code == 303
    _review(client, "approve", confirm=False)                               # 확인란 없이 승인 불가
    _review(client, "approve", comment="좋음")                              # 의견 5자 미만
    _review(client, "approve", digest="0" * 64)                             # 화면을 연 뒤 내용이 바뀐 경우
    with app.app_context():
        assert [r["decision"] for r in storage.list_content_reviews("debate", DRAFT_TOPIC)] == ["start_review"]
    assert _review(client, "approve").status_code == 303
    with app.app_context():
        records = storage.list_content_reviews("debate", DRAFT_TOPIC)
        admin_id = str(_uid(app, ADMIN))
    assert [(r["decision"], r["from_state"], r["to_state"]) for r in records] == \
        [("start_review", "draft", "in_review"), ("approve", "in_review", "approved")]
    target = ac.find_target("debate", DRAFT_TOPIC, include_fixtures=True)
    assert all(r["content_digest"] == target.digest and r["reviewer_user_id"] == admin_id and r["reviewer_name"] == "관리자 김"
               and r["content_version"] == "1" and r["created_at"] for r in records)
    assert _file_hash("dev_fixtures/debates/dev-f1.json") == before          # 정본 파일은 그대로
    _enroll(client, "dev-f1")
    assert client.get("/discuss/dev-f1/draft-topic-hidden").status_code == 404   # 학생 화면에서도 여전히 초안
    html = client.get("/admin/content/release").get_data(as_text=True)
    assert DRAFT_TOPIC in html and "#" + records[-1]["id"] in html
    plan = json.loads(client.get("/admin/content/release?download=1").get_data(as_text=True))
    assert [i["target_id"] for i in plan["items"]] == [DRAFT_TOPIC] and plan["items"][0]["content_digest"] == target.digest


def test_ai_named_reviewer_cannot_approve(app, client):
    _make_admin(app, client, email="bot@example.test", name="Claude AI 검토")
    _review(client, "start_review")
    with app.app_context():
        assert storage.list_content_reviews("debate", DRAFT_TOPIC) == []


def test_review_state_ignores_records_for_old_content():
    target = ac.find_target("debate", DRAFT_TOPIC, include_fixtures=True)
    old = {"content_digest": "f" * 64, "to_state": "approved", "decision": "approve", "id": "1", "created_at": None}
    state = ac.review_state(target, [old])
    assert state["state"] == "draft" and state["source"] == "file" and state["stale"] == 1
    assert ac.release_plan([target], {target.key: [old]})["items"] == []


@pytest.fixture
def content_copy(tmp_path, monkeypatch):
    """정본 콘텐츠의 임시 복사본 (릴리스 반영 시험용 — 실제 content/ 는 건드리지 않는다)."""
    copy_dir = tmp_path / "content"
    shutil.copytree(content.CONTENT_DIR, copy_dir)
    monkeypatch.setattr(content, "CONTENT_DIR", str(copy_dir))
    content.load_catalog.cache_clear()
    yield copy_dir
    content.load_catalog.cache_clear()


def test_release_apply_binds_approval_to_digest(app, client, content_copy, tmp_path):
    _make_admin(app, client)
    _review(client, "start_review")
    _review(client, "approve")
    plan = json.loads(client.get("/admin/content/release?download=1").get_data(as_text=True))
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    runner = app.test_cli_runner()
    res = runner.invoke(args=["content-release-apply", str(plan_file), "--dry-run"])
    assert res.exit_code == 0 and "Verified (dry run; files unchanged)" in res.output
    assert json.loads((content_copy / "dev_fixtures/debates/dev-f1.json").read_text(encoding="utf-8"))["topics"][2]["review"]["status"] == "draft"
    res = runner.invoke(args=["content-release-apply", str(plan_file)])
    assert res.exit_code == 0 and "Applied" in res.output, res.output
    topic = json.loads((content_copy / "dev_fixtures/debates/dev-f1.json").read_text(encoding="utf-8"))["topics"][2]
    assert topic["review"]["status"] == "approved" and topic["review"]["reviewer"]["role"] == "admin"
    assert topic["review"]["reviewer"]["review_id"] == plan["items"][0]["review_id"]
    cat = content.load_catalog(True)
    from econova import debates
    assert "draft-topic-hidden" in [t["id"] for t in debates.topics_for(cat.course("dev-f1"), cat.sources)]
    # 승인 뒤 내용을 고치면 검사기가 거부한다 (지문 불일치)
    data = json.loads((content_copy / "dev_fixtures/debates/dev-f1.json").read_text(encoding="utf-8"))
    data["topics"][2]["policy_question"] = "A changed question"
    (content_copy / "dev_fixtures/debates/dev-f1.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(content.ContentError, match="fingerprint mismatch"):
        debates.topics_for(cat.course("dev-f1"), cat.sources)
    # 다시 반영하려 해도 지문이 달라 건너뛴다
    assert "Skipped: content changed after approval (fingerprint mismatch)" in runner.invoke(args=["content-release-apply", str(plan_file)]).output


def test_release_apply_refuses_forged_or_production(app, client, content_copy, tmp_path, monkeypatch):
    target = ac.find_target("debate", DRAFT_TOPIC, include_fixtures=True)
    forged = {"schema_version": 1, "kind": "econova_release_plan", "items": [
        {"target_type": "debate", "target_id": DRAFT_TOPIC, "course_id": "dev-f1", "file": target.file, "content_version": "1",
         "content_digest": target.digest, "review_id": "999", "reviewer_name": "누군가", "comment": "", "approved_at": "2026-11-03"}]}
    plan_file = tmp_path / "forged.json"
    plan_file.write_text(json.dumps(forged), encoding="utf-8")
    runner = app.test_cli_runner()
    assert "Skipped: No review record in this DB" in runner.invoke(args=["content-release-apply", str(plan_file)]).output
    assert json.loads((content_copy / target.file).read_text(encoding="utf-8"))["topics"][2]["review"]["status"] == "draft"
    monkeypatch.setenv("RENDER", "1")
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    assert runner.invoke(args=["content-release-apply", str(plan_file)]).exit_code != 0


def test_admin_review_schema_rules():
    base = {"status": "approved", "approved_at": "2026-11-10", "history": [{"status": "approved", "at": "2026-11-10", "by": "관리자 김"}]}
    digest = "a" * 64
    with pytest.raises(content.ContentError, match="review_id"):
        lesson_content._parse_review({**base, "reviewer": {"name": "관리자 김", "role": "admin"}}, "t", False, digest)
    with pytest.raises(content.ContentError, match="fingerprint mismatch"):
        lesson_content._parse_review({**base, "reviewer": {"name": "관리자 김", "role": "admin", "review_id": "3"},
                                      "content_digest": "b" * 64}, "t", False, digest)
    ok = lesson_content._parse_review({**base, "reviewer": {"name": "관리자 김", "role": "admin", "review_id": "3"},
                                       "content_digest": digest}, "t", False, digest)
    assert ok["status"] == "approved"
    assert lesson_content._parse_review({**base, "reviewer": {"name": "김선생", "role": "teacher"}}, "t", False, digest)  # 예전 기록 호환
    with pytest.raises(content.ContentError):
        lesson_content._parse_review({**base, "reviewer": {"name": "x", "role": "fixture"}}, "t", False, digest)
    with pytest.raises(content.ContentError):
        lesson_content._parse_review({**base, "reviewer": {"name": "GPT 검토", "role": "admin", "review_id": "1"},
                                      "content_digest": digest}, "t", False, digest)


def test_overview_explains_why_courses_are_not_ready():
    rows = {r["id"]: r for r in ac.overview()}
    assert set(rows) == {f"c0{i}" for i in range(1, 10)} and all(r["status"] == "coming_soon" for r in rows.values())
    assert any("learning materials are not approved" in b for b in rows["c02"]["blockers"])
    assert any("no answer key, so the assessment cannot be opened" in b for b in rows["c02"]["blockers"])
    assert any("passing criteria are not approved" in b for b in rows["c02"]["blockers"])
    assert any("The capstone project guide and rubric are not approved." in b for b in rows["c09"]["blockers"])
    assert not any(r["error"] for r in rows.values())


def test_assessment_and_capstone_digests_ignore_only_policy_status():
    data = {"id": "x", "version": 1, "passing": {"score_ratio": 0.7, "status": "proposed"}, "review": {"status": "draft"}}
    approved = copy.deepcopy(data)
    approved["passing"]["status"] = "approved"
    assert lesson_content.assessment_digest(data) == lesson_content.assessment_digest(approved)
    changed = copy.deepcopy(data)
    changed["passing"]["score_ratio"] = 0.6
    assert lesson_content.assessment_digest(changed) != lesson_content.assessment_digest(data)
    d = json.load(open(os.path.join(ROOT, "content", "capstone", "c09.json"), encoding="utf-8"))
    d2 = copy.deepcopy(d)
    d2["rubric"]["status"] = "approved"
    assert cap.capstone_digest(d) == cap.capstone_digest(d2)
    d2["rubric"]["criteria"][0]["weight"] += 1
    assert cap.capstone_digest(d) != cap.capstone_digest(d2)


# ------------------------------------------------------------- 개인 학습 보고서
def test_report_is_accurate_and_private(app, client):
    signup(client)
    login(client)
    set_csrf(client)
    html = client.get("/report").get_data(as_text=True)
    assert "My learning report" in html and "You aren't enrolled in any courses yet." in html
    assert "Ask AI to explain these recommendations" not in html
    _enroll(client, "dev-f1")
    _post(client, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    quiz = content.get_catalog().course("dev-f1").lesson("dev-f1-l1").quiz_assessment
    take(client, "/learn/dev-f1/dev-f1-l1/quiz", quiz, correct=False)
    take(client, "/learn/dev-f1/dev-f1-l1/quiz", quiz, correct=True)
    _post(client, "/learn/dev-f1/dev-f1-l2/material-reviewed")
    from econova import report
    with app.app_context():
        r = report.build(_uid(app), content.get_catalog())
        again = report.build(_uid(app), content.get_catalog())
    assert r["totals"] == {"courses": 1, "completed_courses": 0, "lessons_completed": 1, "lessons_in_progress": 1,
                           "lessons_total": 3}
    [a] = r["assessments"]
    assert (a["first"], a["latest"], a["best"], a["change"]) == (0, 100, 100, 100) and len(a["points"]) == 2
    [m] = r["analysis"]["measured"]
    assert m["correct"] == 2 and m["total"] == 2 and m["provisional"]      # 가장 최근 응시 기준, 2문항 → 잠정
    assert r["assessments"] == again["assessments"] and r["analysis"] == again["analysis"]
    kinds = [t[1] for t in r["timeline"]]
    assert kinds.count("Submitted lesson quiz") == 2 and kinds.count("Reviewed learning materials") == 2 and "Enrolled" in kinds
    html = client.get("/report").get_data(as_text=True)
    assert "First 0% · Best 100% · Latest 100% · Change +100 percentage points" in html and 'role="img"' in html
    assert "Provisional" in html
    assert '"mastery"' in html and "%</strong>" not in html
    _switch(client, "other@example.com")
    html = client.get("/report").get_data(as_text=True)
    assert "You aren't enrolled in any courses yet." in html and quiz.title not in html


# ------------------------------------------------------------- SDG 캡스톤
def _cap_form(defn, **override):
    values = {}
    for f in defn.fields:
        values[f["id"]] = "7" if f["type"] == "sdg" else "가" * max(f["min_chars"], 5)
    values.update(override)
    return values


def test_capstone_unpublished_and_access_rules(app, client):
    signup(client)
    login(client)
    set_csrf(client)
    assert client.get("/capstone/c09").status_code == 403                    # c09 는 공개 전
    assert client.post("/capstone/c09/edit", data={"csrf_token": CSRF}).status_code == 403
    assert client.get("/capstone/dev-f1").status_code == 404                 # 캡스톤 없는 강좌
    assert client.get("/capstone/dev-f3").status_code == 303                 # 수강 전
    course = content.load_catalog(False).course("c09")
    assert course.capstone.review_status == "draft" and course.capstone.rubric["status"] == "provisional"
    assert cap.completion_policy(course) is None


def test_capstone_draft_edit_versions_and_ownership(app, client):
    signup(client)
    login(client)
    set_csrf(client)
    _enroll(client, "dev-f3")
    defn = content.get_catalog().course("dev-f3").capstone
    page = "/capstone/dev-f3/edit"
    assert "Write your project" in client.get(page).get_data(as_text=True)
    res = client.post(page, data={"csrf_token": CSRF, "sdg": "7", "problem": "Energy access problem"})
    assert res.status_code == 303
    client.post(page, data={"csrf_token": CSRF, "sdg": "7", "problem": "Energy access problem"})   # 바뀐 것 없음
    res = client.post(page, data={"csrf_token": CSRF, "sdg": "99", "problem": "x" * 3000})
    html = res.get_data(as_text=True)
    assert res.status_code == 200 and "Please choose an SDG from 1 to 17." in html and "Please shorten this to 2000 characters or fewer" in html and "x" * 50 in html   # 입력은 남아 있음
    client.post(page, data={"csrf_token": CSRF, "sdg": "7", "problem": "Energy access problem, described more specifically"})
    with app.app_context():
        uid = _uid(app)
        versions = storage.list_capstone_versions(uid, "dev-f3")
        project = storage.get_capstone(uid, "dev-f3")
    assert [v["version"] for v in versions] == [1, 2] and versions[0]["sections"]["problem"] == "Energy access problem"
    assert project["status"] == "draft" and project["current_version"] == 2
    assert "Energy access problem" in client.get("/capstone/dev-f3/versions/1").get_data(as_text=True)
    _switch(client, "other@example.com")
    _enroll(client, "dev-f3")
    assert client.get("/capstone/dev-f3/versions/1").status_code == 404
    assert "Energy access" not in client.get("/capstone/dev-f3/edit").get_data(as_text=True)


def test_capstone_submission_self_assessment_and_completion(app, client):
    signup(client)
    login(client)
    set_csrf(client)
    _enroll(client, "dev-f3")
    course = content.get_catalog().course("dev-f3")
    defn = course.capstone
    home = "/capstone/dev-f3"
    client.post(home + "/edit", data={"csrf_token": CSRF, **_cap_form(defn, reflection="")})
    client.post(home + "/submit", data={"csrf_token": CSRF})                  # 필수 칸 부족
    with app.app_context():
        assert storage.get_capstone(_uid(app), "dev-f3")["status"] == "draft"
    client.post(home + "/edit", data={"csrf_token": CSRF, **_cap_form(defn)})
    assert client.post(home + "/submit", data={"csrf_token": CSRF}).headers["Location"].endswith("/self-assessment")
    partial = {f"score_{c['id']}": "3" for c in defn.rubric["criteria"][:3]}
    res = client.post(home + "/self-assessment", data={"csrf_token": CSRF, "version": "2", **partial})
    assert res.status_code == 200 and "Please choose a level" in res.get_data(as_text=True)
    scores = {f"score_{c['id']}": "2" if i == 0 else "4" for i, c in enumerate(defn.rubric["criteria"])}
    assert client.post(home + "/self-assessment", data={"csrf_token": CSRF, "version": "1", **scores}).status_code == 303
    with app.app_context():
        assert storage.list_capstone_self_assessments(_uid(app), "dev-f3") == []   # 옛 버전 번호로는 저장 안 됨
    client.post(home + "/self-assessment", data={"csrf_token": CSRF, "version": "2", **scores})
    client.post(home + "/submit", data={"csrf_token": CSRF})
    with app.app_context():
        uid = _uid(app)
        project = storage.get_capstone(uid, "dev-f3")
        assert project["status"] == "submitted" and project["submitted_version"] == 3
        assert storage.get_enrollment(uid, "dev-f3")["status"] == "active"   # 레슨을 아직 안 끝냄
    html = client.get(home).get_data(as_text=True)
    assert "○ All lessons completed" in html and "✔ A version with all required fields submitted" in html
    assert "It is not an official academic achievement or certification" in html
    for lesson in course.lessons:
        _post(client, f"/learn/dev-f3/{lesson.id}/material-reviewed")
    html = client.get(home).get_data(as_text=True)                            # 다시 열면 결정적 규칙으로 수료 기록
    with app.app_context():
        enrollment = storage.get_enrollment(uid, "dev-f3")
    assert enrollment["status"] == "completed" and enrollment["completion_policy"] == "dev_capstone"
    assert enrollment["completion_attempt_id"] == "capstone-v3" and "(development test)" in html
    s = cap.weighted_summary(defn, {c["id"]: {"level": 2 if i == 0 else 4} for i, c in enumerate(defn.rubric["criteria"])})
    assert s["average_level"] == 3.7 and s["improve"] == [defn.rubric["criteria"][0]["name"]] and s["complete"]


def test_real_capstone_completion_needs_human_approved_rubric():
    course = content.load_catalog(False).course("c09")
    published = dataclasses.replace(course, status="published",
                                    capstone=dataclasses.replace(course.capstone, review={**course.capstone.review,
                                                                                         "status": "approved"}))
    assert cap.completion_policy(published) is None                          # 루브릭이 아직 provisional
    rubric_ok = dataclasses.replace(published, capstone=dataclasses.replace(
        published.capstone, rubric={**published.capstone.rubric, "status": "approved"}))
    assert cap.completion_policy(rubric_ok) == "capstone_self_directed"


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["rubric"]["criteria"][0].update(weight=50), "weights must add up to 100"),
    (lambda d: d["rubric"].update(status="approved"), "rubric cannot be approved on its own"),
    (lambda d: d["steps"][0].update(lesson_id="c01-l1"), "lesson_id"),
    (lambda d: d["steps"].pop(), "reflection"),
    (lambda d: d["rubric"]["criteria"][0]["descriptors"].pop("4"), "descriptors"),
])
def test_capstone_definition_validation(mutate, message):
    d = json.load(open(os.path.join(ROOT, "content", "capstone", "c09.json"), encoding="utf-8"))
    mutate(d)
    with pytest.raises(content.ContentError, match=message):
        cap.parse_definition(d, "c09", ("c09-l1", "c09-l2", "c09-l3"))


def test_capstone_ai_coach_is_optional_and_isolated(app, client, monkeypatch):
    signup(client)
    login(client)
    set_csrf(client)
    _enroll(client, "dev-f3")
    defn = content.get_catalog().course("dev-f3").capstone
    client.post("/capstone/dev-f3/edit", data={"csrf_token": CSRF, **_cap_form(defn)})
    client.post("/capstone/dev-f3/feedback", data={"csrf_token": CSRF})
    assert "AI features are turned off right now." in client.get("/capstone/dev-f3").get_data(as_text=True)
    from econova.ai import client as ai_client
    monkeypatch.setenv("ECONOVA_AI_PROVIDER", "mock")
    mock = ai_client.MockProvider()
    monkeypatch.setattr(ai_client, "get_provider", lambda s=None: mock)
    assert client.post("/capstone/dev-f3/feedback", data={"csrf_token": CSRF, "step": "problem"}).status_code == 303
    html = client.get("/capstone/dev-f3").get_data(as_text=True)
    assert "AI-generated" in html and "Questions to think about" in html
    req = mock.calls[-1]
    assert f"<{STUDENT_TAG}>" in req.messages[-1]["content"] and "student@example.com" not in json.dumps(req.messages, ensure_ascii=False)
    mock.responder = lambda r: {"strengths": ["Nice work https://example.com/fake"], "questions": [], "missing_perspectives": [],
                                "assumptions_to_check": [], "structure_suggestions": [], "limitations": ""}
    client.post("/capstone/dev-f3/feedback", data={"csrf_token": CSRF, "step": "sdg"})
    with app.app_context():
        uid = _uid(app)
        fb = storage.list_capstone_feedback(uid, "dev-f3")
        assert len(fb) == 1 and storage.get_enrollment(uid, "dev-f3")["status"] == "active"   # 링크 답은 버림, 수료와 무관
    assert client.post("/capstone/dev-f3/feedback", data={"csrf_token": CSRF, "step": "nope"}).status_code == 400


def test_lesson_and_course_pages_link_capstone(client):
    signup(client)
    login(client)
    set_csrf(client)
    _enroll(client, "dev-f3")
    html = client.get("/learn/dev-f3/dev-f3-l2").get_data(as_text=True)
    assert "Capstone project steps linked to this lesson" in html and "5. Incentives and trade-offs" in html
    assert "View Capstone project" in client.get("/courses/dev-f3").get_data(as_text=True)
    assert "The Capstone project opens once its guide and self-assessment criteria have been reviewed." in client.get("/courses/c09").get_data(as_text=True)


# ------------------------------------------------------------- 보안 설정
def test_production_secret_key_and_cookie_flags(monkeypatch):
    monkeypatch.setenv("RENDER", "1")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(config.ConfigError, match="SECRET_KEY"):
        config.secret_key()
    monkeypatch.setenv("SECRET_KEY", config.DEFAULT_SECRET_KEY)
    with pytest.raises(config.ConfigError):
        config.secret_key()
    monkeypatch.setenv("SECRET_KEY", "z" * 40)
    assert config.secret_key() == "z" * 40
    import app as app_module
    assert app_module.app.config["SESSION_COOKIE_HTTPONLY"] and app_module.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_login_rate_limit(app, client):
    signup(client)
    for _ in range(10):
        assert login(client, password="wrong-password").status_code == 401
    assert login(client).status_code == 429                                  # 맞는 비밀번호도 잠시 막힘
    assert login(client, email="someone-else@example.com", password="x").status_code == 401   # 다른 이메일은 영향 없음
    # Phase 8B-1: 15분 구간 카운터 — 30분 뒤에는 다시 로그인할 수 있다 (자세한 규칙은 tests/test_phase8b1.py)
    import datetime as _dt
    later = storage._utcnow() + _dt.timedelta(minutes=31)
    real_now = storage._utcnow
    storage._utcnow = lambda: later
    try:
        assert login(client).status_code == 302
    finally:
        storage._utcnow = real_now


# ------------------------------------------------------------- 저장소
def test_migration_7_on_phase6_database(sqlite_app, tmp_path, monkeypatch):
    monkeypatch.setitem(sqlite_app.config, "DATABASE", str(tmp_path / "phase6.db"))
    full = storage.SQLITE_MIGRATIONS
    with sqlite_app.app_context():
        storage.SQLITE_MIGRATIONS = full[:6]
        try:
            storage.init_db()
            storage.create_user("old@example.com", "Old", "h")
            uid = storage.get_user_by_email("old@example.com")["id"]
            storage.enroll_course(uid, "dev-f1", "beginner", 1)
            conv = storage.create_ai_conversation(uid, "tutor", course_id="dev-f1", lesson_id="dev-f1-l1")
        finally:
            storage.SQLITE_MIGRATIONS = full
        assert storage.migrate_sqlite() == [7, 8, 9]
        assert storage.get_enrollment(uid, "dev-f1") is not None and storage.get_ai_conversation(uid, conv) is not None
        assert roles.role_of(storage.get_user_by_id(uid)) == "student"
        with pytest.raises(sqlite3.IntegrityError):
            storage.get_db().execute("INSERT INTO econ_content_reviews (target_type, target_id, content_version, content_digest,"
                                     " decision, from_state, to_state, reviewer_user_id, reviewer_name, created_at)"
                                     " VALUES ('x','y','1','d','auto_approve','draft','approved','1','n','2026-11-03 00:00:00')")
        with pytest.raises(ValueError):
            storage.add_content_review({"decision": "auto_approve"})


def test_firestore_phase7_layout(firestore_app, fake_fs):
    with firestore_app.app_context():
        storage.create_user("a@example.com", "A", "h")
        storage.grant_admin("a@example.com", "운영자", "테스트 확인 방법")
        assert storage.get_admin_grant("a@example.com") and storage.get_user_by_email("a@example.com")["role"] == "admin"
        rid = storage.add_content_review({"target_type": "debate", "target_id": "t", "content_version": "1",
                                          "content_digest": "d" * 64, "decision": "start_review", "from_state": "draft",
                                          "to_state": "in_review", "reviewer_user_id": "a@example.com", "reviewer_name": "A"})
        assert storage.get_content_review(rid)["decision"] == "start_review"
        v1 = storage.save_capstone_version("a@example.com", "dev-f3", {"sdg": "7"}, 1)
        v2 = storage.save_capstone_version("a@example.com", "dev-f3", {"sdg": "7"}, 1, kind="submitted")
        storage.save_capstone_self_assessment("a@example.com", "dev-f3", v2, 1, {"concepts": {"level": 3, "note": ""}})
        assert (v1, v2) == (1, 2) and storage.get_capstone("a@example.com", "dev-f3")["status"] == "submitted"
        assert storage.list_capstone_self_assessments("a@example.com", "dev-f3")[0]["scores"]["concepts"]["level"] == 3
        assert storage.list_capstone_versions("b@example.com", "dev-f3") == []
        key = storage.login_key("a@example.com")
        storage.record_login_failure(key, storage._utcnow(), storage._utcnow() - datetime.timedelta(minutes=15))
        assert storage.count_login_failures(key, storage._utcnow() - datetime.timedelta(minutes=15)) == 1
    paths = set(fake_fs.docs)
    assert ("econ_admin_grants", "a@example.com") in paths and ("econ_content_reviews", rid) in paths
    assert ("users", "a@example.com", "econ_capstone", "dev-f3", "versions", "2") in paths
