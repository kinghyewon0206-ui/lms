"""추천 결과를 학생이 이해하기 쉬운 말로 풀어 쓰는 AI 설명 (선택). 분석(순위·정답률)은 econova/recommendations.py 가
결정적으로 계산하고, AI 는 그 숫자만 쓸 수 있다. 다른 백분율을 쓰면 표시하지 않는다."""
from econova.ai import client, safety, usage
from econova.ai.client import AIError, AIRequest

SCHEMA = {"type": "object", "properties": {
    "message": {"type": "string", "maxLength": 700},
    "tips": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 250}},
}}


def explain(user_id, analysis, provider=None):
    items = [{k: it[k] for k in ("term", "lesson_title", "status", "percent", "correct", "total", "reason")}
             for it in analysis["items"]]
    facts = {"items": items, "next_lessons": [{k: n[k] for k in ("course_title", "lesson_title")} for n in analysis["next_lessons"]],
             "insufficient_evidence": analysis["insufficient"],
             "rules": analysis["rules"]}
    req = AIRequest(task="recommendation", system=safety.system_prompt("recommendation"),
                    messages=[{"role": "user", "content": safety.material_block(facts)}], schema=SCHEMA,
                    payload={**facts, "student_text": ""}, user_ref=safety.pseudonym(user_id))
    s = client.settings()
    allowed = {float(i["percent"]) for i in items if i["percent"] is not None} | \
        {float(analysis["rules"]["review_below_percent"])}

    def check(data):
        if not all(safety.numbers_supported(t, allowed) for t in [data["message"]] + list(data["tips"])):
            raise AIError("invalid_response", "분석에 없는 수치")
    data = usage.run(user_id, req, "recommendation", str([i["term"] for i in items]), provider=provider, s=s, check=check)
    return {"message": safety.clip(data["message"], 700), "tips": [safety.clip(t, 250) for t in data["tips"]]}
