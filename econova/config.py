"""환경 설정. 어떤 저장소(sqlite / firestore)를 쓸지는 DB_BACKEND 로만 정한다.

예전에는 FIREBASE_CREDENTIALS_JSON 이 있기만 하면 Firestore 를 썼다. 그래서 로컬 .env 에 운영 키가 있으면
로컬 실행이 운영 데이터베이스를 건드렸다. 이제는 DB_BACKEND=firestore 라고 직접 적어야만 Firestore 를 쓴다.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOTENV_PATH = os.path.join(BASE_DIR, ".env")  # 테스트에서는 다른 경로로 바꿔 실제 .env 를 읽지 않게 한다

BACKENDS = ("sqlite", "firestore")


class ConfigError(RuntimeError):
    """설정이 잘못돼서 안전하게 실행할 수 없을 때."""


def env(name):
    """환경변수 또는 .env 파일에서 값을 읽는다. (.env 는 저장 즉시 반영, 서버 재시작 불필요)"""
    if os.environ.get(name):
        return os.environ[name]
    try:
        with open(DOTENV_PATH, encoding="utf-8") as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key.strip() == name:
                    return value.strip().strip("\"'")
    except OSError:
        pass
    return ""


def is_production():
    """운영 환경인지. Render 는 모든 서비스에 RENDER 환경변수를 넣어 준다. 다른 곳에서는 APP_ENV=production."""
    return bool(os.environ.get("RENDER")) or env("APP_ENV").strip().lower() == "production"


def db_backend():
    """'sqlite' 또는 'firestore'. 설정하지 않으면 sqlite.

    운영 환경에서 DB_BACKEND 를 빠뜨리면 재배포 때 지워지는 sqlite 에 회원 데이터가 쌓이므로,
    조용히 sqlite 로 넘어가지 않고 실행을 멈춘다.
    """
    value = env("DB_BACKEND").strip().lower()
    if not value:
        if is_production():
            raise ConfigError("운영 환경에서는 DB_BACKEND 를 반드시 설정해야 합니다. (예: DB_BACKEND=firestore)")
        return "sqlite"
    if value not in BACKENDS:
        raise ConfigError(f"DB_BACKEND 는 {' / '.join(BACKENDS)} 중 하나여야 합니다. (현재: {value!r})")
    if value == "firestore" and not env("FIREBASE_CREDENTIALS_JSON"):
        raise ConfigError("DB_BACKEND=firestore 인데 FIREBASE_CREDENTIALS_JSON 이 없습니다.")
    return value


def sqlite_path():
    """sqlite 파일 위치. SQLITE_PATH 로 바꿀 수 있다. (테스트는 임시 파일을 쓴다)"""
    return env("SQLITE_PATH") or os.path.join(BASE_DIR, "lms.db")
