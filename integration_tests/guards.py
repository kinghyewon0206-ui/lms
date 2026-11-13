"""실제 외부 연동 시험(Phase 8B-2)을 시작해도 되는지 검사한다. 하나라도 어긋나면 접속하기 전에 거부한다.

기본은 'fake' (외부 접속 없음). 'live' 는 사람이 개발 전용 자원을 직접 정하고 승인한 값을 환경변수로 줄 때만 동작한다.
이 모듈은 파일 내용(키 값)을 출력하지 않는다. 오류 메시지에는 어떤 조건이 어긋났는지만 적는다.

Firestore live 조건 (ECONOVA_IT_FIRESTORE=live)
- ECONOVA_IT_FIREBASE_PROJECT_ID      사람이 지정한 ECONOVA 프로젝트 id (예: econova-dev). 이름에 dev/test/it/qa/sandbox/staging
                                      구간이 있어야 한다. 이 id 한 곳에만 접속한다 (다른 프로젝트는 키·접속 확인에서 거부)
- ECONOVA_IT_FIREBASE_CREDENTIALS_FILE 저장소 밖 절대 경로, 소유자만 읽을 수 있는 권한(600), 그 키의 project_id 가 위와 같아야 함
- ECONOVA_IT_FIRESTORE_APPROVAL        위 프로젝트 id 를 한 번 더 그대로 적는다 (승인 확인)
- 셸에 FIREBASE_CREDENTIALS_JSON 이 있으면 거부 (운영 키가 섞이지 않게), 운영 환경 표시(RENDER/APP_ENV)가 있으면 거부
접속한 뒤에도: 클라이언트의 project 가 같은지, 표식 문서(econova_it/marker)가 있는지, users 에 시험 계정만 있는지 확인한다.

OpenAI live 조건 (ECONOVA_IT_OPENAI=live)
- ECONOVA_IT_OPENAI_KEY_FILE      저장소 밖 절대 경로, 권한 600, 내용은 키 한 줄
- ECONOVA_IT_OPENAI_MODEL         모델 이름 (기본값 없음 — 사람이 고른다)
- ECONOVA_IT_OPENAI_MAX_REQUESTS  이번 실행에서 보낼 수 있는 최대 요청 수 (1~30)
- ECONOVA_IT_OPENAI_APPROVAL      "<모델>:<최대 요청 수>" 를 그대로 적는다 (승인 확인)
- 셸에 OPENAI_API_KEY 가 있으면 거부 (운영 키가 섞이지 않게)
"""
import json
import os
import re
import stat
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODES = ("fake", "live")
IT_EMAIL_DOMAIN = "econova-it.invalid"   # 시험 계정 전용 (실제로 존재할 수 없는 도메인)
MARKER = ("econova_it", "marker")
MARKER_PURPOSE = "econova-integration-tests"
DEV_LABELS = {"dev", "test", "it", "qa", "sandbox", "staging"}
PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
MAX_OPENAI_REQUESTS = 30
MAX_REQUEST_BYTES = 24000          # 요청 하나의 본문 상한 (입력 토큰 상한 ≈ 6천)
MAX_OUTPUT_TOKENS = 700


class IntegrationRefused(Exception):
    """실제 연동을 시작하지 않는다. 메시지는 사람이 고칠 수 있는 조건만 담는다 (비밀값 없음)."""


def mode(name, environ=None):
    environ = os.environ if environ is None else environ
    value = (environ.get(name) or "fake").strip().lower()
    if value not in MODES:
        raise IntegrationRefused(f"{name} 는 fake 또는 live 여야 합니다.")
    return value


def _production_flags(environ):
    if environ.get("RENDER") or (environ.get("APP_ENV") or "").strip().lower() in ("production", "prod"):
        raise IntegrationRefused("운영 환경 표시(RENDER/APP_ENV=production)가 있는 곳에서는 연동 시험을 하지 않습니다.")


def _secret_file(path, label):
    """저장소 밖, 소유자만 읽을 수 있는 일반 파일인지. 내용은 여기서 읽지 않는다."""
    if not path:
        raise IntegrationRefused(f"{label} 경로가 없습니다.")
    if not os.path.isabs(path):
        raise IntegrationRefused(f"{label} 는 절대 경로여야 합니다.")
    real = os.path.realpath(path)
    root = os.path.realpath(ROOT)
    if real == root or real.startswith(root + os.sep):
        raise IntegrationRefused(f"{label} 가 저장소 안에 있습니다. 저장소 밖(예: ~/econova-dev-secrets/)으로 옮기세요.")
    if os.path.basename(real) == ".env":
        raise IntegrationRefused(f"{label} 로 .env 를 쓰지 않습니다.")
    if not os.path.isfile(real):
        raise IntegrationRefused(f"{label} 파일이 없습니다.")
    if stat.S_IMODE(os.stat(real).st_mode) & 0o077:
        raise IntegrationRefused(f"{label} 권한이 너무 넓습니다. chmod 600 으로 소유자만 읽게 하세요.")
    return real


def check_project_id(expected):
    if not expected:
        raise IntegrationRefused("ECONOVA_IT_FIREBASE_PROJECT_ID (개발 프로젝트 id)가 없습니다.")
    if not PROJECT_ID.match(expected):
        raise IntegrationRefused("ECONOVA_IT_FIREBASE_PROJECT_ID 형식이 Firebase 프로젝트 id 가 아닙니다.")
    if not DEV_LABELS & set(expected.split("-")):
        raise IntegrationRefused("개발 프로젝트 id 에 dev/test/it/qa/sandbox/staging 구간이 없습니다 (예: econova-dev).")


@dataclass(frozen=True)
class FirestoreLive:
    project_id: str
    credentials_path: str


def firestore_live(environ=None):
    """live 조건을 모두 확인하고 FirestoreLive 를 돌려준다. 접속은 하지 않는다."""
    environ = os.environ if environ is None else environ
    _production_flags(environ)
    if environ.get("FIREBASE_CREDENTIALS_JSON"):
        raise IntegrationRefused("셸에 FIREBASE_CREDENTIALS_JSON 이 있습니다 (운영 키일 수 있음). unset 한 뒤 다시 실행하세요.")
    expected = (environ.get("ECONOVA_IT_FIREBASE_PROJECT_ID") or "").strip()
    check_project_id(expected)
    if (environ.get("ECONOVA_IT_FIRESTORE_APPROVAL") or "").strip() != expected:
        raise IntegrationRefused("ECONOVA_IT_FIRESTORE_APPROVAL 에 승인한 개발 프로젝트 id 를 그대로 적어 주세요.")
    path = _secret_file(environ.get("ECONOVA_IT_FIREBASE_CREDENTIALS_FILE"), "ECONOVA_IT_FIREBASE_CREDENTIALS_FILE")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        raise IntegrationRefused("서비스 계정 키 파일을 JSON 으로 읽을 수 없습니다.")
    if not isinstance(data, dict) or data.get("type") != "service_account":
        raise IntegrationRefused("서비스 계정 키(type=service_account)가 아닙니다.")
    if data.get("project_id") != expected:
        raise IntegrationRefused("키 파일의 project_id 가 승인한 개발 프로젝트와 다릅니다. 접속하지 않습니다.")
    if not str(data.get("client_email", "")).endswith(f"@{expected}.iam.gserviceaccount.com"):
        raise IntegrationRefused("키 파일의 서비스 계정이 승인한 개발 프로젝트 소속이 아닙니다.")
    return FirestoreLive(project_id=expected, credentials_path=path)


def check_connected(client_project, marker, user_ids, expected):
    """접속한 뒤의 확인. marker: 표식 문서 dict 또는 None, user_ids: users 컬렉션 문서 id 일부."""
    if client_project != expected:
        raise IntegrationRefused("접속한 Firestore 프로젝트가 승인한 개발 프로젝트가 아닙니다.")
    if not marker or marker.get("purpose") != MARKER_PURPOSE or marker.get("project_id") != expected:
        raise IntegrationRefused("개발 프로젝트 표식 문서(econova_it/marker)가 없습니다. "
                                 "python -m integration_tests.firestore_marker create 로 먼저 만드세요 (같은 승인 조건 필요).")
    others = [u for u in user_ids if not u.endswith("@" + IT_EMAIL_DOMAIN)]
    if others:
        raise IntegrationRefused(f"이 프로젝트에 시험 계정이 아닌 사용자 문서가 {len(others)}개 있습니다. 실제 사용자가 있는 "
                                 "프로젝트에서는 시험하지 않습니다.")


@dataclass(frozen=True)
class OpenAILive:
    key_path: str
    model: str
    max_requests: int


def openai_live(environ=None):
    environ = os.environ if environ is None else environ
    _production_flags(environ)
    if environ.get("OPENAI_API_KEY"):
        raise IntegrationRefused("셸에 OPENAI_API_KEY 가 있습니다 (운영 키일 수 있음). unset 하고 개발 키는 "
                                 "ECONOVA_IT_OPENAI_KEY_FILE 로 주세요.")
    model = (environ.get("ECONOVA_IT_OPENAI_MODEL") or "").strip()
    if not model or not re.fullmatch(r"[A-Za-z0-9._:-]{2,64}", model):
        raise IntegrationRefused("ECONOVA_IT_OPENAI_MODEL 에 사용할 모델 이름을 적어 주세요 (기본값 없음).")
    try:
        max_requests = int(environ.get("ECONOVA_IT_OPENAI_MAX_REQUESTS") or "0")
    except ValueError:
        max_requests = 0
    if not 1 <= max_requests <= MAX_OPENAI_REQUESTS:
        raise IntegrationRefused(f"ECONOVA_IT_OPENAI_MAX_REQUESTS 는 1~{MAX_OPENAI_REQUESTS} 사이여야 합니다.")
    if (environ.get("ECONOVA_IT_OPENAI_APPROVAL") or "").strip() != f"{model}:{max_requests}":
        raise IntegrationRefused("ECONOVA_IT_OPENAI_APPROVAL 에 '<모델>:<최대 요청 수>' 를 그대로 적어 주세요.")
    path = _secret_file(environ.get("ECONOVA_IT_OPENAI_KEY_FILE"), "ECONOVA_IT_OPENAI_KEY_FILE")
    return OpenAILive(key_path=path, model=model, max_requests=max_requests)


def read_key(path):
    """키 파일 내용 (한 줄). 형식만 확인하고 값은 어디에도 출력하지 않는다."""
    with open(path, encoding="utf-8") as f:
        key = f.read().strip()
    if not re.fullmatch(r"sk-[A-Za-z0-9_\-]{20,200}", key):
        raise IntegrationRefused("ECONOVA_IT_OPENAI_KEY_FILE 내용이 OpenAI 키 형식(sk-…) 한 줄이 아닙니다.")
    return key
