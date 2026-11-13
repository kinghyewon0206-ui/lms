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
import time

import firebase_admin
from firebase_admin import credentials as fb_credentials, firestore as fb_firestore
from flask import current_app, g

from econova import config, progress


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


# ---------------------------------------------------------------- 스키마
# sqlite 마이그레이션. 번호 순서대로 한 번씩만 실행되고, 실행한 번호는 schema_migrations 에 남는다.
# 규칙: 이미 배포된 마이그레이션은 고치지 않고 새 번호를 추가한다. ECONOVA 사용자 데이터가 있는 테이블은 DROP 하지 않는다.
# (예외: 9번은 운영을 끝낸 이전 LMS 의 테이블을 지운다 — 2026-11 결정으로 이전 LMS 기록은 보존하지 않는다)
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


def _migrate_2_econova_enrollment(db):
    """ECONOVA 수강 신청과 레슨 진도. 기존 LMS 테이블은 건드리지 않는다.
    course_id·lesson_id 는 DB 번호가 아니라 content/*.json 의 고정 문자열 id 다."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS econ_enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            course_id TEXT NOT NULL,
            selected_difficulty TEXT NOT NULL DEFAULT 'beginner'
                CHECK (selected_difficulty IN ('beginner', 'intermediate', 'advanced')),
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed')),
            enrolled_at TEXT NOT NULL,
            completed_at TEXT,
            content_version INTEGER NOT NULL,
            UNIQUE (user_id, course_id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS econ_lesson_progress (
            enrollment_id INTEGER NOT NULL REFERENCES econ_enrollments(id) ON DELETE CASCADE,
            course_id TEXT NOT NULL,
            lesson_id TEXT NOT NULL,
            material_reviewed INTEGER NOT NULL DEFAULT 0,
            material_reviewed_at TEXT,
            quiz_submitted INTEGER NOT NULL DEFAULT 0,
            quiz_submission_id TEXT,
            quiz_submitted_at TEXT,
            quiz_score REAL,
            status TEXT NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started', 'in_progress', 'completed')),
            completed_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (enrollment_id, lesson_id)
        )
        """
    )


def _migrate_3_econova_diagnostic(db):
    """진단평가 응시 기록과, 수강 난이도가 어디서 왔는지(manual / diagnostic). 기존 행은 'manual' 로 채워진다.
    응시 기록은 고치지 않고 쌓기만 한다 (재응시는 새 행). 채점 당시의 문항 버전·기준·결과를 그대로 저장한다."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS econ_diagnostic_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            diagnostic_id TEXT NOT NULL,
            diagnostic_version INTEGER NOT NULL,
            score INTEGER NOT NULL,
            max_score INTEGER NOT NULL,
            recommended_level TEXT NOT NULL CHECK (recommended_level IN ('beginner', 'intermediate', 'advanced')),
            results_json TEXT NOT NULL,
            by_category_json TEXT NOT NULL,
            thresholds_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_econ_diag_user ON econ_diagnostic_attempts (user_id, id)")
    _add_missing_columns(db, "econ_enrollments", (("difficulty_source", "TEXT NOT NULL DEFAULT 'manual'"),))


def _migrate_4_econova_assessments(db):
    """형성 퀴즈·최종 평가 응시 기록과 강좌 수료 근거. 응시 기록은 고치지 않고 쌓기만 한다.
    submission_token 은 화면을 열 때 서버가 만든 일회용 값이다. (user_id, token) 이 같으면 같은 제출로 보고 한 번만 저장한다."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS econ_assessment_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            enrollment_id INTEGER NOT NULL REFERENCES econ_enrollments(id) ON DELETE CASCADE,
            course_id TEXT NOT NULL,
            lesson_id TEXT,
            assessment_id TEXT NOT NULL,
            assessment_version INTEGER NOT NULL,
            course_content_version INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('lesson_quiz', 'final')),
            submission_token TEXT NOT NULL,
            answers_json TEXT NOT NULL,
            results_json TEXT NOT NULL,
            score REAL NOT NULL,
            max_score REAL NOT NULL,
            ratio REAL NOT NULL CHECK (ratio >= 0 AND ratio <= 1),
            passed INTEGER,
            passing_json TEXT,
            status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted')),
            created_at TEXT NOT NULL,
            UNIQUE (user_id, submission_token)
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_econ_attempt_user ON econ_assessment_attempts (user_id, assessment_id, id)")
    _add_missing_columns(db, "econ_enrollments", (("completion_attempt_id", "TEXT"), ("completion_policy", "TEXT")))


def _migrate_5_econova_simulations(db):
    """시뮬레이션 저장 기록. 결과는 서버가 다시 계산한 값만 저장한다 (학생이 보낸 결과는 저장하지 않음)."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS econ_simulation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            simulation_id TEXT NOT NULL CHECK (simulation_id IN ('supply-demand', 'carbon-tax')),
            lesson_id TEXT,
            calc_version TEXT NOT NULL,
            inputs_json TEXT NOT NULL,
            results_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_econ_sim_user ON econ_simulation_runs (user_id, id)")


def _migrate_6_econova_ai(db):
    """AI 대화·사용량. 기존 테이블은 건드리지 않는다 (새 테이블만 추가).
    - 대화/메시지: 학생 본인 것만. 메시지는 보존 기간(ECONOVA_AI_RETENTION_DAYS)이 지나면 purge_ai_data 로 지운다.
    - 사용량: 학생별·날짜별 요청 수와 토큰 수, 전체 날짜별 합계 (여러 워커가 같은 DB 를 보므로 한도가 공유된다).
    - 잠금: 학생별 동시 요청 1개 (오래된 잠금은 시간이 지나면 풀린다)."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS econ_ai_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('tutor', 'feedback', 'debate')),
            course_id TEXT, lesson_id TEXT, topic_id TEXT, attempt_id TEXT,
            stage TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_econ_ai_conv_user ON econ_ai_conversations (user_id, kind, updated_at);
        CREATE TABLE IF NOT EXISTS econ_ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES econ_ai_conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('student', 'assistant')),
            content TEXT NOT NULL,
            meta_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_econ_ai_msg_conv ON econ_ai_messages (conversation_id, id);
        CREATE TABLE IF NOT EXISTS econ_ai_usage (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            day TEXT NOT NULL,
            requests INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            last_request_hash TEXT, last_request_at TEXT,
            PRIMARY KEY (user_id, day)
        );
        CREATE TABLE IF NOT EXISTS econ_ai_usage_global (
            day TEXT PRIMARY KEY,
            requests INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS econ_ai_locks (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            acquired_at TEXT NOT NULL
        );
        """
    )


def _migrate_7_econova_platform(db):
    """Phase 7: 플랫폼 관리자 권한 기록, 콘텐츠 검토 감사 기록, SDG 캡스톤, 로그인 시도 제한. 새 테이블만 추가한다.
    users.role 은 그대로 둔다 (기존 'student'·'teacher' 값 보존). 관리자 권한은 role='admin' 이면서 유효한 부여 기록이
    있을 때만 인정한다 (econova/roles.py)."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS econ_admin_grants (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            granted_at TEXT NOT NULL,
            granted_by TEXT NOT NULL,
            verification TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            revoked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS econ_content_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            content_version TEXT NOT NULL,
            content_digest TEXT NOT NULL,
            decision TEXT NOT NULL CHECK (decision IN ('start_review', 'approve', 'request_changes', 'reopen')),
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL CHECK (to_state IN ('draft', 'in_review', 'approved')),
            reviewer_user_id TEXT NOT NULL,
            reviewer_name TEXT NOT NULL,
            comment TEXT NOT NULL DEFAULT '',
            refs_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_econ_reviews_target ON econ_content_reviews (target_type, target_id, id);
        CREATE TABLE IF NOT EXISTS econ_capstone_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            course_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'submitted')),
            current_version INTEGER NOT NULL DEFAULT 0,
            submitted_version INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            submitted_at TEXT,
            UNIQUE (user_id, course_id)
        );
        CREATE TABLE IF NOT EXISTS econ_capstone_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES econ_capstone_projects(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('draft', 'submitted')),
            definition_version INTEGER NOT NULL,
            sections_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (project_id, version)
        );
        CREATE TABLE IF NOT EXISTS econ_capstone_self_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES econ_capstone_projects(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            rubric_version INTEGER NOT NULL,
            scores_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS econ_capstone_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES econ_capstone_projects(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            feedback_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS econ_login_attempts (
            key TEXT NOT NULL,
            attempted_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_econ_login_key ON econ_login_attempts (key, attempted_at);
        """
    )


def _migrate_8_econova_login_counters(db):
    """Phase 8B-1: 로그인 실패 카운터 (계정·IP·계정+IP 별, 15분 구간). 키는 해시라 이메일·IP 원문을 저장하지 않는다.
    기존 econ_login_attempts 는 지우지 않는다 (더는 쓰지 않으며 purge 때 비운다)."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS econ_login_counters (
            key TEXT PRIMARY KEY,
            count INTEGER NOT NULL DEFAULT 0,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_econ_login_counters_exp ON econ_login_counters (expires_at);
        """
    )


def _migrate_9_drop_legacy_lms(db):
    """이전 LMS(대학 공개 강의·AI 커리큘럼)를 없앴다. 그 테이블과 기록은 보존하지 않기로 했다 (2026-11 결정).
    users 테이블은 ECONOVA 가 그대로 쓴다. 외래키 순서대로 지운다."""
    db.executescript(
        """
        DROP TABLE IF EXISTS curriculum_items;
        DROP TABLE IF EXISTS curricula;
        DROP TABLE IF EXISTS courses;
        DROP TABLE IF EXISTS course_views;
        """
    )


# (번호, 설명, 함수). 새 테이블은 다음 번호로 추가한다.
SQLITE_MIGRATIONS = [
    (1, "기존 LMS 스키마", _migrate_1_legacy_lms),
    (2, "ECONOVA 수강 신청·레슨 진도", _migrate_2_econova_enrollment),
    (3, "ECONOVA 진단평가·난이도 출처", _migrate_3_econova_diagnostic),
    (4, "ECONOVA 퀴즈·최종 평가 응시와 수료", _migrate_4_econova_assessments),
    (5, "ECONOVA 시뮬레이션 저장", _migrate_5_econova_simulations),
    (6, "ECONOVA AI 대화·사용량", _migrate_6_econova_ai),
    (7, "ECONOVA 관리자·콘텐츠 검토·캡스톤·로그인 제한", _migrate_7_econova_platform),
    (8, "ECONOVA 로그인 실패 카운터", _migrate_8_econova_login_counters),
    (9, "이전 LMS 테이블 삭제", _migrate_9_drop_legacy_lms),
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


def init_db():
    """sqlite 스키마를 최신으로 맞춘다. Firestore 는 스키마가 없어 할 일이 없다. 앱 import 때는 실행되지 않는다."""
    if not using_firestore():
        migrate_sqlite()


# ============================================================================
# ECONOVA 수강 신청·레슨 진도
#   sqlite   : econ_enrollments, econ_lesson_progress
#   Firestore: users/{user_id}/econ_enrollments/{course_id}
#              users/{user_id}/econ_enrollments/{course_id}/lessons/{lesson_id}
# 두 저장소 모두 같은 모양의 dict 를 돌려준다 (시각은 UTC 기준 naive datetime).
# 진도 상태 계산은 econova.progress 가 맡고, 여기서는 읽고 쓰기만 한다.
# ============================================================================

class NotEnrolledError(Exception):
    """수강 신청하지 않은 강좌의 진도를 바꾸려고 했을 때."""


_TS_FORMAT = "%Y-%m-%d %H:%M:%S"
_ENROLLMENT_FIELDS = ("course_id", "selected_difficulty", "difficulty_source", "status", "enrolled_at", "completed_at",
                      "content_version", "completion_attempt_id", "completion_policy")
DIFFICULTY_SOURCES = ("manual", "diagnostic")
_PROGRESS_FIELDS = tuple(progress.empty_record("", ""))
_PROGRESS_BOOLS = ("material_reviewed", "quiz_submitted")
_PROGRESS_TIMES = ("material_reviewed_at", "quiz_submitted_at", "completed_at", "updated_at")


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)


def _as_dt(value):
    """sqlite 문자열 / Firestore datetime 을 같은 모양(naive UTC datetime)으로."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        if value.tzinfo:
            value = value.astimezone(datetime.timezone.utc)
        # Firestore 는 datetime 의 하위 클래스(DatetimeWithNanoseconds)를 돌려준다. 그 값에 .replace() 를 한 뒤 다시 쓰면
        # Firestore 라이브러리가 인코딩하지 못하므로(실제 연동 시험에서 확인) 표준 datetime 으로 새로 만든다.
        return datetime.datetime(value.year, value.month, value.day, value.hour, value.minute, value.second,
                                 value.microsecond)
    return datetime.datetime.strptime(value, _TS_FORMAT)


def _sql_ts(value):
    return value.strftime(_TS_FORMAT) if value else None


def _enrollment_dict(user_id, data):
    out = {"user_id": user_id, **{k: data.get(k) for k in _ENROLLMENT_FIELDS}}
    out["enrolled_at"], out["completed_at"] = _as_dt(out["enrolled_at"]), _as_dt(out["completed_at"])
    out["difficulty_source"] = out["difficulty_source"] or "manual"   # 예전 Firestore 문서에는 이 필드가 없다
    return out


def _progress_dict(data):
    out = {k: data.get(k) for k in _PROGRESS_FIELDS}
    for k in _PROGRESS_BOOLS:
        out[k] = bool(out[k])
    for k in _PROGRESS_TIMES:
        out[k] = _as_dt(out[k])
    out["status"] = out["status"] or progress.NOT_STARTED
    return out


def _enrollment_ref(db, user_id, course_id):
    return db.collection("users").document(str(user_id)).collection("econ_enrollments").document(course_id)


def enroll_course(user_id, course_id, difficulty, content_version, difficulty_source="manual"):
    """수강 신청. 새로 신청했으면 True, 이미 수강 중이면 아무것도 바꾸지 않고 False.
    difficulty_source: 난이도를 학생이 직접 골랐으면 manual, 진단평가 추천을 그대로 썼으면 diagnostic."""
    if difficulty_source not in DIFFICULTY_SOURCES:
        raise ValueError("difficulty_source 가 잘못됐습니다.")
    now = _utcnow()
    if using_firestore():
        db = _fs()
        ref = _enrollment_ref(db, user_id, course_id)

        @fb_firestore.transactional
        def _txn(transaction):
            if ref.get(transaction=transaction).exists:
                return False
            transaction.set(ref, {"course_id": course_id, "selected_difficulty": difficulty,
                                  "difficulty_source": difficulty_source, "status": "active",
                                  "enrolled_at": now.replace(tzinfo=datetime.timezone.utc), "completed_at": None,
                                  "content_version": content_version})
            return True

        return _txn(db.transaction())
    db = get_db()
    cur = db.execute(
        # OR IGNORE 는 CHECK 위반(잘못된 난이도)까지 조용히 넘기므로, 중복(UNIQUE)만 무시하도록 ON CONFLICT 를 쓴다
        "INSERT INTO econ_enrollments (user_id, course_id, selected_difficulty, difficulty_source, enrolled_at,"
        " content_version) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (user_id, course_id) DO NOTHING",
        (user_id, course_id, difficulty, difficulty_source, _sql_ts(now), content_version),
    )
    db.commit()
    return cur.rowcount == 1


def get_enrollment(user_id, course_id):
    if using_firestore():
        snap = _enrollment_ref(_fs(), user_id, course_id).get()
        return _enrollment_dict(user_id, snap.to_dict()) if snap.exists else None
    row = get_db().execute("SELECT * FROM econ_enrollments WHERE user_id = ? AND course_id = ?",
                           (user_id, course_id)).fetchone()
    return _enrollment_dict(user_id, dict(row)) if row else None


def list_enrollments(user_id):
    """수강 중인 강좌들, 신청한 순서대로."""
    if using_firestore():
        col = _fs().collection("users").document(str(user_id)).collection("econ_enrollments")
        rows = [_enrollment_dict(user_id, d.to_dict()) for d in col.stream()]
        rows.sort(key=lambda r: (r["enrolled_at"] or datetime.datetime.min, r["course_id"]))
        return rows
    return [_enrollment_dict(user_id, dict(r)) for r in get_db().execute(
        "SELECT * FROM econ_enrollments WHERE user_id = ? ORDER BY enrolled_at, id", (user_id,))]


def set_enrollment_difficulty(user_id, course_id, difficulty):
    """본인 수강 정보의 난이도를 바꾼다. 수강 중이 아니면 False."""
    if using_firestore():
        ref = _enrollment_ref(_fs(), user_id, course_id)
        if not ref.get().exists:
            return False
        ref.update({"selected_difficulty": difficulty, "difficulty_source": "manual"})
        return True
    db = get_db()
    cur = db.execute("UPDATE econ_enrollments SET selected_difficulty = ?, difficulty_source = 'manual'"
                     " WHERE user_id = ? AND course_id = ?",
                     (difficulty, user_id, course_id))
    db.commit()
    return cur.rowcount == 1


# 진도 행의 course_id 는 복사본이다. 어느 강좌의 기록인지는 항상 수강 정보(econ_enrollments)의 course_id 로 정한다.
_PROGRESS_SELECT = ", ".join("e.course_id AS course_id" if f == "course_id" else f"p.{f}" for f in _PROGRESS_FIELDS)


def list_lesson_progress(user_id, course_id):
    """{lesson_id: 진도 기록}. 기록이 없는 레슨은 빠져 있다 (= not_started)."""
    if using_firestore():
        col = _enrollment_ref(_fs(), user_id, course_id).collection("lessons")
        return {d.id: _progress_dict(d.to_dict()) for d in col.stream()}
    rows = get_db().execute(
        f"SELECT {_PROGRESS_SELECT} FROM econ_lesson_progress p JOIN econ_enrollments e ON e.id = p.enrollment_id"
        " WHERE e.user_id = ? AND e.course_id = ?", (user_id, course_id))
    return {r["lesson_id"]: _progress_dict(dict(r)) for r in rows}


def list_all_lesson_progress(user_id):
    """{course_id: {lesson_id: 진도 기록}} — 대시보드에서 한 번에 읽는다."""
    if using_firestore():
        out = {e["course_id"]: list_lesson_progress(user_id, e["course_id"]) for e in list_enrollments(user_id)}
        return {cid: recs for cid, recs in out.items() if recs}   # sqlite 와 같게: 기록이 없는 강좌는 뺀다
    out = {}
    for r in get_db().execute(
            f"SELECT {_PROGRESS_SELECT} FROM econ_lesson_progress p JOIN econ_enrollments e ON e.id = p.enrollment_id"
            " WHERE e.user_id = ?", (user_id,)):
        out.setdefault(r["course_id"], {})[r["lesson_id"]] = _progress_dict(dict(r))
    return out


def update_lesson_progress(user_id, course_id, lesson_id, requirements, *, material_reviewed=False,
                           quiz_submission_id=None, quiz_score=None, event_time=None):
    """레슨 진도에 이벤트를 반영하고 새 기록을 돌려준다. 읽기-계산-쓰기를 한 트랜잭션에서 한다.
    수강 신청하지 않은 강좌면 NotEnrolledError. event_time 은 이벤트가 실제로 일어난 시각(예: 퀴즈 제출 시각).
    바뀐 것이 없으면(같은 이벤트를 다시 반영) 쓰지 않는다."""
    now = _as_dt(event_time) or _utcnow()
    if using_firestore():
        db = _fs()
        enrollment = _enrollment_ref(db, user_id, course_id)
        ref = enrollment.collection("lessons").document(lesson_id)

        @fb_firestore.transactional
        def _txn(transaction):
            if not enrollment.get(transaction=transaction).exists:
                raise NotEnrolledError()
            snap = ref.get(transaction=transaction)
            old = _progress_dict(snap.to_dict()) if snap.exists else progress.empty_record(course_id, lesson_id)
            rec = progress.apply_event(old, requirements, now, material_reviewed=material_reviewed,
                                       quiz_submission_id=quiz_submission_id, quiz_score=quiz_score)
            if snap.exists and rec == old:
                return rec
            transaction.set(ref, {k: (v.replace(tzinfo=datetime.timezone.utc) if isinstance(v, datetime.datetime) else v)
                                  for k, v in rec.items()})
            return rec

        return _txn(db.transaction())

    db = get_db()
    if db.in_transaction:
        # 이 연결에 커밋하지 않은 다른 쓰기가 남아 있으면 BEGIN 이 실패하고, 아래 rollback 이 그 쓰기까지 지운다.
        # 지금 지원하는 흐름에서는 생기지 않지만, 남의 변경을 조용히 지우지 않도록 시작 전에 멈춘다.
        raise RuntimeError("커밋하지 않은 변경이 남아 있는 DB 연결에서는 레슨 진도를 저장할 수 없습니다.")
    try:
        db.execute("BEGIN IMMEDIATE")   # 같은 레슨을 동시에 바꿔도 마지막 계산이 앞의 변경을 덮지 않게 잠근다
        row = db.execute("SELECT id FROM econ_enrollments WHERE user_id = ? AND course_id = ?",
                         (user_id, course_id)).fetchone()
        if row is None:
            raise NotEnrolledError()
        old_row = db.execute("SELECT * FROM econ_lesson_progress WHERE enrollment_id = ? AND lesson_id = ?",
                             (row["id"], lesson_id)).fetchone()
        old = _progress_dict(dict(old_row)) if old_row else progress.empty_record(course_id, lesson_id)
        rec = progress.apply_event(old, requirements, now, material_reviewed=material_reviewed,
                                   quiz_submission_id=quiz_submission_id, quiz_score=quiz_score)
        if old_row is not None and rec == old:
            db.commit()
            return rec
        values = {k: (_sql_ts(v) if k in _PROGRESS_TIMES else int(v) if k in _PROGRESS_BOOLS else v) for k, v in rec.items()}
        cols = ", ".join(values)
        db.execute(
            f"INSERT INTO econ_lesson_progress (enrollment_id, {cols}) VALUES (?, {', '.join('?' * len(values))})"
            f" ON CONFLICT(enrollment_id, lesson_id) DO UPDATE SET {', '.join(f'{k} = excluded.{k}' for k in values)}",
            (row["id"], *values.values()),
        )
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return rec


# ============================================================================
# ECONOVA 진단평가 응시 기록
#   sqlite   : econ_diagnostic_attempts
#   Firestore: users/{user_id}/econ_diagnostic_attempts/{attempt_id}
# 기록은 추가만 한다. 문항·기준이 나중에 바뀌어도 예전 결과를 다시 계산하지 않는다.
# ============================================================================
_ATTEMPT_JSON = ("results", "by_category", "thresholds")


def _attempt_dict(attempt_id, data):
    out = {"id": str(attempt_id), **{k: data.get(k) for k in ("diagnostic_id", "diagnostic_version", "score", "max_score",
                                                               "recommended_level", "created_at")}}
    for k in _ATTEMPT_JSON:
        value = data.get(k) if k in data else data.get(f"{k}_json")
        out[k] = json.loads(value) if isinstance(value, str) else value
    out["created_at"] = _as_dt(out["created_at"])
    return out


def save_diagnostic_attempt(user_id, result):
    """채점 결과(diagnostic.score 가 만든 dict)를 새 응시 기록으로 저장하고 id(문자열)를 돌려준다."""
    now = _utcnow()
    fields = {k: result[k] for k in ("diagnostic_id", "diagnostic_version", "score", "max_score", "recommended_level")}
    if using_firestore():
        ref = _fs().collection("users").document(str(user_id)).collection("econ_diagnostic_attempts").document()
        # Firestore 문서 id 는 무작위라 순서를 정할 수 없으므로, 같은 초에 두 번 제출해도 순서가 정해지게 마이크로초까지 저장한다
        ref.set({**fields, **{k: result[k] for k in _ATTEMPT_JSON},
                 "created_at": datetime.datetime.now(datetime.timezone.utc)})
        return ref.id
    db = get_db()
    cur = db.execute(
        "INSERT INTO econ_diagnostic_attempts (user_id, diagnostic_id, diagnostic_version, score, max_score,"
        " recommended_level, results_json, by_category_json, thresholds_json, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, *fields.values(), *(json.dumps(result[k], ensure_ascii=False) for k in _ATTEMPT_JSON), _sql_ts(now)),
    )
    db.commit()
    return str(cur.lastrowid)


def get_diagnostic_attempt(user_id, attempt_id):
    """본인의 응시 기록만 돌려준다. 남의 기록이거나 없으면 None."""
    if using_firestore():
        snap = _fs().collection("users").document(str(user_id)).collection("econ_diagnostic_attempts") \
            .document(str(attempt_id)).get()
        return _attempt_dict(snap.id, snap.to_dict()) if snap.exists else None
    if not str(attempt_id).isdigit():
        return None
    row = get_db().execute("SELECT * FROM econ_diagnostic_attempts WHERE id = ? AND user_id = ?",
                           (int(attempt_id), user_id)).fetchone()
    return _attempt_dict(row["id"], dict(row)) if row else None


def list_diagnostic_attempts(user_id):
    """본인의 응시 기록, 최신순."""
    if using_firestore():
        col = _fs().collection("users").document(str(user_id)).collection("econ_diagnostic_attempts")
        rows = [_attempt_dict(d.id, d.to_dict()) for d in col.stream()]
        rows.sort(key=lambda r: (r["created_at"] or datetime.datetime.min, r["id"]), reverse=True)
        return rows
    return [_attempt_dict(r["id"], dict(r)) for r in get_db().execute(
        "SELECT * FROM econ_diagnostic_attempts WHERE user_id = ? ORDER BY created_at DESC, id DESC", (user_id,))]


# ============================================================================
# ECONOVA 퀴즈·최종 평가 응시 기록과 수료
#   sqlite   : econ_assessment_attempts, econ_enrollments.completion_*
#   Firestore: users/{user_id}/econ_assessment_attempts/{submission_token}
# 기록은 추가만 한다(점수를 고치는 경로 없음). 같은 제출 토큰은 한 번만 저장된다.
# ============================================================================
class DuplicateSubmission(Exception):
    """같은 제출 토큰으로 이미 저장된 기록이 있을 때. attempt_id 로 그 기록을 가리킨다."""

    def __init__(self, attempt_id):
        super().__init__(attempt_id)
        self.attempt_id = attempt_id


_AA_FIELDS = ("course_id", "lesson_id", "assessment_id", "assessment_version", "course_content_version", "kind", "score",
              "max_score", "ratio", "passed", "status", "created_at", "submission_token")
_AA_JSON = ("answers", "results", "passing")


def _aa_dict(attempt_id, data):
    out = {"id": str(attempt_id), **{k: data.get(k) for k in _AA_FIELDS}}
    for k in _AA_JSON:
        value = data.get(k) if k in data else data.get(f"{k}_json")
        out[k] = json.loads(value) if isinstance(value, str) else value
    out["passed"] = None if out["passed"] is None else bool(out["passed"])
    out["created_at"] = _as_dt(out["created_at"])
    return out


class AttemptLimitReached(Exception):
    """응시 횟수 제한에 이미 닿았다 (동시에 여러 번 제출해도 제한을 넘지 않게 저장 단계에서 다시 확인)."""


def save_assessment_attempt(user_id, record, token, max_attempts=0):
    """채점된 응시 기록을 저장하고 id 를 돌려준다. 수강하지 않았으면 NotEnrolledError,
    같은 토큰으로 이미 저장됐으면 DuplicateSubmission(기존 id), 횟수 제한(max_attempts>0)에 닿았으면 AttemptLimitReached.
    횟수 확인과 저장을 한 트랜잭션에서 한다 (sqlite: BEGIN IMMEDIATE, Firestore: 평가별 응시 수 문서)."""
    token = str(token)
    fields = {k: record[k] for k in ("course_id", "lesson_id", "assessment_id", "assessment_version", "course_content_version",
                                     "kind", "score", "max_score", "ratio", "passed")}
    if using_firestore():
        db = _fs()
        enrollment = _enrollment_ref(db, user_id, record["course_id"])
        user_doc = db.collection("users").document(str(user_id))
        ref = user_doc.collection("econ_assessment_attempts").document(token)
        counter = user_doc.collection("econ_assessment_counters").document(record["assessment_id"])
        # 응시 수 문서가 아직 없으면(예전 기록) 지금까지의 응시 수로 시작한다
        existing_count = None if counter.get().exists else sum(
            1 for d in user_doc.collection("econ_assessment_attempts").stream()
            if (d.to_dict() or {}).get("assessment_id") == record["assessment_id"])

        @fb_firestore.transactional
        def _txn(transaction):
            if not enrollment.get(transaction=transaction).exists:
                raise NotEnrolledError()
            if ref.get(transaction=transaction).exists:
                raise DuplicateSubmission(token)
            snap = counter.get(transaction=transaction)
            count = int((snap.to_dict() or {}).get("count") or 0) if snap.exists else int(existing_count or 0)
            if max_attempts and count >= max_attempts:
                raise AttemptLimitReached()
            transaction.set(counter, {"count": count + 1})
            transaction.set(ref, {**fields, **{k: record[k] for k in _AA_JSON}, "status": "submitted",
                                  "submission_token": token, "created_at": datetime.datetime.now(datetime.timezone.utc)})
            return token

        return _txn(db.transaction())
    db = get_db()
    if db.in_transaction:
        db.commit()
    db.execute("BEGIN IMMEDIATE")   # 횟수 확인과 저장 사이에 다른 제출이 끼어들지 못하게 잠근다
    row = db.execute("SELECT id FROM econ_enrollments WHERE user_id = ? AND course_id = ?",
                     (user_id, record["course_id"])).fetchone()
    if row is None:
        db.rollback()
        raise NotEnrolledError()
    if max_attempts:
        used = db.execute("SELECT COUNT(*) AS n FROM econ_assessment_attempts WHERE user_id = ? AND assessment_id = ?",
                          (user_id, record["assessment_id"])).fetchone()["n"]
        duplicate = db.execute("SELECT id FROM econ_assessment_attempts WHERE user_id = ? AND submission_token = ?",
                               (user_id, token)).fetchone()
        if duplicate is None and used >= max_attempts:
            db.rollback()
            raise AttemptLimitReached()
    try:
        cur = db.execute(
            "INSERT INTO econ_assessment_attempts (user_id, enrollment_id, course_id, lesson_id, assessment_id,"
            " assessment_version, course_content_version, kind, score, max_score, ratio, passed, submission_token,"
            " answers_json, results_json, passing_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, row["id"], fields["course_id"], fields["lesson_id"], fields["assessment_id"], fields["assessment_version"],
             fields["course_content_version"], fields["kind"], fields["score"], fields["max_score"], fields["ratio"],
             None if fields["passed"] is None else int(fields["passed"]), token,
             *(json.dumps(record[k], ensure_ascii=False) for k in _AA_JSON), _sql_ts(_utcnow())),
        )
    except sqlite3.IntegrityError:
        db.rollback()
        existing = db.execute("SELECT id FROM econ_assessment_attempts WHERE user_id = ? AND submission_token = ?",
                              (user_id, token)).fetchone()
        if existing is None:
            raise
        raise DuplicateSubmission(str(existing["id"]))
    db.commit()
    return str(cur.lastrowid)


def get_assessment_attempt(user_id, attempt_id):
    """본인의 응시 기록만. 남의 기록이거나 없으면 None."""
    if using_firestore():
        snap = _fs().collection("users").document(str(user_id)).collection("econ_assessment_attempts") \
            .document(str(attempt_id)).get()
        return _aa_dict(snap.id, snap.to_dict()) if snap.exists else None
    if not str(attempt_id).isdigit():
        return None
    row = get_db().execute("SELECT * FROM econ_assessment_attempts WHERE id = ? AND user_id = ?",
                           (int(attempt_id), user_id)).fetchone()
    return _aa_dict(row["id"], dict(row)) if row else None


def find_attempt_by_token(user_id, token):
    if using_firestore():
        return get_assessment_attempt(user_id, token)
    row = get_db().execute("SELECT * FROM econ_assessment_attempts WHERE user_id = ? AND submission_token = ?",
                           (user_id, str(token))).fetchone()
    return _aa_dict(row["id"], dict(row)) if row else None


def list_assessment_attempts(user_id, course_id=None, assessment_id=None):
    """본인의 응시 기록, 최신순. 강좌·평가로 거를 수 있다."""
    if using_firestore():
        col = _fs().collection("users").document(str(user_id)).collection("econ_assessment_attempts")
        rows = [_aa_dict(d.id, d.to_dict()) for d in col.stream()]
        rows = [r for r in rows if (course_id is None or r["course_id"] == course_id)
                and (assessment_id is None or r["assessment_id"] == assessment_id)]
        rows.sort(key=lambda r: (r["created_at"] or datetime.datetime.min, r["id"]), reverse=True)
        return rows
    sql, args = "SELECT * FROM econ_assessment_attempts WHERE user_id = ?", [user_id]
    if course_id is not None:
        sql, args = sql + " AND course_id = ?", args + [course_id]
    if assessment_id is not None:
        sql, args = sql + " AND assessment_id = ?", args + [assessment_id]
    return [_aa_dict(r["id"], dict(r)) for r in get_db().execute(sql + " ORDER BY id DESC", args)]


def complete_enrollment(user_id, course_id, attempt_id, policy, at=None):
    """강좌 수료 기록. 이미 수료했으면 처음 수료 기록을 그대로 두고 False. at: 근거가 된 응시의 제출 시각."""
    now = _as_dt(at) or _utcnow()
    if using_firestore():
        db = _fs()
        ref = _enrollment_ref(db, user_id, course_id)

        @fb_firestore.transactional
        def _txn(transaction):
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                raise NotEnrolledError()
            if (snap.to_dict() or {}).get("status") == "completed":
                return False
            transaction.set(ref, {"status": "completed", "completed_at": now.replace(tzinfo=datetime.timezone.utc),
                                  "completion_attempt_id": str(attempt_id), "completion_policy": policy}, merge=True)
            return True

        return _txn(db.transaction())
    db = get_db()
    cur = db.execute("UPDATE econ_enrollments SET status = 'completed', completed_at = ?, completion_attempt_id = ?,"
                     " completion_policy = ? WHERE user_id = ? AND course_id = ? AND status != 'completed'",
                     (_sql_ts(now), str(attempt_id), policy, user_id, course_id))
    db.commit()
    if cur.rowcount == 0 and get_enrollment(user_id, course_id) is None:
        raise NotEnrolledError()
    return cur.rowcount == 1


# ============================================================================
# ECONOVA 시뮬레이션 저장 기록
#   sqlite   : econ_simulation_runs
#   Firestore: users/{user_id}/econ_simulation_runs/{run_id}
# ============================================================================
def _sim_dict(run_id, data):
    out = {"id": str(run_id), **{k: data.get(k) for k in ("simulation_id", "lesson_id", "calc_version", "created_at")}}
    for k in ("inputs", "results"):
        value = data.get(k) if k in data else data.get(f"{k}_json")
        out[k] = json.loads(value) if isinstance(value, str) else value
    out["created_at"] = _as_dt(out["created_at"])
    return out


def save_simulation_run(user_id, simulation_id, lesson_id, inputs, results, calc_version):
    """서버가 계산한 시뮬레이션 결과를 저장하고 id 를 돌려준다."""
    if using_firestore():
        ref = _fs().collection("users").document(str(user_id)).collection("econ_simulation_runs").document()
        ref.set({"simulation_id": simulation_id, "lesson_id": lesson_id, "calc_version": calc_version,
                 "inputs": inputs, "results": results, "created_at": datetime.datetime.now(datetime.timezone.utc)})
        return ref.id
    db = get_db()
    cur = db.execute(
        "INSERT INTO econ_simulation_runs (user_id, simulation_id, lesson_id, calc_version, inputs_json, results_json,"
        " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, simulation_id, lesson_id, calc_version, json.dumps(inputs, ensure_ascii=False),
         json.dumps(results, ensure_ascii=False), _sql_ts(_utcnow())))
    db.commit()
    return str(cur.lastrowid)


def get_simulation_run(user_id, run_id):
    """본인의 기록만. 남의 기록이거나 없으면 None."""
    if using_firestore():
        snap = _fs().collection("users").document(str(user_id)).collection("econ_simulation_runs").document(str(run_id)).get()
        return _sim_dict(snap.id, snap.to_dict()) if snap.exists else None
    if not str(run_id).isdigit():
        return None
    row = get_db().execute("SELECT * FROM econ_simulation_runs WHERE id = ? AND user_id = ?", (int(run_id), user_id)).fetchone()
    return _sim_dict(row["id"], dict(row)) if row else None


def list_simulation_runs(user_id):
    """본인의 기록, 최신순."""
    if using_firestore():
        col = _fs().collection("users").document(str(user_id)).collection("econ_simulation_runs")
        rows = [_sim_dict(d.id, d.to_dict()) for d in col.stream()]
        rows.sort(key=lambda r: (r["created_at"] or datetime.datetime.min, r["id"]), reverse=True)
        return rows
    return [_sim_dict(r["id"], dict(r)) for r in get_db().execute(
        "SELECT * FROM econ_simulation_runs WHERE user_id = ? ORDER BY id DESC", (user_id,))]


# ============================================================================
# ECONOVA AI 대화·사용량 (Phase 6)
#   sqlite   : econ_ai_conversations, econ_ai_messages, econ_ai_usage, econ_ai_usage_global, econ_ai_locks
#   Firestore: users/{user_id}/econ_ai_conversations/{id}  (+ 하위 messages/{id})
#              users/{user_id}/econ_ai_usage/{day}, econ_ai_usage_global/{day}, econ_ai_locks/{user_id}
# AI 결과는 여기에만 쓴다. 점수·진도·수료·수강 정보는 이 계층에서 절대 바꾸지 않는다.
# ============================================================================
AI_KINDS = ("tutor", "feedback", "debate")
_AI_SCOPE = ("course_id", "lesson_id", "topic_id", "attempt_id")


class AILimitExceeded(Exception):
    """사용 한도 초과. scope: 'user' | 'global' | 'duplicate'."""

    def __init__(self, scope):
        super().__init__(scope)
        self.scope = scope


def _conv_dict(conv_id, data):
    out = {"id": str(conv_id), "kind": data.get("kind"), "stage": data.get("stage") or "open",
           **{k: data.get(k) for k in _AI_SCOPE}}
    out["created_at"], out["updated_at"] = _as_dt(data.get("created_at")), _as_dt(data.get("updated_at"))
    return out


def _msg_dict(msg_id, data):
    meta = data.get("meta") if "meta" in data else data.get("meta_json")
    return {"id": str(msg_id), "role": data.get("role"), "content": data.get("content") or "",
            "meta": json.loads(meta) if isinstance(meta, str) else (meta or {}), "created_at": _as_dt(data.get("created_at"))}


def _ai_convs(user_id):
    return _fs().collection("users").document(str(user_id)).collection("econ_ai_conversations")


def create_ai_conversation(user_id, kind, **scope):
    if kind not in AI_KINDS:
        raise ValueError(kind)
    scope = {k: (str(scope[k]) if scope.get(k) is not None else None) for k in _AI_SCOPE}
    now = _utcnow()
    if using_firestore():
        ref = _ai_convs(user_id).document()
        ref.set({"kind": kind, "stage": "open", **scope, "created_at": now.replace(tzinfo=datetime.timezone.utc),
                 "updated_at": now.replace(tzinfo=datetime.timezone.utc)})
        return ref.id
    db = get_db()
    cur = db.execute("INSERT INTO econ_ai_conversations (user_id, kind, course_id, lesson_id, topic_id, attempt_id,"
                     " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (user_id, kind, *[scope[k] for k in _AI_SCOPE], _sql_ts(now), _sql_ts(now)))
    db.commit()
    return str(cur.lastrowid)


def get_ai_conversation(user_id, conv_id):
    """본인의 대화만. 남의 대화이거나 없으면 None."""
    if using_firestore():
        snap = _ai_convs(user_id).document(str(conv_id)).get()
        return _conv_dict(snap.id, snap.to_dict()) if snap.exists else None
    if not str(conv_id).isdigit():
        return None
    row = get_db().execute("SELECT * FROM econ_ai_conversations WHERE id = ? AND user_id = ?",
                           (int(conv_id), user_id)).fetchone()
    return _conv_dict(row["id"], dict(row)) if row else None


def find_ai_conversations(user_id, kind, **scope):
    """본인의 대화 중 kind·범위가 같은 것, 최근 순."""
    want = {k: str(v) for k, v in scope.items() if v is not None}
    if using_firestore():
        rows = [_conv_dict(d.id, d.to_dict()) for d in _ai_convs(user_id).stream()]
    else:
        rows = [_conv_dict(r["id"], dict(r)) for r in get_db().execute(
            "SELECT * FROM econ_ai_conversations WHERE user_id = ? AND kind = ?", (user_id, kind))]
    rows = [r for r in rows if r["kind"] == kind and all(r.get(k) == v for k, v in want.items())]
    rows.sort(key=lambda r: (r["updated_at"] or datetime.datetime.min, int(r["id"]) if r["id"].isdigit() else 0),
              reverse=True)
    return rows


def set_ai_conversation_stage(user_id, conv_id, stage):
    now = _utcnow()
    if using_firestore():
        _ai_convs(user_id).document(str(conv_id)).set(
            {"stage": stage, "updated_at": now.replace(tzinfo=datetime.timezone.utc)}, merge=True)
        return
    db = get_db()
    db.execute("UPDATE econ_ai_conversations SET stage = ?, updated_at = ? WHERE id = ? AND user_id = ?",
               (stage, _sql_ts(now), int(conv_id), user_id))
    db.commit()


def add_ai_message(user_id, conv_id, role, content, meta=None):
    """본인 대화에 메시지 하나를 더한다. 대화가 본인 것이 아니면 LookupError."""
    if role not in ("student", "assistant"):
        raise ValueError(role)
    if get_ai_conversation(user_id, conv_id) is None:
        raise LookupError("conversation")
    now = _utcnow()
    meta = meta or {}
    if using_firestore():
        conv = _ai_convs(user_id).document(str(conv_id))
        ref = conv.collection("messages").document()
        ref.set({"role": role, "content": content, "meta": meta, "seq": time.time_ns(),
                 "created_at": now.replace(tzinfo=datetime.timezone.utc)})
        conv.set({"updated_at": now.replace(tzinfo=datetime.timezone.utc)}, merge=True)
        return ref.id
    db = get_db()
    cur = db.execute("INSERT INTO econ_ai_messages (conversation_id, role, content, meta_json, created_at)"
                     " VALUES (?, ?, ?, ?, ?)", (int(conv_id), role, content, json.dumps(meta, ensure_ascii=False),
                                                 _sql_ts(now)))
    db.execute("UPDATE econ_ai_conversations SET updated_at = ? WHERE id = ?", (_sql_ts(now), int(conv_id)))
    db.commit()
    return str(cur.lastrowid)


def list_ai_messages(user_id, conv_id, limit=None):
    """본인 대화의 메시지, 오래된 것부터. limit 이 있으면 마지막 limit 개."""
    if get_ai_conversation(user_id, conv_id) is None:
        return []
    if using_firestore():
        docs = list(_ai_convs(user_id).document(str(conv_id)).collection("messages").stream())
        docs.sort(key=lambda d: d.to_dict().get("seq") or 0)
        rows = [_msg_dict(d.id, d.to_dict()) for d in docs]
    else:
        rows = [_msg_dict(r["id"], dict(r)) for r in get_db().execute(
            "SELECT * FROM econ_ai_messages WHERE conversation_id = ? ORDER BY id", (int(conv_id),))]
    return rows[-limit:] if limit else rows


def reserve_ai_request(user_id, day, per_user_limit, global_limit, request_hash, now, duplicate_window):
    """요청 하나를 사용량에 먼저 기록한다(실패한 요청도 센다). 한도를 넘거나, 방금 '성공한' 요청과 같은 요청이
    곧바로 반복되면 AILimitExceeded. (실패한 요청은 같은 내용으로 다시 시도할 수 있다)
    학생별·전체 카운터를 한 트랜잭션에서 확인·증가시키므로 여러 워커가 동시에 와도 한도를 넘지 않는다."""
    if using_firestore():
        db = _fs()
        user_ref = _fs().collection("users").document(str(user_id)).collection("econ_ai_usage").document(day)
        global_ref = db.collection("econ_ai_usage_global").document(day)

        @fb_firestore.transactional
        def _txn(transaction):
            u = user_ref.get(transaction=transaction).to_dict() or {}
            gl = global_ref.get(transaction=transaction).to_dict() or {}
            _check_ai_limits(u, gl, per_user_limit, global_limit, request_hash, now, duplicate_window)
            transaction.set(user_ref, {"requests": int(u.get("requests") or 0) + 1}, merge=True)
            transaction.set(global_ref, {"requests": int(gl.get("requests") or 0) + 1}, merge=True)

        return _txn(db.transaction())
    db = get_db()
    if db.in_transaction:
        db.commit()
    try:
        db.execute("BEGIN IMMEDIATE")
        u = db.execute("SELECT * FROM econ_ai_usage WHERE user_id = ? AND day = ?", (user_id, day)).fetchone()
        gl = db.execute("SELECT * FROM econ_ai_usage_global WHERE day = ?", (day,)).fetchone()
        _check_ai_limits(dict(u) if u else {}, dict(gl) if gl else {}, per_user_limit, global_limit, request_hash, now,
                         duplicate_window)
        db.execute("INSERT INTO econ_ai_usage (user_id, day, requests) VALUES (?, ?, 1)"
                   " ON CONFLICT(user_id, day) DO UPDATE SET requests = requests + 1", (user_id, day))
        db.execute("INSERT INTO econ_ai_usage_global (day, requests) VALUES (?, 1)"
                   " ON CONFLICT(day) DO UPDATE SET requests = requests + 1", (day,))
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _check_ai_limits(u, gl, per_user_limit, global_limit, request_hash, now, duplicate_window):
    if int(gl.get("requests") or 0) >= global_limit:
        raise AILimitExceeded("global")
    if int(u.get("requests") or 0) >= per_user_limit:
        raise AILimitExceeded("user")
    last_at = _as_dt(u.get("last_request_at"))
    if request_hash and u.get("last_request_hash") == request_hash and last_at and \
            (now - last_at).total_seconds() < duplicate_window:
        raise AILimitExceeded("duplicate")


def record_ai_tokens(user_id, day, input_tokens, output_tokens, request_hash=None, at=None):
    """성공한 요청의 토큰 수를 더하고, 반복 요청 확인용 지문(request_hash)을 남긴다."""
    i, o = max(0, int(input_tokens or 0)), max(0, int(output_tokens or 0))
    at = at or _utcnow()
    if using_firestore():
        fields = {"input_tokens": fb_firestore.Increment(i), "output_tokens": fb_firestore.Increment(o)}
        if request_hash:
            fields.update(last_request_hash=request_hash, last_request_at=at.replace(tzinfo=datetime.timezone.utc))
        _fs().collection("users").document(str(user_id)).collection("econ_ai_usage").document(day).set(fields, merge=True)
        _fs().collection("econ_ai_usage_global").document(day).set(
            {"input_tokens": fb_firestore.Increment(i), "output_tokens": fb_firestore.Increment(o)}, merge=True)
        return
    db = get_db()
    db.execute("UPDATE econ_ai_usage SET input_tokens = input_tokens + ?, output_tokens = output_tokens + ?,"
               " last_request_hash = COALESCE(?, last_request_hash), last_request_at = COALESCE(?, last_request_at)"
               " WHERE user_id = ? AND day = ?",
               (i, o, request_hash, _sql_ts(at) if request_hash else None, user_id, day))
    db.execute("UPDATE econ_ai_usage_global SET input_tokens = input_tokens + ?, output_tokens = output_tokens + ?"
               " WHERE day = ?", (i, o, day))
    db.commit()


def get_ai_usage(user_id, day):
    keys = ("requests", "input_tokens", "output_tokens")
    if using_firestore():
        u = _fs().collection("users").document(str(user_id)).collection("econ_ai_usage").document(day).get().to_dict() or {}
        gl = _fs().collection("econ_ai_usage_global").document(day).get().to_dict() or {}
    else:
        db = get_db()
        row = db.execute("SELECT * FROM econ_ai_usage WHERE user_id = ? AND day = ?", (user_id, day)).fetchone()
        grow = db.execute("SELECT * FROM econ_ai_usage_global WHERE day = ?", (day,)).fetchone()
        u, gl = (dict(row) if row else {}), (dict(grow) if grow else {})
    return {"user": {k: int(u.get(k) or 0) for k in keys}, "global": {k: int(gl.get(k) or 0) for k in keys}}


def acquire_ai_lock(user_id, now, ttl_seconds):
    """학생별 동시 AI 요청을 1개로 제한한다. 잡았으면 True. ttl 이 지난 잠금(비정상 종료)은 넘겨받는다."""
    if using_firestore():
        db = _fs()
        ref = db.collection("econ_ai_locks").document(str(user_id))

        @fb_firestore.transactional
        def _txn(transaction):
            snap = ref.get(transaction=transaction)
            held = _as_dt((snap.to_dict() or {}).get("acquired_at")) if snap.exists else None
            if held and (now - held).total_seconds() < ttl_seconds:
                return False
            transaction.set(ref, {"acquired_at": now.replace(tzinfo=datetime.timezone.utc)})
            return True

        return _txn(db.transaction())
    db = get_db()
    if db.in_transaction:
        db.commit()
    stale = _sql_ts(now - datetime.timedelta(seconds=ttl_seconds))
    db.execute("DELETE FROM econ_ai_locks WHERE user_id = ? AND acquired_at < ?", (user_id, stale))
    cur = db.execute("INSERT INTO econ_ai_locks (user_id, acquired_at) VALUES (?, ?) ON CONFLICT(user_id) DO NOTHING",
                     (user_id, _sql_ts(now)))
    db.commit()
    return cur.rowcount == 1


def release_ai_lock(user_id):
    if using_firestore():
        _fs().collection("econ_ai_locks").document(str(user_id)).delete()
        return
    db = get_db()
    db.execute("DELETE FROM econ_ai_locks WHERE user_id = ?", (user_id,))
    db.commit()


def purge_ai_data(before, usage_before=None):
    """보존 기간이 지난 AI 메시지를 지우고(남은 메시지가 없는 대화도 지움), 오래된 사용량 기록을 지운다.
    지운 (메시지 수, 대화 수) 를 돌려준다. 점수·진도·수강 기록은 건드리지 않는다."""
    usage_day = (usage_before or before).strftime("%Y-%m-%d")
    if using_firestore():
        msgs = convs = 0
        for user in _fs().collection("users").stream():
            col = _fs().collection("users").document(user.id).collection("econ_ai_conversations")
            for conv in col.stream():
                mcol = col.document(conv.id).collection("messages")
                left = 0
                for m in mcol.stream():
                    if (_as_dt(m.to_dict().get("created_at")) or before) < before:
                        mcol.document(m.id).delete()
                        msgs += 1
                    else:
                        left += 1
                if not left and (_as_dt(conv.to_dict().get("updated_at")) or before) < before:
                    col.document(conv.id).delete()
                    convs += 1
            ucol = _fs().collection("users").document(user.id).collection("econ_ai_usage")
            for d in ucol.stream():
                if d.id < usage_day:
                    ucol.document(d.id).delete()
        return msgs, convs
    db = get_db()
    ts = _sql_ts(before)
    msgs = db.execute("DELETE FROM econ_ai_messages WHERE created_at < ?", (ts,)).rowcount
    convs = db.execute("DELETE FROM econ_ai_conversations WHERE updated_at < ? AND NOT EXISTS"
                       " (SELECT 1 FROM econ_ai_messages m WHERE m.conversation_id = econ_ai_conversations.id)",
                       (ts,)).rowcount
    db.execute("DELETE FROM econ_ai_usage WHERE day < ?", (usage_day,))
    db.execute("DELETE FROM econ_ai_locks WHERE acquired_at < ?", (ts,))
    db.commit()
    return msgs, convs


# ============================================================================
# Phase 7: 플랫폼 관리자 권한 기록
#   sqlite   : users.role + econ_admin_grants
#   Firestore: users/{id}.role + econ_admin_grants/{user_id}
# 웹 요청으로는 권한을 바꾸지 않는다. CLI(flask admin-grant / admin-revoke)만 쓴다.
# ============================================================================
def set_user_role(user_id, role):
    if role not in ("student", "admin"):
        raise ValueError(role)
    if using_firestore():
        _fs().collection("users").document(str(user_id)).set({"role": role}, merge=True)
        return
    db = get_db()
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    db.commit()


def grant_admin(user_id, granted_by, verification, note=""):
    now = _utcnow()
    if using_firestore():
        _fs().collection("econ_admin_grants").document(str(user_id)).set(
            {"granted_at": now.replace(tzinfo=datetime.timezone.utc), "granted_by": granted_by,
             "verification": verification, "note": note, "revoked_at": None})
    else:
        db = get_db()
        db.execute("INSERT INTO econ_admin_grants (user_id, granted_at, granted_by, verification, note) VALUES (?, ?, ?, ?, ?)"
                   " ON CONFLICT(user_id) DO UPDATE SET granted_at = excluded.granted_at, granted_by = excluded.granted_by,"
                   " verification = excluded.verification, note = excluded.note, revoked_at = NULL",
                   (user_id, _sql_ts(now), granted_by, verification, note))
        db.commit()
    set_user_role(user_id, "admin")


def revoke_admin(user_id):
    now = _utcnow()
    if using_firestore():
        ref = _fs().collection("econ_admin_grants").document(str(user_id))
        if ref.get().exists:
            ref.set({"revoked_at": now.replace(tzinfo=datetime.timezone.utc)}, merge=True)
    else:
        db = get_db()
        db.execute("UPDATE econ_admin_grants SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                   (_sql_ts(now), user_id))
        db.commit()
    set_user_role(user_id, "student")


def get_admin_grant(user_id):
    """유효한(취소되지 않은) 관리자 부여 기록, 없으면 None."""
    if using_firestore():
        snap = _fs().collection("econ_admin_grants").document(str(user_id)).get()
        data = snap.to_dict() if snap.exists else None
    else:
        row = get_db().execute("SELECT * FROM econ_admin_grants WHERE user_id = ?", (user_id,)).fetchone()
        data = dict(row) if row else None
    if not data or data.get("revoked_at"):
        return None
    return {"granted_at": _as_dt(data.get("granted_at")), "granted_by": data.get("granted_by"),
            "verification": data.get("verification"), "note": data.get("note") or ""}


def list_admin_user_ids():
    if using_firestore():
        return sorted(d.id for d in _fs().collection("econ_admin_grants").stream() if not (d.to_dict() or {}).get("revoked_at"))
    return [r["user_id"] for r in get_db().execute("SELECT user_id FROM econ_admin_grants WHERE revoked_at IS NULL")]


# ============================================================================
# Phase 7: 콘텐츠 검토 감사 기록 (추가만, 수정·삭제 없음)
#   sqlite   : econ_content_reviews
#   Firestore: econ_content_reviews/{auto id} (seq 로 순서 보장)
# ============================================================================
REVIEW_DECISIONS = ("start_review", "approve", "request_changes", "reopen")
_REVIEW_FIELDS = ("target_type", "target_id", "content_version", "content_digest", "decision", "from_state", "to_state",
                  "reviewer_user_id", "reviewer_name", "comment")


def _review_dict(rid, data):
    refs = data.get("refs") if "refs" in data else data.get("refs_json")
    out = {"id": str(rid), **{k: data.get(k) for k in _REVIEW_FIELDS},
           "refs": json.loads(refs) if isinstance(refs, str) else (refs or {}), "created_at": _as_dt(data.get("created_at"))}
    out["seq"] = data.get("seq") or (int(rid) if str(rid).isdigit() else 0)
    return out


def add_content_review(record):
    """검토 결정 하나를 추가한다 (감사 기록이므로 고치거나 지우는 함수는 없다)."""
    if record["decision"] not in REVIEW_DECISIONS:
        raise ValueError(record["decision"])
    now = _utcnow()
    fields = {k: str(record[k]) if record.get(k) is not None else "" for k in _REVIEW_FIELDS}
    refs = record.get("refs") or {}
    if using_firestore():
        ref = _fs().collection("econ_content_reviews").document()
        ref.set({**fields, "refs": refs, "seq": time.time_ns(), "created_at": now.replace(tzinfo=datetime.timezone.utc)})
        return ref.id
    db = get_db()
    cur = db.execute(f"INSERT INTO econ_content_reviews ({', '.join(_REVIEW_FIELDS)}, refs_json, created_at)"
                     f" VALUES ({', '.join('?' * len(_REVIEW_FIELDS))}, ?, ?)",
                     (*fields.values(), json.dumps(refs, ensure_ascii=False), _sql_ts(now)))
    db.commit()
    return str(cur.lastrowid)


def list_content_reviews(target_type=None, target_id=None):
    """검토 기록, 오래된 것부터."""
    if using_firestore():
        rows = [_review_dict(d.id, d.to_dict()) for d in _fs().collection("econ_content_reviews").stream()]
        rows = [r for r in rows if (target_type is None or r["target_type"] == target_type)
                and (target_id is None or r["target_id"] == target_id)]
        rows.sort(key=lambda r: r["seq"])
        return rows
    sql, args = "SELECT * FROM econ_content_reviews", []
    if target_type is not None:
        sql, args = sql + " WHERE target_type = ? AND target_id = ?", [target_type, target_id]
    return [_review_dict(r["id"], dict(r)) for r in get_db().execute(sql + " ORDER BY id", args)]


def get_content_review(review_id):
    if using_firestore():
        snap = _fs().collection("econ_content_reviews").document(str(review_id)).get()
        return _review_dict(snap.id, snap.to_dict()) if snap.exists else None
    if not str(review_id).isdigit():
        return None
    row = get_db().execute("SELECT * FROM econ_content_reviews WHERE id = ?", (int(review_id),)).fetchone()
    return _review_dict(row["id"], dict(row)) if row else None


# ============================================================================
# Phase 7: SDG 캡스톤 프로젝트 (학생 본인 것만)
#   sqlite   : econ_capstone_projects, econ_capstone_versions, econ_capstone_self_assessments, econ_capstone_feedback
#   Firestore: users/{id}/econ_capstone/{course_id} + 하위 versions/{version}, self_assessments/{auto}, feedback/{auto}
# ============================================================================
_CAP_FIELDS = ("course_id", "status", "current_version", "submitted_version", "created_at", "updated_at", "submitted_at")


def _cap_dict(pid, data):
    out = {"id": str(pid), **{k: data.get(k) for k in _CAP_FIELDS}}
    for k in ("created_at", "updated_at", "submitted_at"):
        out[k] = _as_dt(out[k])
    out["current_version"] = int(out["current_version"] or 0)
    return out


def _cap_doc(user_id, course_id):
    return _fs().collection("users").document(str(user_id)).collection("econ_capstone").document(course_id)


def get_capstone(user_id, course_id):
    if using_firestore():
        snap = _cap_doc(user_id, course_id).get()
        return _cap_dict(snap.id, snap.to_dict()) if snap.exists else None
    row = get_db().execute("SELECT * FROM econ_capstone_projects WHERE user_id = ? AND course_id = ?",
                           (user_id, course_id)).fetchone()
    return _cap_dict(row["id"], dict(row)) if row else None


def list_capstones(user_id):
    if using_firestore():
        col = _fs().collection("users").document(str(user_id)).collection("econ_capstone")
        return [_cap_dict(d.id, d.to_dict()) for d in col.stream()]
    return [_cap_dict(r["id"], dict(r)) for r in get_db().execute(
        "SELECT * FROM econ_capstone_projects WHERE user_id = ? ORDER BY id", (user_id,))]


def save_capstone_version(user_id, course_id, sections, definition_version, kind="draft"):
    """새 버전을 저장한다 (이전 버전은 그대로 남는다). 반환: 새 버전 번호. 제출(kind='submitted')이면 상태도 바꾼다."""
    if kind not in ("draft", "submitted"):
        raise ValueError(kind)
    now = _utcnow()
    if using_firestore():
        db = _fs()
        ref = _cap_doc(user_id, course_id)

        @fb_firestore.transactional
        def _txn(transaction):
            snap = ref.get(transaction=transaction)
            data = snap.to_dict() if snap.exists else {"course_id": course_id, "status": "draft", "current_version": 0,
                                                        "created_at": now.replace(tzinfo=datetime.timezone.utc)}
            version = int(data.get("current_version") or 0) + 1
            data.update(current_version=version, updated_at=now.replace(tzinfo=datetime.timezone.utc))
            if kind == "submitted":
                data.update(status="submitted", submitted_version=version, submitted_at=now.replace(tzinfo=datetime.timezone.utc))
            elif data.get("status") == "submitted":
                data["status"] = "draft"   # 제출 뒤 다시 고치기 시작하면 새 초안 (예전 제출본은 버전으로 남음)
            transaction.set(ref, data)
            transaction.set(ref.collection("versions").document(str(version)),
                            {"version": version, "kind": kind, "definition_version": definition_version,
                             "sections": sections, "created_at": now.replace(tzinfo=datetime.timezone.utc)})
            return version

        return _txn(db.transaction())
    db = get_db()
    if db.in_transaction:
        db.commit()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT INTO econ_capstone_projects (user_id, course_id, created_at, updated_at) VALUES (?, ?, ?, ?)"
                   " ON CONFLICT(user_id, course_id) DO NOTHING", (user_id, course_id, _sql_ts(now), _sql_ts(now)))
        row = db.execute("SELECT * FROM econ_capstone_projects WHERE user_id = ? AND course_id = ?",
                         (user_id, course_id)).fetchone()
        version = row["current_version"] + 1
        db.execute("INSERT INTO econ_capstone_versions (project_id, version, kind, definition_version, sections_json,"
                   " created_at) VALUES (?, ?, ?, ?, ?, ?)",
                   (row["id"], version, kind, definition_version, json.dumps(sections, ensure_ascii=False), _sql_ts(now)))
        if kind == "submitted":
            db.execute("UPDATE econ_capstone_projects SET current_version = ?, status = 'submitted', submitted_version = ?,"
                       " submitted_at = ?, updated_at = ? WHERE id = ?", (version, version, _sql_ts(now), _sql_ts(now), row["id"]))
        else:
            db.execute("UPDATE econ_capstone_projects SET current_version = ?, status = 'draft', updated_at = ? WHERE id = ?",
                       (version, _sql_ts(now), row["id"]))
        db.commit()
        return version
    except BaseException:
        db.rollback()
        raise


def _ver_dict(data):
    sections = data.get("sections") if "sections" in data else data.get("sections_json")
    return {"version": int(data["version"]), "kind": data.get("kind"), "definition_version": data.get("definition_version"),
            "sections": json.loads(sections) if isinstance(sections, str) else (sections or {}),
            "created_at": _as_dt(data.get("created_at"))}


def list_capstone_versions(user_id, course_id):
    """본인 프로젝트의 버전들, 오래된 것부터."""
    if using_firestore():
        docs = [_ver_dict(d.to_dict()) for d in _cap_doc(user_id, course_id).collection("versions").stream()]
        return sorted(docs, key=lambda v: v["version"])
    project = get_capstone(user_id, course_id)
    if project is None:
        return []
    return [_ver_dict(dict(r)) for r in get_db().execute(
        "SELECT * FROM econ_capstone_versions WHERE project_id = ? ORDER BY version", (int(project["id"]),))]


def get_capstone_version(user_id, course_id, version):
    return next((v for v in list_capstone_versions(user_id, course_id) if v["version"] == int(version)), None)


def _cap_child(user_id, course_id, table, sub, version, field, payload):
    now = _utcnow()
    if using_firestore():
        _cap_doc(user_id, course_id).collection(sub).document().set(
            {"version": version, **payload, "seq": time.time_ns(), "created_at": now.replace(tzinfo=datetime.timezone.utc)})
        return
    project = get_capstone(user_id, course_id)
    if project is None:
        raise LookupError("project")
    db = get_db()
    cols = ", ".join(payload)
    db.execute(f"INSERT INTO {table} (project_id, version, {cols}, created_at) VALUES (?, ?, {', '.join('?' * len(payload))}, ?)",
               (int(project["id"]), version, *[json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                                               for v in payload.values()], _sql_ts(now)))
    db.commit()


def _cap_children(user_id, course_id, table, sub, json_field):
    if using_firestore():
        rows = [d.to_dict() for d in _cap_doc(user_id, course_id).collection(sub).stream()]
        rows.sort(key=lambda r: r.get("seq") or 0)
    else:
        project = get_capstone(user_id, course_id)
        if project is None:
            return []
        rows = [dict(r) for r in get_db().execute(f"SELECT * FROM {table} WHERE project_id = ? ORDER BY id",
                                                  (int(project["id"]),))]
    out = []
    for r in rows:
        value = r.get(json_field.replace("_json", "")) if json_field.replace("_json", "") in r else r.get(json_field)
        out.append({"version": int(r["version"]), json_field.replace("_json", ""): json.loads(value) if isinstance(value, str) else value,
                    "rubric_version": r.get("rubric_version"), "created_at": _as_dt(r.get("created_at"))})
    return out


def save_capstone_self_assessment(user_id, course_id, version, rubric_version, scores):
    _cap_child(user_id, course_id, "econ_capstone_self_assessments", "self_assessments", version, "scores",
               {"rubric_version": rubric_version, "scores_json": scores} if not using_firestore()
               else {"rubric_version": rubric_version, "scores": scores})


def list_capstone_self_assessments(user_id, course_id):
    return _cap_children(user_id, course_id, "econ_capstone_self_assessments", "self_assessments", "scores_json")


def save_capstone_feedback(user_id, course_id, version, feedback):
    _cap_child(user_id, course_id, "econ_capstone_feedback", "feedback", version, "feedback",
               {"feedback_json": feedback} if not using_firestore() else {"feedback": feedback})


def list_capstone_feedback(user_id, course_id):
    return _cap_children(user_id, course_id, "econ_capstone_feedback", "feedback", "feedback_json")


# ============================================================================
# Phase 7: 로그인 시도 제한 (이메일 해시 기준, 여러 워커가 같은 기록을 본다)
#   sqlite   : econ_login_attempts
#   Firestore: econ_login_attempts/{key} {"times": [...]}
# ============================================================================
def login_key(email):
    return hashlib.sha256(("login:" + str(email or "").strip().lower()).encode("utf-8")).hexdigest()[:32]


def count_login_failures(key, since):
    if using_firestore():
        snap = _fs().collection("econ_login_attempts").document(key).get()
        times = [_as_dt(t) for t in ((snap.to_dict() or {}).get("times") or [])] if snap.exists else []
        return sum(1 for t in times if t and t >= since)
    return get_db().execute("SELECT COUNT(*) AS n FROM econ_login_attempts WHERE key = ? AND attempted_at >= ?",
                            (key, _sql_ts(since))).fetchone()["n"]


def record_login_failure(key, at, keep_after):
    if using_firestore():
        ref = _fs().collection("econ_login_attempts").document(key)
        snap = ref.get()
        times = [t for t in ((snap.to_dict() or {}).get("times") or []) if (_as_dt(t) or at) >= keep_after]
        ref.set({"times": times[-50:] + [at.replace(tzinfo=datetime.timezone.utc)]})
        return
    db = get_db()
    db.execute("DELETE FROM econ_login_attempts WHERE key = ? AND attempted_at < ?", (key, _sql_ts(keep_after)))
    db.execute("INSERT INTO econ_login_attempts (key, attempted_at) VALUES (?, ?)", (key, _sql_ts(at)))
    db.commit()


def clear_login_failures(key):
    if using_firestore():
        _fs().collection("econ_login_attempts").document(key).delete()
        return
    db = get_db()
    db.execute("DELETE FROM econ_login_attempts WHERE key = ?", (key,))
    db.commit()


# ============================================================================
# Phase 7: 운영용 집계 (개인별 기록이 아닌 숫자만)
# ============================================================================
def aggregate_counts(day):
    """가입자 수, 강좌별 수강 수, 오늘 AI 요청 합계. 학생 개인 정보·기록은 돌려주지 않는다."""
    if using_firestore():
        users = list(_fs().collection("users").stream())
        per_course = {}
        for u in users:
            for e in _fs().collection("users").document(u.id).collection("econ_enrollments").stream():
                per_course[e.id] = per_course.get(e.id, 0) + 1
        gl = _fs().collection("econ_ai_usage_global").document(day).get().to_dict() or {}
        return {"users": len(users), "enrollments": per_course, "ai_requests_today": int(gl.get("requests") or 0)}
    db = get_db()
    per_course = {r["course_id"]: r["n"] for r in db.execute(
        "SELECT course_id, COUNT(*) AS n FROM econ_enrollments GROUP BY course_id")}
    gl = db.execute("SELECT requests FROM econ_ai_usage_global WHERE day = ?", (day,)).fetchone()
    return {"users": db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"], "enrollments": per_course,
            "ai_requests_today": gl["requests"] if gl else 0}


# ============================================================================
# Phase 8B-1: 로그인 실패 카운터 (econova/login_guard.py 가 키를 만든다)
#   sqlite   : econ_login_counters(key, count, expires_at)
#   Firestore: econ_login_counters/{key} {count, expires_at}
# ============================================================================
def incr_login_counter(key, expires_at):
    if using_firestore():
        _fs().collection("econ_login_counters").document(key).set(
            {"count": fb_firestore.Increment(1), "expires_at": expires_at.replace(tzinfo=datetime.timezone.utc)}, merge=True)
        return
    db = get_db()
    db.execute("INSERT INTO econ_login_counters (key, count, expires_at) VALUES (?, 1, ?)"
               " ON CONFLICT(key) DO UPDATE SET count = count + 1, expires_at = excluded.expires_at",
               (key, _sql_ts(expires_at)))
    db.commit()


def sum_login_counters(keys, now):
    """만료되지 않은 카운터들의 합."""
    total = 0
    for key in keys:
        if using_firestore():
            data = _fs().collection("econ_login_counters").document(key).get().to_dict() or {}
            exp, count = _as_dt(data.get("expires_at")), int(data.get("count") or 0)
        else:
            row = get_db().execute("SELECT count, expires_at FROM econ_login_counters WHERE key = ?", (key,)).fetchone()
            exp, count = (_as_dt(row["expires_at"]), row["count"]) if row else (None, 0)
        if exp is not None and exp > now:
            total += count
    return total


def delete_login_counters(keys):
    if using_firestore():
        for key in keys:
            _fs().collection("econ_login_counters").document(key).delete()
        return
    db = get_db()
    db.executemany("DELETE FROM econ_login_counters WHERE key = ?", [(k,) for k in keys])
    db.commit()


def purge_login_counters(now):
    """만료된 로그인 카운터와 예전 형식(econ_login_attempts) 기록을 지운다. 지운 수를 돌려준다."""
    if using_firestore():
        n = 0
        for d in _fs().collection("econ_login_counters").stream():
            exp = _as_dt((d.to_dict() or {}).get("expires_at"))
            if exp is None or exp <= now:
                _fs().collection("econ_login_counters").document(d.id).delete()
                n += 1
        for d in _fs().collection("econ_login_attempts").stream():
            _fs().collection("econ_login_attempts").document(d.id).delete()
            n += 1
        return n
    db = get_db()
    n = db.execute("DELETE FROM econ_login_counters WHERE expires_at <= ?", (_sql_ts(now),)).rowcount
    n += db.execute("DELETE FROM econ_login_attempts").rowcount
    db.commit()
    return n
