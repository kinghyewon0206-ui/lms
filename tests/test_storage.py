"""저장소 계층: sqlite 스키마·마이그레이션·외래키, 가짜 Firestore 로 확인하는 Firestore 코드."""
import sqlite3

import pytest

from econova import storage
from econova.legacy_catalog import SEED_COURSES


# ------------------------------------------------------------------ sqlite
def test_init_db_creates_schema_and_seeds(sqlite_app):
    with sqlite_app.app_context():
        db = storage.get_db()
        tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"users", "courses", "curricula", "curriculum_items", "course_views", "schema_migrations",
                "econ_enrollments", "econ_lesson_progress"} <= tables
        assert db.execute("SELECT COUNT(*) FROM courses WHERE curated = 1").fetchone()[0] == len(SEED_COURSES)
        assert [r["version"] for r in db.execute("SELECT version FROM schema_migrations ORDER BY version")] == [v for v, _, _ in storage.SQLITE_MIGRATIONS]


def test_init_db_is_idempotent(sqlite_app):
    with sqlite_app.app_context():
        storage.init_db()
        assert storage.migrate_sqlite() == []  # 이미 적용된 번호는 다시 돌지 않는다
        db = storage.get_db()
        assert db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == len(SEED_COURSES)
        assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == len(storage.SQLITE_MIGRATIONS)


def test_foreign_keys_are_enforced(sqlite_app):
    with sqlite_app.app_context():
        db = storage.get_db()
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO curricula (user_id, title, track, level, hours_per_week) VALUES (999, 't', 'econ', 0, 5)")


def test_deleting_curriculum_removes_items(sqlite_app):
    with sqlite_app.app_context():
        storage.create_user("a@example.com", "A", "hash")
        uid = storage.get_user_by_email("a@example.com")["id"]
        cid = storage.create_curriculum(uid, "t", "econ", 0, 5, "rule", "", "")
        storage.add_curriculum_item(cid, storage.curated_course_id("econ-micro"), 1, "r")
        storage.delete_curriculum(cid)
        db = storage.get_db()
        assert db.execute("SELECT COUNT(*) FROM curriculum_items").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM curricula").fetchone()[0] == 0


def test_upgrading_old_database_keeps_data(sqlite_app, tmp_path, monkeypatch):
    """예전 lms.db(hours·curated·추가 컬럼이 없던 시절)를 올려도 행이 지워지지 않는다. 예전 코드는 courses 를 DROP 했다."""
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
        CREATE TABLE curriculum_items (id INTEGER PRIMARY KEY AUTOINCREMENT,
            curriculum_id INTEGER NOT NULL REFERENCES curricula(id) ON DELETE CASCADE,
            course_id INTEGER NOT NULL REFERENCES courses(id), position INTEGER NOT NULL, reason TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0);
        INSERT INTO users (email, name, password_hash) VALUES ('old@example.com', 'Old', 'h');
        INSERT INTO courses (university, title, description, level, url) VALUES ('X', 'Old course', 'd', '입문', 'https://old.example.edu/');
        INSERT INTO curricula (user_id, title, track, level, hours_per_week) VALUES (1, 'old plan', 'econ', 0, 5);
        INSERT INTO curriculum_items (curriculum_id, course_id, position, reason, done) VALUES (1, 1, 1, 'why', 1);
    """)
    con.close()
    monkeypatch.setitem(sqlite_app.config, "DATABASE", str(old))
    with sqlite_app.app_context():
        storage.init_db()
        db = storage.get_db()
        assert tuple(db.execute("SELECT title, hours, curated FROM courses WHERE id = 1").fetchone()) ==("Old course", 40, 0)
        assert storage.get_user_by_email("old@example.com")["name"] == "Old"
        items = storage.list_curriculum_items(1)
        assert [(i["title"], i["done"], i["plan_weeks"], i["tips"]) for i in items] == [("Old course", 1, 0, "")]
        assert storage.list_curricula(1)[0]["source"] == "rule"


# ------------------------------------------------------- Firestore (가짜)
def test_firestore_seed_and_list_courses(firestore_app, fake_fs):
    courses = fake_fs.dump("courses")
    assert set(courses) == {c[0] for c in SEED_COURSES}
    with firestore_app.app_context():
        listed = storage.list_courses()
        assert [r["id"] for r in listed] == [c[0] for c in SEED_COURSES]  # seed_order 순서
        assert {r["university"] for r in storage.list_courses("MIT")} == {"MIT"}
        assert storage.curated_course_id("econ-micro") == "econ-micro"


def test_firestore_user_uses_email_as_id(firestore_app, fake_fs):
    with firestore_app.app_context():
        storage.create_user("s@example.com", "S", "hash")
        with pytest.raises(storage.DuplicateEmailError):
            storage.create_user("s@example.com", "S2", "hash2")
        user = storage.get_user_by_id("s@example.com")
        assert (user["id"], user["name"], user["role"]) == ("s@example.com", "S", "student")
        assert storage.get_user_by_email("nobody@example.com") is None
    assert fake_fs.dump("users")["s@example.com"]["password_hash"] == "hash"


def test_firestore_curriculum_lifecycle(firestore_app, fake_fs):
    with firestore_app.app_context():
        cid = storage.create_curriculum("s@example.com", "plan", "econ", 0, 5, "rule", "", "goal")
        for pos, slug in enumerate(("econ-micro", "finance"), start=1):
            storage.add_curriculum_item(cid, storage.curated_course_id(slug), pos, f"reason {pos}")
        items = storage.list_curriculum_items(cid)
        assert [i["title"] for i in items] == [SEED_COURSES[[c[0] for c in SEED_COURSES].index(s)][2]
                                               for s in ("econ-micro", "finance")]
        storage.toggle_curriculum_item(cid, items[0]["item_id"])
        row = storage.list_curricula("s@example.com")[0]
        assert (row["total"], row["done"]) == (2, 1)
        assert storage.get_curriculum(cid, "other@example.com") is None  # 남의 커리큘럼은 못 본다
        storage.delete_curriculum(cid)
        assert storage.list_curricula("s@example.com") == []
    assert not any(p[0] == "curricula" for p in fake_fs.docs)


def test_firestore_custom_course_is_created_once(firestore_app, fake_fs):
    item = {"slug": None, "title": "새 강의", "hours": 30,
            "custom": {"university": "Test", "description": "d", "level": "입문", "url": "https://test.example.edu/c"}}
    with firestore_app.app_context():
        first = storage.resolve_course_id(item)
        assert storage.resolve_course_id(item) == first
    assert fake_fs.dump("courses")[first]["curated"] is False


def test_firestore_course_views(firestore_app):
    with firestore_app.app_context():
        storage.bump_course_view("econ-micro")
        storage.bump_course_view("econ-micro")
        storage.bump_course_view("finance")
        assert storage.course_views() == {"econ-micro": 2, "finance": 1}
