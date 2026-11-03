"""저장소 계층: 로컬·테스트는 sqlite3 파일, 운영은 Firebase Firestore.

어느 쪽을 쓸지는 DB_BACKEND 설정으로만 정한다 (econova.config.db_backend).
Render 무료 플랜은 재배포할 때마다 디스크가 초기화되는데, Firestore 는 서버 밖에 저장되니
재배포해도 회원 데이터가 지워지지 않는다.

라우트(app.py)는 이 모듈의 함수만 부르고, sqlite / Firestore 차이는 여기 안에서만 다룬다.
ECONOVA 의 새 데이터(수강, 진도 등)도 같은 방식으로 이 계층에 추가한다.
"""
import datetime
import hashlib
import json
import sqlite3

import firebase_admin
from firebase_admin import credentials as fb_credentials, firestore as fb_firestore
from flask import current_app, g

from econova import config
from econova.legacy_catalog import SEED_COURSES


def init_app(app):
    """Flask 앱에 요청이 끝날 때 sqlite 연결을 닫는 훅을 건다."""
    app.teardown_appcontext(close_db)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")  # sqlite 는 연결마다 켜야 외래키 제약이 실제로 검사된다
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


class DuplicateEmailError(Exception):
    """이미 가입된 이메일로 회원가입을 시도했을 때."""


def using_firestore():
    return config.db_backend() == "firestore"


_fb_app = None


def _fs():
    """Firestore 클라이언트. Firebase 앱은 프로세스당 한 번만 초기화해야 해서 전역에 캐시한다."""
    global _fb_app
    if not using_firestore():  # 운영 키가 .env 에 있어도 DB_BACKEND=firestore 가 아니면 절대 접속하지 않는다
        raise config.ConfigError("DB_BACKEND 가 firestore 가 아닌데 Firestore 에 접속하려고 했습니다.")
    if _fb_app is None:
        cred = fb_credentials.Certificate(json.loads(config.env("FIREBASE_CREDENTIALS_JSON")))
        _fb_app = firebase_admin.initialize_app(cred)
    return fb_firestore.client(_fb_app)


def create_user(email, name, password_hash):
    """새 사용자를 만든다. 이메일이 이미 있으면 DuplicateEmailError."""
    if using_firestore():
        db = _fs()
        ref = db.collection("users").document(email)

        @fb_firestore.transactional
        def _txn(transaction):
            if ref.get(transaction=transaction).exists:
                raise DuplicateEmailError()
            transaction.set(ref, {
                "email": email, "name": name, "password_hash": password_hash,
                "role": "student", "created_at": fb_firestore.SERVER_TIMESTAMP,
            })

        _txn(db.transaction())
        return
    try:
        get_db().execute(
            "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)", (email, name, password_hash)
        )
        get_db().commit()
    except sqlite3.IntegrityError:
        raise DuplicateEmailError()


def get_user_by_email(email):
    if using_firestore():
        snap = _fs().collection("users").document(email).get()
        if not snap.exists:
            return None
        return {**snap.to_dict(), "id": snap.id}
    return get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def get_user_by_id(uid):
    # Firestore 에서는 이메일을 사용자 문서의 id 로 쓴다 (자동으로 유일해지고, 이메일로 바로 조회 가능).
    return get_user_by_email(uid) if using_firestore() else get_db().execute(
        "SELECT * FROM users WHERE id = ?", (uid,)
    ).fetchone()


def list_courses(university=None):
    """curated=1 인(직접 고른) 강의 목록. university 를 주면 그 대학만."""
    if using_firestore():
        rows = [{**d.to_dict(), "id": d.id} for d in _fs().collection("courses").where("curated", "==", True).stream()]
        rows.sort(key=lambda r: r.get("seed_order", 0))
        return [r for r in rows if r["university"] == university] if university else rows
    db = get_db()
    if university:
        return db.execute(
            "SELECT * FROM courses WHERE curated = 1 AND university = ? ORDER BY id", (university,)
        ).fetchall()
    return db.execute("SELECT * FROM courses WHERE curated = 1 ORDER BY id").fetchall()


def curated_course_id(slug):
    """SEED_COURSES 의 slug 에 해당하는 courses 문서/행의 id."""
    if using_firestore():
        return slug
    url = next(c[6] for c in SEED_COURSES if c[0] == slug)
    return get_db().execute("SELECT id FROM courses WHERE url = ?", (url,)).fetchone()["id"]


def resolve_course_id(item):
    """커리큘럼 항목이 가리키는 courses 문서/행의 id. 목록 밖(AI 가 찾은) 강의는 없으면 새로 만든다."""
    if item["slug"]:
        return curated_course_id(item["slug"])

    c = item["custom"]
    url = c["url"]
    if using_firestore():
        cid = hashlib.sha1(url.encode()).hexdigest()[:16]
        ref = _fs().collection("courses").document(cid)
        if not ref.get().exists:
            ref.set({"university": c["university"], "title": item["title"], "description": c["description"],
                      "level": c["level"], "hours": item["hours"], "url": url, "curated": False})
        return cid

    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO courses (university, title, description, level, hours, url, curated)"
        " VALUES (?, ?, ?, ?, ?, ?, 0)",
        (c["university"], item["title"], c["description"], c["level"], item["hours"], url),
    )
    return db.execute("SELECT id FROM courses WHERE url = ?", (url,)).fetchone()["id"]


def bump_course_view(slug):
    """강의를 본 횟수를 1 올린다. (인기 순위에 쓴다)"""
    if using_firestore():
        _fs().collection("course_views").document(slug).set({"views": fb_firestore.Increment(1)}, merge=True)
        return
    db = get_db()
    db.execute(
        "INSERT INTO course_views (slug, views) VALUES (?, 1) ON CONFLICT(slug) DO UPDATE SET views = views + 1", (slug,)
    )
    db.commit()


def course_views():
    """{slug: 조회수}"""
    if using_firestore():
        return {d.id: int((d.to_dict() or {}).get("views", 0)) for d in _fs().collection("course_views").stream()}
    return {r["slug"]: r["views"] for r in get_db().execute("SELECT slug, views FROM course_views")}


def create_curriculum(user_id, title, track, level, hours_per_week, source, note, goal_text,
                       days_per_week=0, hours_per_day=0):
    if using_firestore():
        ref = _fs().collection("curricula").document()
        ref.set({
            "user_id": user_id, "title": title, "track": track, "level": level,
            "hours_per_week": hours_per_week, "source": source, "note": note, "goal_text": goal_text,
            "days_per_week": days_per_week, "hours_per_day": hours_per_day,
            "created_at": fb_firestore.SERVER_TIMESTAMP,
        })
        return ref.id
    db = get_db()
    cur = db.execute(
        "INSERT INTO curricula (user_id, title, track, level, hours_per_week, source, note, goal_text,"
        " days_per_week, hours_per_day) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, title, track, level, hours_per_week, source, note, goal_text, days_per_week, hours_per_day),
    )
    db.commit()
    return cur.lastrowid


def add_curriculum_item(cid, course_id, position, reason, weeks=0, tips=""):
    if using_firestore():
        _fs().collection("curricula").document(cid).collection("items").document().set({
            "course_id": course_id, "position": position, "reason": reason, "done": False,
            "weeks": weeks, "tips": tips,
        })
        return
    get_db().execute(
        "INSERT INTO curriculum_items (curriculum_id, course_id, position, reason, weeks, tips)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (cid, course_id, position, reason, weeks, tips),
    )
    get_db().commit()


def list_curricula(user_id):
    """사용자의 커리큘럼 목록 (강의 개수·완료 개수 포함), 최신순."""
    if using_firestore():
        db = _fs()
        rows = []
        for d in db.collection("curricula").where("user_id", "==", user_id).stream():
            data = d.to_dict()
            items = [i.to_dict() for i in db.collection("curricula").document(d.id).collection("items").stream()]
            rows.append({**data, "id": d.id, "total": len(items), "done": sum(1 for i in items if i.get("done"))})
        rows.sort(key=lambda r: r.get("created_at") or datetime.datetime.min, reverse=True)
        return rows
    return get_db().execute(
        """
        SELECT c.*, COUNT(i.id) AS total, COALESCE(SUM(i.done), 0) AS done
        FROM curricula c LEFT JOIN curriculum_items i ON i.curriculum_id = c.id
        WHERE c.user_id = ? GROUP BY c.id ORDER BY c.id DESC
        """,
        (user_id,),
    ).fetchall()


def get_curriculum(cid, user_id):
    """본인 소유일 때만 돌려준다."""
    if using_firestore():
        snap = _fs().collection("curricula").document(cid).get()
        if not snap.exists or snap.to_dict().get("user_id") != user_id:
            return None
        return {**snap.to_dict(), "id": snap.id}
    return get_db().execute(
        "SELECT * FROM curricula WHERE id = ? AND user_id = ?", (cid, user_id)
    ).fetchone()


def list_curriculum_items(cid):
    """강의 정보와 합쳐서, 순서대로."""
    if using_firestore():
        db = _fs()
        items = list(db.collection("curricula").document(cid).collection("items").stream())
        items.sort(key=lambda d: d.to_dict().get("position", 0))
        out = []
        for d in items:
            it = d.to_dict()
            course_snap = db.collection("courses").document(it["course_id"]).get()
            course = course_snap.to_dict() if course_snap.exists else {}
            out.append({**course, "item_id": d.id, "reason": it.get("reason", ""), "done": bool(it.get("done")),
                        "plan_weeks": it.get("weeks") or 0, "tips": it.get("tips", "")})
        return out
    return get_db().execute(
        """
        SELECT i.id AS item_id, i.reason, i.done, i.weeks AS plan_weeks, i.tips, c.*
        FROM curriculum_items i JOIN courses c ON c.id = i.course_id
        WHERE i.curriculum_id = ? ORDER BY i.position
        """,
        (cid,),
    ).fetchall()


def toggle_curriculum_item(cid, item_id):
    if using_firestore():
        ref = _fs().collection("curricula").document(cid).collection("items").document(item_id)
        snap = ref.get()
        if snap.exists:
            ref.update({"done": not snap.to_dict().get("done")})
        return
    db = get_db()
    db.execute("UPDATE curriculum_items SET done = 1 - done WHERE id = ? AND curriculum_id = ?", (item_id, cid))
    db.commit()


def delete_curriculum(cid):
    if using_firestore():
        db = _fs()
        for d in db.collection("curricula").document(cid).collection("items").stream():
            d.reference.delete()
        db.collection("curricula").document(cid).delete()
        return
    db = get_db()
    db.execute("DELETE FROM curriculum_items WHERE curriculum_id = ?", (cid,))
    db.execute("DELETE FROM curricula WHERE id = ?", (cid,))
    db.commit()


# ---------------------------------------------------------------- 스키마
# sqlite 마이그레이션. 번호 순서대로 한 번씩만 실행되고, 실행한 번호는 schema_migrations 에 남는다.
# 규칙: 이미 배포된 마이그레이션은 고치지 않고 새 번호를 추가한다. 사용자 데이터가 있는 테이블은 DROP 하지 않는다.
# (Firestore 는 스키마가 없어서 마이그레이션 대신 문서를 읽을 때 기본값을 채운다)

def _columns(db, table):
    return [r["name"] for r in db.execute(f"PRAGMA table_info({table})")]


def _add_missing_columns(db, table, columns):
    for col, ddl in columns:
        if col not in _columns(db, table):
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _migrate_1_legacy_lms(db):
    """기존 LMS 스키마. 이 번호가 생기기 전에 만들어진 lms.db 에도 안전하게(있는 건 건드리지 않고) 적용된다."""
    db.execute("CREATE TABLE IF NOT EXISTS course_views (slug TEXT PRIMARY KEY, views INTEGER NOT NULL DEFAULT 0)")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            level TEXT NOT NULL,
            hours INTEGER NOT NULL DEFAULT 40,
            url TEXT NOT NULL UNIQUE,
            curated INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    # 예전 코드는 hours 컬럼이 없으면 courses 를 DROP 했다 (커리큘럼 항목이 가리키는 강의까지 사라짐). 이제는 컬럼만 더한다.
    _add_missing_columns(db, "courses", (("hours", "INTEGER NOT NULL DEFAULT 40"), ("curated", "INTEGER NOT NULL DEFAULT 0")))
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS curricula (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            track TEXT NOT NULL,
            level INTEGER NOT NULL,
            hours_per_week INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _add_missing_columns(db, "curricula", (
        ("source", "TEXT NOT NULL DEFAULT 'rule'"), ("note", "TEXT NOT NULL DEFAULT ''"),
        ("goal_text", "TEXT NOT NULL DEFAULT ''"), ("days_per_week", "INTEGER NOT NULL DEFAULT 0"),
        ("hours_per_day", "REAL NOT NULL DEFAULT 0"),
    ))
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS curriculum_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            curriculum_id INTEGER NOT NULL REFERENCES curricula(id) ON DELETE CASCADE,
            course_id INTEGER NOT NULL REFERENCES courses(id),
            position INTEGER NOT NULL,
            reason TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    _add_missing_columns(db, "curriculum_items", (("weeks", "INTEGER NOT NULL DEFAULT 0"), ("tips", "TEXT NOT NULL DEFAULT ''")))


# (번호, 설명, 함수). ECONOVA 테이블은 여기에 2, 3, ... 으로 추가한다.
SQLITE_MIGRATIONS = [
    (1, "기존 LMS 스키마", _migrate_1_legacy_lms),
]


def migrate_sqlite():
    """아직 적용하지 않은 마이그레이션을 순서대로 적용하고, 적용한 번호 목록을 돌려준다."""
    db = get_db()
    db.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
               "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    done = {r["version"] for r in db.execute("SELECT version FROM schema_migrations")}
    applied = []
    for version, name, fn in SQLITE_MIGRATIONS:
        if version in done:
            continue
        fn(db)
        db.execute("INSERT INTO schema_migrations (version, name) VALUES (?, ?)", (version, name))
        db.commit()
        applied.append(version)
    return applied


def seed_courses():
    """SEED_COURSES 를 강의 목록에 넣거나 갱신한다. (몇 번 실행해도 결과가 같다)"""
    if using_firestore():
        db = _fs()
        batch = db.batch()
        for i, c in enumerate(SEED_COURSES):
            slug, university, title, description, level, hours, url = c
            batch.set(db.collection("courses").document(slug), {
                "university": university, "title": title, "description": description,
                "level": level, "hours": hours, "url": url, "curated": True, "seed_order": i,
            })
        batch.commit()
        return
    db = get_db()
    db.executemany(
        """
        INSERT INTO courses (university, title, description, level, hours, url, curated)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(url) DO UPDATE SET university = excluded.university, title = excluded.title,
            description = excluded.description, level = excluded.level, hours = excluded.hours, curated = 1
        """,
        [c[1:] for c in SEED_COURSES],
    )
    db.commit()


def init_db():
    """스키마를 최신으로 맞추고 강의 목록을 채운다. 앱 import 때는 실행되지 않는다 (flask --app app init-db)."""
    if not using_firestore():  # Firestore 는 스키마가 없어서 테이블을 만들 필요가 없다
        migrate_sqlite()
    seed_courses()
