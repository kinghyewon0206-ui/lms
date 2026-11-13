"""경제 토론. 학생 의견은 항상 저장하고(학생의 작업 보존), AI 를 쓸 수 없으면 주제에 적힌 안내 질문으로 이어 간다.
AI 는 동의를 강요하지 않고, 주장 유형(모형·실증 근거·가정·가치 판단·상충관계)을 구분하며, 승자나 정답을 정하지 않는다."""
from econova import debates, quotas, storage
from econova.ai import client, safety, usage
from econova.ai.client import AIError, AIRequest

TURN_SCHEMA = {"type": "object", "properties": {
    "reflection": {"type": "string", "maxLength": 600},
    "follow_up_question": {"type": "string", "maxLength": 300},
    "perspectives_considered": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 60}},
    "claim_types": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {
        "claim": {"type": "string", "maxLength": 200},
        "type": {"type": "string", "enum": list(debates.CLAIM_TYPES)}}}},
}}
SUMMARY_SCHEMA = {"type": "object", "properties": {
    "summary": {"type": "string", "maxLength": 800},
    "arguments": {"type": "array", "maxItems": 6, "items": {"type": "object", "properties": {
        "perspective_id": {"type": "string", "maxLength": 60},
        "points": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 300}}}}},
    "trade_offs": {"type": "array", "maxItems": 5, "items": {"type": "string", "maxLength": 300}},
    "open_questions": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 300}},
    "note": {"type": "string", "maxLength": 300},
}}


def _topic_material(course, topic):
    return {"course": course.title_ko, "topic": topic["title"], "background": topic["background"],
            "policy_question": topic["policy_question"],
            "perspectives": [{k: p[k] for k in ("id", "name", "summary", "reasoning", "assumptions")} for p in topic["perspectives"]],
            "guiding_questions": topic["guiding_questions"], "trade_offs": topic["trade_offs"]}


def conversation(user_id, course, topic, conv_id=None, create=False):
    if conv_id:
        conv = storage.get_ai_conversation(user_id, conv_id)
        if conv is None or conv["kind"] != "debate" or conv["topic_id"] != topic["id"] or conv["course_id"] != course.id:
            raise LookupError("conversation")
        return conv
    found = storage.find_ai_conversations(user_id, "debate", course_id=course.id, topic_id=topic["id"])
    if found:
        return found[0]
    if not create:
        return None
    check_new_debate(user_id, course, topic)
    return storage.get_ai_conversation(user_id, storage.create_ai_conversation(
        user_id, "debate", course_id=course.id, topic_id=topic["id"]))


def check_new_debate(user_id, course, topic):
    """새 토론을 만들어도 되는가 (주제별·전체 개수 한도). 안 되면 QuotaExceeded."""
    quotas.check("DEBATES_PER_TOPIC", len(storage.find_ai_conversations(user_id, "debate", course_id=course.id,
                                                                         topic_id=topic["id"])))
    quotas.check("DEBATES_TOTAL", len(storage.find_ai_conversations(user_id, "debate")))


def new_conversation(user_id, course, topic):
    check_new_debate(user_id, course, topic)
    return storage.get_ai_conversation(user_id, storage.create_ai_conversation(
        user_id, "debate", course_id=course.id, topic_id=topic["id"]))


def student_turns(messages):
    return sum(1 for m in messages if m["role"] == "student")


def _history_messages(messages, limit):
    out = []
    for m in messages[-limit:] if limit else []:
        out.append({"role": "user", "content": safety.student_block(m["content"])} if m["role"] == "student"
                   else {"role": "assistant", "content": m["content"]})
    return out


def respond(user_id, course, topic, conv, text, provider=None):
    """학생 의견을 저장하고 후속 질문을 붙인다. 반환: 저장한 진행자 메시지 meta. AI 실패는 안내 질문으로 대신하고
    meta['ai_error'] 에 학생용 이유를 담는다 (학생 의견은 이미 저장됨)."""
    s = client.settings()
    text = safety.clean_student_text(text, s.max_input_chars)
    messages = storage.list_ai_messages(user_id, conv["id"])
    if conv["stage"] != "open" or student_turns(messages) >= topic["max_turns"]:
        raise AIError("unavailable", "debate has ended")
    storage.add_ai_message(user_id, conv["id"], "student", text)
    turn = student_turns(messages) + 1
    material = _topic_material(course, topic)
    meta = {"source": "ai"}
    try:
        req = AIRequest(task="debate_turn", system=safety.system_prompt("debate_turn"),
                        messages=[{"role": "user", "content": safety.material_block(material)}]
                        + _history_messages(messages, s.max_history)
                        + [{"role": "user", "content": safety.student_block(text)}],
                        schema=TURN_SCHEMA, payload={**material, "student_text": text}, user_ref=safety.pseudonym(user_id))
        data = usage.run(user_id, req, f"debate:{conv['id']}", text, provider=provider, s=s)
        ids = {p["id"] for p in topic["perspectives"]}
        meta.update(reflection=safety.clip(data["reflection"], 600),
                    follow_up_question=safety.clip(data["follow_up_question"], 300),
                    perspectives_considered=[p for p in data["perspectives_considered"] if p in ids],
                    claim_types=[{"claim": safety.clip(c["claim"], 200), "type": c["type"],
                                  "type_label": debates.CLAIM_TYPES[c["type"]]} for c in data["claim_types"]])
    except AIError as exc:
        guides = topic["guiding_questions"]
        meta = {"source": "guide", "ai_error": exc.message, "reflection": "",
                "follow_up_question": guides[(turn - 1) % len(guides)], "perspectives_considered": [], "claim_types": []}
    storage.add_ai_message(user_id, conv["id"], "assistant", meta["follow_up_question"], meta=meta)
    return meta


def summarize(user_id, course, topic, conv, provider=None):
    """토론 정리. AI 를 못 쓰면 학생 의견과 주제의 상충관계로 만든 기본 정리. 정리 후 토론은 닫힌다."""
    s = client.settings()
    messages = storage.list_ai_messages(user_id, conv["id"])
    mine = [m["content"] for m in messages if m["role"] == "student"]
    if not mine:
        raise AIError("empty")
    material = _topic_material(course, topic)
    names = {p["id"]: p["name"] for p in topic["perspectives"]}
    try:
        req = AIRequest(task="debate_summary", system=safety.system_prompt("debate_summary"),
                        messages=[{"role": "user", "content": safety.material_block(material)}]
                        + [{"role": "user", "content": safety.student_block("\n---\n".join(mine[-8:]))}],
                        schema=SUMMARY_SCHEMA, payload={**material, "student_text": " ".join(mine)},
                        user_ref=safety.pseudonym(user_id))
        data = usage.run(user_id, req, f"debate-summary:{conv['id']}", str(len(mine)), provider=provider, s=s)
        summary = {"source": "ai", "summary": safety.clip(data["summary"], 800),
                   "arguments": [{"perspective": names[a["perspective_id"]], "points": [safety.clip(p, 300) for p in a["points"]]}
                                 for a in data["arguments"] if a["perspective_id"] in names],
                   "trade_offs": [safety.clip(t, 300) for t in data["trade_offs"]],
                   "open_questions": [safety.clip(q, 300) for q in data["open_questions"]],
                   "note": safety.clip(data["note"], 300)}
    except AIError as exc:
        summary = {"source": "guide", "ai_error": exc.message,
                   "summary": f"Here is a summary of your {len(mine)} response(s) and the perspectives and trade-offs for this topic (automatic summary, not AI).",
                   "arguments": [{"perspective": p["name"], "points": [p["summary"]]} for p in topic["perspectives"]],
                   "my_points": mine, "trade_offs": topic["trade_offs"], "open_questions": topic["guiding_questions"][:2],
                   "note": "This question does not have a single correct answer."}
    storage.add_ai_message(user_id, conv["id"], "assistant", "Debate summary", meta={"summary": summary})
    storage.set_ai_conversation_stage(user_id, conv["id"], "summarized")
    return summary
