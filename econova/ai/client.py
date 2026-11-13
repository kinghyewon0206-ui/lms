"""AI 공급자와 설정.

ECONOVA_AI_PROVIDER = off (기본) | mock | openai
- off   : AI 기능을 쓰지 않는다. 결정적 기능(추천·기본 피드백·토론 안내 질문)은 그대로 동작한다.
- mock  : 네트워크 없이 정해진 규칙으로 답하는 모의 공급자. 자동 테스트·개발용. 운영에서는 켤 수 없다.
- openai: 서버의 OPENAI_API_KEY 로 OpenAI Chat Completions 를 부른다 (기존 LMS 와 같은 방식, 추가 의존성 없음).
          키는 서버에서만 읽고 화면·JavaScript·응답으로 보내지 않는다.

모든 응답은 기능별 JSON 스키마로 검사한다 (validate). 형식이 틀리면 표시하지 않는다.
"""
import json
import logging
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from econova import config

log = logging.getLogger("econova.ai")
PROVIDERS = ("off", "mock", "openai")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

MESSAGES_KO = {
    "disabled": "AI features are turned off right now. You can still use the learning materials, quizzes, and simulations.",
    "rate_limited": "You've used all of your AI requests for today. Please try again tomorrow.",
    "global_limit": "AI help is paused for today because of high demand. You can keep using the learning materials and quizzes.",
    "duplicate": "You just sent the same message. Wait a moment before sending it again, or try rewording your question.",
    "busy": "Still working on your previous request. Please try again in a moment.",
    "empty": "Please type a message first.",
    "too_long": "Your message is too long. Please shorten it and try again.",
    "timeout": "The AI took too long to respond, so the request was stopped. Please try again in a moment. Your learning progress is safe.",
    "provider_error": "We couldn't connect to the AI service. Please try again in a moment. Your learning progress is safe.",
    "invalid_response": "The AI response couldn't be verified, so it wasn't shown. Please try again.",
    "unavailable": "AI help isn't available for this content (there are no approved learning materials yet).",
    "feedback_off": "AI explanations of wrong answers are turned off right now (so answer keys and explanations are not sent to an outside AI service). Please review with the explanations above and the learning materials.",
}


class AIError(Exception):
    """AI 요청 실패. code 는 MESSAGES_KO 의 키. 학생에게는 message 만 보여준다 (내부 정보 없음)."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail

    @property
    def message(self):
        return MESSAGES_KO.get(self.code, MESSAGES_KO["provider_error"])


def _int(name, default, lo, hi):
    try:
        value = int(config.env(name) or default)
    except ValueError:
        raise config.ConfigError(f"{name} must be an integer.")
    if not lo <= value <= hi:
        raise config.ConfigError(f"{name} must be between {lo} and {hi}.")
    return value


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    daily_requests: int          # 학생 1명이 하루에 보낼 수 있는 AI 요청
    global_daily_requests: int   # 서비스 전체 하루 요청 상한 (예상 밖 비용 방지)
    max_input_chars: int         # 학생 입력 최대 길이
    max_history: int             # 공급자에게 보내는 이전 메시지 수
    max_output_tokens: int
    timeout: int                 # 초
    lock_ttl: int                # 동시 요청 잠금이 풀리는 시간(초). timeout 보다 길다
    duplicate_window: int        # 같은 요청을 다시 받지 않는 시간(초)
    retention_days: int          # AI 대화 보존 기간

    @property
    def enabled(self):
        return self.provider != "off"


def settings():
    """보수적인 기본값. 모두 ECONOVA_AI_* 환경변수로 바꿀 수 있다."""
    provider = (config.env("ECONOVA_AI_PROVIDER") or "off").strip().lower()
    if provider not in PROVIDERS:
        raise config.ConfigError(f"ECONOVA_AI_PROVIDER must be one of: {' / '.join(PROVIDERS)}.")
    if provider == "mock" and config.is_production():
        raise config.ConfigError("The mock AI provider (ECONOVA_AI_PROVIDER=mock) cannot be enabled in production.")
    if provider == "openai" and not config.env("OPENAI_API_KEY"):
        raise config.ConfigError("ECONOVA_AI_PROVIDER=openai is set, but OPENAI_API_KEY is missing.")
    timeout = _int("ECONOVA_AI_TIMEOUT_SECONDS", 20, 3, 120)
    return Settings(
        provider=provider,
        model=(config.env("ECONOVA_AI_MODEL") or config.env("OPENAI_MODEL") or "gpt-4o-mini").strip(),
        daily_requests=_int("ECONOVA_AI_DAILY_REQUESTS", 20, 1, 500),
        global_daily_requests=_int("ECONOVA_AI_GLOBAL_DAILY_REQUESTS", 300, 1, 100000),
        max_input_chars=_int("ECONOVA_AI_MAX_INPUT_CHARS", 600, 50, 4000),
        max_history=_int("ECONOVA_AI_MAX_HISTORY", 6, 0, 20),
        max_output_tokens=_int("ECONOVA_AI_MAX_OUTPUT_TOKENS", 700, 100, 4000),
        timeout=timeout,
        lock_ttl=timeout + 15,
        duplicate_window=_int("ECONOVA_AI_DUPLICATE_SECONDS", 20, 0, 3600),
        retention_days=_int("ECONOVA_AI_RETENTION_DAYS", 30, 1, 3650),
    )


@dataclass
class AIRequest:
    task: str                    # tutor | feedback | debate_turn | debate_summary | recommendation
    system: str                  # 서버가 정한 지시문 (학생이 바꿀 수 없음)
    messages: list               # [{"role": "user"|"assistant", "content": str}] — 서버가 조립한 것만
    schema: dict                 # 응답 JSON 스키마
    payload: dict = field(default_factory=dict)   # 모의 공급자용 구조화 맥락 (실제 공급자에는 messages 로만 전달)
    user_ref: str = ""           # 가명 (이메일·이름 아님)


@dataclass
class AIResult:
    data: dict
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


# ------------------------------------------------------------------ 구조화 응답 검사
def validate(data, schema, path="$"):
    """이 프로젝트가 쓰는 JSON 스키마 부분집합(object/array/string/enum/integer/number/boolean)으로 검사한다.
    틀리면 AIError('invalid_response'). additionalProperties 는 항상 금지로 본다."""
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(data, dict):
            raise AIError("invalid_response", f"{path}: not an object")
        props = schema.get("properties", {})
        extra = set(data) - set(props)
        missing = set(schema.get("required", props)) - set(data)
        if extra or missing:
            raise AIError("invalid_response", f"{path}: field mismatch extra={sorted(extra)} missing={sorted(missing)}")
        for k, sub in props.items():
            if k in data:
                validate(data[k], sub, f"{path}.{k}")
    elif kind == "array":
        if not isinstance(data, list) or len(data) > schema.get("maxItems", 50):
            raise AIError("invalid_response", f"{path}: invalid array type or length")
        for i, item in enumerate(data):
            validate(item, schema["items"], f"{path}[{i}]")
    elif kind == "string":
        if not isinstance(data, str) or len(data) > schema.get("maxLength", 4000):
            raise AIError("invalid_response", f"{path}: invalid string type or length")
        if "enum" in schema and data not in schema["enum"]:
            raise AIError("invalid_response", f"{path}: value not allowed")
    elif kind == "integer":
        if not isinstance(data, int) or isinstance(data, bool):
            raise AIError("invalid_response", f"{path}: not an integer")
    elif kind == "boolean":
        if not isinstance(data, bool):
            raise AIError("invalid_response", f"{path}: not a boolean")
    else:
        raise AIError("invalid_response", f"{path}: unknown schema type")
    return data


def _strict(schema):
    """OpenAI strict 모드용: 모든 object 에 additionalProperties=false, required=전체. (maxLength 등은 서버에서 검사)"""
    if schema.get("type") == "object":
        props = {k: _strict(v) for k, v in schema["properties"].items()}
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    if schema.get("type") == "array":
        return {"type": "array", "items": _strict(schema["items"])}
    out = {"type": schema["type"]}
    if "enum" in schema:
        out["enum"] = list(schema["enum"])
    return out


# ------------------------------------------------------------------ 공급자
class OpenAIProvider:
    name = "openai"

    def __init__(self, s):
        self.s = s

    def complete(self, req):
        api_key = config.env("OPENAI_API_KEY")
        if not api_key:
            raise AIError("disabled", "missing key")
        body = {
            "model": self.s.model,
            "messages": [{"role": "system", "content": req.system}] + req.messages,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": f"econova_{req.task}", "strict": True,
                                                "schema": _strict(req.schema)}},
            "max_completion_tokens": self.s.max_output_tokens,
            "temperature": 0.3,
            "user": req.user_ref,
        }
        http = urllib.request.Request(OPENAI_URL, data=json.dumps(body).encode("utf-8"),
                                      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(http, timeout=self.s.timeout) as resp:
                raw = json.loads(resp.read())
        except (socket.timeout, TimeoutError):
            raise AIError("timeout")
        except urllib.error.HTTPError as exc:   # 응답 본문(요청 내용이 섞일 수 있음)은 기록하지 않는다
            raise AIError("provider_error", f"HTTP {exc.code}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if isinstance(getattr(exc, "reason", None), socket.timeout):
                raise AIError("timeout")
            raise AIError("provider_error", type(exc).__name__)
        try:
            choice = raw["choices"][0]
            if choice.get("finish_reason") not in ("stop", None) or choice["message"].get("refusal"):
                raise AIError("invalid_response", f"finish_reason={choice.get('finish_reason')}")
            data = json.loads(choice["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise AIError("invalid_response", "response format")
        usage = raw.get("usage") or {}
        return AIResult(data=data, input_tokens=int(usage.get("prompt_tokens") or 0),
                        output_tokens=int(usage.get("completion_tokens") or 0), model=str(raw.get("model") or ""))


class MockProvider:
    """네트워크 없이 결정적으로 답하는 모의 공급자 (테스트·개발 미리보기 전용).
    학생 입력에 다음 표시가 있으면 실패 상황을 흉내 낸다: [mock:timeout] [mock:error] [mock:invalid] [mock:fake-source]."""
    name = "mock"

    def __init__(self, responder=None):
        self.responder = responder
        self.calls = []

    def complete(self, req):
        self.calls.append(req)
        text = req.payload.get("student_text", "")
        if "[mock:timeout]" in text:
            raise AIError("timeout")
        if "[mock:error]" in text:
            raise AIError("provider_error", "mock")
        if "[mock:invalid]" in text:
            return AIResult(data={"unexpected": True}, input_tokens=5, output_tokens=1, model="mock")
        data = self.responder(req) if self.responder else _mock_answer(req)
        if "[mock:fake-source]" in text and "used_source_ids" in data:
            data["used_source_ids"] = list(data["used_source_ids"]) + ["made-up-source-2026"]
        size = sum(len(m["content"]) for m in req.messages) + len(req.system)
        return AIResult(data=data, input_tokens=size // 4, output_tokens=len(json.dumps(data, ensure_ascii=False)) // 4,
                        model="mock")


def _mock_answer(req):
    p = req.payload
    if req.task == "tutor":
        concepts = p.get("concepts") or []
        first = concepts[0] if concepts else None
        sources = [s["id"] for s in p.get("sources", [])][:1]
        return {
            "answer": (f"[Mock AI answer] Here is a {p.get('level_name', '')} explanation for the lesson '{p.get('lesson', '')}'. "
                       + (f"Key concept '{first['term']}': {first['definition']}" if first else "There is no approved concept explanation.")),
            "grounding": "grounded" if first else "insufficient",
            "used_source_ids": sources,
            "beyond_sources": "This is a practice explanation from the mock provider. It is not a real AI answer.",
            "follow_up_questions": [f"Can you explain '{o}' in your own words?" for o in (p.get("objectives") or [])[:2]],
            "limitations": "This is a mock response, so it does not understand your actual question."
                           + ("" if sources else " No verified sources are linked to this lesson."),
        }
    if req.task == "feedback":
        return {"items": [{"question_id": q["id"],
                           "why_incorrect": f"[Mock AI] Your answer ({q['student_answer'] or 'no answer'}) is different from the correct answer.",
                           "concept_explanation": q.get("approved_explanation", ""),
                           "simpler_example": "This is a practice example from the mock provider.",
                           "review_topic": q.get("objective_text", "")} for q in p.get("questions", [])],
                "follow_up_questions": ["How would you explain this concept to a friend?"],
                "limitations": "This is a mock response. Your score does not change."}
    if req.task == "debate_turn":
        perspectives = [x["id"] for x in p.get("perspectives", [])]
        return {"reflection": "[Mock AI] Thanks for sharing your view. Let's separate your evidence from your assumptions.",
                "follow_up_question": (p.get("guiding_questions") or ["How might someone with a different perspective see this?"])[0],
                "perspectives_considered": perspectives[:2],
                "claim_types": [{"claim": "The main claim in your opinion", "type": "value_judgment"}]}
    if req.task == "debate_summary":
        return {"summary": "[Mock AI] Here is a summary of the claims and trade-offs from the debate.",
                "arguments": [{"perspective_id": x["id"], "points": [x["summary"]]} for x in p.get("perspectives", [])][:4],
                "trade_offs": list(p.get("trade_offs") or [])[:3] or ["Choosing between efficiency and equity"],
                "open_questions": ["What additional evidence might change your conclusion?"],
                "note": "This is a mock response. This question does not have a single correct answer."}
    if req.task == "capstone":
        steps = [s["title"] for s in p.get("steps", [])]
        return {"strengths": ["[Mock AI] You are filling in your project step by step."],
                "questions": [f"What is the most important evidence for '{t}'?" for t in steps[:2]],
                "missing_perspectives": ["Could you add the view of groups that might lose out under this solution?"],
                "assumptions_to_check": ["How could you check the assumption that costs will turn out as expected?"],
                "structure_suggestions": ["Try organizing it as problem, evidence, solution, then limitations."],
                "limitations": "This is a mock response. It is not a score or an evaluation."}
    if req.task == "recommendation":
        items = p.get("items") or []
        return {"message": "[Mock AI] " + (f"It would help to review '{items[0]['term']}' first." if items
                                            else "There isn't enough evidence yet."),
                "tips": [f"{it['term']}: {it['reason']}" for it in items[:3]]}
    raise AIError("invalid_response", "unknown task")


def feedback_enabled():
    """AI 오답 설명을 켤지 (ECONOVA_AI_FEEDBACK=on|off, 기본 off).
    오답 설명은 그 학생이 틀린 문항의 정답·승인된 해설을 AI 공급자에게 보내야 하므로, 정책으로 허용할 때만 켠다
    (2026-11 결정: 운영에서는 꺼 둔다). AI 공급자 자체가 off 이면 이 값과 상관없이 꺼진다."""
    value = (config.env("ECONOVA_AI_FEEDBACK") or "off").strip().lower()
    if value not in ("on", "off"):
        raise config.ConfigError("ECONOVA_AI_FEEDBACK must be on or off.")
    return value == "on" and settings().enabled


_mock_singleton = None


def get_provider(s=None):
    """설정에 맞는 공급자. off 이면 None."""
    global _mock_singleton
    s = s or settings()
    if s.provider == "off":
        return None
    if s.provider == "mock":
        _mock_singleton = _mock_singleton or MockProvider()
        return _mock_singleton
    return OpenAIProvider(s)


_SECRETISH = re.compile(r"sk-[A-Za-z0-9_\-]{10,}|AIza[0-9A-Za-z_\-]{20,}")


def redact(text):
    """로그에 남기기 전에 키처럼 보이는 문자열을 지운다."""
    return _SECRETISH.sub("[redacted]", str(text))
