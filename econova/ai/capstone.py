"""캡스톤 AI 코치 (선택). 학생이 쓴 프로젝트 글에 대해 질문·빠진 관점·점검할 가정·구성 제안을 돌려준다.
점수·등급·인증을 만들지 않고, 출처·통계를 지어내지 않는다. 링크(URL)가 들어간 답은 표시하지 않는다.
AI 가 꺼져 있어도 캡스톤은 단계별 안내와 자기평가 루브릭으로 끝까지 할 수 있다."""
import re

from econova import storage
from econova.ai import client, context, safety, usage
from econova.ai.client import AIError, AIRequest

LIST = {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 300}}
SCHEMA = {"type": "object", "properties": {
    "strengths": LIST, "questions": LIST, "missing_perspectives": LIST, "assumptions_to_check": LIST,
    "structure_suggestions": LIST, "limitations": {"type": "string", "maxLength": 400}}}
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)


def feedback(user_id, course, defn, version, sections, sdg_names, focus_step=None, provider=None):
    s = client.settings()
    steps = [st for st in defn.steps if focus_step in (None, "", st["id"])] or list(defn.steps)
    concepts = []
    for lesson in course.lessons:
        concepts += [{"term": t, "definition": d} for t, d in context.concept_terms(course, lesson.id).values()]
    sdg = str(sections.get("sdg") or "")
    facts = {"project": "학생의 자기주도 SDG 경제 캡스톤 (공식 과제·평가 아님)",
             "sdg": {"number": sdg, "name": sdg_names.get(int(sdg), ("", ""))[0] if sdg.isdigit() else ""},
             "steps": [{"id": st["id"], "title": st["title"], "guidance": st["guidance"]} for st in steps],
             "rubric_criteria": [{"name": c["name"], "description": c["description"]} for c in defn.rubric["criteria"]],
             "approved_concepts": concepts[:20],
             "rule": "점수·등급을 매기지 말 것. 출처·통계·인용을 만들지 말 것. 학생에게 근거를 직접 확인하라고 안내할 것."}
    student_text = "\n\n".join(f"[{f['label']}]\n{sections.get(f['id'], '')}" for st in steps for f in st["fields"]
                               if f["type"] != "sdg")[:8000]
    req = AIRequest(task="capstone", system=safety.system_prompt("capstone"),
                    messages=[{"role": "user", "content": safety.material_block(facts)},
                              {"role": "user", "content": safety.student_block(student_text)}],
                    schema=SCHEMA, payload={**facts, "student_text": student_text}, user_ref=safety.pseudonym(user_id))

    def check(data):
        texts = [x for k in SCHEMA["properties"] if k != "limitations" for x in data[k]] + [data["limitations"]]
        if any(_URL.search(t) for t in texts):
            raise AIError("invalid_response", "링크 포함")
    data = usage.run(user_id, req, f"capstone:{course.id}:{version}:{focus_step or ''}", str(version), provider=provider,
                     s=s, check=check)
    out = {k: [safety.clip(x, 300) for x in data[k]] for k in SCHEMA["properties"] if k != "limitations"}
    out["limitations"] = safety.clip(data["limitations"], 400)
    out["focus_step"] = focus_step or ""
    storage.save_capstone_feedback(user_id, course.id, version, out)
    return out
