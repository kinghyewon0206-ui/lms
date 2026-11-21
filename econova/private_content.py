"""평가 정답 키 분리: 공개 문항 정의(저장소) + 비공개 정답 키(저장소 밖)를 신뢰할 수 있는 서버에서만 합친다.

공개 저장소의 평가 파일(content/assessments/<id>.json, content/diagnostic.json)에는 문항·선택지·학습목표·난이도·배점만 둔다.
정답·허용오차·해설·검증식(check/verify)은 비공개 폴더(config.private_content_dir())의 <평가 id>.answers.json 에 둔다.
폴더 구조가 평평하므로(하위 폴더 없음) Render Secret Files 에 파일 그대로 올릴 수 있다.

키 파일 형식 (schema_version 1):
    {"schema_version": 1, "kind": "assessment_keys", "assessment_id": "c02-l1-quiz", "assessment_version": 1,
     "questions": {"q1": {"question_version": 1, "public_sha256": "...", "answer": "b", "explanation": "...", "check": {...}}}}

public_sha256 은 공개 문항의 채점에 영향을 주는 부분(id·version·type·prompt·선택지·단위)의 지문이다. 공개 문항이 바뀌었는데
키가 그대로면 지문이 달라지고, 그 평가는 열리지 않는다(fail closed). 키가 없을 때도 마찬가지다. 다른 값으로 대신 채점하지 않는다.

개발용 fixture 의 키는 합성(가짜) 값이라 저장소의 content/dev_fixtures/private/ 에 둔다 ("synthetic": true).
"""
import copy
import hashlib
import json
import os

from econova import config
from econova.lesson_content import ContentError

PRIVATE_QUESTION_KEYS = ("answer", "tolerance", "explanation", "check", "verify")
KEYS_SUFFIX = ".answers.json"
FIXTURE_KEYS_DIR = os.path.join(config.BASE_DIR, "content", "dev_fixtures", "private")


class KeysUnavailable(ContentError):
    """정답 키가 없거나 공개 문항과 맞지 않는다. 그 평가만 열지 않는다 (카탈로그 전체는 정상)."""


def question_fingerprint(q):
    """공개 문항 중 채점에 영향을 주는 부분의 sha256."""
    core = {"id": q.get("id"), "version": q.get("version"), "type": q.get("type"), "prompt": q.get("prompt"),
            "choices": [{"id": c.get("id"), "text": c.get("text")} for c in q.get("choices") or []],
            "unit": q.get("unit") or ""}
    return hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def public_violations(data):
    """공개 평가 데이터 안에 들어 있으면 안 되는 정답 정보의 위치 목록."""
    found = []
    for q in (data or {}).get("questions") or []:
        if isinstance(q, dict):
            found += [f"{q.get('id', '?')}.{k}" for k in PRIVATE_QUESTION_KEYS if k in q]
            found += [f"{q.get('id', '?')}.choices[{c.get('id')}].correct" for c in q.get("choices") or []
                      if isinstance(c, dict) and ("correct" in c or "is_correct" in c)]
    if isinstance(data, dict) and ("answers" in data or "answer_key" in data):
        found.append("answers")
    return found


def keys_path(assessment_id, fixture=False):
    """정답 키 파일 경로. 비공개 폴더를 설정하지 않은 운영 환경에서는 None."""
    base = FIXTURE_KEYS_DIR if fixture else config.private_content_dir()
    return os.path.join(base, f"{assessment_id}{KEYS_SUFFIX}") if base else None


def read_keys(assessment_id, fixture=False):
    """정답 키를 읽는다. 없으면 KeysUnavailable. (읽은 내용은 로그·오류 메시지에 넣지 않는다)
    실제 평가의 키는 (1) 묶음(ECONOVA_PRIVATE_KEYS_BUNDLE 또는 Secret Manager)이 설정돼 있으면 거기서,
    (2) 아니면 비공개 폴더(ECONOVA_PRIVATE_CONTENT_DIR)에서 읽는다. 개발용 fixture 키는 항상 저장소의 합성 키 폴더에서 읽는다."""
    if not fixture:
        bundle = key_bundle()
        if bundle is not None:
            data = bundle.get(assessment_id)
            if data is None:
                raise KeysUnavailable(f"{assessment_id}: the answer key bundle has no key for this assessment.")
            return _check_keys(assessment_id, data, fixture)
    path = keys_path(assessment_id, fixture)
    if path is None:
        raise KeysUnavailable(f"{assessment_id}: the private answer key folder (ECONOVA_PRIVATE_CONTENT_DIR) is not set.")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise KeysUnavailable(f"{assessment_id}: the answer key file does not exist.")
    except (OSError, json.JSONDecodeError):
        raise KeysUnavailable(f"{assessment_id}: the answer key file cannot be read.")
    return _check_keys(assessment_id, data, fixture)


def _check_keys(assessment_id, data, fixture):
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("kind") != "assessment_keys":
        raise KeysUnavailable(f"{assessment_id}: the answer key file has an invalid format.")
    if data.get("assessment_id") != assessment_id:
        raise KeysUnavailable(f"{assessment_id}: the answer key file's assessment_id does not match.")
    if fixture and data.get("synthetic") is not True:
        raise KeysUnavailable(f"{assessment_id}: dev fixture keys must include \"synthetic\": true.")
    return data


def merge(public, keys, where):
    """공개 정의 + 정답 키 → 서버 전용 전체 데이터(복사본). 하나라도 맞지 않으면 KeysUnavailable."""
    if keys.get("assessment_version") != public.get("version"):
        raise KeysUnavailable(f"{where}: the answer key's assessment version ({keys.get('assessment_version')}) does not match "
                              f"the public file version ({public.get('version')}).")
    entries = keys.get("questions")
    public_ids = [q.get("id") for q in public.get("questions") or []]
    if not isinstance(entries, dict) or set(entries) != set(public_ids):
        raise KeysUnavailable(f"{where}: the answer key's question list does not match the public questions.")
    full = copy.deepcopy(public)
    for q in full["questions"]:
        entry = entries[q["id"]]
        if not isinstance(entry, dict) or entry.get("question_version") != q.get("version"):
            raise KeysUnavailable(f"{where} question {q['id']}: the answer key's question version does not match.")
        if entry.get("public_sha256") != question_fingerprint(q):
            raise KeysUnavailable(f"{where} question {q['id']}: the public question changed, so the answer key must be re-checked.")
        unknown = set(entry) - {"question_version", "public_sha256"} - set(PRIVATE_QUESTION_KEYS)
        if unknown:
            raise KeysUnavailable(f"{where} question {q['id']}: the answer key has unknown fields {sorted(unknown)}.")
        q.update({k: copy.deepcopy(entry[k]) for k in PRIVATE_QUESTION_KEYS if k in entry})
    return full


def split(full, assessment_id, synthetic=False):
    """정답이 들어 있는 전체 데이터 → (공개 정의, 정답 키). 이전 형식 파일을 옮기거나 테스트 데이터를 만들 때 쓴다."""
    public = copy.deepcopy(full)
    entries = {}
    for q in public.get("questions") or []:
        q.pop("answer_key", None)
        for c in q.get("choices") or []:
            c.pop("correct", None)
            c.pop("is_correct", None)
        private = {k: q.pop(k) for k in PRIVATE_QUESTION_KEYS if k in q}
        entries[q["id"]] = {"question_version": q.get("version"), "public_sha256": question_fingerprint(q), **private}
    keys = {"schema_version": 1, "kind": "assessment_keys", "assessment_id": assessment_id,
            "assessment_version": full.get("version"), "questions": entries}
    if synthetic:
        keys["synthetic"] = True
    return public, keys


# ---------------------------------------------------------------- 서버리스 배포용 정답 키 묶음 (Vercel 등: 파일을 둘 곳이 없음)
# 형식: {"schema_version": 1, "kind": "assessment_key_bundle", "keys": {assessment_id: <키 파일 내용>}} 를 gzip → base64.
# 출처 두 가지 중 하나:
#   ECONOVA_PRIVATE_KEYS_BUNDLE      : 그 문자열 자체 (Vercel 의 Sensitive 환경변수)
#   ECONOVA_PRIVATE_KEYS_SECRET      : Google Secret Manager 의 비밀 이름 (projects/<p>/secrets/<s>/versions/<v>)
#                                      — Firestore 와 같은 서비스 계정으로 읽는다 (그 계정에 secretAccessor 권한 필요)
# 프로세스당 한 번 읽어 메모리에만 둔다. 디스크에 쓰지 않고, 내용은 로그에 남기지 않는다.
BUNDLE_KIND = "assessment_key_bundle"
_bundle_cache = {"source": None, "keys": None}


def encode_bundle(keys_by_id):
    import base64
    import gzip
    raw = json.dumps({"schema_version": 1, "kind": BUNDLE_KIND, "keys": keys_by_id}, ensure_ascii=False,
                     sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")


def decode_bundle(text):
    import base64
    import binascii
    import gzip
    try:
        data = json.loads(gzip.decompress(base64.b64decode(text.strip(), validate=True)).decode("utf-8"))
    except (binascii.Error, OSError, ValueError, EOFError):
        raise KeysUnavailable("the answer key bundle cannot be decoded.")
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("kind") != BUNDLE_KIND \
            or not isinstance(data.get("keys"), dict):
        raise KeysUnavailable("the answer key bundle has an invalid format.")
    return data["keys"]


def _secret_manager_text(name):
    """Secret Manager REST 로 비밀 값을 읽는다 (추가 라이브러리 없이 google-auth 만 사용)."""
    import base64
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    info = json.loads(config.env("FIREBASE_CREDENTIALS_JSON") or "{}")
    creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    resp = AuthorizedSession(creds).get(f"https://secretmanager.googleapis.com/v1/{name}:access", timeout=10)
    if resp.status_code != 200:
        raise KeysUnavailable(f"Secret Manager returned HTTP {resp.status_code} for the answer key bundle.")
    return base64.b64decode(resp.json()["payload"]["data"]).decode("ascii")


def key_bundle():
    """설정된 묶음을 {assessment_id: keys} 로 돌려준다. 묶음을 쓰지 않으면 None."""
    inline = config.env("ECONOVA_PRIVATE_KEYS_BUNDLE").strip()
    secret = config.env("ECONOVA_PRIVATE_KEYS_SECRET").strip()
    if not inline and not secret:
        return None
    source = ("inline", hashlib.sha256(inline.encode()).hexdigest()) if inline else ("secret", secret)
    if _bundle_cache["source"] != source:
        text = inline if inline else _secret_manager_text(secret)
        _bundle_cache.update(source=source, keys=decode_bundle(text))
    return _bundle_cache["keys"]
