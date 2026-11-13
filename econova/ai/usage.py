"""AI 요청 한 번의 공통 흐름: 설정 확인 → 동시 요청 잠금 → 한도 예약(실패해도 센다) → 공급자 호출 → 스키마 검사
→ 토큰 기록 → 잠금 해제. 한도는 저장소(sqlite/Firestore)에 있어 여러 gunicorn 워커·인스턴스가 같은 한도를 본다.

로그에는 기능 이름·결과 코드·토큰 수만 남긴다. 프롬프트·학생 글·AI 답변·키는 남기지 않는다.
"""
import datetime
import hashlib
import time

from econova import storage
from econova.ai import client
from econova.ai.client import AIError, AIRequest


def today():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def request_hash(task, scope, text):
    return hashlib.sha256(f"{task}|{scope}|{text}".encode("utf-8")).hexdigest()[:32]


def run(user_id, req: AIRequest, scope_key, text_for_dedupe, provider=None, s=None, check=None):
    """AI 요청을 한 번 실행하고 검사된 data(dict)를 돌려준다. 실패하면 AIError (학생용 한국어 message 포함).
    check(data) 는 기능별 추가 검사 (실패하면 AIError). 점수·진도·수료는 어디에서도 바꾸지 않는다.
    토큰은 응답을 받았으면 검사 결과와 상관없이 기록하고(비용), 반복 요청 지문은 성공했을 때만 남긴다."""
    s = s or client.settings()
    provider = provider or client.get_provider(s)
    if provider is None:
        raise AIError("disabled")
    now = storage._utcnow()
    fingerprint = request_hash(req.task, scope_key, text_for_dedupe)
    if not storage.acquire_ai_lock(user_id, now, s.lock_ttl):
        raise AIError("busy")
    started = time.monotonic()
    try:
        try:
            storage.reserve_ai_request(user_id, today(), s.daily_requests, s.global_daily_requests,
                                       fingerprint, now, s.duplicate_window)
        except storage.AILimitExceeded as exc:
            raise AIError({"user": "rate_limited", "global": "global_limit", "duplicate": "duplicate"}[exc.scope])
        try:
            result = provider.complete(req)
        except AIError:
            raise
        except Exception as exc:   # 예상하지 못한 공급자 오류도 학습 흐름을 깨지 않는다
            raise AIError("provider_error", type(exc).__name__)
        if time.monotonic() - started > s.timeout + 5:
            raise AIError("timeout")
        try:
            client.validate(result.data, req.schema)
            if check is not None:
                check(result.data)
        except AIError:
            storage.record_ai_tokens(user_id, today(), result.input_tokens, result.output_tokens)
            raise
        storage.record_ai_tokens(user_id, today(), result.input_tokens, result.output_tokens, fingerprint, now)
        client.log.info("ai ok task=%s tokens=%s/%s", req.task, result.input_tokens, result.output_tokens)
        return result.data
    except AIError as exc:
        client.log.warning("ai fail task=%s code=%s", req.task, exc.code)
        raise
    finally:
        storage.release_ai_lock(user_id)
