"""Publication rehearsal with the REAL curriculum (c01 exam course, c09 capstone course) on a throwaway copy.

Nothing here touches content/, the review database or any real approval: a synthetic admin approves items in a
temporary database, a signed release plan is applied to a temporary content copy, and c01/c09 are marked published
only in that copy. Then real student journeys run against real lessons and the real private answer keys.
Needs the private keys (ECONOVA_REAL_PRIVATE_CONTENT_DIR); skipped otherwise.
"""
import json
import os
import re

import pytest

from econova import admin_content as ac
from econova import content, storage
from tests.conftest import CSRF, login, set_csrf, signup
from tests.test_econova_routes import _enroll, _post, take
from tests.test_phase7 import content_copy  # noqa: F401 (fixture)

REAL_DIR = os.environ.get("ECONOVA_REAL_PRIVATE_CONTENT_DIR")
pytestmark = pytest.mark.skipif(not REAL_DIR, reason="Skipped: no real answer key folder (ECONOVA_REAL_PRIVATE_CONTENT_DIR)")
HANGUL = re.compile(r"[가-힣]")


@pytest.fixture
def rehearsal(sqlite_app, content_copy, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setenv("ECONOVA_PRIVATE_CONTENT_DIR", REAL_DIR)
    monkeypatch.setenv("ECONOVA_AI_PROVIDER", "mock")
    monkeypatch.setenv("ECONOVA_AI_FEEDBACK", "off")
    monkeypatch.setenv("ECONOVA_RELEASE_SIGNING_KEY", "rehearsal-signing-key-" + "x" * 24)
    monkeypatch.delenv("ECONOVA_DEV_FIXTURES", raising=False)
    monkeypatch.delenv("ECONOVA_CONTENT_PREVIEW", raising=False)
    app = sqlite_app
    admin = app.test_client()
    signup(admin, email="rehearsal-admin@example.test", name="Rehearsal Admin")
    with app.app_context():
        storage.grant_admin(storage.get_user_by_email("rehearsal-admin@example.test")["id"], "Rehearsal",
                            "Synthetic admin in a throwaway database for a release rehearsal")
    login(admin, email="rehearsal-admin@example.test")
    set_csrf(admin)

    def approve(t):
        page = admin.get(f"/admin/content/{t.type}/{t.id}")
        assert page.status_code == 200, (t.type, t.id)
        digest = re.search(r'name="content_digest" value="([^"]+)"', page.get_data(as_text=True)).group(1)
        for decision in ("start_review", "approve"):
            admin.post(f"/admin/content/{t.type}/{t.id}/review", data={
                "csrf_token": CSRF, "content_digest": digest, "decision": decision,
                "comment": "Release rehearsal on a throwaway copy." if decision == "approve" else "",
                "confirm_reviewed": "1"})

    for cid in ("c01", "c09"):
        targets = ac.course_targets(f"courses/{cid}.json")
        for t in [t for t in targets if t.type != "passing"] + [t for t in targets if t.type == "passing"]:
            approve(t)

    plan = json.loads(admin.get("/admin/content/release?download=1").get_data(as_text=True))
    assert plan.get("signature") and plan["items"], "signed plan with items"
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    res = app.test_cli_runner().invoke(args=["content-release-apply", str(plan_file)])
    assert res.exit_code == 0 and "Applied" in res.output, res.output

    for cid in ("c01", "c09"):   # publishing is a separate human decision; done here only in the throwaway copy
        path = content_copy / "courses" / f"{cid}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "published"
        for lesson in data["lessons"]:
            lesson["status"] = "published"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    content.load_catalog.cache_clear()
    cat = content.get_catalog()
    assert cat.course("c01").published and cat.course("c09").published and cat.course("c02").published   # competition version: all courses open
    return app


def _student(app, email):
    client = app.test_client()
    signup(client, email=email, name="Rehearsal Student")
    login(client, email=email)
    set_csrf(client)
    return client


def _page(client, url, status=200):
    res = client.get(url)
    html = res.get_data(as_text=True)
    assert res.status_code == status, (url, res.status_code)
    assert not HANGUL.search(html), url
    return html


def test_real_c01_journey_with_real_keys(rehearsal):
    app = rehearsal
    s = _student(app, "student1@example.test")
    course = content.get_catalog().course("c01")
    catalog = _page(s, "/courses")
    from econova import config
    assert not config.dev_fixtures_enabled(), "fixtures must be off in the rehearsal"
    i = catalog.find("Dev Test Course")
    assert i == -1 and "Economics &amp; Choices" in catalog, catalog[max(0, i - 300):i + 100]
    assert _enroll(s, "c01", "advanced").status_code in (302, 303)
    assert _enroll(s, "c02").status_code in (302, 303)
    with app.app_context():
        uid = storage.get_user_by_email("student1@example.test")["id"]
        # competition version: every course is open, so c02 enrollment succeeds too
        assert storage.get_enrollment(uid, "c02") is not None and storage.get_enrollment(uid, "c01")["selected_difficulty"] == "advanced"
    for lesson in course.lessons:
        for level in ("beginner", "intermediate", "advanced"):
            html = _page(s, f"/learn/c01/{lesson.id}?level={level}")
            assert lesson.content.levels[level]["summary"].split(".")[0] in html
        _post(s, f"/learn/c01/{lesson.id}/material-reviewed")
        quiz_html = _page(s, f"/learn/c01/{lesson.id}/quiz")
        for q in lesson.quiz_assessment.questions:                      # keys and explanations never reach the take page
            assert q["explanation"] not in quiz_html
        _page(s, take(s, f"/learn/c01/{lesson.id}/quiz", lesson.quiz_assessment, correct=True))
    _page(s, "/dashboard")
    # final: two failed attempts (answers stay hidden), then a pass on the third and last attempt
    for _ in range(2):
        result = _page(s, take(s, "/courses/c01/final", course.final, correct=False))
        assert "shown only after you pass or use all your attempts" in result
        assert not any(q["explanation"] in result for q in course.final.questions)
    _page(s, take(s, "/courses/c01/final", course.final, correct=True))
    with app.app_context():
        enrollment = storage.get_enrollment(uid, "c01")
    assert enrollment["status"] == "completed"
    assert "Course completed" in _page(s, "/courses/c01/completion")
    assert "Economics &amp; Choices" in _page(s, "/report")
    # tutor (mock), lab and debate pages work for a published course
    lesson = course.lessons[0]
    lhtml = s.get(f"/learn/c01/{lesson.id}").get_data(as_text=True)
    conv = re.search(r'data-conversation="([^"]*)"', lhtml)
    assert conv, "the AI Tutor panel is shown for approved, published material"
    r = s.post("/api/tutor", data={"csrf_token": CSRF, "course_id": "c01", "lesson_id": lesson.id,
                                   "message": "What is opportunity cost?", "conversation_id": conv.group(1)})
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] and "Mock" in json.dumps(body)
    _page(s, "/lab/supply-demand")
    _page(s, "/discuss")


def test_attempt_limit_and_numeric_rounding_on_real_c01(rehearsal):
    app = rehearsal
    s = _student(app, "student2@example.test")
    course = content.get_catalog().course("c01")
    _enroll(s, "c01")
    for lesson in course.lessons:
        _post(s, f"/learn/c01/{lesson.id}/material-reviewed")
        take(s, f"/learn/c01/{lesson.id}/quiz", lesson.quiz_assessment, correct=True)
    for _ in range(3):
        take(s, "/courses/c01/final", course.final, correct=False)
    page = s.get("/courses/c01/final")
    assert page.status_code in (302, 303, 403) or "used all your attempts" in page.get_data(as_text=True)
    # numeric scoring through the real key: "60.0" and "60" are equal, "60%" is not a number
    from econova import grading
    q5 = next(q for q in course.lessons[0].quiz_assessment.questions if q["id"] == "c01-l1-q5")
    assert grading.is_correct(q5, "60") and grading.is_correct(q5, "60.0") and not grading.is_correct(q5, "60%")


def test_real_c09_capstone_journey(rehearsal):
    app = rehearsal
    s = _student(app, "capstone@example.test")
    course = content.get_catalog().course("c09")
    defn = course.capstone
    assert course.final is None
    _enroll(s, "c09")
    home = "/capstone/c09"
    _page(s, home)
    values = {f["id"]: ("6" if f["type"] == "sdg" else ("In District K, many students miss school because water points break and are not repaired. " * 6)[: max(f["min_chars"] + 20, 60)])
              for f in defn.fields}
    s.post(home + "/edit", data={"csrf_token": CSRF, **values})
    res = s.post(home + "/submit", data={"csrf_token": CSRF})
    assert res.headers["Location"].endswith("/self-assessment")
    _page(s, home + "/self-assessment")
    with app.app_context():
        uid = storage.get_user_by_email("capstone@example.test")["id"]
        version = storage.get_capstone(uid, "c09")["current_version"]
    scores = {f"score_{c['id']}": "3" for c in defn.rubric["criteria"]}
    assert s.post(home + "/self-assessment", data={"csrf_token": CSRF, "version": str(version), **scores}).status_code == 303
    s.post(home + "/submit", data={"csrf_token": CSRF})
    for lesson in course.lessons:
        _page(s, f"/learn/c09/{lesson.id}")
        _post(s, f"/learn/c09/{lesson.id}/material-reviewed")
        if "quiz" in lesson.requirements:
            take(s, f"/learn/c09/{lesson.id}/quiz", lesson.quiz_assessment, correct=True)
    _page(s, home)
    with app.app_context():
        enrollment = storage.get_enrollment(uid, "c09")
    assert enrollment["status"] == "completed" and enrollment["completion_policy"] == "capstone_self_directed"
    _page(s, "/report")


def test_unpublished_courses_and_fixtures_stay_hidden_in_rehearsal(rehearsal):
    s = _student(rehearsal, "student3@example.test")
    for cid in ("c02", "c03", "c04", "c05", "c06", "c07", "c08"):
        course = content.get_catalog().course(cid)
        res = s.get(f"/learn/{cid}/{course.lessons[0].id}")
        assert res.status_code != 200 or course.lessons[0].content.levels["beginner"]["summary"] not in res.get_data(as_text=True)
    assert "Dev Test Course" not in _page(s, "/courses")
