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
    "disabled": "AI 기능이 지금은 꺼져 있어요. 학습자료·퀴즈·시뮬레이션은 그대로 이용할 수 있어요.",
    "rate_limited": "오늘 사용할 수 있는 AI 요청 횟수를 모두 썼어요. 내일 다시 이용해 주세요.",
    "global_limit": "오늘은 AI 사용량이 많아 잠시 멈췄어요. 학습자료와 퀴즈는 계속 이용할 수 있어요.",
    "duplicate": "방금 같은 내용을 보냈어요. 조금 뒤에 다시 보내거나 질문을 바꿔 주세요.",
    "busy": "이전 요청에 답하는 중이에요. 잠시 후 다시 보내 주세요.",
    "empty": "내용을 입력해 주세요.",
    "too_long": "글이 너무 길어요. 조금 줄여서 보내 주세요.",
    "timeout": "AI 응답이 늦어져 멈췄어요. 잠시 후 다시 시도해 주세요. 지금까지의 학습 기록은 그대로예요.",
    "provider_error": "AI 서비스에 연결하지 못했어요. 잠시 후 다시 시도해 주세요. 지금까지의 학습 기록은 그대로예요.",
    "invalid_response": "AI 답변을 확인할 수 없어 표시하지 않았어요. 다시 시도해 주세요.",
    "unavailable": "이 내용에는 AI 도움을 쓸 수 없어요 (승인된 학습자료가 없어요).",
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
        raise config.ConfigError(f"{name} 는 정수여야 합니다.")
    if not lo <= value <= hi:
        raise config.ConfigError(f"{name} 는 {lo}~{hi} 사이여야 합니다.")
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
        raise config.ConfigError(f"ECONOVA_AI_PROVIDER 는 {' / '.join(PROVIDERS)} 중 하나여야 합니다.")
    if provider == "mock" and config.is_production():
        raise config.ConfigError("운영 환경에서는 모의 AI(ECONOVA_AI_PROVIDER=mock)를 켤 수 없습니다.")
    if provider == "openai" and not config.env("OPENAI_API_KEY"):
        raise config.ConfigError("ECONOVA_AI_PROVIDER=openai 인데 OPENAI_API_KEY 가 없습니다.")
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
            raise AIError("invalid_response", f"{path}: object 아님")
        props = schema.get("properties", {})
        extra = set(data) - set(props)
        missing = set(schema.get("required", props)) - set(data)
        if extra or missing:
            raise AIError("invalid_response", f"{path}: 항목 불일치 extra={sorted(extra)} missing={sorted(missing)}")
        for k, sub in props.items():
            if k in data:
                validate(data[k], sub, f"{path}.{k}")
    elif kind == "array":
        if not isinstance(data, list) or len(data) > schema.get("maxItems", 50):
            raise AIError("invalid_response", f"{path}: array 형식·길이")
        for i, item in enumerate(data):
            validate(item, schema["items"], f"{path}[{i}]")
    elif kind == "string":
        if not isinstance(data, str) or len(data) > schema.get("maxLength", 4000):
            raise AIError("invalid_response", f"{path}: string 형식·길이")
        if "enum" in schema and data not in schema["enum"]:
            raise AIError("invalid_response", f"{path}: 허용되지 않은 값")
    elif kind == "integer":
        if not isinstance(data, int) or isinstance(data, bool):
            raise AIError("invalid_response", f"{path}: integer 아님")
    elif kind == "boolean":
        if not isinstance(data, bool):
            raise AIError("invalid_response", f"{path}: boolean 아님")
    else:
        raise AIError("invalid_response", f"{path}: 알 수 없는 스키마 형식")
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
            raise AIError("disabled", "키 없음")
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
            raise AIError("invalid_response", "응답 형식")
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
            "answer": (f"[모의 AI 답변] '{p.get('lesson', '')}' 레슨의 {p.get('level_name', '')} 설명이에요. "
                       + (f"핵심 개념 '{first['term']}': {first['definition']}" if first else "승인된 개념 설명이 없어요.")),
            "grounding": "grounded" if first else "insufficient",
            "used_source_ids": sources,
            "beyond_sources": "모의 공급자가 만든 연습용 추가 설명이에요. 실제 AI 답변이 아니에요.",
            "follow_up_questions": [f"'{o}' 를 내 말로 설명해 볼까요?" for o in (p.get("objectives") or [])[:2]],
            "limitations": "모의 응답이라 실제 질문 내용을 이해하지 않아요." + ("" if sources else " 이 레슨에는 확인된 출처가 연결되어 있지 않아요."),
        }
    if req.task == "feedback":
        return {"items": [{"question_id": q["id"],
                           "why_incorrect": f"[모의 AI] 고른 답({q['student_answer'] or '응답 없음'})은 정답과 달라요.",
                           "concept_explanation": q.get("approved_explanation", ""),
                           "simpler_example": "모의 공급자가 만든 연습용 예시예요.",
                           "review_topic": q.get("objective_text", "")} for q in p.get("questions", [])],
                "follow_up_questions": ["이 개념을 친구에게 설명한다면 어떻게 말할까요?"],
                "limitations": "모의 응답이에요. 점수는 바뀌지 않아요."}
    if req.task == "debate_turn":
        perspectives = [x["id"] for x in p.get("perspectives", [])]
        return {"reflection": "[모의 AI] 의견을 잘 들었어요. 근거와 가정을 나눠서 생각해 봐요.",
                "follow_up_question": (p.get("guiding_questions") or ["다른 관점에서는 어떻게 볼까요?"])[0],
                "perspectives_considered": perspectives[:2],
                "claim_types": [{"claim": "학생 의견의 핵심 주장", "type": "value_judgment"}]}
    if req.task == "debate_summary":
        return {"summary": "[모의 AI] 토론에서 나온 주장과 상충관계를 정리했어요.",
                "arguments": [{"perspective_id": x["id"], "points": [x["summary"]]} for x in p.get("perspectives", [])][:4],
                "trade_offs": list(p.get("trade_offs") or [])[:3] or ["효율과 형평 사이의 선택"],
                "open_questions": ["어떤 근거가 더 있으면 결론이 달라질까요?"],
                "note": "모의 응답이에요. 정해진 정답이 있는 문제가 아니에요."}
    if req.task == "capstone":
        steps = [s["title"] for s in p.get("steps", [])]
        return {"strengths": ["[모의 AI] 단계별로 내용을 채워 가고 있어요."],
                "questions": [f"'{t}' 에서 가장 중요한 근거는 무엇인가요?" for t in steps[:2]],
                "missing_perspectives": ["이 해결책으로 손해를 볼 수 있는 집단의 입장도 적어 볼까요?"],
                "assumptions_to_check": ["비용이 예상대로 나올 것이라는 가정을 어떻게 확인할 수 있을까요?"],
                "structure_suggestions": ["문제 → 근거 → 해결책 → 한계 순서로 정리해 보세요."],
                "limitations": "모의 응답이에요. 점수나 평가가 아니에요."}
    if req.task == "recommendation":
        items = p.get("items") or []
        return {"message": "[모의 AI] " + (f"'{items[0]['term']}' 부터 다시 보면 좋겠어요." if items else "지금은 근거가 부족해요."),
                "tips": [f"{it['term']}: {it['reason']}" for it in items[:3]]}
    raise AIError("invalid_response", "알 수 없는 작업")


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
    return _SECRETISH.sub("[가림]", str(text))
