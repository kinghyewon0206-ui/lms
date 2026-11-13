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
    """키 파일을 읽는다. 없으면 KeysUnavailable. (읽은 내용은 로그·오류 메시지에 넣지 않는다)"""
    path = keys_path(assessment_id, fixture)
    if path is None:
        raise KeysUnavailable(f"{assessment_id}: 비공개 정답 키 폴더(ECONOVA_PRIVATE_CONTENT_DIR)가 설정되지 않았습니다.")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise KeysUnavailable(f"{assessment_id}: 정답 키 파일이 없습니다.")
    except (OSError, json.JSONDecodeError):
        raise KeysUnavailable(f"{assessment_id}: 정답 키 파일을 읽을 수 없습니다.")
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("kind") != "assessment_keys":
        raise KeysUnavailable(f"{assessment_id}: 정답 키 파일 형식이 잘못됐습니다.")
    if data.get("assessment_id") != assessment_id:
        raise KeysUnavailable(f"{assessment_id}: 정답 키 파일의 assessment_id 가 다릅니다.")
    if fixture and data.get("synthetic") is not True:
        raise KeysUnavailable(f"{assessment_id}: 개발용 fixture 키에는 \"synthetic\": true 가 있어야 합니다.")
    return data


def merge(public, keys, where):
    """공개 정의 + 정답 키 → 서버 전용 전체 데이터(복사본). 하나라도 맞지 않으면 KeysUnavailable."""
    if keys.get("assessment_version") != public.get("version"):
        raise KeysUnavailable(f"{where}: 정답 키의 평가 버전({keys.get('assessment_version')})이 "
                              f"공개 파일 버전({public.get('version')})과 다릅니다.")
    entries = keys.get("questions")
    public_ids = [q.get("id") for q in public.get("questions") or []]
    if not isinstance(entries, dict) or set(entries) != set(public_ids):
        raise KeysUnavailable(f"{where}: 정답 키의 문항 목록이 공개 문항과 다릅니다.")
    full = copy.deepcopy(public)
    for q in full["questions"]:
        entry = entries[q["id"]]
        if not isinstance(entry, dict) or entry.get("question_version") != q.get("version"):
            raise KeysUnavailable(f"{where} 문항 {q['id']}: 정답 키의 문항 버전이 다릅니다.")
        if entry.get("public_sha256") != question_fingerprint(q):
            raise KeysUnavailable(f"{where} 문항 {q['id']}: 공개 문항이 바뀌어 정답 키를 다시 확인해야 합니다.")
        unknown = set(entry) - {"question_version", "public_sha256"} - set(PRIVATE_QUESTION_KEYS)
        if unknown:
            raise KeysUnavailable(f"{where} 문항 {q['id']}: 정답 키에 알 수 없는 항목 {sorted(unknown)} 이 있습니다.")
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
