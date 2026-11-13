"""저장소 계층: sqlite 스키마·마이그레이션·외래키, 가짜 Firestore 로 확인하는 Firestore 코드."""
import sqlite3

import pytest

from econova import storage

LEGACY_TABLES = {"courses", "curricula", "curriculum_items", "course_views"}


# ------------------------------------------------------------------ sqlite
def test_init_db_creates_schema_without_legacy_tables(sqlite_app):
    with sqlite_app.app_context():
        db = storage.get_db()
        tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"users", "schema_migrations", "econ_enrollments", "econ_lesson_progress"} <= tables
        assert not tables & LEGACY_TABLES                       # 9번 마이그레이션이 이전 LMS 테이블을 지운다
        assert [r["version"] for r in db.execute("SELECT version FROM schema_migrations ORDER BY version")] == \
            [v for v, _, _ in storage.SQLITE_MIGRATIONS]


def test_init_db_is_idempotent(sqlite_app):
    with sqlite_app.app_context():
        storage.init_db()
        assert storage.migrate_sqlite() == []  # 이미 적용된 번호는 다시 돌지 않는다
        db = storage.get_db()
        assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == len(storage.SQLITE_MIGRATIONS)


def test_foreign_keys_are_enforced(sqlite_app):
    with sqlite_app.app_context():
        db = storage.get_db()
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO econ_enrollments (user_id, course_id, selected_difficulty, enrolled_at, content_version) "
                       "VALUES (999, 'c02', 'beginner', '2026-11-13 00:00:00', 1)")   # 없는 사용자 → 외래키 위반


def test_upgrading_an_old_lms_database_drops_legacy_tables_but_keeps_users(sqlite_app, tmp_path, monkeypatch):
    """이전 LMS 시절 lms.db 를 올리면 대학 강의·커리큘럼 테이블은 지워지고(보존하지 않기로 결정) 계정은 남는다."""
    old = tmp_path / "old.db"
    con = sqlite3.connect(old)
    con.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'student', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE courses (id INTEGER PRIMARY KEY AUTOINCREMENT, university TEXT NOT NULL, title TEXT NOT NULL,
            description TEXT NOT NULL, level TEXT NOT NULL, url TEXT NOT NULL UNIQUE);
        CREATE TABLE curricula (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL, track TEXT NOT NULL, level INTEGER NOT NULL, hours_per_week INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO users (email, name, password_hash) VALUES ('old@example.com', 'Old', 'h');
        INSERT INTO courses (university, title, description, level, url) VALUES ('X', 'Old course', 'd', '입문', 'https://old.example.edu/');
        INSERT INTO curricula (user_id, title, track, level, hours_per_week) VALUES (1, 'old plan', 'econ', 0, 5);
    """)
    con.close()
    monkeypatch.setitem(sqlite_app.config, "DATABASE", str(old))
    with sqlite_app.app_context():
        storage.init_db()
        db = storage.get_db()
        tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert not tables & LEGACY_TABLES
        assert storage.get_user_by_email("old@example.com")["name"] == "Old"


# ------------------------------------------------------- Firestore (가짜)
def test_firestore_init_writes_nothing(firestore_app, fake_fs):
    """Firestore 에는 미리 채울 것이 없다 (이전 LMS 의 강의 목록 시드는 없앴다)."""
    assert fake_fs.docs == {}


def test_firestore_user_uses_email_as_id(firestore_app, fake_fs):
    with firestore_app.app_context():
        storage.create_user("s@example.com", "S", "hash")
        with pytest.raises(storage.DuplicateEmailError):
            storage.create_user("s@example.com", "S2", "hash2")
        user = storage.get_user_by_id("s@example.com")
        assert (user["id"], user["name"], user["role"]) == ("s@example.com", "S", "student")
        assert storage.get_user_by_email("nobody@example.com") is None
    assert fake_fs.dump("users")["s@example.com"]["password_hash"] == "hash"
