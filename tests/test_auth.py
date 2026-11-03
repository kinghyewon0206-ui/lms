"""회원가입·로그인·세션·CSRF 회귀 테스트. 두 저장소(sqlite, 가짜 Firestore)에서 모두 실행된다."""
import pytest

from econova import storage
from tests.conftest import CSRF, login, set_csrf, signup


def _user(app, email):
    with app.app_context():
        return storage.get_user_by_email(email)


def test_signup_then_login(app, client):
    res = signup(client)
    assert res.status_code == 302 and res.headers["Location"].endswith("/login")
    user = _user(app, "student@example.com")
    assert user["name"] == "학생" and user["role"] == "student"
    assert user["password_hash"] != "password123" and user["password_hash"].startswith("pbkdf2:sha256")

    res = login(client)
    assert res.status_code == 302 and res.headers["Location"].endswith("/dashboard")
    with client.session_transaction() as s:
        assert s["user_id"] == user["id"]
    assert "학생님" in client.get("/dashboard").get_data(as_text=True)


def test_email_is_normalized(app, client):
    signup(client, email="  Mixed@Example.COM ")
    assert _user(app, "mixed@example.com") is not None
    assert login(client, email="MIXED@example.com").status_code == 302


def test_duplicate_email_rejected(app, client):
    signup(client)
    res = signup(client, name="다른 사람")
    assert res.status_code == 400
    assert "이미 가입된 이메일" in res.get_data(as_text=True)
    assert _user(app, "student@example.com")["name"] == "학생"


@pytest.mark.parametrize("kwargs, message", [
    ({"name": ""}, "이름을 입력"),
    ({"email": "not-an-email"}, "올바른 이메일"),
    ({"password": "short"}, "8자 이상"),
    ({"confirm": "different123"}, "일치하지 않습니다"),
])
def test_signup_validation(app, client, kwargs, message):
    res = signup(client, **kwargs)
    assert res.status_code == 400
    assert message in res.get_data(as_text=True)
    assert _user(app, kwargs.get("email", "student@example.com")) is None


@pytest.mark.parametrize("email, password", [("student@example.com", "wrong-password"), ("nobody@example.com", "password123")])
def test_login_failure(client, email, password):
    signup(client)
    res = login(client, email=email, password=password)
    assert res.status_code == 401
    assert "올바르지 않습니다" in res.get_data(as_text=True)
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_login_clears_previous_session(client):
    signup(client)
    with client.session_transaction() as s:
        s["leftover"] = "x"
    login(client)
    with client.session_transaction() as s:
        assert "leftover" not in s and "user_id" in s


def test_logout(logged_in):
    res = logged_in.post("/logout", data={"csrf_token": CSRF})
    assert res.status_code == 302
    with logged_in.session_transaction() as s:
        assert "user_id" not in s
    assert logged_in.get("/dashboard").status_code == 302


def test_logout_requires_post(logged_in):
    assert logged_in.get("/logout").status_code == 405


@pytest.mark.parametrize("path", ["/dashboard", "/courses", "/courses/c02", "/learn/c02/c02-l1", "/legacy",
                                  "/legacy/courses", "/course/econ-micro", "/watch/econ-micro", "/curriculum",
                                  "/curriculum/new", "/curriculum/quick"])
def test_login_required(client, path):
    res = client.get(path)
    assert res.status_code == 302 and res.headers["Location"].endswith("/login")


def test_stale_session_user_is_treated_as_logged_out(client):
    with client.session_transaction() as s:
        s["user_id"] = "ghost@example.com"
    assert client.get("/dashboard").status_code == 302


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_csrf_required_on_post(app, client, token):
    set_csrf(client)
    data = {"name": "학생", "email": "csrf@example.com", "password": "password123", "confirm": "password123"}
    if token:
        data["csrf_token"] = token
    assert client.post("/signup", data=data).status_code == 400
    assert client.post("/login", data={"email": "x@example.com", "password": "x"}).status_code == 400
    assert _user(app, "csrf@example.com") is None


def test_csrf_without_session_token(client):
    # 세션에 토큰이 없으면 아무 값도 통과하지 못한다
    assert client.post("/login", data={"email": "x@example.com", "password": "x", "csrf_token": "-"}).status_code == 400


def test_csrf_header_for_json(logged_in):
    res = logged_in.post("/curriculum/chat", json={"messages": []})
    assert res.status_code == 400  # 토큰 없음
    res = logged_in.post("/curriculum/chat", json={"messages": []}, headers={"X-CSRF-Token": CSRF})
    assert res.status_code == 400 and "잘못된 요청" in res.get_json()["error"]  # 토큰은 통과, 내용 검증에서 거절
