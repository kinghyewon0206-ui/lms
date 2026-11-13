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


def dev_fixtures_enabled():
    """개발용 테스트 강좌(content/dev_fixtures)를 보여줄지. ECONOVA_DEV_FIXTURES=1 일 때만 켜지고,
    운영 환경에서 켜려고 하면 실행을 멈춘다. (가짜 자료가 학생에게 보이면 안 되므로)"""
    if env("ECONOVA_DEV_FIXTURES").strip() != "1":
        return False
    if is_production():
        raise ConfigError("운영 환경에서는 ECONOVA_DEV_FIXTURES 를 켤 수 없습니다.")
    return True


def content_preview_enabled():
    """검토 전 초안(draft·in_review) 학습자료 미리보기(/preview/...)를 켤지. ECONOVA_CONTENT_PREVIEW=1 일 때만 켜지고,
    운영 환경에서 켜려고 하면 실행을 멈춘다. (초안이 학생에게 공개되면 안 되므로)"""
    if env("ECONOVA_CONTENT_PREVIEW").strip() != "1":
        return False
    if is_production():
        raise ConfigError("운영 환경에서는 ECONOVA_CONTENT_PREVIEW 를 켤 수 없습니다.")
    return True


def private_content_dir():
    """정답 키·교사용 검토 문서처럼 공개 저장소에 두면 안 되는 자료의 폴더 (ECONOVA_PRIVATE_CONTENT_DIR).

    기본값은 저장소 밖이다. 개발: ~/econova-private. 운영: 기본값 없음 (설정하지 않으면 정답 키가 필요한 평가는
    열리지 않는다 — 조용히 다른 값으로 채점하지 않는다). Render 에서는 Secret Files 를 쓰고 그 폴더(/etc/secrets)를 적는다.
    저장소 안을 가리키면 실수로 커밋될 수 있으므로 실행을 멈춘다 (.gitignore 된 폴더라도 허용하지 않는다).
    """
    value = env("ECONOVA_PRIVATE_CONTENT_DIR").strip()
    if not value:
        return None if is_production() else os.path.join(os.path.expanduser("~"), "econova-private")
    path = os.path.realpath(os.path.expanduser(value))
    if path == os.path.realpath(BASE_DIR) or path.startswith(os.path.realpath(BASE_DIR) + os.sep):
        raise ConfigError("ECONOVA_PRIVATE_CONTENT_DIR 는 저장소 밖 폴더여야 합니다 (정답 키가 커밋되지 않도록).")
    return path


DEFAULT_SECRET_KEY = "dev-only-change-me"


def secret_key():
    """세션 서명 키. 운영에서는 32자 이상의 SECRET_KEY 가 반드시 있어야 한다 (기본값이면 세션 위조가 가능)."""
    value = os.environ.get("SECRET_KEY") or env("SECRET_KEY")
    if is_production() and (not value or value == DEFAULT_SECRET_KEY or len(value) < 32):
        raise ConfigError("운영 환경에서는 32자 이상의 SECRET_KEY 를 설정해야 합니다.")
    return value or DEFAULT_SECRET_KEY


def sqlite_path():
    """sqlite 파일 위치. SQLITE_PATH 로 바꿀 수 있다. (테스트는 임시 파일을 쓴다)"""
    return env("SQLITE_PATH") or os.path.join(BASE_DIR, "lms.db")
