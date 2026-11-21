"""Google 로그인 (OAuth 2.0 인가 코드 흐름 + PKCE, 서버에서 ID 토큰 검증).

- 범위는 openid email profile 만 요청한다 (다른 Google API 권한 없음).
- 시작할 때 state(위조 요청 차단)·nonce(토큰 재사용 차단)·PKCE code_verifier 를 세션에 저장하고, 콜백에서 모두 확인한다.
- ID 토큰은 google-auth 로 서명·aud(우리 클라이언트 id)·iss(accounts.google.com)·exp 를 검증하고, nonce·email_verified 를 따로 확인한다.
- 공급자 계정은 이메일이 아니라 Google 의 고정 id (sub) 로 식별한다. 이메일이 같다고 계정을 자동으로 합치지 않는다.
- 설정: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET (둘 다 있어야 켜짐), 선택 GOOGLE_OAUTH_REDIRECT_URI.
  클라이언트 비밀값은 환경변수로만 받고 로그·화면에 쓰지 않는다.
"""
import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from econova import config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
SCOPES = "openid email profile"
SESSION_KEY = "google_oauth"
STATE_MAX_AGE = 600          # 시작 후 10분 안에 돌아와야 한다
PROVIDER = "google"


class GoogleAuthError(Exception):
    """사용자에게는 일반 안내만 보이고, 이유는 서버 로그에만 남긴다 (토큰·비밀값은 넣지 않는다)."""


def settings():
    client_id = config.env("GOOGLE_OAUTH_CLIENT_ID").strip()
    secret = config.env("GOOGLE_OAUTH_CLIENT_SECRET").strip()
    redirect = config.env("GOOGLE_OAUTH_REDIRECT_URI").strip()
    if bool(client_id) != bool(secret):
        raise config.ConfigError("Set both GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET (or neither).")
    if redirect and config.is_production() and not redirect.startswith("https://"):
        raise config.ConfigError("GOOGLE_OAUTH_REDIRECT_URI must use https in production.")
    if client_id and config.is_production() and not redirect:
        raise config.ConfigError("Set GOOGLE_OAUTH_REDIRECT_URI (the exact callback URL registered in Google Cloud) in production.")
    return {"client_id": client_id, "client_secret": secret, "redirect_uri": redirect}


def enabled():
    s = settings()
    return bool(s["client_id"] and s["client_secret"])


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def begin(session, intent, redirect_uri, user_id=None):
    """Google 로그인 화면 주소를 만든다. intent: 'login'(로그인·가입) 또는 'link'(로그인한 계정에 연결)."""
    s = settings()
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    session[SESSION_KEY] = {"state": state, "nonce": nonce, "verifier": verifier, "intent": intent,
                            "user_id": user_id, "redirect_uri": redirect_uri, "at": int(time.time())}
    params = {"client_id": s["client_id"], "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPES,
              "state": state, "nonce": nonce, "prompt": "select_account",
              "code_challenge": _b64url(hashlib.sha256(verifier.encode("ascii")).digest()), "code_challenge_method": "S256"}
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def take_pending(session, returned_state):
    """세션에 저장한 시작 정보를 꺼낸다 (한 번만 쓸 수 있다). state 가 다르거나 오래됐으면 GoogleAuthError."""
    pending = session.pop(SESSION_KEY, None)
    if not pending or not returned_state:
        raise GoogleAuthError("no pending Google sign-in in this session")
    if not secrets.compare_digest(str(pending.get("state", "")), str(returned_state)):
        raise GoogleAuthError("state mismatch")
    if int(time.time()) - int(pending.get("at", 0)) > STATE_MAX_AGE:
        raise GoogleAuthError("sign-in attempt expired")
    return pending


def exchange_code(code, verifier, redirect_uri):
    """인가 코드를 ID 토큰으로 바꾼다 (서버 대 서버). 반환: id_token 문자열."""
    s = settings()
    body = urllib.parse.urlencode({"code": code, "client_id": s["client_id"], "client_secret": s["client_secret"],
                                   "redirect_uri": redirect_uri, "grant_type": "authorization_code",
                                   "code_verifier": verifier}).encode("ascii")
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:      # 응답 본문은 기록하지 않는다
        raise GoogleAuthError(f"token endpoint returned HTTP {exc.code}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise GoogleAuthError(f"token endpoint unreachable ({type(exc).__name__})")
    token = data.get("id_token") if isinstance(data, dict) else None
    if not token:
        raise GoogleAuthError("no id_token in token response")
    return token


def _verify_signature_and_audience(token, client_id):
    """google-auth 로 서명(Google 공개키), aud, exp, iss 를 검증한다. 테스트에서는 이 함수를 바꿔 끼운다."""
    from google.auth.transport import requests as ga_requests
    from google.oauth2 import id_token as ga_id_token
    return ga_id_token.verify_oauth2_token(token, ga_requests.Request(), audience=client_id, clock_skew_in_seconds=10)


def verify_id_token(token, nonce):
    """검증된 클레임을 돌려준다. 실패하면 GoogleAuthError."""
    client_id = settings()["client_id"]
    try:
        claims = _verify_signature_and_audience(token, client_id)
    except ValueError as exc:   # 서명·만료·aud 가 틀리면 google-auth 가 ValueError 를 낸다
        raise GoogleAuthError(f"invalid ID token ({str(exc)[:80]})")
    if claims.get("iss") not in ISSUERS:
        raise GoogleAuthError("unexpected issuer")
    aud = claims.get("aud")
    if not (aud == client_id or (isinstance(aud, list) and client_id in aud)):   # 문자열이면 정확히 같아야 한다 (부분 일치 금지)
        raise GoogleAuthError("unexpected audience")
    if int(claims.get("exp", 0)) < int(time.time()) - 10:
        raise GoogleAuthError("token expired")
    if not nonce or not secrets.compare_digest(str(claims.get("nonce", "")), str(nonce)):
        raise GoogleAuthError("nonce mismatch")
    if not str(claims.get("sub", "")).strip():
        raise GoogleAuthError("missing subject")
    if claims.get("email_verified") is not True and str(claims.get("email_verified")).lower() != "true":
        raise GoogleAuthError("email not verified by Google")
    return claims
