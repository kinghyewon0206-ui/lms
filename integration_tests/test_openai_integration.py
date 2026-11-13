"""OpenAI 연동 시험 (Phase 8B-2). fake 는 가짜 Chat Completions 응답으로, live 는 승인한 개발 키·모델·요청 예산으로 한다.

앱의 실제 코드(OpenAIProvider → usage.run → 기능별 검사)를 그대로 지난다. 모든 요청은 보내기 '전에' 검사한다
(conftest.inspect_body): 본문·출력 상한, 가명 사용자 값, 금지 문자열(시험 계정 이메일·이름·비밀번호, 합성 정답 키의 해설,
출처 레지스트리의 확인 메모, 승인 전 실제 c02 학습자료 문장, 선택: 실제 정답 키 해설).

live 요청 수(기본 시험 전부): 모델 확인 1 + 튜터 1 + 토론 1 + 추천 1 + 캡스톤 1 + 잘못된 키 1 = 6회
오답 설명은 그 학생이 틀린 문항의 정답·해설을 공급자에게 보내므로, 정책 승인 전에는 live 에서 건너뛴다
(ECONOVA_IT_OPENAI_ALLOW_FEEDBACK=1 이면 +1회).
"""
import glob
import json
import os
import re
import secrets
import string
import urllib.request

import pytest

from econova import content, storage
from econova.ai import client as ai_client
from econova.ai import context as ai_context
from econova.ai import usage
from econova.ai.safety import MATERIAL_TAG
from integration_tests import fake_backends
from integration_tests.conftest import AI_LIVE, CSRF, ROOT, post, take

SYNTHETIC_SOURCE = {"id": "it-synthetic-src-1", "title": "ECONOVA 연동 시험용 합성 출처 (실제 문헌 아님)",
                    "author": "ECONOVA 시험", "container": "합성 자료", "published": "2026"}
FABRICATED = "fabricated-source-9999"


def _needles():
    """요청에 있으면 안 되는 문자열 (앞 60자). 값은 출력하지 않는다."""
    out = set()
    for p in glob.glob(os.path.join(ROOT, "content/dev_fixtures/private/*.answers.json")):
        for q in json.load(open(p, encoding="utf-8"))["questions"].values():
            if len(str(q.get("explanation") or "")) >= 15:
                out.add(str(q["explanation"])[:60])
    for src in json.load(open(os.path.join(ROOT, "content/sources.json"), encoding="utf-8"))["sources"]:
        method = (src.get("verification") or {}).get("method")
        if method and len(method) >= 15:
            out.add(method[:60])
    for p in glob.glob(os.path.join(ROOT, "content/lessons/*.json")):   # 승인 전 실제 학습자료 (튜터에 쓰이면 안 됨)
        for lv in json.load(open(p, encoding="utf-8"))["levels"].values():
            for sec in lv["sections"]:
                out.update(par[:60] for par in sec["paragraphs"] if len(par) >= 30)
    real = os.environ.get("ECONOVA_IT_REAL_KEYS_DIR")   # 선택: 실제 정답 키 해설도 대조 (로컬에서만 읽음)
    if real:
        for p in glob.glob(os.path.join(real, "*.answers.json")):
            for q in json.load(open(p, encoding="utf-8"))["questions"].values():
                if len(str(q.get("explanation") or "")) >= 20:
                    out.add(str(q["explanation"])[:60])
    return out


@pytest.fixture
def ai_user(new_user, openai_transport, monkeypatch):
    u = new_user("연동시험학생")
    openai_transport.forbidden[:] = [u.email, "연동시험학생", "it-password-123", *_needles()]
    real = ai_context.lesson_context

    def with_synthetic_source(*args, **kwargs):   # 근거 확인용 합성 출처 1개 (학습자료 파일은 바꾸지 않음)
        ctx = real(*args, **kwargs)
        ctx["sources"] = [SYNTHETIC_SOURCE]
        return ctx
    monkeypatch.setattr(ai_context, "lesson_context", with_synthetic_source)
    return u


def _flash_errors(c):
    with c.session_transaction() as s:
        return [m for cat, m in s.get("_flashes", []) if cat == "error"]


def _tamper_add_fabricated_source():
    """실제(또는 가짜) 응답을 받은 뒤 출처 목록에 지어낸 id 를 덧붙인다 → 서버가 걸러내는지 확인."""
    inner = urllib.request.urlopen

    def call(req, timeout=None):
        with inner(req, timeout=timeout) as resp:
            raw = json.loads(resp.read())
        data = json.loads(raw["choices"][0]["message"]["content"])
        data["used_source_ids"] = list(data.get("used_source_ids") or []) + [FABRICATED]
        raw["choices"][0]["message"]["content"] = json.dumps(data, ensure_ascii=False)
        return fake_backends._Resp(json.dumps(raw).encode("utf-8"))
    return call


# ------------------------------------------------------------------ 모델·구조화 응답
def test_model_accepts_strict_json_schema(openai_transport, app):
    """선택한 모델이 이 앱의 요청 형식(json_schema strict, max_completion_tokens, temperature)을 받아들이는가."""
    with app.app_context():
        s = ai_client.settings()
        req = ai_client.AIRequest(task="probe", system="Reply only with the JSON object requested.",
                                  messages=[{"role": "user", "content": "Return ok='yes'."}],
                                  schema={"type": "object", "properties": {"ok": {"type": "string", "maxLength": 10}}},
                                  user_ref="u_" + "0" * 20)
        try:
            result = ai_client.OpenAIProvider(s).complete(req)
        except ai_client.AIError as exc:
            errors = getattr(openai_transport, "http_errors", [])
            pytest.fail(f"모델이 요청 형식을 받지 않았습니다: {exc.code} {errors[-1] if errors else ''}")
        ai_client.validate(result.data, req.schema)
        assert result.input_tokens > 0 and result.output_tokens > 0


# ------------------------------------------------------------------ 튜터: 근거·지어낸 출처·토큰 기록
def test_tutor_grounding_rejects_fabricated_citation_and_counts_tokens(ai_user, openai_transport, app, monkeypatch):
    post(ai_user.client, "/courses/dev-f1/enroll")
    monkeypatch.setattr(urllib.request, "urlopen", _tamper_add_fabricated_source())
    with app.app_context():
        before = storage.get_ai_usage(ai_user.id, usage.today())["user"]
    res = ai_user.client.post("/api/tutor", data={"csrf_token": CSRF, "course_id": "dev-f1", "lesson_id": "dev-f1-l1",
                                                  "message": "Please explain simply where supply and demand meet."})
    assert res.status_code == 200, res.get_json()
    msg = res.get_json()["message"]
    assert FABRICATED not in json.dumps(msg) and msg["dropped_sources"] >= 1      # 지어낸 출처는 화면에 없음
    assert all(s["id"] == SYNTHETIC_SOURCE["id"] for s in msg["sources"])
    assert msg["grounding"] in ("partial", "insufficient")                         # grounded 로 표시하지 않음
    assert "could not be verified" in msg["limitations"]
    with app.app_context():
        after = storage.get_ai_usage(ai_user.id, usage.today())["user"]
    reported = openai_transport.usage[-1]
    assert after["requests"] == before["requests"] + 1
    assert after["input_tokens"] - before["input_tokens"] == int(reported["prompt_tokens"])
    assert after["output_tokens"] - before["output_tokens"] == int(reported["completion_tokens"])
    body = openai_transport.bodies[-1]
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["user"].startswith("u_") and ai_user.email not in json.dumps(body, ensure_ascii=False)


# ------------------------------------------------------------------ 다른 기능의 구조화 응답
def test_debate_recommendation_and_capstone_responses_validate(ai_user, openai_transport, app):
    c = ai_user.client
    post(c, "/courses/dev-f1/enroll")
    sent = openai_transport.sent
    c.post("/discuss/dev-f1/price-ceiling-food/respond", data={"csrf_token": CSRF, "message": "A price ceiling is good for consumers."})
    assert _flash_errors(c) == [] and openai_transport.sent == sent + 1
    lesson = content.get_catalog().course("dev-f1").lesson("dev-f1-l1")
    post(c, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    take(c, "/learn/dev-f1/dev-f1-l1/quiz", lesson.quiz_assessment, correct=False)   # 추천 근거가 생기게
    res = c.post("/api/recommendations/explain", data={"csrf_token": CSRF})
    assert res.status_code == 200, res.get_json()
    assert openai_transport.sent == sent + 2
    post(c, "/courses/dev-f3/enroll")
    post(c, "/capstone/dev-f3/edit", sdg="7", problem="Energy costs in our area")
    post(c, "/capstone/dev-f3/feedback")
    assert _flash_errors(c) == [] and openai_transport.sent == sent + 3
    with app.app_context():
        assert len(storage.list_capstone_feedback(ai_user.id, "dev-f3")) == 1


@pytest.mark.skipif(AI_LIVE is not None and os.environ.get("ECONOVA_IT_OPENAI_ALLOW_FEEDBACK") != "1",
                    reason="오답 설명은 틀린 문항의 정답·해설을 보낸다 — 정책 승인 전에는 live 에서 보내지 않음")
def test_feedback_sends_only_the_students_wrong_items(ai_user, openai_transport, app):
    c = ai_user.client
    post(c, "/courses/dev-f1/enroll")
    post(c, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    quiz = content.get_catalog().course("dev-f1").lesson("dev-f1-l1").quiz_assessment
    first, rest = quiz.questions[0], quiz.questions[1:]
    # 첫 문항은 맞히고 나머지는 틀린다 → 맞힌 문항의 정답·해설은 보내면 안 된다
    openai_transport.forbidden[:] = [x for x in openai_transport.forbidden
                                     if x not in {str(q["explanation"])[:60] for q in rest}]
    html = c.get("/learn/dev-f1/dev-f1-l1/quiz").get_data(as_text=True)
    token = re.search(r'name="submission_token" value="([^"]+)"', html).group(1)
    answers = {f"q_{first['id']}": first["answer"] if first["type"] == "mcq" else f"{first['answer']:g}"}
    answers.update({f"q_{q['id']}": ("b" if q["type"] == "mcq" and q["answer"] == "a" else "-1") for q in rest})
    url = c.post("/learn/dev-f1/dev-f1-l1/quiz", data={"csrf_token": CSRF, "submission_token": token, **answers}).headers["Location"]
    c.post(url + "/explain", data={"csrf_token": CSRF})
    assert _flash_errors(c) == []
    material = next(m["content"] for m in openai_transport.bodies[-1]["messages"] if m["content"].startswith(f"<{MATERIAL_TAG}>"))
    sent = json.loads(material[len(f"<{MATERIAL_TAG}>\n"):-len(f"\n</{MATERIAL_TAG}>")])["questions"]
    assert sorted(q["id"] for q in sent) == sorted(q["id"] for q in rest)   # 맞힌 문항은 정답·해설 모두 보내지 않음
    assert first["prompt"] not in material


# ------------------------------------------------------------------ 실패 처리
@pytest.mark.skipif(AI_LIVE is not None, reason="시간 초과·서버 오류·거절·잘림은 fake 로만 재현한다 (live 비용 없음)")
@pytest.mark.parametrize("behaviour,code,status", [
    ("timeout", "timeout", 504), ("http_500", "provider_error", 502), ("refusal", "invalid_response", 502),
    ("length", "invalid_response", 502), ("not_json", "invalid_response", 502), ("invalid_schema", "invalid_response", 502)])
def test_provider_failures_are_contained(ai_user, openai_transport, app, behaviour, code, status):
    post(ai_user.client, "/courses/dev-f1/enroll")
    openai_transport.behaviour = behaviour
    res = ai_user.client.post("/api/tutor", data={"csrf_token": CSRF, "course_id": "dev-f1", "lesson_id": "dev-f1-l1",
                                                  "message": f"질문 {behaviour}"})
    assert res.status_code == status and res.get_json()["code"] == code
    assert "sk-" not in res.get_data(as_text=True)
    with app.app_context():
        assert storage.find_ai_conversations(ai_user.id, "tutor", lesson_id="dev-f1-l1") == []   # 실패하면 대화를 남기지 않음
        assert storage.get_ai_usage(ai_user.id, usage.today())["user"]["requests"] == 1   # 실패한 요청도 센다


def test_invalid_key_is_reported_without_leaking(ai_user, openai_transport, app, monkeypatch):
    """잘못된 키 → 401 → 학생에게는 일반 안내만 (live 1회, 토큰 비용 없음)."""
    post(ai_user.client, "/courses/dev-f1/enroll")
    bad = "sk-invalid-" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
    monkeypatch.setenv("OPENAI_API_KEY", bad)
    if AI_LIVE is None:
        openai_transport.behaviour = "http_401"
    res = ai_user.client.post("/api/tutor", data={"csrf_token": CSRF, "course_id": "dev-f1", "lesson_id": "dev-f1-l1",
                                                  "message": "invalid key test"})
    assert res.status_code == 502 and res.get_json()["code"] == "provider_error"
    assert bad not in res.get_data(as_text=True)
    if AI_LIVE is not None:
        assert openai_transport.http_errors[-1]["status"] == 401
