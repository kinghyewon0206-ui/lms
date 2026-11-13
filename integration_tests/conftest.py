"""연동 시험 공통 설정 (Phase 8B-2).

tests/ 와 따로 둔 이유: tests/conftest.py 는 Firebase SDK·외부 네트워크를 아예 막는다. 이 폴더는 같은 시험을
- fake (기본): 가짜 Firestore(직렬화·재시도 흉내)·가짜 OpenAI 로, 외부 접속 없이
- live      : 사람이 승인한 개발 전용 Firebase 프로젝트·개발용 OpenAI 키로 (integration_tests/guards.py 의 조건을 모두 만족할 때만)
실행한다. 실행 방법과 승인 절차는 docs/phase-8b2-integration.md.

어느 모드든 .env 는 읽지 않고, 셸의 운영 변수(FIREBASE_CREDENTIALS_JSON, OPENAI_API_KEY 등)는 지운 뒤 시작한다.
실제 정답 키 폴더는 쓰지 않는다 (빈 임시 폴더 + 개발용 합성 키). 시험 계정은 IT_EMAIL_DOMAIN 만 쓴다.
"""
import itertools
import os
import re
import sys
import tempfile
import urllib.request
import uuid
from dataclasses import dataclass

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from econova import config  # noqa: E402

config.DOTENV_PATH = os.path.join(ROOT, "integration_tests", "_no_dotenv_here")   # 존재하지 않는 경로
from integration_tests import guards  # noqa: E402

try:   # 접속하기 전에 모든 조건을 확인한다. 하나라도 어긋나면 시험 전체를 시작하지 않는다.
    FS_MODE = guards.mode("ECONOVA_IT_FIRESTORE")
    AI_MODE = guards.mode("ECONOVA_IT_OPENAI")
    FS_LIVE = guards.firestore_live() if FS_MODE == "live" else None
    AI_LIVE = guards.openai_live() if AI_MODE == "live" else None
except guards.IntegrationRefused as _exc:
    pytest.exit(f"[연동 시험 거부] {_exc}", returncode=4)

for _name in ("DB_BACKEND", "FIREBASE_CREDENTIALS_JSON", "OPENAI_API_KEY", "OPENAI_MODEL", "RENDER", "APP_ENV",
              "SQLITE_PATH", "AI_PROVIDER", "ECONOVA_AI_PROVIDER", "ECONOVA_AI_MODEL", "ECONOVA_TRUSTED_PROXY_HOPS"):
    os.environ.pop(_name, None)
os.environ["ECONOVA_PRIVATE_CONTENT_DIR"] = tempfile.mkdtemp(prefix="econova-it-private-")
os.environ["ECONOVA_DEV_FIXTURES"] = "1"

import firebase_admin  # noqa: E402
from firebase_admin import credentials as _fb_credentials, firestore as _fb_firestore  # noqa: E402

FIREBASE_CALLS = []
if FS_LIVE is None:
    def _blocked(name):
        def fn(*args, **kwargs):
            FIREBASE_CALLS.append(name)
            raise AssertionError(f"fake 모드에서 Firebase 호출이 발생했습니다: {name}")
        return fn
    firebase_admin.initialize_app = _blocked("firebase_admin.initialize_app")
    _fb_credentials.Certificate = _blocked("credentials.Certificate")
    _fb_firestore.client = _blocked("firestore.client")
else:
    _real_init = firebase_admin.initialize_app

    def _checked_init(credential=None, *args, **kwargs):   # 두 번째 확인: 실제로 초기화하는 키의 프로젝트
        if getattr(credential, "project_id", None) != FS_LIVE.project_id:
            raise AssertionError("승인하지 않은 Firebase 프로젝트로 초기화하려 했습니다.")
        return _real_init(credential, *args, **kwargs)
    firebase_admin.initialize_app = _checked_init

import app as app_module  # noqa: E402
from econova import diagnostic, storage  # noqa: E402
from econova.ai import client as ai_client  # noqa: E402
from integration_tests import fake_backends  # noqa: E402
from integration_tests.transport import GuardedTransport, inspect_body  # noqa: E402
from tests import fake_firestore  # noqa: E402

CSRF = "it-csrf-token"


def pytest_report_header(config):
    return [f"ECONOVA 연동 시험: Firestore={FS_MODE}" + (f" ({FS_LIVE.project_id})" if FS_LIVE else "")
            + f", OpenAI={AI_MODE}" + (f" (모델 {AI_LIVE.model}, 최대 {AI_LIVE.max_requests}회)" if AI_LIVE else "")]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """기본은 모든 urllib 요청 거부. OpenAI 시험만 openai_transport 로 바꾼다 (Firebase SDK 는 urllib 를 쓰지 않음)."""
    def refuse(*args, **kwargs):
        raise AssertionError("허용되지 않은 외부 네트워크 요청입니다.")
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", refuse)


@pytest.fixture(autouse=True)
def _synthetic_diagnostic(monkeypatch):
    monkeypatch.setattr(diagnostic, "PATH", diagnostic.FIXTURE_PATH)
    monkeypatch.setattr(diagnostic, "KEYS_FIXTURE", True)


@pytest.fixture(autouse=True)
def _firebase_untouched_in_fake():
    start = len(FIREBASE_CALLS)
    yield
    assert FIREBASE_CALLS[start:] == []


# ------------------------------------------------------------------ Firestore 백엔드
@dataclass
class Backend:
    app: object
    db: object
    live: bool
    run_id: str

    def ids(self, collection):
        ref = self.db.collection(collection)
        if self.live:
            return [d.id for d in ref.select([]).stream()]   # 문서 id 만 (내용은 읽지 않음)
        return [s.id for s in ref.stream()]

    def collections(self):
        if self.live:
            return [c.id for c in self.db.collections()]
        return sorted({p[0] for p in self.db.docs})

    def delete_tree(self, ref):
        self.db.recursive_delete(ref)


_counter = itertools.count(1)


@pytest.fixture(scope="session")
def backend():
    mp = pytest.MonkeyPatch()
    flask_app = app_module.app
    sqlite_guard = os.path.join(tempfile.mkdtemp(prefix="econova-it-"), "must-not-be-created.db")
    flask_app.config.update(TESTING=True, DATABASE=sqlite_guard)
    mp.setenv("DB_BACKEND", "firestore")
    if FS_LIVE is None:
        db = fake_backends.RetryingFirestore()
        mp.setenv("FIREBASE_CREDENTIALS_JSON", '{"type": "service_account", "project_id": "fake-econova-it"}')
        mp.setattr(storage, "_fs", lambda: db)
        mp.setattr(storage, "fb_firestore", fake_backends.module)
        mp.setattr(fake_firestore.FakeDocRef, "get", fake_backends.strict_get)
        b = Backend(flask_app, db, False, uuid.uuid4().hex[:8])
    else:
        with open(FS_LIVE.credentials_path, encoding="utf-8") as f:
            mp.setenv("FIREBASE_CREDENTIALS_JSON", f.read())   # 이 프로세스 안에서만. 출력·저장하지 않는다
        with flask_app.app_context():
            db = storage._fs()
        b = Backend(flask_app, db, True, uuid.uuid4().hex[:8])
        marker = db.collection(guards.MARKER[0]).document(guards.MARKER[1]).get()
        try:
            guards.check_connected(db.project, marker.to_dict() if marker.exists else None, b.ids("users"),
                                   FS_LIVE.project_id)
        except guards.IntegrationRefused as exc:
            mp.undo()
            pytest.exit(f"[연동 시험 거부] {exc}", returncode=4)
    before = {c: set(b.ids(c)) for c in b.collections()}
    with flask_app.app_context():
        storage.init_db()
    yield b
    # 정리: 이번 실행에서 새로 생긴 최상위 문서만 하위 컬렉션까지 지운다 (표식 문서·이전 문서는 그대로)
    leftovers = 0
    for c in b.collections():
        for doc_id in set(b.ids(c)) - before.get(c, set()):
            b.delete_tree(b.db.collection(c).document(doc_id))
    for c in b.collections():
        leftovers += len(set(b.ids(c)) - before.get(c, set()))
    mp.undo()
    assert leftovers == 0, f"정리 뒤에도 시험 문서 {leftovers}개가 남았습니다."
    assert not os.path.exists(sqlite_guard), "firestore 모드에서 sqlite 파일이 만들어졌습니다."


@pytest.fixture
def app(backend, monkeypatch):
    monkeypatch.setenv("ECONOVA_AI_PROVIDER", "mock")    # Firestore 시험은 모의 AI 로 (외부 요청 없음)
    monkeypatch.setenv("ECONOVA_AI_DUPLICATE_SECONDS", "0")
    return backend.app


@pytest.fixture
def new_user(backend, app):
    """새 시험 계정과 그 계정으로 로그인한 클라이언트. 계정마다 다른 가상 IP 를 쓴다 (로그인 제한이 섞이지 않게)."""
    def make(name="연동시험"):
        n = next(_counter)
        email = f"it-{backend.run_id}-{n}@{guards.IT_EMAIL_DOMAIN}"
        c = app.test_client()
        c.environ_base["REMOTE_ADDR"] = f"198.18.{n // 250}.{n % 250 + 1}"
        signup(c, email, name)
        assert login(c, email).status_code == 302
        set_csrf(c)
        with app.app_context():
            uid = storage.get_user_by_email(email)["id"]
        return User(email=email, id=uid, client=c, ip=c.environ_base["REMOTE_ADDR"])
    return make


@dataclass
class User:
    email: str
    id: str
    client: object
    ip: str


def set_csrf(c):
    with c.session_transaction() as s:
        s["csrf_token"] = CSRF


def signup(c, email, name="연동시험", password="it-password-123"):
    set_csrf(c)
    return c.post("/signup", data={"name": name, "email": email, "password": password, "confirm": password,
                                   "csrf_token": CSRF})


def login(c, email, password="it-password-123", **kw):
    set_csrf(c)
    return c.post("/login", data={"email": email, "password": password, "csrf_token": CSRF}, **kw)


def post(c, path, **data):
    return c.post(path, data={"csrf_token": CSRF, **data})


def take(c, page_url, assessment, correct=True):
    """화면을 열어 일회용 토큰을 받고 답을 채워 제출한다. (결과 주소, 사용한 토큰)"""
    html = c.get(page_url).get_data(as_text=True)
    token = re.search(r'name="submission_token" value="([^"]+)"', html).group(1)
    answers = {}
    for q in assessment.questions:
        if correct:
            answers[f"q_{q['id']}"] = q["answer"] if q["type"] == "mcq" else f"{q['answer']:g}"
        else:
            answers[f"q_{q['id']}"] = "b" if q["type"] == "mcq" and q["answer"] == "a" else "-1"
    res = c.post(page_url, data={"csrf_token": CSRF, "submission_token": token, **answers})
    assert res.status_code == 302 and "/assessments/attempts/" in res.headers["Location"], res.status_code
    return res.headers["Location"], token, answers


# ------------------------------------------------------------------ OpenAI 전송 (fake / live)
@pytest.fixture
def openai_transport(app, monkeypatch):
    """OpenAI 시험용 전송. fake 는 FakeOpenAI(+같은 검사), live 는 GuardedTransport. (app 뒤에 설정해야 공급자가 openai)"""
    monkeypatch.setenv("ECONOVA_AI_PROVIDER", "openai")
    monkeypatch.setenv("ECONOVA_AI_DUPLICATE_SECONDS", "0")
    monkeypatch.setenv("ECONOVA_AI_MAX_OUTPUT_TOKENS", str(min(guards.MAX_OUTPUT_TOKENS, 500)))
    if AI_LIVE is None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-" + "x" * 30)
        monkeypatch.setenv("ECONOVA_AI_MODEL", "fake-model")
        fake = fake_backends.FakeOpenAI()
        fake.forbidden = []

        def call(req, timeout=None):   # live 와 같은 보내기 전 검사
            if req.full_url != ai_client.OPENAI_URL:
                raise AssertionError("허용되지 않은 주소로 요청하려 했습니다.")
            inspect_body(req.data, fake.forbidden)
            return fake(req, timeout)
        monkeypatch.setattr(urllib.request, "urlopen", call)
        return fake
    monkeypatch.setenv("OPENAI_API_KEY", guards.read_key(AI_LIVE.key_path))
    monkeypatch.setenv("ECONOVA_AI_MODEL", AI_LIVE.model)
    t = _live_transport()
    monkeypatch.setattr(urllib.request, "urlopen", t)
    return t


_LIVE_TRANSPORT = []


def _live_transport():
    """실행 전체에서 하나 (예산은 실행 단위로 센다)."""
    if not _LIVE_TRANSPORT:
        _LIVE_TRANSPORT.append(GuardedTransport(_REAL_URLOPEN, AI_LIVE.max_requests))
    return _LIVE_TRANSPORT[0]


_REAL_URLOPEN = urllib.request.urlopen


def pytest_terminal_summary(terminalreporter):
    if _LIVE_TRANSPORT:
        t = _LIVE_TRANSPORT[0]
        tin = sum(int(u.get("prompt_tokens") or 0) for u in t.usage)
        tout = sum(int(u.get("completion_tokens") or 0) for u in t.usage)
        terminalreporter.write_line(f"OpenAI live: 보낸 요청 {t.sent}/{t.budget}, 공급자 기록 토큰 입력 {tin} · 출력 {tout}, "
                                    f"HTTP 오류 {[(e['status'], e['code'], e['param']) for e in t.http_errors]}")
