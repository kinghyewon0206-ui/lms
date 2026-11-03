"""앱을 import 하기만 해서는 어떤 데이터베이스도 바뀌지 않아야 한다.

이미 import 된 테스트 프로세스로는 확인할 수 없으므로 새 파이썬 프로세스에서 import 한다.
운영 키가 든 것처럼 꾸민 .env 를 주고, Firebase SDK 를 부르면 표시 파일을 남기게 한다.
"""
import hashlib
import os
import sqlite3
import subprocess
import sys

from tests.conftest import FAKE_CREDENTIALS, ROOT

SCRIPT = r"""
import os, sys
sys.path.insert(0, os.environ["LMS_ROOT"])
import firebase_admin
from firebase_admin import firestore
def touched(*a, **k):
    open(os.environ["FIREBASE_MARKER"], "w").close()
    raise SystemExit("firebase called")
firebase_admin.initialize_app = touched
firestore.client = touched
from econova import config
config.DOTENV_PATH = os.environ["FAKE_DOTENV"]
import app
print("imported", config.db_backend())
"""


def _run(tmp_path, **extra_env):
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"OPENAI_API_KEY=sk-test\nFIREBASE_CREDENTIALS_JSON={FAKE_CREDENTIALS}\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if k not in ("DB_BACKEND", "FIREBASE_CREDENTIALS_JSON", "RENDER", "APP_ENV", "SQLITE_PATH")}
    env.update(LMS_ROOT=ROOT, FAKE_DOTENV=str(dotenv), FIREBASE_MARKER=str(tmp_path / "firebase-called"), **extra_env)
    return subprocess.run([sys.executable, "-I", "-c", SCRIPT], env=env, cwd=tmp_path,
                          capture_output=True, text=True, timeout=60)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_import_does_not_modify_existing_sqlite(tmp_path):
    db_path = tmp_path / "existing.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    con.execute("INSERT INTO users (email) VALUES ('keep@example.com')")
    con.commit()
    con.close()
    before = _digest(db_path)

    result = _run(tmp_path, SQLITE_PATH=str(db_path))

    assert result.returncode == 0, result.stderr
    assert "imported sqlite" in result.stdout
    assert _digest(db_path) == before
    assert not (tmp_path / "firebase-called").exists()


def test_import_does_not_create_sqlite_file(tmp_path):
    db_path = tmp_path / "new.db"
    result = _run(tmp_path, SQLITE_PATH=str(db_path))
    assert result.returncode == 0, result.stderr
    assert not db_path.exists()
    assert not (tmp_path / "firebase-called").exists()


def test_import_with_explicit_firestore_does_not_connect(tmp_path):
    # DB_BACKEND=firestore 여도 import 만으로는 접속·쓰기를 하지 않는다 (예전에는 강의 49개를 덮어썼다)
    result = _run(tmp_path, DB_BACKEND="firestore", SQLITE_PATH=str(tmp_path / "x.db"))
    assert result.returncode == 0, result.stderr
    assert "imported firestore" in result.stdout
    assert not (tmp_path / "firebase-called").exists()


def test_production_without_backend_refuses_to_start(tmp_path):
    result = _run(tmp_path, RENDER="true", SQLITE_PATH=str(tmp_path / "x.db"))
    assert result.returncode != 0
    assert "ConfigError" in result.stderr
    assert not (tmp_path / "x.db").exists()
    assert not (tmp_path / "firebase-called").exists()
