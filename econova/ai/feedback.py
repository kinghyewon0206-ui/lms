"""제출한 평가의 오답 설명. 점수는 저장된 결정적 채점 결과가 기준이며 AI 는 바꾸지 않는다.

- 본인 응시 기록만 (storage.get_assessment_attempt 가 소유자를 확인).
- 지금 평가가 같은 평가·같은 버전·승인됨·정답 키 있음일 때만 — 결과 화면이 정답·해설을 보여주는 바로 그 경우.
  (정답 키를 결과 화면 밖으로 내보내지 않는다.)
- 틀린 문항만, 문항 버전이 같은 것만 다룬다. AI 를 못 쓰면 승인된 해설로 만든 기본 피드백을 보여준다.
"""
from econova import quotas, storage
from econova.ai import client, context, safety, usage
from econova.ai.client import AIError, AIRequest

MAX_QUESTIONS = 10
SCHEMA = {"type": "object", "properties": {
    "items": {"type": "array", "maxItems": MAX_QUESTIONS, "items": {"type": "object", "properties": {
        "question_id": {"type": "string", "maxLength": 80},
        "why_incorrect": {"type": "string", "maxLength": 600},
        "concept_explanation": {"type": "string", "maxLength": 800},
        "simpler_example": {"type": "string", "maxLength": 600},
        "review_topic": {"type": "string", "maxLength": 200}}}},
    "follow_up_questions": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 200}},
    "limitations": {"type": "string", "maxLength": 400},
}}


def eligible(attempt, assessment):
    """이 응시 기록에 해설(과 AI 설명)을 보여줘도 되는가."""
    return (assessment is not None and assessment.id == attempt["assessment_id"]
            and assessment.version == attempt.get("assessment_version") and assessment.approved
            and assessment.answer_keys)


def _answer_text(q, raw):
    if q["type"] == "mcq":
        choice = next((c for c in q["choices"] if c["id"] == raw), None)
        return choice["text"] if choice else ""
    return str(raw or "")


def wrong_questions(attempt, assessment, course):
    """틀린 문항(버전이 같은 것만)의 결정적 정보 — 기본 피드백이자 AI 맥락."""
    out = []
    for r in attempt.get("results") or []:
        q = assessment.question(r["id"])
        if r.get("correct") or q is None or q.get("version") != r.get("version"):
            continue
        terms = context.concept_terms(course, q["lesson_id"])
        lesson = course.lesson(q["lesson_id"]) if course else None
        out.append({
            "id": q["id"], "prompt": q["prompt"], "type": q["type"],
            "choices": [c["text"] for c in q.get("choices", ())],
            "student_answer": _answer_text(q, r.get("answer")),
            "correct_answer": _answer_text(q, q["answer"]) if q["type"] == "mcq" else f"{q['answer']:g} (tolerance ±{q['tolerance']:g})",
            "approved_explanation": q["explanation"], "objective_text": q["objective_text"],
            "concepts": [{"term": terms[c][0], "definition": terms[c][1]} for c in q["concept_ids"] if c in terms],
            "lesson_id": q["lesson_id"], "lesson_title": lesson.title_ko if lesson else q["lesson_id"],
        })
    return out[:MAX_QUESTIONS]


def latest(user_id, attempt_id):
    convs = storage.find_ai_conversations(user_id, "feedback", attempt_id=attempt_id)
    if not convs:
        return None
    msgs = [m for m in storage.list_ai_messages(user_id, convs[0]["id"]) if m["role"] == "assistant"]
    return msgs[-1]["meta"] if msgs else None


def explain(user_id, attempt, assessment, course, level, provider=None):
    """AI 오답 설명을 만들어 저장하고 화면용 dict 를 돌려준다. 점수·진도·수료는 바꾸지 않는다."""
    if not client.feedback_enabled():   # 정답·해설을 공급자에게 보내지 않는다 (공급자를 부르기 전에 멈춤)
        raise AIError("feedback_off")
    if not eligible(attempt, assessment):
        raise AIError("unavailable", "explanations cannot be shown for this attempt")
    wrong = wrong_questions(attempt, assessment, course)
    if not wrong:
        raise AIError("unavailable", "no incorrect questions")
    convs = storage.find_ai_conversations(user_id, "feedback", attempt_id=attempt["id"])
    done = sum(1 for m in storage.list_ai_messages(user_id, convs[0]["id"]) if m["role"] == "student") if convs else 0
    quotas.check("FEEDBACK_REQUESTS", done)
    s = client.settings()
    facts = {"assessment": assessment.title, "level": level, "score": attempt["score"], "max_score": attempt["max_score"],
             "note": "The score has already been graded deterministically and saved. It cannot be changed.",
             "questions": [{k: v for k, v in q.items() if k not in ("lesson_id",)} for q in wrong]}
    req = AIRequest(task="feedback", system=safety.system_prompt("feedback"),
                    messages=[{"role": "user", "content": safety.material_block(facts)}], schema=SCHEMA,
                    payload={**facts, "student_text": ""}, user_ref=safety.pseudonym(user_id))
    by_id = {q["id"]: q for q in wrong}

    def check(data):   # 틀린 문항에 대한 설명이 하나도 없으면 실패로 본다
        if not any(it["question_id"] in by_id for it in data["items"]):
            raise AIError("invalid_response", "no valid question explanations")
    data = usage.run(user_id, req, f"feedback:{attempt['id']}", "explain", provider=provider, s=s, check=check)
    items, seen = [], set()
    for it in data["items"]:
        q = by_id.get(it["question_id"])
        if q is None or q["id"] in seen:
            continue   # 틀리지 않은 문항·없는 문항에 대한 설명은 버린다 (결과를 지어내지 않게)
        seen.add(q["id"])
        items.append({"question_id": q["id"], "prompt": q["prompt"], "lesson_id": q["lesson_id"],
                      "lesson_title": q["lesson_title"],
                      **{k: safety.clip(it[k], SCHEMA["properties"]["items"]["items"]["properties"][k]["maxLength"])
                         for k in ("why_incorrect", "concept_explanation", "simpler_example", "review_topic")}})
    if not items:
        raise AIError("invalid_response", "no valid question explanations")
    result = {"items": items, "follow_up_questions": [safety.clip(q, 200) for q in data["follow_up_questions"]][:3],
              "limitations": safety.clip(data["limitations"], 400), "missing": len(by_id) - len(items),
              "assessment_version": assessment.version}
    convs = storage.find_ai_conversations(user_id, "feedback", attempt_id=attempt["id"])
    conv_id = convs[0]["id"] if convs else storage.create_ai_conversation(
        user_id, "feedback", course_id=attempt["course_id"], lesson_id=attempt.get("lesson_id"), attempt_id=attempt["id"])
    storage.add_ai_message(user_id, conv_id, "student", "Request for wrong-answer explanation")
    storage.add_ai_message(user_id, conv_id, "assistant", "AI explanation of wrong answers", meta=result)
    return result
