"""DB_BACKEND 선택 규칙."""
import pytest

from econova import config
from tests.conftest import FAKE_CREDENTIALS


def test_default_is_sqlite():
    assert config.db_backend() == "sqlite"


def test_credentials_alone_do_not_select_firestore(monkeypatch):
    # 예전 버그: FIREBASE_CREDENTIALS_JSON 이 있기만 하면 Firestore(운영)를 썼다
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", FAKE_CREDENTIALS)
    assert config.db_backend() == "sqlite"


def test_credentials_in_dotenv_do_not_select_firestore(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"OPENAI_API_KEY=sk-test\nFIREBASE_CREDENTIALS_JSON={FAKE_CREDENTIALS}\n", encoding="utf-8")
    monkeypatch.setattr(config, "DOTENV_PATH", str(dotenv))
    assert config.env("FIREBASE_CREDENTIALS_JSON")  # .env 를 실제로 읽고 있는지
    assert config.db_backend() == "sqlite"


def test_explicit_firestore(monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "firestore")
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", FAKE_CREDENTIALS)
    assert config.db_backend() == "firestore"


def test_explicit_firestore_in_dotenv(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"DB_BACKEND=Firestore\nFIREBASE_CREDENTIALS_JSON={FAKE_CREDENTIALS}\n", encoding="utf-8")
    monkeypatch.setattr(config, "DOTENV_PATH", str(dotenv))
    assert config.db_backend() == "firestore"


def test_firestore_without_credentials_is_rejected(monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "firestore")
    with pytest.raises(config.ConfigError):
        config.db_backend()


def test_unknown_backend_is_rejected(monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "mysql")
    with pytest.raises(config.ConfigError):
        config.db_backend()


@pytest.mark.parametrize("name, value", [("RENDER", "true"), ("APP_ENV", "production")])
def test_production_requires_explicit_backend(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(config.ConfigError):
        config.db_backend()
    monkeypatch.setenv("DB_BACKEND", "sqlite")  # 명시하면 허용
    assert config.db_backend() == "sqlite"


def test_sqlite_path_override(monkeypatch, tmp_path):
    assert config.sqlite_path().endswith("lms.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "x.db"))
    assert config.sqlite_path() == str(tmp_path / "x.db")
