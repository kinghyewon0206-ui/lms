"""Phase 8B-1: 앱 전체 AI 스위치(off 면 외부 AI 요청 0), 로그인 남용 방지(계정+IP·계정·IP, 신뢰 프록시, 공유 네트워크),
학생 저장 한도, 권한이 취소된 관리자의 승인. 실제 OpenAI·Firebase 는 부르지 않는다."""
import datetime
import io
import json
import urllib.request

import pytest

from econova import admin_content as ac
from econova import config, content, login_guard, quotas, storage
from econova.ai import client as ai_client
from tests.conftest import CSRF, login, set_csrf, signup
from tests.test_econova_routes import _enroll, _post, _uid, take
from tests.test_phase7 import DRAFT_TOPIC, _make_admin, _review, content_copy  # noqa: F401

pytestmark = pytest.mark.usefixtures("fixtures_on")


# ------------------------------------------------------------- AI 스위치
@pytest.fixture
def network_spy(monkeypatch):
    calls = []

    def spy(req, timeout=None):
        calls.append(getattr(req, "full_url", str(req)))
        raise AssertionError("외부 요청이 발생했습니다")
    monkeypatch.setattr(urllib.request, "urlopen", spy)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-" + "R" * 30)   # 키가 있어도 스위치가 off 면 요청하지 않아야 한다
    return calls


def _all_ai_entry_points(c):
    """앱의 모든 AI 진입점을 한 번씩 부른다 (ECONOVA + 이전 LMS)."""
    out = {}
    out["legacy_chat"] = c.post("/curriculum/chat", json={"messages": [{"role": "user", "content": "경제 공부"}]},
                                headers={"X-CSRF-Token": CSRF})
    out["legacy_quick"] = c.post("/curriculum/quick", data={"csrf_token": CSRF, "track": "cs", "level": "0", "hours": "5"})
    _enroll(c, "dev-f1")
    out["tutor"] = c.post("/api/tutor", data={"csrf_token": CSRF, "course_id": "dev-f1", "lesson_id": "dev-f1-l1",
                                              "message": "질문"})
    _post(c, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    quiz = content.get_catalog().course("dev-f1").lesson("dev-f1-l1").quiz_assessment
    url = take(c, "/learn/dev-f1/dev-f1-l1/quiz", quiz, correct=False)
    out["feedback"] = c.post(url + "/explain", data={"csrf_token": CSRF})
    out["debate"] = c.post("/discuss/dev-f1/price-ceiling-food/respond", data={"csrf_token": CSRF, "message": "의견"})
    out["recs"] = c.post("/api/recommendations/explain", data={"csrf_token": CSRF})
    _enroll(c, "dev-f3")
    c.post("/capstone/dev-f3/edit", data={"csrf_token": CSRF, "sdg": "7", "problem": "문제"})
    out["capstone"] = c.post("/capstone/dev-f3/feedback", data={"csrf_token": CSRF})
    return out


def test_provider_off_makes_no_external_ai_request_anywhere(app, logged_in, network_spy, monkeypatch):
    monkeypatch.setenv("ECONOVA_AI_PROVIDER", "off")
    out = _all_ai_entry_points(logged_in)
    assert network_spy == []
    assert out["legacy_chat"].status_code == 503 and "간단 모드" in out["legacy_chat"].get_json()["error"]
    assert out["legacy_quick"].status_code == 302                       # 규칙 기반 추천으로 정상 생성
    assert out["tutor"].status_code == 503 and out["tutor"].get_json()["code"] == "disabled"
    assert out["recs"].status_code in (409, 503)
    with app.app_context():
        from econova.ai import usage
        assert storage.get_ai_usage(_uid(app), usage.today())["global"]["requests"] == 0
        assert storage.count_curricula(_uid(app)) == 1


def test_provider_mock_stays_local_and_dev_only(app, logged_in, network_spy, monkeypatch):
    monkeypatch.setenv("ECONOVA_AI_PROVIDER", "mock")
    monkeypatch.setenv("ECONOVA_AI_DUPLICATE_SECONDS", "0")
    res = logged_in.post("/curriculum/chat", json={"messages": [{"role": "user", "content": "경제 공부"}]},
                         headers={"X-CSRF-Token": CSRF})
    assert res.status_code == 200 and res.get_json()["reply"].startswith("[모의 AI]")
    _all_ai_entry_points(logged_in)
    assert network_spy == []
    monkeypatch.setenv("RENDER", "1")
    monkeypatch.setenv("SECRET_KEY", "s" * 40)
    with pytest.raises(config.ConfigError, match="모의 AI"):
        ai_client.settings()


def test_provider_openai_requires_server_key(monkeypatch):
    monkeypatch.setenv("ECONOVA_AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(config.ConfigError, match="OPENAI_API_KEY"):
        ai_client.settings()


# ------------------------------------------------------------- 로그인 남용 방지
def _try(c, email, password, ip="10.0.0.1", xff=None):
    set_csrf(c)
    headers = {"X-Forwarded-For": xff} if xff else {}
    return c.post("/login", data={"email": email, "password": password, "csrf_token": CSRF}, headers=headers,
                  environ_base={"REMOTE_ADDR": ip}).status_code


def test_account_ip_limit_and_spoofed_forwarded_header(app, client):
    signup(client)
    for i in range(10):   # 매번 X-Forwarded-For 를 바꿔도(위조) 프록시를 믿지 않으면 같은 곳으로 센다
        assert _try(client, "student@example.com", "wrong", xff=f"203.0.113.{i}") == 401
    assert _try(client, "student@example.com", "password123", xff="198.51.100.7") == 429
    assert _try(client, "student@example.com", "password123", ip="10.0.0.2") == 302   # 다른 네트워크의 주인은 로그인 가능


def test_shared_school_network_is_not_locked_out(app, client):
    for i in range(40):   # 같은 학교 IP 에서 40명이 각자 두 번씩 틀린 뒤 맞게 입력
        signup(client, email=f"s{i}@example.com")
    for i in range(40):
        assert _try(client, f"s{i}@example.com", "wrong", ip="192.0.2.10") == 401
        assert _try(client, f"s{i}@example.com", "wrong", ip="192.0.2.10") == 401
    assert all(_try(client, f"s{i}@example.com", "password123", ip="192.0.2.10") == 302 for i in range(40))


def test_ip_limit_stops_credential_stuffing(app, client, monkeypatch):
    monkeypatch.setenv("ECONOVA_LOGIN_MAX_PER_IP", "30")
    for i in range(30):
        assert _try(client, f"victim{i}@example.com", "guess", ip="203.0.113.50") == 401
    assert _try(client, "another@example.com", "guess", ip="203.0.113.50") == 429
    assert _try(client, "another@example.com", "guess", ip="203.0.113.51") == 401   # 다른 IP 는 영향 없음


def test_trusted_proxy_uses_only_the_proxy_appended_address(app, client, monkeypatch):
    monkeypatch.setenv("ECONOVA_TRUSTED_PROXY_HOPS", "1")
    signup(client)
    for i in range(10):   # 왼쪽 값(클라이언트가 위조 가능)을 바꿔도 프록시가 붙인 오른쪽 값이 같으면 같은 곳
        assert _try(client, "student@example.com", "wrong", ip="10.9.9.9", xff=f"1.1.1.{i}, 203.0.113.9") == 401
    assert _try(client, "student@example.com", "password123", ip="10.9.9.9", xff="5.5.5.5, 203.0.113.9") == 429
    assert _try(client, "student@example.com", "password123", ip="10.9.9.9", xff="203.0.113.10") == 302
    with app.test_request_context(headers={"X-Forwarded-For": "not-an-ip"}, environ_base={"REMOTE_ADDR": "10.1.1.1"}):
        assert login_guard.client_ip() == "10.1.1.1"   # 형식이 틀리면 직접 연결 주소


def test_account_wide_limit_spares_known_device(app, client, monkeypatch):
    monkeypatch.setenv("ECONOVA_TRUSTED_PROXY_HOPS", "1")
    monkeypatch.setenv("ECONOVA_LOGIN_MAX_PER_ACCOUNT", "20")
    signup(client)
    assert _try(client, "student@example.com", "password123", xff="198.51.100.1") == 302   # 주인이 한 번 로그인 → 기기 쿠키
    owner_cookie = client.get_cookie(login_guard.DEVICE_COOKIE)
    assert owner_cookie is not None
    from flask.testing import FlaskClient
    attacker = app.test_client()
    for i in range(20):   # 여러 IP 에서 같은 계정을 노림
        assert _try(attacker, "student@example.com", "guess", xff=f"203.0.113.{100 + i}") == 401
    assert _try(attacker, "student@example.com", "guess", xff="203.0.113.200") == 429
    assert _try(client, "student@example.com", "password123", xff="198.51.100.2") == 302   # 주인은 잠기지 않음
    stranger = app.test_client()
    assert _try(stranger, "student@example.com", "password123", xff="198.51.100.3") == 429  # 새 기기는 잠시 막힘


def test_counters_expire_are_hashed_and_purged(app, client, monkeypatch):
    signup(client)
    for _ in range(10):
        _try(client, "student@example.com", "wrong")
    assert _try(client, "student@example.com", "password123") == 429
    if not storage.using_firestore():
        with app.app_context():
            keys = [r["key"] for r in storage.get_db().execute("SELECT key FROM econ_login_counters")]
        assert keys and all("student@example.com" not in k and "10.0.0.1" not in k for k in keys)
    later = storage._utcnow() + datetime.timedelta(minutes=31)
    monkeypatch.setattr(storage, "_utcnow", lambda: later)
    assert _try(client, "student@example.com", "password123") == 302
    with app.app_context():
        assert storage.purge_login_counters(later + datetime.timedelta(hours=1)) >= 3


def test_login_limit_settings_are_validated(monkeypatch):
    monkeypatch.setenv("ECONOVA_TRUSTED_PROXY_HOPS", "9")
    with pytest.raises(config.ConfigError):
        login_guard.trusted_proxy_hops()
    monkeypatch.setenv("ECONOVA_LOGIN_MAX_PER_IP", "abc")
    with pytest.raises(config.ConfigError):
        login_guard.limits()


# ------------------------------------------------------------- 저장 한도
@pytest.fixture
def tiny_quotas(monkeypatch):
    for name in quotas.DEFAULTS:
        monkeypatch.setenv(f"ECONOVA_QUOTA_{name}", "2")
    monkeypatch.setenv("ECONOVA_AI_PROVIDER", "mock")
    monkeypatch.setenv("ECONOVA_AI_DUPLICATE_SECONDS", "0")
    provider = ai_client.MockProvider()
    monkeypatch.setattr(ai_client, "get_provider", lambda s=None: provider)


def test_simulation_and_diagnostic_quotas(app, logged_in, tiny_quotas):
    for _ in range(3):
        logged_in.post("/lab/supply-demand/save", data={"csrf_token": CSRF, "a": "100", "b": "2", "c": "10", "d": "1"})
    res = logged_in.post("/lab/supply-demand/save", data={"csrf_token": CSRF, "a": "100", "b": "2", "c": "10", "d": "1"})
    assert "저장 한도(2개)" in logged_in.get(res.headers["Location"]).get_data(as_text=True)
    for _ in range(3):
        logged_in.post("/diagnostic/take", data={"csrf_token": CSRF})
    with app.app_context():
        uid = _uid(app)
        assert len(storage.list_simulation_runs(uid)) == 2 and len(storage.list_diagnostic_attempts(uid)) == 2


def test_quiz_quota_only_for_unlimited_quizzes(app, logged_in, tiny_quotas):
    _enroll(logged_in, "dev-f1")
    _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    quiz = content.get_catalog().course("dev-f1").lesson("dev-f1-l1").quiz_assessment
    assert not quiz.max_attempts
    take(logged_in, "/learn/dev-f1/dev-f1-l1/quiz", quiz)
    take(logged_in, "/learn/dev-f1/dev-f1-l1/quiz", quiz)
    html = logged_in.get("/learn/dev-f1/dev-f1-l1/quiz").get_data(as_text=True)
    token = html.split('name="submission_token" value="')[1].split('"')[0]
    res = logged_in.post("/learn/dev-f1/dev-f1-l1/quiz", data={"csrf_token": CSRF, "submission_token": token})
    assert res.status_code == 303 and "저장 한도(2개)" in logged_in.get(res.headers["Location"]).get_data(as_text=True)
    with app.app_context():
        uid = _uid(app)
        assert len(storage.list_assessment_attempts(uid, assessment_id=quiz.id)) == 2   # 기존 기록은 그대로
        assert storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]["quiz_submitted"]


def test_ai_quotas(app, logged_in, tiny_quotas):
    _enroll(logged_in, "dev-f1")
    data = {"csrf_token": CSRF, "course_id": "dev-f1", "lesson_id": "dev-f1-l1", "message": "질문"}
    assert logged_in.post("/api/tutor", data=data).status_code == 200          # 메시지 2개
    res = logged_in.post("/api/tutor", data=data)
    assert res.status_code == 409 and "저장 한도(2개)" in res.get_json()["error"]
    page = "/discuss/dev-f1/price-ceiling-food"
    logged_in.post(page + "/respond", data={"csrf_token": CSRF, "message": "의견"})
    logged_in.post(page + "/new", data={"csrf_token": CSRF})
    res = logged_in.post(page + "/new", data={"csrf_token": CSRF})
    assert "이 주제의 토론 저장 한도" in logged_in.get(res.headers["Location"]).get_data(as_text=True)
    with app.app_context():
        assert len(storage.find_ai_conversations(_uid(app), "debate")) == 2


def test_capstone_quota_keeps_student_text(app, logged_in, tiny_quotas):
    _enroll(logged_in, "dev-f3")
    for i in range(2):
        logged_in.post("/capstone/dev-f3/edit", data={"csrf_token": CSRF, "sdg": "7", "problem": f"버전 {i}"})
    res = logged_in.post("/capstone/dev-f3/edit", data={"csrf_token": CSRF, "sdg": "7", "problem": "지우면 안 되는 학생 글"})
    html = res.get_data(as_text=True)
    assert res.status_code == 200 and "저장 한도(2개)" in html and "지우면 안 되는 학생 글" in html
    with app.app_context():
        assert len(storage.list_capstone_versions(_uid(app), "dev-f3")) == 2


def test_legacy_curricula_quota(app, logged_in, tiny_quotas):
    for _ in range(2):
        logged_in.post("/curriculum/quick", data={"csrf_token": CSRF, "track": "cs", "level": "0", "hours": "5"})
    res = logged_in.post("/curriculum/quick", data={"csrf_token": CSRF, "track": "cs", "level": "0", "hours": "5"})
    assert res.status_code == 409 and "내 커리큘럼 저장 한도" in res.get_data(as_text=True)
    res = logged_in.post("/curriculum/chat", json={"messages": [{"role": "user", "content": "경제"}]},
                         headers={"X-CSRF-Token": CSRF})
    assert res.status_code == 409


def test_quota_settings_are_validated(monkeypatch):
    assert quotas.validate_all()["SIMULATION_RUNS"] == 200
    monkeypatch.setenv("ECONOVA_QUOTA_SIMULATION_RUNS", "0")
    with pytest.raises(config.ConfigError):
        quotas.validate_all()


# ------------------------------------------------------------- 권한이 취소된 관리자의 승인
def test_revoked_reviewer_approval_is_not_releasable(app, client, content_copy, tmp_path):  # noqa: F811
    _make_admin(app, client)
    _review(client, "start_review")
    _review(client, "approve")
    plan = json.loads(client.get("/admin/content/release?download=1").get_data(as_text=True))
    assert plan["items"]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    with app.app_context():
        storage.revoke_admin(_uid(app, "admin@example.test"))
    res = app.test_cli_runner().invoke(args=["content-release-apply", str(path)])
    assert "권한이 취소됨" in res.output and "반영함" not in res.output
    with app.app_context():
        reviews = {}
        for r in storage.list_content_reviews():
            reviews.setdefault(f"{r['target_type']}:{r['target_id']}", []).append(r)
        targets = [t for row in ac.overview(include_fixtures=True) for t in row.get("targets", [])]
        assert ac.release_plan(targets, reviews, reviewer_active=lambda u: storage.get_admin_grant(u) is not None)["items"] == []


def test_students_never_reach_admin_content(app, client, monkeypatch):
    monkeypatch.delenv("ECONOVA_CONTENT_PREVIEW", raising=False)
    signup(client)
    login(client)
    set_csrf(client)
    for path in ("/admin", "/admin/content", "/admin/content/release", "/admin/content/release?download=1",
                 "/admin/content/assessment/dev-f1-final", "/preview/dev-f1/dev-f1-l1"):
        assert client.get(path).status_code == 404, path
