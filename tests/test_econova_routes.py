"""ECONOVA 화면: 카탈로그, 수강 신청, 대시보드, 강좌 상세, 레슨 접근, 진도, 난이도.
sqlite 와 가짜 Firestore 양쪽에서 실행된다. 공개된 실제 강좌가 아직 없으므로 개발용 테스트 강좌를 켠다."""
import pytest

from econova import content, learning, storage
from tests.conftest import CSRF, login, set_csrf, signup

pytestmark = pytest.mark.usefixtures("fixtures_on")
DONE_PILL = 'pill pill-completed">레슨 완료'   # 레슨 페이지의 완료 배지 ("레슨 완료 조건" 제목과 구분)


def _post(client, path, **data):
    return client.post(path, data={"csrf_token": CSRF, **data})


def _uid(app, email="student@example.com"):
    with app.app_context():
        return storage.get_user_by_email(email)["id"]


def _enroll(client, course_id, difficulty=None):
    data = {"difficulty": difficulty} if difficulty else {}
    return _post(client, f"/courses/{course_id}/enroll", **data)


def take(client, page_url, assessment, correct=True):
    """실제 화면 흐름으로 평가를 제출한다: 화면을 열어 일회용 토큰을 받고, 답을 채워 제출한다. 결과 주소를 돌려준다."""
    import re
    html = client.get(page_url).get_data(as_text=True)
    token = re.search(r'name="submission_token" value="([^"]+)"', html).group(1)
    answers = {}
    for q in assessment.questions:
        if correct:
            answers[f"q_{q['id']}"] = q["answer"] if q["type"] == "mcq" else f"{q['answer']:g}"
        else:
            answers[f"q_{q['id']}"] = "b" if q["type"] == "mcq" and q["answer"] == "a" else "-1"
    res = client.post(page_url, data={"csrf_token": CSRF, "submission_token": token, **answers})
    assert res.status_code == 302 and "/assessments/attempts/" in res.headers["Location"], res.status_code
    return res.headers["Location"]


def _submit_quiz(app, client, course_id, lesson_id, email="student@example.com", correct=True):
    """레슨 형성 퀴즈를 실제로 제출하고, 그 레슨의 진도 기록을 돌려준다."""
    lesson = content.get_catalog().course(course_id).lesson(lesson_id)
    take(client, f"/learn/{course_id}/{lesson_id}/quiz", lesson.quiz_assessment, correct)
    with app.app_context():
        return storage.list_lesson_progress(_uid(app, email), course_id)[lesson_id]


def _switch_user(client, email):
    client.post("/logout", data={"csrf_token": CSRF})
    signup(client, email=email)
    login(client, email=email)
    set_csrf(client)


# ------------------------------------------------------------- 카탈로그
def test_catalog_separates_available_upcoming_enrolled(logged_in):
    html = logged_in.get("/courses").get_data(as_text=True)
    assert "수강 가능한 강좌" in html and "준비 중인 강좌" in html and "수강 중인 강좌" not in html
    assert "시장과 가격" in html and "SDG 2" in html and "SDG 직접 선택" in html
    assert html.count("준비 중 · 신청 불가") == 9               # 실제 강좌 9개는 신청 불가
    assert html.count("개발용 테스트 강좌") >= 2
    assert 'action="/courses/c02/enroll"' not in html

    _enroll(logged_in, "dev-f1")
    html = logged_in.get("/courses").get_data(as_text=True)
    assert "수강 중인 강좌" in html and "/courses/dev-f1/continue" in html


def test_fixtures_hidden_when_disabled(monkeypatch, logged_in):
    monkeypatch.delenv("ECONOVA_DEV_FIXTURES")
    html = logged_in.get("/courses").get_data(as_text=True)
    assert "개발용 테스트 강좌" not in html and "지금 바로 수강 신청할 수 있는 강좌가 없어요" in html
    assert logged_in.get("/courses/dev-f1").status_code == 404
    assert _enroll(logged_in, "dev-f1").status_code == 404


# ------------------------------------------------------------- 수강 신청
def test_cannot_enroll_in_unpublished_course(app, logged_in):
    res = _enroll(logged_in, "c02")
    assert res.status_code == 303
    assert "공개되지 않은 강좌" in logged_in.get(res.headers["Location"]).get_data(as_text=True)
    with app.app_context():
        assert storage.get_enrollment(_uid(app), "c02") is None
    with app.app_context(), pytest.raises(learning.LearningError):   # 화면을 거치지 않아도 막힌다
        learning.enroll(_uid(app), content.get_catalog().course("c02"))


def test_enroll_unknown_course_404(logged_in):
    assert _enroll(logged_in, "c99").status_code == 404


def test_enroll_requires_login_and_csrf(client):
    assert client.post("/courses/dev-f1/enroll", data={"csrf_token": "x"}).status_code == 400
    set_csrf(client)
    res = _enroll(client, "dev-f1")
    assert res.status_code == 302 and res.headers["Location"].endswith("/login")


def test_enroll_multiple_and_duplicate(app, logged_in):
    assert _enroll(logged_in, "dev-f1", "intermediate").status_code == 302
    assert _enroll(logged_in, "dev-f2").status_code == 302
    res = _enroll(logged_in, "dev-f1", "advanced")
    assert "이미 수강 중인 강좌" in logged_in.get(res.headers["Location"]).get_data(as_text=True)
    with app.app_context():
        enrollments = storage.list_enrollments(_uid(app))
    assert sorted(e["course_id"] for e in enrollments) == ["dev-f1", "dev-f2"]
    assert {e["course_id"]: e["selected_difficulty"] for e in enrollments}["dev-f1"] == "intermediate"


def test_enroll_rejects_bad_difficulty(app, logged_in):
    assert _enroll(logged_in, "dev-f1", "expert").status_code == 303
    with app.app_context():
        assert storage.get_enrollment(_uid(app), "dev-f1") is None


# ------------------------------------------------------------- 대시보드
def test_dashboard_empty_state(logged_in):
    html = logged_in.get("/dashboard").get_data(as_text=True)
    assert "안녕하세요, 학생님" in html and "아직 수강 중인 강좌가 없어요" in html and 'href="/courses"' in html


def test_dashboard_cards_and_independent_progress(app, logged_in):
    _enroll(logged_in, "dev-f1")
    _enroll(logged_in, "dev-f2")
    _post(logged_in, "/learn/dev-f2/dev-f2-l2/material-reviewed")   # dev-f2 레슨 2: 자료 확인만 필요 → 완료
    html = logged_in.get("/dashboard").get_data(as_text=True)
    assert "개발용 테스트 강좌 A" in html and "개발용 테스트 강좌 B" in html
    assert "0% · 레슨 0/3 완료" in html and "50% · 레슨 1/2 완료" in html
    assert "/courses/dev-f1/continue" in html and 'href="/courses/dev-f2"' in html
    with app.app_context():
        board = learning.dashboard(_uid(app))
    assert (board["enrolled"], board["completed_lessons"], board["total_lessons"]) == (2, 1, 5)
    assert [c["progress"]["percent"] for c in board["cards"]] == [0, 50]


def test_dashboard_keeps_card_when_course_disappears(monkeypatch, logged_in):
    _enroll(logged_in, "dev-f1")
    monkeypatch.delenv("ECONOVA_DEV_FIXTURES")   # 강좌 정보가 사라져도 기록은 남고 화면이 깨지지 않는다
    res = logged_in.get("/dashboard")
    assert res.status_code == 200 and "이 강좌 정보는 지금 이용할 수 없어요" in res.get_data(as_text=True)


# ------------------------------------------------------------- 강좌 상세
def test_course_detail_before_and_after_enrollment(logged_in):
    html = logged_in.get("/courses/c02").get_data(as_text=True)
    assert "수강 신청 불가" in html and "검토 전 초안" in html and "최종 평가" in html and "수요와 공급" in html
    assert 'href="/learn/c02/' not in html

    html = logged_in.get("/courses/dev-f1").get_data(as_text=True)
    assert 'action="/courses/dev-f1/enroll"' in html
    _enroll(logged_in, "dev-f1", "advanced")
    html = logged_in.get("/courses/dev-f1").get_data(as_text=True)
    assert "내 진도" in html and "0% · 레슨 0/3 완료" in html and 'href="/learn/dev-f1/dev-f1-l1"' in html
    assert '<option value="advanced" selected>' in html and "잠김" in html   # 레슨을 다 끝내기 전 최종 평가는 잠김


def test_course_detail_unknown_404(logged_in):
    assert logged_in.get("/courses/nope").status_code == 404


# ------------------------------------------------------------- 레슨 접근
def test_lesson_access_rules(logged_in):
    assert logged_in.get("/learn/c02/c02-l1").status_code == 403            # 공개 전 강좌
    assert logged_in.get("/learn/dev-f1/dev-f2-l1").status_code == 404      # 다른 강좌의 레슨
    assert logged_in.get("/learn/dev-f1/dev-f1-l9").status_code == 404
    assert logged_in.get("/learn/nope/x").status_code == 404
    res = logged_in.get("/learn/dev-f1/dev-f1-l1")                        # 수강 전
    assert res.status_code == 302 and res.headers["Location"].endswith("/courses/dev-f1")
    _enroll(logged_in, "dev-f1")
    html = logged_in.get("/learn/dev-f1/dev-f1-l1").get_data(as_text=True)
    assert "레슨 완료 조건" in html and "필수 형성 퀴즈 제출" in html and "퀴즈 풀기" in html
    assert "개발용 테스트 자료" in html and "AI 튜터" in html and "AI 기능이 지금은 꺼져 있어요" in html   # 기본값: AI 꺼짐
    for title in ("학습 목표", "검증된 개념 설명", "난이도별 학습 내용", "풀이 예제", "경제 그래프", "SDG 사례",
                  "인터랙티브 시뮬레이션", "형성 퀴즈", "되돌아보기와 피드백"):
        assert title in html


def test_lesson_requires_login(client):
    res = client.get("/learn/dev-f1/dev-f1-l1")
    assert res.status_code == 302 and res.headers["Location"].endswith("/login")


def test_continue_learning(logged_in):
    assert logged_in.get("/courses/c02/continue").headers["Location"].endswith("/courses/c02")
    assert logged_in.get("/courses/dev-f1/continue").headers["Location"].endswith("/courses/dev-f1")  # 수강 전
    _enroll(logged_in, "dev-f2")
    assert logged_in.get("/courses/dev-f2/continue").headers["Location"].endswith("/learn/dev-f2/dev-f2-l1")


# ------------------------------------------------------------- 진도와 완료 규칙
def test_material_review_alone_does_not_complete_quiz_lesson(app, logged_in):
    _enroll(logged_in, "dev-f1")
    res = _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    assert res.status_code == 302
    html = logged_in.get("/learn/dev-f1/dev-f1-l1").get_data(as_text=True)
    assert "학습자료 확인 완료" in html and DONE_PILL not in html and 'pill pill-in_progress">진행 중' in html
    with app.app_context():
        rec = storage.list_lesson_progress(_uid(app), "dev-f1")["dev-f1-l1"]
    assert (rec["status"], rec["material_reviewed"], rec["quiz_submitted"]) == ("in_progress", True, False)
    assert "0% · 레슨 0/3 완료" in logged_in.get("/courses/dev-f1").get_data(as_text=True)


def test_quiz_submission_rules(app, logged_in):
    _enroll(logged_in, "dev-f1")
    _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    cat = content.get_catalog()
    f1, f2, c02 = cat.course("dev-f1"), cat.course("dev-f2"), cat.course("c02")
    # 퀴즈 제출은 화면이 보낸 표시가 아니라 서버에 저장된 본인의 응시 기록으로만 반영된다
    with app.app_context():
        uid = _uid(app)
        with pytest.raises(learning.LearningError, match="찾을 수 없어요"):
            learning.record_quiz_submission(uid, f1, f1.lesson("dev-f1-l1"), "999999")
        with pytest.raises(learning.LearningError, match="필수 퀴즈가 없어요"):   # 퀴즈가 필요 없는 레슨
            learning.record_quiz_submission(uid, f2, f2.lesson("dev-f2-l2"), "1")
        with pytest.raises(learning.LearningError, match="필수 퀴즈가 없어요"):   # 퀴즈가 아직 draft 인 실제 강좌
            learning.record_quiz_submission(uid, c02, c02.lesson("c02-l1"), "1")
    res = _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed", quiz_submitted="1", status="completed")
    with app.app_context():
        assert storage.list_lesson_progress(_uid(app), "dev-f1")["dev-f1-l1"]["status"] == "in_progress"   # 위조 무시
    assert logged_in.get("/learn/dev-f2/dev-f2-l1/quiz").status_code == 303   # 수강 전
    assert logged_in.get("/learn/c02/c02-l1/quiz").status_code == 403         # 공개 전 강좌
    assert logged_in.get("/learn/dev-f2/dev-f2-l2/quiz").status_code in (303, 404)

    rec = _submit_quiz(app, logged_in, "dev-f1", "dev-f1-l1")
    assert rec["status"] == "completed" and rec["quiz_score"] == 1.0
    with app.app_context():
        [attempt] = storage.list_assessment_attempts(_uid(app), assessment_id="dev-f1-l1-quiz")
        with pytest.raises(learning.LearningError, match="퀴즈가 아니에요"):   # 다른 레슨의 퀴즈 기록으로는 안 됨
            learning.record_quiz_submission(_uid(app), f1, f1.lesson("dev-f1-l2"), attempt["id"])
    html = logged_in.get("/courses/dev-f1").get_data(as_text=True)
    assert "33% · 레슨 1/3 완료" in html
    assert DONE_PILL in logged_in.get("/learn/dev-f1/dev-f1-l1").get_data(as_text=True)


def test_quiz_before_material_is_in_progress(app, logged_in):
    _enroll(logged_in, "dev-f1")
    assert _submit_quiz(app, logged_in, "dev-f1", "dev-f1-l2")["status"] == "in_progress"
    _post(logged_in, "/learn/dev-f1/dev-f1-l2/material-reviewed")
    with app.app_context():
        assert storage.list_lesson_progress(_uid(app), "dev-f1")["dev-f1-l2"]["status"] == "completed"


def test_progress_is_independent_between_courses(app, logged_in):
    _enroll(logged_in, "dev-f1")
    _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    _submit_quiz(app, logged_in, "dev-f1", "dev-f1-l1")
    _enroll(logged_in, "dev-f2")                                # 나중에 다른 강좌를 신청해도
    _post(logged_in, "/learn/dev-f2/dev-f2-l2/material-reviewed")
    with app.app_context():
        board = {c["course"].id: c["progress"] for c in learning.dashboard(_uid(app))["cards"]}
    assert (board["dev-f1"]["completed"], board["dev-f1"]["percent"]) == (1, 33)   # dev-f1 은 그대로
    assert (board["dev-f2"]["completed"], board["dev-f2"]["percent"]) == (1, 50)


def test_full_course_lessons_completed_but_not_course_completed(app, logged_in):
    _enroll(logged_in, "dev-f2")
    _post(logged_in, "/learn/dev-f2/dev-f2-l1/material-reviewed")
    _submit_quiz(app, logged_in, "dev-f2", "dev-f2-l1")
    _post(logged_in, "/learn/dev-f2/dev-f2-l2/material-reviewed")
    html = logged_in.get("/dashboard").get_data(as_text=True)
    assert "100% · 레슨 2/2 완료" in html and "레슨 모두 완료 · 최종 평가 예정" in html
    with app.app_context():
        assert storage.get_enrollment(_uid(app), "dev-f2")["status"] == "active"   # 수료는 최종 평가 후 (Phase 4)


def test_material_review_requires_enrollment_and_published_course(app, logged_in):
    res = _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    assert res.status_code == 303 and res.headers["Location"].endswith("/courses/dev-f1")
    assert _post(logged_in, "/learn/c02/c02-l1/material-reviewed").status_code == 403
    with app.app_context():
        assert storage.list_all_lesson_progress(_uid(app)) == {}


# ------------------------------------------------------------- 난이도
def test_difficulty_change(app, logged_in):
    _enroll(logged_in, "dev-f1")
    assert _post(logged_in, "/courses/dev-f1/difficulty", difficulty="intermediate").status_code == 302
    assert _post(logged_in, "/courses/dev-f1/difficulty", difficulty="expert").status_code == 303
    assert _post(logged_in, "/courses/dev-f2/difficulty", difficulty="advanced").status_code == 303   # 수강 전
    with app.app_context():
        assert storage.get_enrollment(_uid(app), "dev-f1")["selected_difficulty"] == "intermediate"
        assert storage.get_enrollment(_uid(app), "dev-f2") is None
    assert "난이도 중 (Intermediate)" in logged_in.get("/learn/dev-f1/dev-f1-l1").get_data(as_text=True)


# ------------------------------------------------------------- 다른 학생
def test_students_cannot_touch_each_other(app, client):
    signup(client)
    login(client)
    set_csrf(client)
    _enroll(client, "dev-f1")
    _post(client, "/learn/dev-f1/dev-f1-l1/material-reviewed")

    _switch_user(client, "other@example.com")
    assert "아직 수강 중인 강좌가 없어요" in client.get("/dashboard").get_data(as_text=True)
    assert _post(client, "/courses/dev-f1/difficulty", difficulty="advanced").status_code == 303
    assert _post(client, "/learn/dev-f1/dev-f1-l2/material-reviewed").status_code == 303
    assert client.get("/learn/dev-f1/dev-f1-l1").status_code == 302

    with app.app_context():
        a = _uid(app)
        assert storage.get_enrollment(a, "dev-f1")["selected_difficulty"] == "beginner"
        assert set(storage.list_lesson_progress(a, "dev-f1")) == {"dev-f1-l1"}
        assert storage.list_enrollments(_uid(app, "other@example.com")) == []


# ------------------------------------------------------------- 다시 로그인
def test_progress_persists_after_relogin(app, client):
    signup(client)
    login(client)
    set_csrf(client)
    _enroll(client, "dev-f1", "advanced")
    _post(client, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    _submit_quiz(app, client, "dev-f1", "dev-f1-l1")
    client.post("/logout", data={"csrf_token": CSRF})
    assert client.get("/dashboard").status_code == 302

    login(client)
    html = client.get("/dashboard").get_data(as_text=True)
    assert "33% · 레슨 1/3 완료" in html and "상 (Advanced)" in html
    html = client.get("/learn/dev-f1/dev-f1-l1").get_data(as_text=True)
    assert DONE_PILL in html
