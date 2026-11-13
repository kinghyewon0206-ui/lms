"""확인용(staging) 프록시 진단 (econova/proxy_diagnostics.py, staging_wsgi.py).

실제 앱을 그대로 쓰기 위해 별도 프로세스에서 staging_wsgi(또는 운영 시작점 app)를 import 해 test client 로 요청한다.
(이미 요청을 처리한 테스트용 앱에는 경로를 더할 수 없고, 환경변수 조합마다 깨끗한 프로세스가 필요하다.)
하위 프로세스는 실제 .env 를 읽지 않고, 외부 네트워크·Firebase 를 막고, 임시 sqlite 를 쓴다.
"""
import json
import os
import secrets
import subprocess
import sys

import pytest

from econova import config, proxy_diagnostics as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = pd.STAGING_SERVICE_NAME
TOKEN = secrets.token_urlsafe(32)

RUNNER = r'''
import json, os, sys, urllib.request
sys.path.insert(0, os.getcwd())
def refuse(*a, **k): raise RuntimeError("network blocked")
urllib.request.urlopen = refuse
import firebase_admin
firebase_admin.initialize_app = refuse
from econova import config
config.DOTENV_PATH = "/nonexistent/econova-no-dotenv"
entry = os.environ["ENTRY"]
try:
    mod = __import__(entry)
except config.ConfigError as exc:
    print(json.dumps({"config_error": str(exc)})); sys.exit(0)
app = mod.app
app.config["TESTING"] = True
from econova import storage
with app.app_context():
    storage.init_db()
out = {"has_route": any(r.rule == "/_staging/proxy-diagnostics" for r in app.url_map.iter_rules())}
c = app.test_client()
for i, req in enumerate(json.loads(os.environ["REQUESTS"])):
    r = c.get(req["path"], headers=req.get("headers", {}), environ_base={"REMOTE_ADDR": req.get("remote", "10.0.0.1")})
    body = r.get_data(as_text=True)
    out[str(i)] = {"status": r.status_code, "body": body, "json": r.get_json(silent=True),
                   "headers": {k: v for k, v in r.headers.items()}}
print(json.dumps(out))
'''


def run(entry="staging_wsgi", requests=(), tmp_path=None, **env):
    e = {k: v for k, v in os.environ.items()
         if not k.startswith(("ECONOVA_", "OPENAI", "FIREBASE", "RENDER", "DB_BACKEND", "SECRET_KEY", "APP_ENV"))}
    e.update(RENDER="true", DB_BACKEND="sqlite", SQLITE_PATH=str(tmp_path / "staging.db"), SECRET_KEY=secrets.token_hex(32),
             ECONOVA_AI_PROVIDER="off", ENTRY=entry, REQUESTS=json.dumps(list(requests)), PYTHONDONTWRITEBYTECODE="1")
    e.update({k: v for k, v in env.items() if v is not None})
    r = subprocess.run([sys.executable, "-c", RUNNER], cwd=ROOT, env=e, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def on(**extra):
    return {"ECONOVA_PROXY_DIAGNOSTICS": "1", "ECONOVA_PROXY_DIAGNOSTICS_TOKEN": TOKEN, "RENDER_SERVICE_NAME": NAME, **extra}


def get(headers=None, path=pd.PATH, remote="10.0.0.1"):
    return {"path": path, "headers": headers or {}, "remote": remote}


# ------------------------------------------------------------------ 설정 검사 (프로세스 없이)
def test_disabled_by_default():
    assert pd.settings({}) == (False, None)
    assert pd.settings({"ECONOVA_PROXY_DIAGNOSTICS": "0", "ECONOVA_PROXY_DIAGNOSTICS_TOKEN": TOKEN,
                        "RENDER_SERVICE_NAME": NAME}) == (False, None)


@pytest.mark.parametrize("token", [None, "", "short-token", "a" * 40, "ab" * 20, TOKEN + "!", "x" * 300])
def test_weak_or_missing_token_refuses_to_start(token):
    env = on(ECONOVA_PROXY_DIAGNOSTICS_TOKEN=token)
    env = {k: v for k, v in env.items() if v is not None}
    with pytest.raises(config.ConfigError, match="TOKEN"):
        pd.settings(env)


@pytest.mark.parametrize("service", [None, "", "lms", f"{NAME}-2", f"x-{NAME}", NAME.upper(), "staging", f"{NAME} "])
def test_exact_staging_service_name_required(service):
    env = {k: v for k, v in on(RENDER_SERVICE_NAME=service).items() if v is not None}
    with pytest.raises(config.ConfigError, match=NAME):
        pd.settings(env)


def test_correct_settings_enable():
    assert pd.settings(on()) == (True, TOKEN)


# ------------------------------------------------------------------ 실제 앱 (하위 프로세스)
def test_route_returns_404_when_disabled(tmp_path):
    out = run(tmp_path=tmp_path, requests=[get({pd.HEADER: TOKEN})], RENDER_SERVICE_NAME=NAME)
    assert out["has_route"] and out["0"]["status"] == 404


def test_misconfigured_staging_refuses_to_start(tmp_path):
    out = run(tmp_path=tmp_path, **on(RENDER_SERVICE_NAME="lms"))
    assert "config_error" in out and NAME in out["config_error"]


def test_production_entry_point_never_has_the_route(tmp_path):
    """운영 서비스(gunicorn app:app)는 진단 변수를 모두 넣어도 경로가 없다."""
    out = run(entry="app", tmp_path=tmp_path, requests=[get({pd.HEADER: TOKEN})], **on())
    assert out["has_route"] is False and out["0"]["status"] == 404


def test_token_checks(tmp_path):
    reqs = [get(), get({pd.HEADER: "wrong-" + TOKEN[6:]}), get({pd.HEADER: TOKEN[:-1]}),
            get({pd.HEADER: TOKEN}, path=pd.PATH + "?token=" + TOKEN), get({pd.HEADER: TOKEN}, path=pd.PATH + "?x=1"),
            get({"Authorization": "Bearer " + TOKEN}), get({pd.HEADER: TOKEN})]
    out = run(tmp_path=tmp_path, requests=reqs, **on())
    assert [out[str(i)]["status"] for i in range(len(reqs))] == [404, 404, 404, 404, 404, 404, 200]
    ok = out["6"]
    assert ok["headers"]["Cache-Control"] == "no-store" and ok["headers"]["Content-Type"].startswith("application/json")
    assert set(ok["json"]) == {"remote_addr", "x_forwarded_for", "x_forwarded_for_count", "x_forwarded_proto", "ip_headers",
                               "candidates", "configured_hops", "resolved_client_ip"}


def test_no_credential_cookie_or_session_leakage(tmp_path):
    headers = {pd.HEADER: TOKEN, "Cookie": "session=SESSIONSECRETVALUE123; econova_known_login=DEVICECOOKIE456",
               "Authorization": "Bearer AUTHSECRET789", "X-Forwarded-For": "198.51.100.7",
               "X-Real-IP": "not-an-ip-SECRET", "CF-Connecting-IP": "198.51.100.8"}
    out = run(tmp_path=tmp_path, requests=[get(headers)], **on())
    r = out["0"]
    assert r["status"] == 200
    for secret in (TOKEN, "SESSIONSECRETVALUE123", "DEVICECOOKIE456", "AUTHSECRET789", "not-an-ip-SECRET"):
        assert secret not in r["body"]
    assert "Set-Cookie" not in r["headers"]
    assert r["json"]["ip_headers"] == {"X-Real-IP": None, "CF-Connecting-IP": "198.51.100.8"}


@pytest.mark.parametrize("hops,expected", [("0", "10.0.0.1"), ("1", "203.0.113.9"), ("2", "198.51.100.20"),
                                           ("3", "10.0.0.1")])
def test_spoofed_forwarded_header_and_hop_configuration(tmp_path, hops, expected):
    """클라이언트가 왼쪽에 넣은 값(6.6.6.6)은 홉 수를 크게 잡지 않는 한 쓰이지 않는다. 목록이 짧으면 직접 연결 주소."""
    xff = "6.6.6.6, 198.51.100.20, 203.0.113.9" if hops != "3" else "198.51.100.20, 203.0.113.9"
    out = run(tmp_path=tmp_path, requests=[get({pd.HEADER: TOKEN, "X-Forwarded-For": xff})],
              ECONOVA_TRUSTED_PROXY_HOPS=hops, **on())
    j = out["0"]["json"]
    assert j["configured_hops"] == int(hops) and j["resolved_client_ip"] == expected
    assert [c["hops"] for c in j["candidates"]] == [0, 1, 2, 3]


def test_token_grants_no_admin_or_user_access(tmp_path):
    reqs = [get({pd.HEADER: TOKEN}, path="/admin/content"), get({pd.HEADER: TOKEN}, path="/admin/diagnostics/request"),
            get({pd.HEADER: TOKEN}, path="/dashboard"), get({pd.HEADER: TOKEN}, path="/report")]
    out = run(tmp_path=tmp_path, requests=reqs, **on())
    for i in range(len(reqs)):
        assert out[str(i)]["status"] in (302, 404), (reqs[i]["path"], out[str(i)]["status"])
        if out[str(i)]["status"] == 302:
            assert "/login" in out[str(i)]["headers"]["Location"]


def test_staging_app_keeps_normal_behaviour_and_production_guards(tmp_path):
    """진단을 켠 확인용 앱도 운영 모드 규칙은 그대로: 개발용 강좌·모의 AI 를 켜면 시작 거부, 화면은 정상."""
    out = run(tmp_path=tmp_path, requests=[get(path="/login"), get(path="/courses/dev-f1")], **on())
    assert out["0"]["status"] == 200 and out["1"]["status"] in (302, 404)   # 개발용 강좌는 보이지 않음 (비로그인은 로그인으로)
    for extra in ({"ECONOVA_DEV_FIXTURES": "1"}, {"ECONOVA_AI_PROVIDER": "mock"}):
        e = {k: v for k, v in os.environ.items() if not k.startswith(("ECONOVA_", "RENDER", "DB_BACKEND"))}
        e.update(RENDER="true", DB_BACKEND="sqlite", SQLITE_PATH=str(tmp_path / "x.db"), SECRET_KEY=secrets.token_hex(32),
                 **on(), **extra)
        code = ("import sys,os; sys.path.insert(0, os.getcwd()); from econova import config; "
                "config.DOTENV_PATH='/nonexistent'; import staging_wsgi; "
                "from econova import content; from econova.ai import client; content.get_catalog(); client.settings()")
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=e, capture_output=True, text=True, timeout=120)
        assert r.returncode != 0 and "ConfigError" in r.stderr
