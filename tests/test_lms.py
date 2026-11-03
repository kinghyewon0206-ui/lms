"""기존 LMS 기능(강의 탐색·영상·커리큘럼) 회귀 테스트. 두 저장소에서 모두 실행된다. AI 는 꺼진 상태(키 없음)."""
import pytest

from econova import storage
from tests.conftest import CSRF, login, set_csrf, signup


def _quick(client, track="econ", level="0", hours="5"):
    return client.post("/curriculum/quick", data={"track": track, "level": level, "hours": hours, "csrf_token": CSRF})


def _cid(res):
    return res.headers["Location"].rsplit("/", 1)[1]


def test_index(client):
    html = client.get("/").get_data(as_text=True)
    assert "ECONOVA" in html and "지속가능발전목표(SDG)로 배우는 경제" in html


def test_index_redirects_when_logged_in(logged_in):
    assert logged_in.get("/").headers["Location"].endswith("/dashboard")


def test_legacy_home(logged_in):
    # 예전 대시보드(내 커리큘럼 + 인기 강의)는 /legacy 로 옮겨 보관한다
    html = logged_in.get("/legacy").get_data(as_text=True)
    assert "안녕하세요, 학생님" in html and "인기 강의" in html and "기존 LMS (보관)" in html


def test_courses_page(logged_in):
    res = logged_in.get("/legacy/courses?q=경제")  # 예전 강의 탐색 (/courses 는 ECONOVA 카탈로그)
    assert res.status_code == 200
    assert "미시경제학 원리" in res.get_data(as_text=True)


def test_course_detail_counts_view_once_per_session(app, logged_in):
    assert logged_in.get("/course/econ-micro").status_code == 200
    assert logged_in.get("/course/econ-micro").status_code == 200
    with app.app_context():
        assert storage.course_views().get("econ-micro") == 1


def test_unknown_course_404(logged_in):
    assert logged_in.get("/course/no-such-course").status_code == 404
    assert logged_in.get("/watch/no-such-course").status_code == 404
    assert logged_in.get("/watch/cip").status_code == 404  # 영상이 없는 강의


def test_watch(logged_in):
    html = logged_in.get("/watch/econ-micro").get_data(as_text=True)
    assert "youtube-nocookie.com/embed/videoseries" in html


def test_curriculum_pages_render(logged_in):
    for path in ("/curriculum", "/curriculum/new", "/curriculum/quick"):
        assert logged_in.get(path).status_code == 200, path


def test_quick_curriculum_rejects_incomplete_answers(app, logged_in):
    assert _quick(logged_in, track="nope").status_code == 400
    assert _quick(logged_in, level="x").status_code == 400
    with app.app_context():
        assert len(storage.list_curricula(_uid(app))) == 0


def _uid(app, email="student@example.com"):
    with app.app_context():
        return storage.get_user_by_email(email)["id"]


def test_quick_curriculum_lifecycle(app, logged_in):
    res = _quick(logged_in)
    assert res.status_code == 302
    cid = _cid(res)

    html = logged_in.get(f"/curriculum/{cid}").get_data(as_text=True)
    assert "학생님의 경제·경영 커리큘럼" in html and "MIT 14.01" in html and "0/5 완료" in html

    with app.app_context():
        items = storage.list_curriculum_items(cid)
    assert len(items) == 5  # 처음(0) 수준이면 경제 경로 5개가 모두 들어간다 (AI 없이 규칙 기반)

    res = logged_in.post(f"/curriculum/{cid}/toggle/{items[0]['item_id']}", data={"csrf_token": CSRF})
    assert res.status_code == 302
    assert "1/5 완료" in logged_in.get(f"/curriculum/{cid}").get_data(as_text=True)
    assert "20%" in logged_in.get("/curriculum").get_data(as_text=True)
    assert "진행 1/5" in logged_in.get("/legacy").get_data(as_text=True)

    logged_in.post(f"/curriculum/{cid}/toggle/{items[0]['item_id']}", data={"csrf_token": CSRF})
    assert "0/5 완료" in logged_in.get(f"/curriculum/{cid}").get_data(as_text=True)

    res = logged_in.post(f"/curriculum/{cid}/delete", data={"csrf_token": CSRF})
    assert res.headers["Location"].endswith("/curriculum")
    assert logged_in.get(f"/curriculum/{cid}").status_code == 404
    with app.app_context():
        assert storage.list_curricula(_uid(app)) == []


def test_other_users_cannot_touch_curriculum(app, client):
    signup(client)
    login(client)
    set_csrf(client)
    cid = _cid(_quick(client))
    with app.app_context():
        item_id = storage.list_curriculum_items(cid)[0]["item_id"]
    client.post("/logout", data={"csrf_token": CSRF})

    signup(client, email="other@example.com")
    login(client, email="other@example.com")
    set_csrf(client)
    assert client.get(f"/curriculum/{cid}").status_code == 404
    assert client.post(f"/curriculum/{cid}/toggle/{item_id}", data={"csrf_token": CSRF}).status_code == 404
    assert client.post(f"/curriculum/{cid}/delete", data={"csrf_token": CSRF}).status_code == 404
    with app.app_context():
        assert len(storage.list_curriculum_items(cid)) == 5
        assert not any(i["done"] for i in storage.list_curriculum_items(cid))


@pytest.mark.parametrize("payload", [
    {},
    {"messages": "hi"},
    {"messages": [{"role": "assistant", "content": "마지막이 사용자 메시지가 아님"}]},
    {"messages": [{"role": "system", "content": "역할 위조"}]},
    {"messages": [{"role": "user", "content": "x" * 1001}]},
])
def test_chat_rejects_bad_requests(logged_in, payload):
    assert logged_in.post("/curriculum/chat", json=payload, headers={"X-CSRF-Token": CSRF}).status_code == 400


def test_chat_without_ai_key_fails_gracefully(app, logged_in):
    res = logged_in.post("/curriculum/chat", json={"messages": [{"role": "user", "content": "경제를 배우고 싶어요"}]},
                         headers={"X-CSRF-Token": CSRF})
    assert res.status_code == 502 and "AI 연결에 실패" in res.get_json()["error"]
    with app.app_context():
        assert storage.list_curricula(_uid(app)) == []
