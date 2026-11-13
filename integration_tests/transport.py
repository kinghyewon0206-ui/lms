"""OpenAI 요청을 보내기 '전에' 검사하는 전송 계층 (Phase 8B-2 연동 시험용). 키·본문은 출력하지 않는다."""
import json
import re
import urllib.error

from econova.ai import client as ai_client
from integration_tests import fake_backends, guards


class GuardedTransport:
    """실제 OpenAI 로 보내기 전에 모든 요청을 검사하는 urlopen 대체 함수 (live).
    - 주소는 Chat Completions 하나만, 요청 수는 승인한 예산까지만 (넘으면 보내지 않고 실패)
    - 본문 크기·출력 토큰 상한, 금지 문자열(시험 계정 이메일·이름, 실제 정답 키 해설 등) 검사는 보내기 '전에'
    - 응답의 usage 를 모아 앱이 기록한 토큰과 비교한다. 키·본문은 출력하지 않는다."""

    def __init__(self, real, budget):
        self.real, self.budget = real, budget
        self.sent = 0
        self.bodies, self.usage, self.http_errors = [], [], []
        self.forbidden = []

    def __call__(self, req, timeout=None):
        if req.full_url != ai_client.OPENAI_URL:
            raise AssertionError("허용되지 않은 주소로 요청하려 했습니다.")
        if self.sent >= self.budget:
            raise AssertionError(f"승인한 요청 예산({self.budget}회)을 넘어 보내지 않았습니다.")
        inspect_body(req.data, self.forbidden)
        self.bodies.append(json.loads(req.data.decode("utf-8")))
        self.sent += 1
        try:
            with self.real(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            try:
                err = json.loads(exc.read() or b"{}").get("error") or {}
            except ValueError:
                err = {}
            self.http_errors.append({"status": exc.code, "type": err.get("type"), "code": err.get("code"),
                                     "param": err.get("param"),
                                     # 401 안내문에는 (일부 가린) 키가 들어 있다 → 키처럼 보이는 부분은 지운다
                                     "message": re.sub(r"sk-\S*", "[redacted]", str(err.get("message") or ""))[:300]})
            raise urllib.error.HTTPError(exc.url, exc.code, "error", {}, None)
        self.usage.append(json.loads(raw).get("usage") or {})
        return fake_backends._Resp(raw)


def inspect_body(data, forbidden):
    """보내기 전 검사: 크기·출력 상한·금지 문자열·사용자 식별값 형식."""
    if len(data) > guards.MAX_REQUEST_BYTES:
        raise AssertionError(f"요청 본문이 상한({guards.MAX_REQUEST_BYTES}바이트)보다 큽니다.")
    body = json.loads(data.decode("utf-8"))
    if int(body.get("max_completion_tokens") or 0) > guards.MAX_OUTPUT_TOKENS:
        raise AssertionError("출력 토큰 상한이 너무 큽니다.")
    if not re.fullmatch(r"u_[0-9a-f]{20}", str(body.get("user", ""))):
        raise AssertionError("공급자에게 보내는 사용자 식별값이 가명 형식이 아닙니다.")
    text = data.decode("utf-8")
    plain = json.dumps(body, ensure_ascii=False)
    for needle in forbidden:
        if needle and (needle in text or needle in plain):
            raise AssertionError("보내면 안 되는 내용(시험 계정 정보·정답 키 등)이 요청에 있습니다.")
    return body
