"""sqlite 모드에서는 Firestore 인증 정보가 있어도 Firebase 를 절대 부르지 않는다."""
import pytest

from econova import config, storage
from tests.conftest import FAKE_CREDENTIALS, FIREBASE_CALLS, login, set_csrf, signup


def test_fs_refuses_in_sqlite_mode(sqlite_app):
    with sqlite_app.app_context(), pytest.raises(config.ConfigError):
        storage._fs()
    assert FIREBASE_CALLS == []


def test_full_flow_in_sqlite_mode_never_calls_firebase(sqlite_app):
    client = sqlite_app.test_client()
    signup(client)
    login(client)
    set_csrf(client)
    for path in ("/dashboard", "/courses", "/course/econ-micro", "/watch/econ-micro", "/curriculum", "/curriculum/quick"):
        assert client.get(path).status_code == 200, path
    res = client.post("/curriculum/quick", data={"track": "econ", "level": "0", "hours": "5", "csrf_token": "test-csrf-token"})
    assert res.status_code == 302
    assert client.get(res.headers["Location"]).status_code == 200
    with sqlite_app.app_context():
        assert storage.get_user_by_email("student@example.com")["email"] == "student@example.com"
    assert FIREBASE_CALLS == []  # 각 테스트 끝의 자동 검사와 별도로 명시적으로도 확인


def test_init_db_command_requires_flag_for_firestore(monkeypatch, sqlite_app):
    # 진짜 _fs 를 그대로 둔 채 firestore 모드로 바꾼다. 플래그 없이 실행하면 접속 전에 멈춰야 한다.
    monkeypatch.setenv("DB_BACKEND", "firestore")
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", FAKE_CREDENTIALS)
    result = sqlite_app.test_cli_runner().invoke(args=["init-db"])
    assert result.exit_code != 0
    assert "--firestore" in result.output
    assert FIREBASE_CALLS == []


def test_init_db_command_sqlite(sqlite_app):
    result = sqlite_app.test_cli_runner().invoke(args=["init-db"])
    assert result.exit_code == 0, result.output
    assert "sqlite" in result.output
