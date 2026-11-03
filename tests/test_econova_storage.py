"""수강·진도 저장소 계약. 같은 테스트를 sqlite 와 가짜 Firestore 에서 모두 돌린다 (app fixture)."""
import sqlite3

import pytest

from econova import progress, storage

BOTH = ("material", "quiz")


def _user(app, email):
    """사용자를 만들고 저장소가 쓰는 user id 를 돌려준다 (sqlite: 정수, Firestore: 이메일)."""
    with app.app_context():
        storage.create_user(email, email.split("@")[0], "hash")
        return storage.get_user_by_email(email)["id"]


def test_enroll_and_prevent_duplicates(app):
    uid = _user(app, "a@example.com")
    with app.app_context():
        assert storage.enroll_course(uid, "dev-f1", "beginner", 1) is True
        assert storage.enroll_course(uid, "dev-f1", "advanced", 2) is False   # 두 번째는 아무것도 바꾸지 않는다
        e = storage.get_enrollment(uid, "dev-f1")
        assert (e["course_id"], e["selected_difficulty"], e["status"], e["content_version"]) == ("dev-f1", "beginner", "active", 1)
        assert e["enrolled_at"] is not None and e["completed_at"] is None
        assert len(storage.list_enrollments(uid)) == 1
        assert storage.get_enrollment(uid, "dev-f2") is None


def test_multiple_enrollments_in_order(app):
    uid = _user(app, "a@example.com")
    with app.app_context():
        for cid in ("dev-f2", "dev-f1"):
            storage.enroll_course(uid, cid, "beginner", 1)
        assert sorted(e["course_id"] for e in storage.list_enrollments(uid)) == ["dev-f1", "dev-f2"]


def test_enrollments_are_per_user(app):
    a, b = _user(app, "a@example.com"), _user(app, "b@example.com")
    with app.app_context():
        storage.enroll_course(a, "dev-f1", "beginner", 1)
        assert storage.list_enrollments(b) == []
        assert storage.set_enrollment_difficulty(b, "dev-f1", "advanced") is False   # 남의 수강 정보는 못 바꾼다
        assert storage.get_enrollment(a, "dev-f1")["selected_difficulty"] == "beginner"
        with pytest.raises(storage.NotEnrolledError):
            storage.update_lesson_progress(b, "dev-f1", "dev-f1-l1", BOTH, material_reviewed=True)
        assert storage.list_lesson_progress(a, "dev-f1") == {}


def test_difficulty_change(app):
    uid = _user(app, "a@example.com")
    with app.app_context():
        storage.enroll_course(uid, "dev-f1", "beginner", 1)
        assert storage.set_enrollment_difficulty(uid, "dev-f1", "intermediate") is True
        assert storage.get_enrollment(uid, "dev-f1")["selected_difficulty"] == "intermediate"


def test_progress_requires_enrollment(app):
    uid = _user(app, "a@example.com")
    with app.app_context(), pytest.raises(storage.NotEnrolledError):
        storage.update_lesson_progress(uid, "dev-f1", "dev-f1-l1", BOTH, material_reviewed=True)


def test_progress_events_and_independence(app):
    uid = _user(app, "a@example.com")
    with app.app_context():
        storage.enroll_course(uid, "dev-f1", "beginner", 1)
        storage.enroll_course(uid, "dev-f2", "beginner", 1)
        r = storage.update_lesson_progress(uid, "dev-f1", "dev-f1-l1", BOTH, material_reviewed=True)
        assert (r["status"], r["material_reviewed"], r["quiz_submitted"]) == ("in_progress", True, False)
        r = storage.update_lesson_progress(uid, "dev-f1", "dev-f1-l1", BOTH, quiz_submission_id="sub-1")
        assert (r["status"], r["quiz_submission_id"]) == ("completed", "sub-1") and r["completed_at"]

        stored = storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]
        assert {k: stored[k] for k in ("status", "material_reviewed", "quiz_submitted", "quiz_submission_id", "quiz_score")} == \
            {"status": "completed", "material_reviewed": True, "quiz_submitted": True, "quiz_submission_id": "sub-1",
             "quiz_score": None}
        assert set(stored) == set(progress.empty_record("", ""))   # 두 저장소가 같은 모양을 돌려준다
        assert storage.list_lesson_progress(uid, "dev-f2") == {}    # 다른 강좌는 그대로
        assert set(storage.list_all_lesson_progress(uid)) == {"dev-f1"}


def test_enrolling_later_does_not_touch_existing_progress(app):
    uid = _user(app, "a@example.com")
    with app.app_context():
        storage.enroll_course(uid, "dev-f1", "beginner", 1)
        storage.update_lesson_progress(uid, "dev-f1", "dev-f1-l1", BOTH, material_reviewed=True)
        before = storage.list_lesson_progress(uid, "dev-f1")
        storage.enroll_course(uid, "dev-f2", "advanced", 1)
        storage.enroll_course(uid, "dev-f1", "advanced", 1)   # 중복 신청도 진도를 지우지 않는다
        assert storage.list_lesson_progress(uid, "dev-f1") == before
        assert storage.get_enrollment(uid, "dev-f1")["selected_difficulty"] == "beginner"


# ------------------------------------------------------------- sqlite 전용
def test_sqlite_constraints(sqlite_app):
    uid = _user(sqlite_app, "a@example.com")
    with sqlite_app.app_context():
        db = storage.get_db()
        with pytest.raises(sqlite3.IntegrityError):   # 없는 사용자
            db.execute("INSERT INTO econ_enrollments (user_id, course_id, enrolled_at, content_version)"
                       " VALUES (999, 'dev-f1', '2026-01-01 00:00:00', 1)")
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError):   # 잘못된 난이도
            storage.enroll_course(uid, "dev-f1", "expert", 1)
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError):   # 잘못된 상태
            db.execute("INSERT INTO econ_enrollments (user_id, course_id, status, enrolled_at, content_version)"
                       " VALUES (?, 'dev-f1', 'gone', '2026-01-01 00:00:00', 1)", (uid,))
        db.rollback()


def test_sqlite_migration_2_on_existing_database(sqlite_app, tmp_path, monkeypatch):
    """Phase 2-0 시점(마이그레이션 1번까지)의 DB 에 2번을 적용해도 기존 데이터가 그대로다."""
    monkeypatch.setitem(sqlite_app.config, "DATABASE", str(tmp_path / "phase-2-0.db"))
    full = storage.SQLITE_MIGRATIONS
    with sqlite_app.app_context():
        storage.SQLITE_MIGRATIONS = full[:1]   # Phase 2-0 상태로 만든다
        try:
            storage.init_db()
        finally:
            storage.SQLITE_MIGRATIONS = full
        db = storage.get_db()
        storage.create_user("old@example.com", "Old", "h")
        uid = storage.get_user_by_email("old@example.com")["id"]
        cid = storage.create_curriculum(uid, "old plan", "econ", 0, 5, "rule", "", "")
        storage.add_curriculum_item(cid, storage.curated_course_id("econ-micro"), 1, "why")
        assert "econ_enrollments" not in {r[0] for r in db.execute("SELECT name FROM sqlite_master")}

        assert storage.migrate_sqlite() == [2]
        assert storage.migrate_sqlite() == []
        assert storage.get_user_by_email("old@example.com")["name"] == "Old"
        assert len(storage.list_curriculum_items(cid)) == 1
        assert db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] > 0
        assert storage.enroll_course(uid, "dev-f1", "beginner", 1) is True


def test_deleting_enrollment_cascades_progress(sqlite_app):
    uid = _user(sqlite_app, "a@example.com")
    with sqlite_app.app_context():
        storage.enroll_course(uid, "dev-f1", "beginner", 1)
        storage.update_lesson_progress(uid, "dev-f1", "dev-f1-l1", BOTH, material_reviewed=True)
        db = storage.get_db()
        db.execute("DELETE FROM econ_enrollments WHERE user_id = ?", (uid,))
        db.commit()
        assert db.execute("SELECT COUNT(*) FROM econ_lesson_progress").fetchone()[0] == 0


# ------------------------------------------------------------- Firestore 전용
def test_firestore_document_layout(firestore_app, fake_fs):
    with firestore_app.app_context():
        storage.create_user("a@example.com", "A", "h")
        storage.enroll_course("a@example.com", "dev-f1", "beginner", 1)
        storage.update_lesson_progress("a@example.com", "dev-f1", "dev-f1-l1", BOTH, material_reviewed=True)
    paths = {p for p in fake_fs.docs if p[0] == "users"}
    assert paths == {
        ("users", "a@example.com"),
        ("users", "a@example.com", "econ_enrollments", "dev-f1"),
        ("users", "a@example.com", "econ_enrollments", "dev-f1", "lessons", "dev-f1-l1"),
    }
    # 기존 컬렉션(courses, curricula 등)과 이름이 겹치지 않는다
    assert not any(p[0] in ("econ_enrollments", "lessons") for p in fake_fs.docs)
