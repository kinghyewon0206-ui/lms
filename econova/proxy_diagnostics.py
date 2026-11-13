"""Render 확인용(staging) 서비스 전용 프록시 진단 (Phase 8B-2). 운영 앱(app:app)에는 붙지 않는다.

staging_wsgi.py 만 install() 을 부른다. 운영 서비스는 `gunicorn app:app` 으로 시작하므로 환경변수를 어떻게 바꿔도 이 경로가
생기지 않는다. 확인용 서비스는 `gunicorn staging_wsgi:app` 으로 시작한다 (같은 앱 + 이 경로 하나).

켜지는 조건 (모두 만족해야 함)
- ECONOVA_PROXY_DIAGNOSTICS=1                  (없으면 경로가 항상 404)
- ECONOVA_PROXY_DIAGNOSTICS_TOKEN              32자 이상, 영문·숫자·-·_, 서로 다른 문자 16개 이상 (예: secrets.token_urlsafe(32))
- RENDER_SERVICE_NAME == STAGING_SERVICE_NAME  Render 가 넣어 주는 서비스 이름이 정확히 같아야 함 (부분 일치 아님)
켜려고 했는데 토큰·서비스 이름이 맞지 않으면 시작을 거부한다 (조용히 열리지 않게).

요청: GET /_staging/proxy-diagnostics, 헤더 X-Econova-Diagnostics: <토큰>. 토큰 비교는 hmac.compare_digest.
쿼리 문자열이 하나라도 있으면 404 (토큰을 주소에 넣는 실수를 막음). 틀리거나 없으면 404.
응답(JSON, no-store): 직접 연결 주소, X-Forwarded-For 목록, 홉 수별 후보, 지금 설정으로 판정한 클라이언트 IP, 프록시가 붙이는
IP 헤더 몇 개(IP 형식만). 쿠키·Authorization·세션·사용자 정보·토큰은 넣지 않는다. 아무것도 기록(log)하지 않는다.
"""
import hmac
import ipaddress
import os
import re

from flask import abort, jsonify, request

from econova import config, login_guard

STAGING_SERVICE_NAME = "econova-proxy-staging"
PATH = "/_staging/proxy-diagnostics"
HEADER = "X-Econova-Diagnostics"
IP_HEADERS = ("X-Real-IP", "True-Client-IP", "CF-Connecting-IP")   # 값이 IP 형식일 때만 보여 준다
_TOKEN = re.compile(r"[A-Za-z0-9_\-]{32,256}")
MAX_CHAIN = 10


def settings(environ=None):
    """(켜졌는가, 토큰). 켜려고 했는데 조건이 틀리면 ConfigError."""
    environ = os.environ if environ is None else environ
    if (environ.get("ECONOVA_PROXY_DIAGNOSTICS") or "").strip() != "1":
        return False, None
    token = (environ.get("ECONOVA_PROXY_DIAGNOSTICS_TOKEN") or "").strip()
    if not _TOKEN.fullmatch(token) or len(set(token)) < 16:
        raise config.ConfigError("ECONOVA_PROXY_DIAGNOSTICS_TOKEN 은 32자 이상의 무작위 값이어야 합니다 "
                                 "(예: python -c \"import secrets; print(secrets.token_urlsafe(32))\").")
    service = environ.get("RENDER_SERVICE_NAME") or ""
    if service != STAGING_SERVICE_NAME:
        raise config.ConfigError(f"프록시 진단은 Render 서비스 '{STAGING_SERVICE_NAME}' 에서만 켤 수 있습니다.")
    return True, token


def _ip_or_none(value):
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return None


def _authorized(token):
    if token is None or request.query_string:
        return False
    given = request.headers.get(HEADER, "")
    return hmac.compare_digest(given.encode("utf-8"), token.encode("utf-8"))


def report():
    """지금 요청의 IP 판정 정보 (최소한만)."""
    info = login_guard.ip_candidates()
    chain = [c[:64] for c in info["chain"]][-MAX_CHAIN:]
    return {
        "remote_addr": info["remote_addr"],
        "x_forwarded_for": chain,
        "x_forwarded_for_count": len(info["chain"]),
        "x_forwarded_proto": (request.headers.get("X-Forwarded-Proto") or "")[:10] or None,
        "ip_headers": {h: _ip_or_none(request.headers.get(h)) for h in IP_HEADERS if request.headers.get(h)},
        "candidates": [{"hops": c["hops"], "ip": c["ip"]} for c in info["candidates"]],
        "configured_hops": info["configured"],
        "resolved_client_ip": login_guard.client_ip(),   # 로그인 제한이 실제로 쓰는 값
    }


def install(app, environ=None):
    """확인용 진단 경로를 붙인다. 꺼져 있어도 경로는 있지만 항상 404."""
    enabled, token = settings(environ)

    @app.route(PATH, methods=["GET"])
    def staging_proxy_diagnostics():
        if not enabled or not _authorized(token):
            abort(404)
        resp = jsonify(report())
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Robots-Tag"] = "noindex"
        return resp

    return enabled
