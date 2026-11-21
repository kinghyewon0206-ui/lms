"""테스트 공통 설정.

안전장치: 테스트는 실제 .env(운영 Firebase 키, OpenAI 키)를 읽지 않고, Firebase·외부 네트워크를 절대 호출하지 않는다.
이 설정은 app 을 import 하기 "전에" 적용되어야 하므로 파일 맨 위에서 한다.
"""
import os
import sys
import tempfile
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from econova import config  # noqa: E402

config.DOTENV_PATH = os.path.join(ROOT, "tests", "_no_dotenv_in_tests")  # 존재하지 않는 경로
for _name in ("DB_BACKEND", "FIREBASE_CREDENTIALS_JSON", "OPENAI_API_KEY", "OPENAI_MODEL", "RENDER", "APP_ENV",
              "SQLITE_PATH", "AI_PROVIDER", "ECONOVA_AI_PROVIDER"):
    os.environ.pop(_name, None)
# 실제 정답 키(저장소 밖 비공개 폴더)는 테스트에서 읽지 않는다: 빈 임시 폴더를 비공개 폴더로 쓴다.
# 그래서 c02 실제 평가·진단평가는 '정답 키 없음(응시 불가)' 상태가 되고, 채점 테스트는 합성 fixture 로 한다.
# 실제 키의 정합성은 tests/test_private_content.py 가 ECONOVA_REAL_PRIVATE_CONTENT_DIR 이 있을 때만 따로 확인한다.
EMPTY_PRIVATE_DIR = tempfile.mkdtemp(prefix="econova-test-private-")
os.environ["ECONOVA_PRIVATE_CONTENT_DIR"] = EMPTY_PRIVATE_DIR
# AI 오답 설명은 운영 기본값이 off 다. 기능 자체를 시험하려고 테스트에서는 켜 두고, 기본값(off)은 test_ai_feedback_off 가 따로 확인한다.
os.environ["ECONOVA_AI_FEEDBACK"] = "on"

# Firebase SDK 를 부르면 기록하고 실패시킨다. 어떤 테스트에서든 이 목록이 비어 있어야 한다.
import firebase_admin  # noqa: E402
from firebase_admin import credentials as _fb_credentials, firestore as _fb_firestore  # noqa: E402

FIREBASE_CALLS = []


def _blocked(name):
    def fn(*args, **kwargs):
        FIREBASE_CALLS.append(name)
        raise AssertionError(f"테스트 중 Firebase 호출이 발생했습니다: {name}")
    return fn


firebase_admin.initialize_app = _blocked("firebase_admin.initialize_app")
_fb_credentials.Certificate = _blocked("credentials.Certificate")
_fb_firestore.client = _blocked("firestore.client")

import app as app_module  # noqa: E402
from econova import diagnostic, storage  # noqa: E402
from tests import fake_firestore  # noqa: E402

FAKE_CREDENTIALS = '{"type": "service_account", "project_id": "not-a-real-project"}'


@pytest.fixture(autouse=True)
def _no_deployment_settings(monkeypatch):
    """개발자 환경의 Google 로그인·Vercel·정답 키 묶음 설정이 테스트에 섞이지 않게 한다 (필요한 테스트가 직접 켠다)."""
    for name in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI", "CRON_SECRET",
                 "ECONOVA_PRIVATE_KEYS_BUNDLE", "ECONOVA_PRIVATE_KEYS_SECRET", "ECONOVA_TIMING_HEADERS", "VERCEL_ENV", "VERCEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """OpenAI·강의 링크 확인 등 외부 요청을 막는다."""
    def refuse(*args, **kwargs):
        raise AssertionError("테스트 중 외부 네트워크 요청이 발생했습니다.")
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", refuse)


@pytest.fixture(autouse=True)
def _synthetic_diagnostic(monkeypatch):
    """진단평가 테스트는 개발용 합성 진단평가(content/dev_fixtures/diagnostic.json + 합성 키)로 한다."""
    monkeypatch.setattr(diagnostic, "PATH", diagnostic.FIXTURE_PATH)
    monkeypatch.setattr(diagnostic, "KEYS_FIXTURE", True)


@pytest.fixture(autouse=True)
def _firebase_untouched():
    start = len(FIREBASE_CALLS)
    yield
    assert FIREBASE_CALLS[start:] == [], "Firebase SDK 가 호출되었습니다."


@pytest.fixture
def sqlite_app(tmp_path, monkeypatch):
    """임시 sqlite 파일을 쓰는 앱. 운영 키가 환경에 있어도 sqlite 를 써야 한다는 것까지 함께 확인한다."""
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", FAKE_CREDENTIALS)
    monkeypatch.delenv("DB_BACKEND", raising=False)
    flask_app = app_module.app
    monkeypatch.setitem(flask_app.config, "DATABASE", str(tmp_path / "test.db"))
    monkeypatch.setitem(flask_app.config, "TESTING", True)
    with flask_app.app_context():
        storage.init_db()
    return flask_app


@pytest.fixture
def fake_fs():
    return fake_firestore.FakeFirestore()


@pytest.fixture
def firestore_app(monkeypatch, fake_fs, tmp_path):
    """DB_BACKEND=firestore 이지만 실제 Firestore 대신 가짜를 쓰는 앱."""
    monkeypatch.setenv("DB_BACKEND", "firestore")
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", FAKE_CREDENTIALS)
    monkeypatch.setattr(storage, "_fs", lambda: fake_fs)
    monkeypatch.setattr(storage, "fb_firestore", fake_firestore.module)
    flask_app = app_module.app
    monkeypatch.setitem(flask_app.config, "DATABASE", str(tmp_path / "must-not-be-created.db"))
    monkeypatch.setitem(flask_app.config, "TESTING", True)
    with flask_app.app_context():
        storage.init_db()
    yield flask_app
    assert not (tmp_path / "must-not-be-created.db").exists(), "firestore 모드에서 sqlite 파일이 만들어졌습니다."


@pytest.fixture(params=["sqlite", "firestore"])
def app(request):
    """같은 테스트를 두 저장소(sqlite, 가짜 Firestore)에서 모두 실행한다."""
    return request.getfixturevalue(f"{request.param}_app")


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def fixtures_on(monkeypatch):
    """개발용 테스트 강좌(content/dev_fixtures)를 켠다. 실제 강좌는 아직 하나도 공개되지 않았기 때문이다."""
    monkeypatch.setenv("ECONOVA_DEV_FIXTURES", "1")


# ------------------------------------------------------------- 도우미
CSRF = "test-csrf-token"


def set_csrf(client):
    with client.session_transaction() as s:
        s["csrf_token"] = CSRF
    return CSRF


def signup(client, email="student@example.com", name="학생", password="password123", confirm=None):
    set_csrf(client)
    return client.post("/signup", data={"name": name, "email": email, "password": password,
                                        "confirm": password if confirm is None else confirm, "csrf_token": CSRF})


def login(client, email="student@example.com", password="password123"):
    set_csrf(client)
    return client.post("/login", data={"email": email, "password": password, "csrf_token": CSRF})


@pytest.fixture
def logged_in(client):
    signup(client)
    login(client)
    set_csrf(client)  # 로그인하면 세션이 비워지므로 토큰을 다시 넣는다
    return client
