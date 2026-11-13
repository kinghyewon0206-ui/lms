"""fake 모드에서 쓰는 가짜 Firestore·가짜 OpenAI. 외부에 접속하지 않는다.

tests/fake_firestore.py 를 바탕으로, 실제 Firestore 에 더 가깝게 다음을 더한다.
- 트랜잭션 쓰기를 모았다가 끝에 한 번에 반영하고, 트랜잭션은 한 번에 하나씩만 실행한다 (Firestore 의 직렬화 보장).
- inject_conflicts 만큼 커밋 직전에 '충돌'을 일으켜 함수를 처음부터 다시 실행한다 (SDK 의 재시도). 이때 앞선 시도의
  쓰기는 버려진다 → 트랜잭션 함수가 다시 실행해도 안전한지(밖에 부작용이 없는지) 확인할 수 있다.
- 트랜잭션 안에서 쓴 뒤에 읽으면 실패시킨다 (Firestore 는 읽기를 모두 쓰기 앞에 해야 한다).

가짜 OpenAI 는 Chat Completions 응답 모양을 그대로 흉내 내는 urlopen 대체 함수다. 실제 OpenAIProvider 코드를 그대로 지난다.
"""
import io
import json
import socket
import threading
import types
import urllib.error

from econova.ai.safety import MATERIAL_TAG
from tests import fake_firestore as base


class RetryingFirestore(base.FakeFirestore):
    def __init__(self):
        super().__init__()
        self.lock = threading.RLock()
        self.inject_conflicts = 0
        self.attempts = 0
        self.retries = 0

    def transaction(self):
        return BufferedTransaction(self)

    def recursive_delete(self, ref):
        prefix = ref.path
        for path in [p for p in self.docs if p[:len(prefix)] == prefix]:
            del self.docs[path]

    @property
    def project(self):
        return "fake-econova-it"


class BufferedTransaction:
    def __init__(self, db):
        self.db = db
        self.writes = []

    def set(self, ref, data, merge=False):
        self.writes.append((ref, data, merge))


def transactional(fn):
    def run(txn):
        db = txn.db
        with db.lock:
            for _ in range(6):
                txn.writes = []
                db.attempts += 1
                result = fn(txn)        # 예외가 나면 쓰기는 버려진다
                if db.inject_conflicts > 0:
                    db.inject_conflicts -= 1
                    db.retries += 1
                    continue
                for ref, data, merge in txn.writes:
                    ref.set(data, merge=merge)
                return result
            raise RuntimeError("트랜잭션 충돌이 계속되었습니다")
    return run


module = types.SimpleNamespace(SERVER_TIMESTAMP=base.module.SERVER_TIMESTAMP, Increment=base.Increment,
                               transactional=transactional)

_original_get = base.FakeDocRef.get


def strict_get(self, transaction=None):
    if transaction is not None and getattr(transaction, "writes", None):
        raise AssertionError("Firestore 트랜잭션에서 쓰기 뒤에 읽었습니다 (실제 Firestore 에서는 오류).")
    return _original_get(self, transaction=transaction)


# ------------------------------------------------------------------ 가짜 OpenAI
class FakeOpenAI:
    """urlopen(req, timeout) 대체. behaviour 로 다음 응답을 정한다:
    'ok' | 'fake_source' | 'invalid_schema' | 'refusal' | 'length' | 'timeout' | 'http_500' | 'http_401' | 'not_json'."""

    def __init__(self):
        self.behaviour = "ok"
        self.bodies = []
        self.usage = []

    @property
    def sent(self):
        return len(self.bodies)

    def __call__(self, req, timeout=None):
        body = json.loads(req.data.decode("utf-8"))
        self.bodies.append(body)
        b = self.behaviour
        if b == "timeout":
            raise socket.timeout("timed out")
        if b in ("http_500", "http_401"):
            raise urllib.error.HTTPError(req.full_url, int(b[5:]), "error", {}, io.BytesIO(b"{}"))
        content = json.dumps(self._answer(body), ensure_ascii=False)
        finish = "length" if b == "length" else "stop"
        message = {"role": "assistant", "content": "not json" if b == "not_json" else content}
        if b == "refusal":
            message["refusal"] = "I can't help with that."
        raw = {"model": body["model"] + "-fake", "choices": [{"index": 0, "finish_reason": finish, "message": message}],
               "usage": {"prompt_tokens": len(req.data) // 4, "completion_tokens": len(content) // 4}}
        self.usage.append(raw["usage"])
        return _Resp(json.dumps(raw).encode("utf-8"))

    def _answer(self, body):
        schema = body["response_format"]["json_schema"]["schema"]
        data = _fill(schema)
        if self.behaviour == "invalid_schema":
            data = {"unexpected": True}
        material = next((m["content"] for m in body["messages"] if m["content"].startswith(f"<{MATERIAL_TAG}>")), "")
        ctx = json.loads(material[len(f"<{MATERIAL_TAG}>\n"):-len(f"\n</{MATERIAL_TAG}>")]) if material else {}
        if isinstance(data.get("items"), list) and data["items"] and "question_id" in data["items"][0]:
            data["items"] = [dict(data["items"][0], question_id=q["id"]) for q in ctx.get("questions", [])]
        if "used_source_ids" in data:   # 서버가 <자료> 에 넣어 준 출처 목록에서만 고른다 (실제 공급자에게 기대하는 행동)
            data["used_source_ids"] = [s["id"] for s in ctx.get("sources", [])][:1]
            data["grounding"] = "grounded" if data["used_source_ids"] else "insufficient"
            if self.behaviour == "fake_source":
                data["used_source_ids"].append("fabricated-source-9999")
        return data


def _fill(schema):
    """strict 스키마에 맞는 최소 응답."""
    kind = schema["type"]
    if kind == "object":
        return {k: _fill(v) for k, v in schema["properties"].items()}
    if kind == "array":
        return [_fill(schema["items"])]
    if kind == "string":
        return schema["enum"][0] if "enum" in schema else "Fake reply"   # 10자 이하 (probe 스키마의 maxLength — 공급자에게는 전달되지 않음)
    if kind == "integer":
        return 1
    if kind == "boolean":
        return False
    raise ValueError(kind)


class _Resp:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

