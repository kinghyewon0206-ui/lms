"""Phase 8B-2: 실제 연동 시험 하네스의 안전장치. 외부에 접속하지 않는다.

- integration_tests/guards.py: 개발 Firebase·개발 OpenAI 를 쓰기 전의 거부 조건
- integration_tests/transport.py: OpenAI 로 보내기 전 검사 (예산·주소·크기·금지 문자열·가명)
- integration_tests 전체를 fake 모드로 실행 (가짜 Firestore·가짜 OpenAI)
- live 를 승인 없이 요청하면 접속 전에 멈추는지
"""
import json
import os
import subprocess
import sys

import pytest

from integration_tests import guards
from integration_tests.transport import GuardedTransport, inspect_body

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEV = "econova-dev-20261110"
PROD = "econova-prod"


def _key_file(tmp_path, project=DEV, mode=0o600, **extra):
    data = {"type": "service_account", "project_id": project,
            "client_email": f"it-runner@{project}.iam.gserviceaccount.com", **extra}
    p = tmp_path / "dev-key.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(p, mode)
    return str(p)


def _fs_env(tmp_path, **over):
    env = {"ECONOVA_IT_FIRESTORE": "live", "ECONOVA_IT_FIREBASE_PROJECT_ID": DEV,
           "ECONOVA_IT_PRODUCTION_PROJECT_ID": PROD, "ECONOVA_IT_FIRESTORE_APPROVAL": DEV,
           "ECONOVA_IT_FIREBASE_CREDENTIALS_FILE": _key_file(tmp_path)}
    env.update(over)
    return {k: v for k, v in env.items() if v is not None}


def test_firestore_live_accepts_only_a_fully_identified_dev_project(tmp_path):
    live = guards.firestore_live(_fs_env(tmp_path))
    assert live.project_id == DEV and live.credentials_path.endswith("dev-key.json")


@pytest.mark.parametrize("over,why", [
    ({"ECONOVA_IT_FIREBASE_PROJECT_ID": None}, "개발 프로젝트 id"),
    ({"ECONOVA_IT_FIREBASE_PROJECT_ID": "econova-20261110", "ECONOVA_IT_FIRESTORE_APPROVAL": "econova-20261110"},
     "dev/test"),
    ({"ECONOVA_IT_FIREBASE_PROJECT_ID": "Bad_Id!"}, "형식"),
    ({"ECONOVA_IT_PRODUCTION_PROJECT_ID": None}, "운영 프로젝트 id"),
    ({"ECONOVA_IT_PRODUCTION_PROJECT_ID": DEV}, "운영 프로젝트 id 와 같습니다"),
    ({"ECONOVA_IT_FIRESTORE_APPROVAL": None}, "APPROVAL"),
    ({"ECONOVA_IT_FIRESTORE_APPROVAL": "econova-dev-other"}, "APPROVAL"),
    ({"FIREBASE_CREDENTIALS_JSON": "{}"}, "FIREBASE_CREDENTIALS_JSON"),
    ({"RENDER": "1"}, "운영 환경"),
    ({"APP_ENV": "production"}, "운영 환경"),
    ({"ECONOVA_IT_FIREBASE_CREDENTIALS_FILE": "relative/key.json"}, "절대 경로"),
    ({"ECONOVA_IT_FIREBASE_CREDENTIALS_FILE": os.path.join(ROOT, "README.md")}, "저장소 안"),
    ({"ECONOVA_IT_FIREBASE_CREDENTIALS_FILE": "/nonexistent/econova/key.json"}, "파일이 없습니다"),
])
def test_firestore_live_refusals(tmp_path, over, why):
    with pytest.raises(guards.IntegrationRefused, match=why):
        guards.firestore_live(_fs_env(tmp_path, **over))


def test_firestore_key_file_contents_must_match(tmp_path):
    cases = [(dict(mode=0o644), "권한"), (dict(project=PROD), "project_id"),
             (dict(type="user"), "service_account"), (dict(client_email="x@other-dev.iam.gserviceaccount.com"), "소속")]
    for kw, why in cases:
        d = tmp_path / why
        d.mkdir()
        with pytest.raises(guards.IntegrationRefused, match=why):
            guards.firestore_live(_fs_env(tmp_path, ECONOVA_IT_FIREBASE_CREDENTIALS_FILE=_key_file(d, **kw)))
    env_file = tmp_path / ".env"
    env_file.write_text("x")
    os.chmod(env_file, 0o600)
    with pytest.raises(guards.IntegrationRefused, match=".env"):
        guards.firestore_live(_fs_env(tmp_path, ECONOVA_IT_FIREBASE_CREDENTIALS_FILE=str(env_file)))


def test_connected_project_marker_and_users_are_checked():
    marker = {"purpose": guards.MARKER_PURPOSE, "project_id": DEV}
    ok_users = [f"it-1-1@{guards.IT_EMAIL_DOMAIN}"]
    guards.check_connected(DEV, marker, ok_users, DEV)
    with pytest.raises(guards.IntegrationRefused, match="프로젝트"):
        guards.check_connected(PROD, marker, ok_users, DEV)
    with pytest.raises(guards.IntegrationRefused, match="표식"):
        guards.check_connected(DEV, None, ok_users, DEV)
    with pytest.raises(guards.IntegrationRefused, match="표식"):
        guards.check_connected(DEV, {**marker, "project_id": PROD}, ok_users, DEV)
    with pytest.raises(guards.IntegrationRefused, match="시험 계정이 아닌"):
        guards.check_connected(DEV, marker, ok_users + ["real.student@school.kr"], DEV)


def _ai_env(tmp_path, **over):
    key = tmp_path / "openai-dev.key"
    key.write_text("sk-dev-" + "A" * 40 + "\n")
    os.chmod(key, 0o600)
    env = {"ECONOVA_IT_OPENAI": "live", "ECONOVA_IT_OPENAI_KEY_FILE": str(key), "ECONOVA_IT_OPENAI_MODEL": "some-model",
           "ECONOVA_IT_OPENAI_MAX_REQUESTS": "8", "ECONOVA_IT_OPENAI_APPROVAL": "some-model:8"}
    env.update(over)
    return {k: v for k, v in env.items() if v is not None}


def test_openai_live_requires_key_file_model_budget_and_approval(tmp_path):
    live = guards.openai_live(_ai_env(tmp_path))
    assert (live.model, live.max_requests) == ("some-model", 8)
    assert guards.read_key(live.key_path).startswith("sk-dev-")
    for over, why in [({"OPENAI_API_KEY": "sk-x"}, "OPENAI_API_KEY"), ({"ECONOVA_IT_OPENAI_MODEL": None}, "모델"),
                      ({"ECONOVA_IT_OPENAI_MAX_REQUESTS": "0"}, "1~30"), ({"ECONOVA_IT_OPENAI_MAX_REQUESTS": "31"}, "1~30"),
                      ({"ECONOVA_IT_OPENAI_APPROVAL": "some-model:30"}, "APPROVAL"), ({"RENDER": "1"}, "운영 환경"),
                      ({"ECONOVA_IT_OPENAI_KEY_FILE": os.path.join(ROOT, "README.md")}, "저장소 안")]:
        with pytest.raises(guards.IntegrationRefused, match=why):
            guards.openai_live(_ai_env(tmp_path, **over))
    bad = tmp_path / "bad.key"
    bad.write_text("not a key")
    os.chmod(bad, 0o600)
    with pytest.raises(guards.IntegrationRefused, match="형식"):
        guards.read_key(str(bad))


class _Req:
    def __init__(self, body, url="https://api.openai.com/v1/chat/completions"):
        self.full_url, self.data = url, json.dumps(body, ensure_ascii=False).encode("utf-8")


def _body(**over):
    return {"model": "m", "messages": [{"role": "user", "content": "안녕"}], "max_completion_tokens": 300,
            "user": "u_" + "a" * 20, **over}


def test_guarded_transport_enforces_budget_and_checks_before_sending():
    sent = []

    def real(req, timeout=None):
        sent.append(req)
        from integration_tests.fake_backends import _Resp
        return _Resp(json.dumps({"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 1}}).encode())
    t = GuardedTransport(real, budget=1)
    t.forbidden = ["student@example.com"]
    for req, why in [(_Req(_body(), url="https://evil.example/v1"), "주소"),
                     (_Req(_body(messages=[{"role": "user", "content": "x" * 30000}])), "상한"),
                     (_Req(_body(max_completion_tokens=5000)), "출력 토큰"),
                     (_Req(_body(user="student@example.com")), "가명"),
                     (_Req(_body(messages=[{"role": "user", "content": "내 메일 student@example.com"}])), "보내면 안 되는")]:
        with pytest.raises(AssertionError, match=why):
            t(req)
    assert sent == [] and t.sent == 0                 # 거부한 요청은 하나도 나가지 않았다
    t(_Req(_body()))
    assert t.sent == 1 and t.usage == [{"prompt_tokens": 3, "completion_tokens": 1}]
    with pytest.raises(AssertionError, match="예산"):
        t(_Req(_body()))
    assert len(sent) == 1
    inspect_body(_Req(_body()).data, [])


def _run_integration(extra_env):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ECONOVA_IT_", "OPENAI", "FIREBASE", "DB_BACKEND"))}
    env.update(extra_env)
    return subprocess.run([sys.executable, "-m", "pytest", "integration_tests", "-q", "-p", "no:cacheprovider"],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)


def test_integration_suite_passes_in_fake_mode():
    r = _run_integration({})
    assert r.returncode == 0, r.stdout[-3000:]
    assert " passed" in r.stdout and "skipped" not in r.stdout   # fake 에서는 건너뛰는 시험 없음 (-q 라 머리말은 생략)


def test_live_mode_without_approval_stops_before_connecting(tmp_path):
    r = _run_integration({"ECONOVA_IT_FIRESTORE": "live"})
    assert r.returncode == 4 and "[연동 시험 거부]" in (r.stdout + r.stderr)
    r = _run_integration({"ECONOVA_IT_OPENAI": "live"})
    assert r.returncode == 4 and "[연동 시험 거부]" in (r.stdout + r.stderr)
    r = subprocess.run([sys.executable, "-m", "integration_tests.firestore_marker", "check"], cwd=ROOT,
                       env={k: v for k, v in os.environ.items() if not k.startswith("ECONOVA_IT_")},
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 4 and "[거부]" in r.stdout


# ------------------------------------------------------------- 프록시 홉 수 확인 화면
def test_request_diagnostics_is_off_by_default_and_admin_only(app, client, monkeypatch):
    from tests.conftest import login, signup
    from tests.test_phase7 import _make_admin
    signup(client, email="stu@example.com")
    login(client, email="stu@example.com")
    assert client.get("/admin/diagnostics/request").status_code == 404
    monkeypatch.setenv("ECONOVA_PROXY_DIAGNOSTICS", "1")
    assert client.get("/admin/diagnostics/request").status_code == 404          # 학생은 켜져 있어도 404
    admin = app.test_client()
    _make_admin(app, admin)
    monkeypatch.delenv("ECONOVA_PROXY_DIAGNOSTICS")
    assert admin.get("/admin/diagnostics/request").status_code == 404           # 꺼져 있으면 관리자도 404
    monkeypatch.setenv("ECONOVA_PROXY_DIAGNOSTICS", "1")
    res = admin.get("/admin/diagnostics/request", headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.9, 10.0.0.5"},
                    environ_base={"REMOTE_ADDR": "10.0.0.1"})
    html = res.get_data(as_text=True)
    assert res.status_code == 200 and res.headers["Cache-Control"] == "no-store"
    assert "10.0.0.1" in html and "203.0.113.9" in html and "1.2.3.4" in html and "항목 3개" in html


def test_ip_candidates_follow_the_right_end_of_the_chain(app):
    from econova import login_guard
    with app.test_request_context(headers={"X-Forwarded-For": "6.6.6.6, 198.51.100.7, 10.1.0.2"},
                                  environ_base={"REMOTE_ADDR": "10.1.0.3"}):
        got = {c["hops"]: c["ip"] for c in login_guard.ip_candidates()["candidates"]}
    assert got == {0: "10.1.0.3", 1: "10.1.0.2", 2: "198.51.100.7", 3: "6.6.6.6"}
    with app.test_request_context(headers={"X-Forwarded-For": "junk"}, environ_base={"REMOTE_ADDR": "10.1.0.3"}):
        got = {c["hops"]: c["ip"] for c in login_guard.ip_candidates()["candidates"]}
    assert got == {0: "10.1.0.3", 1: "10.1.0.3", 2: "10.1.0.3", 3: "10.1.0.3"}
