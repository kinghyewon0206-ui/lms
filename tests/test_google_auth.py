"""Google Sign-In: server-side OAuth (code + PKCE), ID-token checks, account creation, linking and unlinking.

Google itself is never contacted: the token exchange and the signature check are replaced, and the claims that
come back are built here. Everything after the signature check (iss, aud, exp, nonce, sub, email_verified, account
rules) is the real code. Every account test runs on sqlite and on the fake Firestore.
"""
import time
import urllib.parse

import pytest

import app as app_module
from econova import google_auth, roles, storage
from tests.conftest import CSRF, login, set_csrf, signup

CLIENT_ID = "test-client-id.apps.googleusercontent.com"


@pytest.fixture(autouse=True)
def google_configured(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)


class FakeGoogle:
    """Stands in for Google's token endpoint and signature check. `claims` is what the next ID token says."""

    def __init__(self, monkeypatch):
        self.claims = {}
        self.exchanges = []
        self.verify_error = None
        monkeypatch.setattr(google_auth, "exchange_code", self._exchange)
        monkeypatch.setattr(google_auth, "_verify_signature_and_audience", self._verify)

    def _exchange(self, code, verifier, redirect_uri):
        self.exchanges.append({"code": code, "verifier": verifier, "redirect_uri": redirect_uri})
        return "fake.id.token"

    def _verify(self, token, client_id):
        if self.verify_error:
            raise ValueError(self.verify_error)
        return dict(self.claims)


@pytest.fixture
def google(monkeypatch):
    return FakeGoogle(monkeypatch)


def _claims(nonce, sub="google-sub-1", email="judge@example.org", **extra):
    base = {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "exp": int(time.time()) + 600, "nonce": nonce,
            "sub": sub, "email": email, "email_verified": True, "name": "Judge One"}
    base.update(extra)
    return base


def _start(client, path="/auth/google", method="get"):
    res = client.post(path, data={"csrf_token": CSRF}) if method == "post" else client.get(path)
    assert res.status_code in (302, 303), res.status_code
    url = urllib.parse.urlparse(res.headers["Location"])
    return url, dict(urllib.parse.parse_qsl(url.query))


def _sign_in(client, google, sub="google-sub-1", email="judge@example.org", path="/auth/google", method="get", **extra):
    _, params = _start(client, path, method)
    google.claims = _claims(params["nonce"], sub=sub, email=email, **extra)
    return client.get(f"/auth/google/callback?state={params['state']}&code=auth-code")


def _flashes(client):
    with client.session_transaction() as s:
        return " ".join(m for _, m in s.get("_flashes", []))


def _session_user(client):
    with client.session_transaction() as s:
        return s.get("user_id")


# ------------------------------------------------------------------ request to Google
def test_authorization_request_uses_minimal_scopes_state_nonce_and_pkce(client):
    url, params = _start(client)
    assert f"{url.scheme}://{url.netloc}{url.path}" == google_auth.AUTH_URL
    assert params["scope"] == "openid email profile"
    assert params["response_type"] == "code" and params["client_id"] == CLIENT_ID
    assert params["code_challenge_method"] == "S256" and len(params["code_challenge"]) >= 43
    assert len(params["state"]) >= 32 and len(params["nonce"]) >= 32 and params["state"] != params["nonce"]
    assert params["redirect_uri"].endswith("/auth/google/callback")
    assert "access_type" not in params   # no refresh token, no offline access


def test_verifier_sent_to_token_endpoint_matches_challenge(client, google):
    import base64
    import hashlib
    _, params = _start(client)
    google.claims = _claims(params["nonce"])
    client.get(f"/auth/google/callback?state={params['state']}&code=abc")
    verifier = google.exchanges[0]["verifier"]
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert expected == params["code_challenge"] and google.exchanges[0]["code"] == "abc"


def test_configured_redirect_uri_is_used_exactly(client, monkeypatch, google):
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://econova.example.test/auth/google/callback")
    _, params = _start(client)
    assert params["redirect_uri"] == "https://econova.example.test/auth/google/callback"
    google.claims = _claims(params["nonce"])
    client.get(f"/auth/google/callback?state={params['state']}&code=x")
    assert google.exchanges[0]["redirect_uri"] == "https://econova.example.test/auth/google/callback"


# ------------------------------------------------------------------ new account, returning user
def test_new_google_user_gets_a_student_account_without_admin(app, client, google):
    res = _sign_in(client, google)
    assert res.status_code in (302, 303) and res.headers["Location"].endswith("/dashboard")
    assert "created with Google" in _flashes(client)
    with app.app_context():
        user = storage.get_user_by_email("judge@example.org")
        assert user is not None and user["name"] == "Judge One"
        assert not roles.is_admin(user) and storage.get_admin_grant(user["id"]) is None
        identity = storage.get_identity("google", "google-sub-1")
        assert identity["user_id"] == user["id"] and identity["created_account"] is True
    assert _session_user(client) == user["id"]
    # the random password is unknown to everyone: password login does not work
    other = app.test_client()
    login(other, email="judge@example.org", password="")
    assert _session_user(other) is None


def test_returning_google_user_logs_into_the_same_account(app, google):
    first = app.test_client()
    _sign_in(first, google)
    uid = _session_user(first)
    second = app.test_client()
    res = _sign_in(second, google, email="judge@example.org")
    assert res.headers["Location"].endswith("/dashboard") and _session_user(second) == uid
    with app.app_context():
        assert storage.get_identity("google", "google-sub-1")["user_id"] == uid


def test_identity_is_keyed_by_sub_not_email(app, google):
    a = app.test_client()
    _sign_in(a, google, sub="sub-A", email="first@example.org")
    uid = _session_user(a)
    # the same Google account (sub) later reports a different email: still the same ECONOVA account
    b = app.test_client()
    _sign_in(b, google, sub="sub-A", email="renamed@example.org")
    assert _session_user(b) == uid
    with app.app_context():
        assert storage.get_user_by_email("renamed@example.org") is None


def test_google_login_never_grants_admin_even_for_an_existing_admin_email(app, google):
    c = app.test_client()
    signup(c, email="admin@example.org", name="Admin")
    with app.app_context():
        admin = storage.get_user_by_email("admin@example.org")
        storage.grant_admin(admin["id"], "Owner", "test")
    g2 = app.test_client()
    _sign_in(g2, google, sub="attacker-sub", email="admin@example.org")
    assert _session_user(g2) is None, "a matching email must not log in to the existing (admin) account"
    assert "already uses this email" in _flashes(g2)
    with app.app_context():
        assert storage.get_identity("google", "attacker-sub") is None


# ------------------------------------------------------------------ email collision: never merge automatically
def test_existing_password_account_is_not_merged_by_email(app, google):
    c = app.test_client()
    signup(c, email="student@example.com")
    g2 = app.test_client()
    res = _sign_in(g2, google, email="Student@Example.com")
    assert res.headers["Location"].endswith("/login") and _session_user(g2) is None
    assert "link Google from your Account page" in _flashes(g2)
    with app.app_context():
        assert storage.get_identity("google", "google-sub-1") is None
        assert storage.get_identity_for_user("google", storage.get_user_by_email("student@example.com")["id"]) is None


# ------------------------------------------------------------------ explicit linking
def _password_user(app, email="student@example.com"):
    c = app.test_client()
    signup(c, email=email)
    login(c, email=email)
    set_csrf(c)
    return c


def test_logged_in_user_can_link_and_then_sign_in_with_google(app, google):
    c = _password_user(app)
    uid = _session_user(c)
    res = _sign_in(c, google, email="different@gmail.example", path="/account/google/link", method="post")
    assert res.headers["Location"].endswith("/account") and "now linked" in _flashes(c)
    with app.app_context():
        identity = storage.get_identity("google", "google-sub-1")
        assert identity["user_id"] == uid and identity["created_account"] is False
    fresh = app.test_client()
    _sign_in(fresh, google, email="different@gmail.example")
    assert _session_user(fresh) == uid
    assert "different@gmail.example" in c.get("/account").get_data(as_text=True)


def test_link_requires_post_with_csrf_and_login(app, google):
    c = _password_user(app)
    assert c.get("/account/google/link").status_code == 405
    c.post("/account/google/link", data={"csrf_token": "wrong"})
    with c.session_transaction() as s:
        assert google_auth.SESSION_KEY not in s
    anon = app.test_client()
    set_csrf(anon)
    res = anon.post("/account/google/link", data={"csrf_token": CSRF})
    assert res.status_code in (302, 303) and "/login" in res.headers["Location"]


def test_google_account_linked_elsewhere_cannot_be_linked_again(app, google):
    owner = app.test_client()
    _sign_in(owner, google, sub="shared-sub", email="owner@example.org")
    c = _password_user(app)
    res = _sign_in(c, google, sub="shared-sub", email="owner@example.org", path="/account/google/link", method="post")
    assert res.headers["Location"].endswith("/account") and "different ECONOVA account" in _flashes(c)
    with app.app_context():
        assert storage.get_identity("google", "shared-sub")["user_id"] == _session_user(owner)


def test_second_google_account_cannot_be_linked_to_the_same_user(app, google):
    c = _password_user(app)
    _sign_in(c, google, sub="first", path="/account/google/link", method="post")
    res = c.post("/account/google/link", data={"csrf_token": CSRF})
    assert res.headers["Location"].endswith("/account") and "already linked" in _flashes(c)
    with app.app_context():
        assert storage.get_identity_for_user("google", _session_user(c))["subject"] == "first"


def test_link_callback_for_another_session_user_is_refused(app, google):
    c = _password_user(app)
    _, params = _start(c, "/account/google/link", "post")
    # the user logs out and someone else logs in on this browser before the callback returns
    with c.session_transaction() as s:
        pending = s[google_auth.SESSION_KEY]
    login(c, email="nobody@example.org")
    with c.session_transaction() as s:
        s[google_auth.SESSION_KEY] = pending
        s.pop("user_id", None)
    google.claims = _claims(params["nonce"])
    res = c.get(f"/auth/google/callback?state={params['state']}&code=x")
    assert "/login" in res.headers["Location"]
    with app.app_context():
        assert storage.get_identity("google", "google-sub-1") is None


def test_unlink_rules(app, google):
    c = _password_user(app)
    _sign_in(c, google, path="/account/google/link", method="post")
    set_csrf(c)
    c.post("/account/google/unlink", data={"csrf_token": CSRF})
    assert "unlinked" in _flashes(c)
    with app.app_context():
        assert storage.get_identity("google", "google-sub-1") is None
    # an account created with Google has no usable password, so it cannot be unlinked
    g2 = app.test_client()
    _sign_in(g2, google, sub="g-only", email="gonly@example.org")
    set_csrf(g2)
    g2.post("/account/google/unlink", data={"csrf_token": CSRF})
    assert "can't be unlinked" in _flashes(g2)
    with app.app_context():
        assert storage.get_identity("google", "g-only") is not None


def test_identity_uniqueness_in_storage(app):
    c = app.test_client()
    signup(c, email="one@example.org")
    signup(c, email="two@example.org")
    with app.app_context():
        u1, u2 = (storage.get_user_by_email(e)["id"] for e in ("one@example.org", "two@example.org"))
        storage.create_identity("google", "s1", u1)
        with pytest.raises(storage.IdentityConflict):
            storage.create_identity("google", "s1", u2)      # one Google account -> one ECONOVA account
        with pytest.raises(storage.IdentityConflict):
            storage.create_identity("google", "s2", u1)      # one ECONOVA account -> one Google account
        assert storage.get_identity("google", "s1")["user_id"] == u1 and storage.get_identity("google", "s2") is None


# ------------------------------------------------------------------ rejected callbacks
@pytest.mark.parametrize("case", ["state_mismatch", "no_pending", "expired", "replay"])
def test_state_problems_are_rejected(app, client, google, case):
    _, params = _start(client)
    google.claims = _claims(params["nonce"])
    state = params["state"]
    if case == "state_mismatch":
        state = "forged-" + state
    elif case == "no_pending":
        with client.session_transaction() as s:
            s.pop(google_auth.SESSION_KEY)
    elif case == "expired":
        with client.session_transaction() as s:
            s[google_auth.SESSION_KEY] = {**s[google_auth.SESSION_KEY], "at": int(time.time()) - google_auth.STATE_MAX_AGE - 5}
    res = client.get(f"/auth/google/callback?state={state}&code=x")
    if case == "replay":
        assert _session_user(client) is not None
        client.get("/logout")
        with client.session_transaction() as s:
            s.clear()
        res = client.get(f"/auth/google/callback?state={state}&code=x")
    assert res.headers["Location"].endswith("/login")
    assert _session_user(client) is None
    if case != "replay":
        assert google.exchanges == [], "the code must not be exchanged when the state check fails"


@pytest.mark.parametrize("bad", [
    {"nonce": "other-nonce"}, {"nonce": ""}, {"iss": "https://evil.example"}, {"aud": "someone-else"}, {"aud": "x" + CLIENT_ID}, {"aud": ["someone-else"]},
    {"exp": 1}, {"sub": ""}, {"email_verified": False}, {"email_verified": "false"}, {"email": "not-an-email"},
])
def test_bad_id_token_claims_are_rejected(app, client, google, bad):
    _, params = _start(client)
    google.claims = {**_claims(params["nonce"]), **bad}
    res = client.get(f"/auth/google/callback?state={params['state']}&code=x")
    assert res.headers["Location"].endswith("/login") and _session_user(client) is None
    with app.app_context():
        assert storage.get_user_by_email("judge@example.org") is None


def test_invalid_signature_is_rejected_with_a_generic_message(app, client, google):
    google.verify_error = "Could not verify token signature."
    res = _sign_in(client, google)
    assert res.headers["Location"].endswith("/login") and _session_user(client) is None
    msg = _flashes(client)
    assert "could not be completed" in msg and "signature" not in msg


def test_cancelled_sign_in(client, google):
    _, params = _start(client)
    res = client.get(f"/auth/google/callback?state={params['state']}&error=access_denied")
    assert res.headers["Location"].endswith("/login") and "cancelled" in _flashes(client)
    assert google.exchanges == []


def test_token_exchange_failure_does_not_leak_details(app, client, monkeypatch):
    def boom(code, verifier, redirect_uri):
        raise google_auth.GoogleAuthError("token endpoint returned HTTP 400")
    monkeypatch.setattr(google_auth, "exchange_code", boom)
    _, params = _start(client)
    res = client.get(f"/auth/google/callback?state={params['state']}&code=x")
    assert res.headers["Location"].endswith("/login") and "HTTP 400" not in _flashes(client)


# ------------------------------------------------------------------ configuration
def test_google_is_hidden_and_404_when_not_configured(app, client, monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID")
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET")
    for path in ("/login", "/signup"):
        assert "Continue with Google" not in client.get(path).get_data(as_text=True)
    assert client.get("/auth/google").status_code == 404
    assert client.get("/auth/google/callback?state=x&code=y").status_code == 404


def test_button_shown_when_configured(client):
    for path in ("/login", "/signup"):
        html = client.get(path).get_data(as_text=True)
        assert "Continue with Google" in html and 'href="/auth/google"' in html


def test_half_configured_or_insecure_settings_fail_startup_checks(monkeypatch):
    from econova import config
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET")
    with pytest.raises(config.ConfigError):
        google_auth.settings()
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "s")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(config.ConfigError, match="REDIRECT_URI"):
        google_auth.settings()
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://econova.example.test/auth/google/callback")
    with pytest.raises(config.ConfigError, match="https"):
        google_auth.settings()
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://econova.example.test/auth/google/callback")
    assert google_auth.settings()["redirect_uri"].startswith("https://")


def test_client_secret_never_rendered(client):
    for path in ("/login", "/signup", "/auth/google"):
        res = client.get(path)
        assert "test-client-secret" not in res.get_data(as_text=True)
        assert "test-client-secret" not in res.headers.get("Location", "")


def test_existing_password_login_unchanged(app, client):
    signup(client)
    res = login(client)
    assert res.status_code in (302, 303) and _session_user(client) is not None
    assert app_module.app is app


# ------------------------------------------------------------------ records and roles follow the account, not the provider
def test_admin_who_links_google_stays_admin_and_keeps_progress(app, google, fixtures_on):
    from tests.test_econova_routes import _enroll
    c = _password_user(app, email="owner-admin@example.org")
    uid = _session_user(c)
    with app.app_context():
        storage.grant_admin(uid, "Owner", "test")
    assert _enroll(c, "dev-f1").status_code in (302, 303)
    _sign_in(c, google, sub="admin-sub", email="admin.personal@gmail.example", path="/account/google/link", method="post")
    set_csrf(c)
    c.post("/logout", data={"csrf_token": CSRF})
    assert _session_user(c) is None
    g2 = app.test_client()
    _sign_in(g2, google, sub="admin-sub", email="admin.personal@gmail.example")
    assert _session_user(g2) == uid
    with app.app_context():
        user = storage.get_user_by_id(uid)
        assert roles.is_admin(user), "linking Google neither grants nor removes admin"
        assert storage.get_enrollment(uid, "dev-f1") is not None
        assert storage.get_user_by_email("admin.personal@gmail.example") is None, "no duplicate account"


def test_logout_then_google_login_returns_to_same_records(app, google, fixtures_on):
    from tests.test_econova_routes import _enroll
    c = app.test_client()
    _sign_in(c, google, sub="returning", email="returning@example.org")
    uid = _session_user(c)
    set_csrf(c)
    assert _enroll(c, "dev-f1").status_code in (302, 303)
    c.post("/logout", data={"csrf_token": CSRF})
    assert _session_user(c) is None and c.get("/dashboard").status_code in (302, 303)
    _sign_in(c, google, sub="returning", email="returning@example.org")
    assert _session_user(c) == uid
    with app.app_context():
        assert storage.get_enrollment(uid, "dev-f1") is not None


def test_session_is_replaced_on_google_login(app, client, google):
    with client.session_transaction() as s:
        s["planted"] = "attacker-value"
    _sign_in(client, google)
    with client.session_transaction() as s:
        assert "planted" not in s and google_auth.SESSION_KEY not in s
