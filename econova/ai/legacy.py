"""이전 LMS 의 AI 커리큘럼 상담(/curriculum/chat, /curriculum/quick)에도 ECONOVA AI 와 같은 안전장치를 건다 (Phase 7).

이전 기능은 그대로 두되, 실제 OpenAI 호출마다:
- 학생별·전체 하루 요청 한도 (ECONOVA AI 와 같은 저장소 카운터 — 둘을 합쳐 센다, 여러 워커가 공유)
- 요청 하나에서 부를 수 있는 호출 수 상한 (ECONOVA_LEGACY_MAX_CALLS_PER_REQUEST, 기본 6 — 웹 검색이 여러 번 일어나므로)
- 학생별 동시 요청 1개, 시간 제한(ECONOVA_AI_TIMEOUT_SECONDS), 토큰 사용량 기록
- 공급자에게 넘기는 사용자 식별값은 가명 (이메일·이름 아님)
링크 확인 검색은 스레드에서 돌기 때문에, 요청 스레드에서 만든 예산(LegacyBudget)을 넘겨 쓴다.
"""
import threading

from econova import config, storage
from econova.ai import client, safety, usage


def provider():
    """앱 전체 AI 스위치(ECONOVA_AI_PROVIDER)를 이전 LMS 에도 그대로 쓴다: off | mock | openai.
    off  : 외부 AI 요청 없음 (상담은 '간단 모드' 안내, 간단 모드는 규칙 기반 추천)
    mock : 네트워크 없이 정해진 모의 답 (개발·테스트 전용 — 운영에서는 설정 단계에서 시작 거부)
    openai: 서버의 OPENAI_API_KEY 로 실제 요청 (한도·가명·사용량 기록 적용)"""
    return client.settings().provider


def external_allowed():
    """실제 외부 AI(OpenAI) 요청을 해도 되는가. openai 일 때만."""
    return provider() == "openai"


MOCK_CHAT_REPLY = {"type": "question",
                   "message": "[모의 AI] 개발용 모의 응답이에요. 어떤 분야를, 일주일에 몇 시간 공부하고 싶은지 알려 주세요."}


def _max_calls():
    try:
        value = int(config.env("ECONOVA_LEGACY_MAX_CALLS_PER_REQUEST") or 6)
    except ValueError:
        value = 6
    return max(1, min(value, 20))


class LegacyBudget:
    """요청 하나의 AI 호출 예산. 스레드에서 써도 안전하다 (app 을 들고 다니며 호출마다 app context 를 연다)."""

    def __init__(self, app, user_id):
        self.app, self.user_id = app, user_id
        self.s = client.settings()
        self.user_ref = safety.pseudonym(user_id)
        self.max_calls = _max_calls()
        self.calls = 0
        self.blocked = None          # 'rate_limited' | 'global_limit' | 'call_cap' | 'busy'
        self._lock = threading.Lock()
        self.locked = False

    @property
    def timeout(self):
        return self.s.timeout

    def acquire(self):
        """요청 시작: 학생별 동시 요청 잠금."""
        self.locked = storage.acquire_ai_lock(self.user_id, storage._utcnow(), self.s.lock_ttl * 3)
        if not self.locked:
            self.blocked = "busy"
        return self.locked

    def release(self):
        if self.locked:
            storage.release_ai_lock(self.user_id)
            self.locked = False

    def spend(self):
        """실제 공급자 호출 직전에 부른다. 쓸 수 있으면 True."""
        with self._lock:
            if self.blocked in ("rate_limited", "global_limit", "busy"):
                return False
            if self.calls >= self.max_calls:
                self.blocked = self.blocked or "call_cap"
                return False
            self.calls += 1
        with self.app.app_context():
            try:
                storage.reserve_ai_request(self.user_id, usage.today(), self.s.daily_requests, self.s.global_daily_requests,
                                           None, storage._utcnow(), 0)
            except storage.AILimitExceeded as exc:
                with self._lock:
                    self.blocked = {"user": "rate_limited", "global": "global_limit"}.get(exc.scope, "rate_limited")
                return False
        return True

    def record(self, usage_dict):
        """응답의 사용량(usage)을 기록한다 (Chat Completions: prompt/completion_tokens, Responses: input/output_tokens)."""
        u = usage_dict or {}
        i = u.get("prompt_tokens", u.get("input_tokens", 0))
        o = u.get("completion_tokens", u.get("output_tokens", 0))
        with self.app.app_context():
            storage.record_ai_tokens(self.user_id, usage.today(), i, o)

    def message(self):
        if self.blocked == "call_cap":
            return "이번 요청에서 쓸 수 있는 AI 호출을 모두 써서 일부 강의 링크는 확인하지 못했어요."
        return client.MESSAGES_KO.get(self.blocked or "", "")
