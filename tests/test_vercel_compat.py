"""Vercel (serverless) compatibility: production detection, answer-key bundle, cron endpoint, config files, migration 10.

Nothing here contacts Vercel or Google Cloud.
"""
import json
import os
import sqlite3

import pytest

import app as app_module
from econova import config, private_content, storage
from tests.conftest import ROOT


@pytest.fixture(autouse=True)
def _reset_bundle_cache():
    private_content._bundle_cache.update(source=None, keys=None)
    yield
    private_content._bundle_cache.update(source=None, keys=None)


# ------------------------------------------------------------------ production detection
@pytest.mark.parametrize("value,expected", [("production", True), ("preview", True), ("development", False), ("", False)])
def test_vercel_env_counts_as_production(monkeypatch, value, expected):
    for name in ("RENDER", "APP_ENV"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VERCEL_ENV", value)
    assert config.is_production() is expected


def test_vercel_production_requires_firestore_and_strong_secret(monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.delenv("DB_BACKEND", raising=False)
    with pytest.raises(config.ConfigError, match="DB_BACKEND"):
        config.db_backend()
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(config.ConfigError, match="SECRET_KEY"):
        config.secret_key()
    monkeypatch.setenv("ECONOVA_DEV_FIXTURES", "1")
    with pytest.raises(config.ConfigError, match="DEV_FIXTURES"):   # dev fixtures stop the app on Vercel
        config.dev_fixtures_enabled()


# ------------------------------------------------------------------ answer-key bundle
def _fixture_keys():
    keys_dir = private_content.FIXTURE_KEYS_DIR
    out = {}
    for name in sorted(os.listdir(keys_dir)):
        if name.endswith(private_content.KEYS_SUFFIX):
            with open(os.path.join(keys_dir, name), encoding="utf-8") as f:
                data = json.load(f)
            out[data["assessment_id"]] = data
    assert out
    return out


def test_bundle_round_trip_and_read_keys(monkeypatch):
    keys = _fixture_keys()
    text = private_content.encode_bundle(keys)
    assert text.isascii() and private_content.decode_bundle(text) == keys
    aid = next(iter(keys))
    monkeypatch.setenv("ECONOVA_PRIVATE_KEYS_BUNDLE", text)
    monkeypatch.delenv("ECONOVA_PRIVATE_CONTENT_DIR", raising=False)
    # bundle keys are checked exactly like folder keys (fixture keys are synthetic, so read them as non-fixture data)
    assert private_content.key_bundle()[aid] == keys[aid]
    with pytest.raises(private_content.KeysUnavailable, match="no key"):
        private_content.read_keys("not-a-real-assessment")


@pytest.mark.parametrize("text", ["", "not base64 !!", "aGVsbG8=", private_content.encode_bundle({}).replace("A", "B", 3)])
def test_bad_bundle_fails_closed(monkeypatch, text):
    with pytest.raises(private_content.KeysUnavailable):
        private_content.decode_bundle(text)


def test_wrong_kind_bundle_rejected():
    import base64
    import gzip
    raw = json.dumps({"schema_version": 1, "kind": "something_else", "keys": {}}).encode()
    with pytest.raises(private_content.KeysUnavailable, match="invalid format"):
        private_content.decode_bundle(base64.b64encode(gzip.compress(raw)).decode())


def test_secret_manager_source_is_used_and_cached(monkeypatch):
    keys = _fixture_keys()
    calls = []
    monkeypatch.delenv("ECONOVA_PRIVATE_KEYS_BUNDLE", raising=False)
    monkeypatch.setenv("ECONOVA_PRIVATE_KEYS_SECRET", "projects/p/secrets/keys/versions/1")
    monkeypatch.setattr(private_content, "_secret_manager_text",
                        lambda name: calls.append(name) or private_content.encode_bundle(keys))
    assert private_content.key_bundle() == keys
    assert private_content.key_bundle() == keys
    assert calls == ["projects/p/secrets/keys/versions/1"], "one Secret Manager read per instance"


def test_no_bundle_configured_means_folder_mode(monkeypatch):
    monkeypatch.delenv("ECONOVA_PRIVATE_KEYS_BUNDLE", raising=False)
    monkeypatch.delenv("ECONOVA_PRIVATE_KEYS_SECRET", raising=False)
    assert private_content.key_bundle() is None


def test_bundle_cli_refuses_to_write_inside_the_repository(sqlite_app):
    res = sqlite_app.test_cli_runner().invoke(args=["private-keys-bundle", "--output", os.path.join(ROOT, "keys-bundle.b64")])
    assert res.exit_code != 0 and "outside the repository" in res.output
    assert not os.path.exists(os.path.join(ROOT, "keys-bundle.b64"))


def test_bundle_cli_refuses_when_keys_are_missing(sqlite_app, monkeypatch, tmp_path):
    monkeypatch.setenv("ECONOVA_PRIVATE_CONTENT_DIR", str(tmp_path / "empty"))
    monkeypatch.delenv("ECONOVA_PRIVATE_KEYS_BUNDLE", raising=False)
    monkeypatch.delenv("ECONOVA_PRIVATE_KEYS_SECRET", raising=False)
    out = tmp_path / "bundle.b64"
    res = sqlite_app.test_cli_runner().invoke(args=["private-keys-bundle", "--output", str(out)])
    assert res.exit_code != 0 and "Not written" in res.output and not out.exists()


# ------------------------------------------------------------------ cron endpoint
def test_cron_endpoint_hidden_without_secret(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert client.get("/internal/cron/daily-cleanup").status_code == 404


def test_cron_endpoint_requires_bearer_secret(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "cron-secret-for-tests-0123456789")
    assert client.get("/internal/cron/daily-cleanup").status_code == 401
    assert client.get("/internal/cron/daily-cleanup", headers={"Authorization": "Bearer wrong"}).status_code == 401
    res = client.get("/internal/cron/daily-cleanup", headers={"Authorization": "Bearer cron-secret-for-tests-0123456789"})
    assert res.status_code == 200 and res.get_json()["ok"] is True
    again = client.get("/internal/cron/daily-cleanup", headers={"Authorization": "Bearer cron-secret-for-tests-0123456789"})
    assert again.status_code == 200, "repeat runs are safe (Vercel may deliver a cron twice)"


# ------------------------------------------------------------------ timing headers for cold-start measurement
def test_timing_headers_only_when_enabled(client, monkeypatch):
    monkeypatch.delenv("ECONOVA_TIMING_HEADERS", raising=False)
    assert "Server-Timing" not in client.get("/login").headers
    monkeypatch.setenv("ECONOVA_TIMING_HEADERS", "1")
    res = client.get("/login")
    assert res.headers["Server-Timing"].startswith("app;dur=") and "served=" in res.headers["X-Econova-Instance"]


# ------------------------------------------------------------------ client IP behind Vercel
def test_vercel_forwarded_for_with_one_trusted_hop(sqlite_app, monkeypatch):
    from econova import login_guard
    monkeypatch.setenv("ECONOVA_TRUSTED_PROXY_HOPS", "1")
    with sqlite_app.test_request_context("/login", headers={"X-Forwarded-For": "203.0.113.9"}, environ_base={"REMOTE_ADDR": "10.0.0.1"}):
        assert login_guard.client_ip() == "203.0.113.9"
    monkeypatch.setenv("ECONOVA_TRUSTED_PROXY_HOPS", "0")
    with sqlite_app.test_request_context("/login", headers={"X-Forwarded-For": "203.0.113.9"}, environ_base={"REMOTE_ADDR": "10.0.0.1"}):
        assert login_guard.client_ip() == "10.0.0.1"


# ------------------------------------------------------------------ deployment files
def test_vercel_config_files():
    with open(os.path.join(ROOT, "vercel.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg["git"]["deploymentEnabled"]["main"] is False, "legacy main must never auto-deploy as ECONOVA"
    assert cfg["functions"]["app.py"]["maxDuration"] <= 300
    for cron in cfg.get("crons", []):
        minute, hour, *rest = cron["schedule"].split()
        assert minute.isdigit() and hour.isdigit(), "Hobby allows at most one run per day"
        assert cron["path"] in {str(r) for r in app_module.app.url_map.iter_rules()}
    with open(os.path.join(ROOT, ".vercelignore"), encoding="utf-8") as f:
        ignored = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    for needed in ("tests/", "docs/", "tools/", "*.answers.json", "keys-bundle*", ".env", "content/dev_fixtures/"):
        assert needed in ignored
    assert "content/" not in ignored and "static/" not in ignored, "the app reads content/ and serves static/"
    with open(os.path.join(ROOT, ".python-version"), encoding="utf-8") as f:
        assert f.read().strip() == "3.12"
    assert hasattr(app_module, "app"), "Vercel finds the Flask instance named app in app.py"


def test_no_answer_keys_or_bundles_in_repository():
    bad = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".venv", ".git", "__pycache__", ".pytest_cache")]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), ROOT)
            if name.startswith("keys-bundle") or (name.endswith(".answers.json") and not rel.startswith("content/dev_fixtures/private/")):
                bad.append(rel)
    assert not bad, bad


# ------------------------------------------------------------------ migration 10 is additive
def test_migration_10_adds_identity_table_without_touching_users(tmp_path):
    db_path = tmp_path / "m.db"
    flask_app = app_module.app
    old = flask_app.config.get("DATABASE")
    flask_app.config["DATABASE"] = str(db_path)
    try:
        with flask_app.app_context():
            storage.init_db()
            storage.create_user("keep@example.org", "Keep", "hash")
            storage.init_db()     # running migrations again changes nothing
            assert storage.get_user_by_email("keep@example.org")["name"] == "Keep"
        con = sqlite3.connect(db_path)
        cols = {r[1] for r in con.execute("PRAGMA table_info(econ_user_identities)")}
        assert {"provider", "subject", "user_id", "email_at_link", "created_account"} <= cols
        assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        con.close()
    finally:
        flask_app.config["DATABASE"] = old
