"""레슨 AI 튜터. 맥락은 서버가 승인된 자료로 만들고(context.lesson_context), 대화 기록은 서버에 저장한다.
브라우저는 질문 글(과 본인 대화 id)만 보낸다. system/assistant 메시지나 자료를 보내도 쓰지 않는다."""
from econova import quotas, storage
from econova.ai import client, context, safety, usage
from econova.ai.client import AIError, AIRequest

SCHEMA = {"type": "object", "properties": {
    "answer": {"type": "string", "maxLength": 2000},
    "grounding": {"type": "string", "enum": ["grounded", "partial", "insufficient"]},
    "used_source_ids": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 80}},
    "beyond_sources": {"type": "string", "maxLength": 1200},
    "follow_up_questions": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 200}},
    "limitations": {"type": "string", "maxLength": 500},
}}
GROUNDING_KO = {"grounded": "승인된 학습자료에 근거", "partial": "일부만 학습자료에 근거", "insufficient": "학습자료에 근거가 부족"}
SUGGESTED = ("이 개념을 더 쉬운 예로 설명해 줄래요?", "그래프에서 무엇이 움직이는지 설명해 줄래요?",
             "이 내용이 SDG 와 어떻게 연결돼요?")


def conversation_for(user_id, lesson, conv_id=None, create=False):
    """본인의 이 레슨 튜터 대화. conv_id 가 남의 것이거나 다른 레슨 것이면 LookupError."""
    if conv_id:
        conv = storage.get_ai_conversation(user_id, conv_id)
        if conv is None or conv["kind"] != "tutor" or conv["lesson_id"] != lesson.id:
            raise LookupError("conversation")
        return conv
    found = storage.find_ai_conversations(user_id, "tutor", lesson_id=lesson.id)
    if found:
        return found[0]
    if not create:
        return None
    return storage.get_ai_conversation(user_id, storage.create_ai_conversation(
        user_id, "tutor", course_id=lesson.course_id, lesson_id=lesson.id))


def history(user_id, lesson, limit=20):
    conv = conversation_for(user_id, lesson)
    return (conv, storage.list_ai_messages(user_id, conv["id"], limit=limit)) if conv else (None, [])


def _latest_sim(user_id, lesson):
    runs = [r for r in storage.list_simulation_runs(user_id) if r.get("lesson_id") == lesson.id]
    return runs[0] if runs else None


def ask(user_id, course, lesson, level, text, sources, conv_id=None, provider=None):
    """질문 하나에 답한다. 반환: {"conversation_id", "message": 화면용 dict}. 실패는 AIError."""
    s = client.settings()
    text = safety.clean_student_text(text, s.max_input_chars)
    ctx = context.lesson_context(course, lesson, level, sources, sim_run=_latest_sim(user_id, lesson))
    conv = conversation_for(user_id, lesson, conv_id)   # 대화는 답을 받은 뒤에야 만든다 (실패하면 아무것도 남기지 않음)
    if conv is not None:   # 질문+답 2개를 새로 저장하므로 2개 여유가 있어야 한다 (AI 를 부르기 전에 확인)
        quotas.check("TUTOR_MESSAGES", len(storage.list_ai_messages(user_id, conv["id"])), adding=2)
    past = storage.list_ai_messages(user_id, conv["id"], limit=s.max_history) if conv and s.max_history else []
    messages = [{"role": "user", "content": safety.material_block(ctx)}]
    for m in past:   # 서버에 저장된 기록만 쓴다 (학생 글은 다시 감싼다)
        messages.append({"role": "user", "content": safety.student_block(m["content"])} if m["role"] == "student"
                        else {"role": "assistant", "content": m["content"]})
    messages.append({"role": "user", "content": safety.student_block(text)})
    req = AIRequest(task="tutor", system=safety.system_prompt("tutor"), messages=messages, schema=SCHEMA,
                    payload={**ctx, "student_text": text}, user_ref=safety.pseudonym(user_id))
    data = usage.run(user_id, req, f"tutor:{lesson.id}", text, provider=provider, s=s)
    allowed = {src["id"]: src for src in ctx["sources"]}
    kept, dropped = safety.filter_source_ids(data["used_source_ids"], allowed)
    limitations = safety.clip(data["limitations"], 500)
    grounding = data["grounding"]
    if dropped:
        grounding = "partial" if grounding == "grounded" else grounding
        limitations = (limitations + " " if limitations else "") + \
            f"확인할 수 없는 출처 표시 {len(dropped)}개는 지웠어요 (승인된 출처 목록에 없음)."
    no_source_note = "이 레슨에는 확인된 출처가 연결되어 있지 않아요."
    if not ctx["sources"] and no_source_note not in limitations:
        limitations = (limitations + " " if limitations else "") + no_source_note
    message = {"answer": safety.clip(data["answer"], 2000), "grounding": grounding,
               "grounding_label": GROUNDING_KO[grounding],
               "sources": [allowed[sid] for sid in kept],
               "beyond_sources": safety.clip(data["beyond_sources"], 1200),
               "follow_up_questions": [safety.clip(q, 200) for q in data["follow_up_questions"]][:3],
               "limitations": limitations.strip(), "dropped_sources": len(dropped)}
    conv = conv or conversation_for(user_id, lesson, create=True)
    storage.add_ai_message(user_id, conv["id"], "student", text)
    storage.add_ai_message(user_id, conv["id"], "assistant", message["answer"], meta=message)
    return {"conversation_id": conv["id"], "message": message}
