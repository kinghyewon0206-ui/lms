"""End-to-end student journeys on isolated local data (dev fixtures, mock AI, no network, no real student data).

1. Exam course:     sign up → diagnostic → enroll → lesson → formative quiz → final → completion → learning report
2. Capstone course: enroll → three lessons → capstone draft → submit → rubric self-assessment → reflection → completion
3. Unpublished real courses (c01–c09) stay closed to students and open only through admin review / preview.
Every page a student sees along the way must be English.
"""
import re

import pytest

from econova import content, storage
from tests.conftest import CSRF, login, set_csrf, signup
from tests.test_econova_routes import _enroll, _post, _uid, take

HANGUL = re.compile(r"[가-힣]")
pytestmark = pytest.mark.usefixtures("fixtures_on")


@pytest.fixture(autouse=True)
def _mock_ai(monkeypatch):
    monkeypatch.setenv("ECONOVA_AI_PROVIDER", "mock")     # never a real provider in these journeys
    monkeypatch.setenv("ECONOVA_AI_FEEDBACK", "off")


def _english(client, url, status=200):
    res = client.get(url)
    html = res.get_data(as_text=True)
    assert res.status_code == status, (url, res.status_code)
    assert not HANGUL.search(html), url
    return html


def _student(client, email="learner@example.com"):
    signup(client, email=email, name="Jordan Learner")
    login(client, email=email)
    set_csrf(client)
    return client


def test_exam_course_journey_from_signup_to_learning_report(app, client):
    _student(client)
    html = _english(client, "/dashboard")
    assert "Jordan Learner" in html

    # diagnostic assessment (synthetic test diagnostic from conftest)
    from tests.test_diagnostic import TEST, _answers, _submit
    res = _submit(client, _answers(len(TEST["questions"])))
    assert res.status_code == 302 and "/diagnostic/attempts/" in res.headers["Location"]
    html = _english(client, res.headers["Location"])
    assert "Recommended level" in html

    # enroll in a published (dev) exam course and learn every lesson
    course = content.get_catalog().course("dev-f2")
    assert _enroll(client, "dev-f2").status_code in (302, 303)
    _english(client, "/courses/dev-f2")
    for lesson in course.lessons:
        html = _english(client, f"/learn/dev-f2/{lesson.id}")
        assert lesson.title in html
        _post(client, f"/learn/dev-f2/{lesson.id}/material-reviewed")
        if "quiz" in lesson.requirements:
            result = take(client, f"/learn/dev-f2/{lesson.id}/quiz", lesson.quiz_assessment)
            _english(client, result)

    # final assessment → completion
    result = take(client, "/courses/dev-f2/final", course.final, correct=True)
    _english(client, result)
    with app.app_context():
        enrollment = storage.get_enrollment(_uid(app, "learner@example.com"), "dev-f2")
    assert enrollment["status"] == "completed"
    assert "Course completed" in _english(client, "/courses/dev-f2/completion")

    # learning report summarizes the journey
    report = _english(client, "/report")
    assert course.title in report or course.title_ko in report
    assert "Diagnostic" in report or "diagnostic" in report


def _capstone_values(defn, reflection=True):
    values = {}
    for f in defn.fields:
        if f["type"] == "sdg":
            values[f["id"]] = "6"
        else:
            values[f["id"]] = ("In my town, unreliable water access keeps students out of school. " * 8)[: max(f["min_chars"] + 20, 40)]
    if not reflection:
        values["reflection"] = ""
    return values


def test_capstone_course_journey_lessons_submission_self_assessment_reflection(app, client):
    _student(client, "capstone@example.com")
    _enroll(client, "dev-f3")
    course = content.get_catalog().course("dev-f3")
    defn = course.capstone
    home = "/capstone/dev-f3"
    assert course.final is None                                  # capstone courses end without a final exam
    _english(client, home)

    # draft without reflection cannot be submitted
    client.post(home + "/edit", data={"csrf_token": CSRF, **_capstone_values(defn, reflection=False)})
    client.post(home + "/submit", data={"csrf_token": CSRF})
    with app.app_context():
        assert storage.get_capstone(_uid(app, "capstone@example.com"), "dev-f3")["status"] == "draft"

    # full draft with reflection → submit → rubric self-assessment on every criterion
    client.post(home + "/edit", data={"csrf_token": CSRF, **_capstone_values(defn)})
    res = client.post(home + "/submit", data={"csrf_token": CSRF})
    assert res.headers["Location"].endswith("/self-assessment")
    _english(client, home + "/self-assessment")
    with app.app_context():
        version = storage.get_capstone(_uid(app, "capstone@example.com"), "dev-f3")["current_version"]
    scores = {f"score_{c['id']}": "3" for c in defn.rubric["criteria"]}
    assert client.post(home + "/self-assessment", data={"csrf_token": CSRF, "version": str(version), **scores}).status_code == 303
    client.post(home + "/submit", data={"csrf_token": CSRF})

    with app.app_context():
        uid = _uid(app, "capstone@example.com")
        assert storage.get_enrollment(uid, "dev-f3")["status"] == "active"     # lessons not finished yet
    # complete all three lessons → completion is recorded on the next visit
    for lesson in course.lessons:
        _english(client, f"/learn/dev-f3/{lesson.id}")
        _post(client, f"/learn/dev-f3/{lesson.id}/material-reviewed")
    html = _english(client, home)
    with app.app_context():
        enrollment = storage.get_enrollment(uid, "dev-f3")
    assert enrollment["status"] == "completed" and enrollment["completion_policy"] == "dev_capstone"
    assert "All lessons completed" in html
    _english(client, "/report")


COURSES = [f"c0{n}" for n in range(1, 10)]


@pytest.mark.parametrize("course_id", COURSES)
def test_unpublished_real_courses_are_closed_to_students(app, client, course_id, monkeypatch):
    monkeypatch.delenv("ECONOVA_CONTENT_PREVIEW", raising=False)
    _student(client, f"s-{course_id}@example.com")
    course = content.get_catalog().course(course_id)
    assert not course.published
    _enroll(client, course_id)
    with app.app_context():
        assert storage.get_enrollment(_uid(app, f"s-{course_id}@example.com"), course_id) is None
    lesson = course.lessons[0]
    for url in (f"/learn/{course_id}/{lesson.id}", f"/learn/{course_id}/{lesson.id}/quiz", f"/courses/{course_id}/final",
                f"/preview/{course_id}/{lesson.id}"):
        res = client.get(url)
        assert res.status_code != 200 or "Not visible to students" not in res.get_data(as_text=True), url
        assert lesson.content.levels["beginner"]["summary"] not in res.get_data(as_text=True), url
    if course.capstone is not None:
        assert client.get(f"/capstone/{course_id}").status_code == 403


def test_admin_can_review_unpublished_content_without_the_preview_switch(app, client, monkeypatch):
    monkeypatch.delenv("ECONOVA_CONTENT_PREVIEW", raising=False)
    signup(client, email="reviewer@example.test", name="Review Admin")
    with app.app_context():
        storage.grant_admin(storage.get_user_by_email("reviewer@example.test")["id"], "Test operator", "Test account created in tests")
    login(client, email="reviewer@example.test")
    set_csrf(client)
    html = _english(client, "/preview/c01/c01-l1?level=advanced")
    assert "Not visible to students" in html
    html = _english(client, "/admin/content/assessment/c01-final")
    assert "Admin-only page" in html and "never sent to student pages" in html   # answers appear only here (keys are not loaded in tests)
    _english(client, "/admin/content/capstone/c09")
    _english(client, "/admin/content/diagnostic/econ-diagnostic")
