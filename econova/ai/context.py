"""AI 에게 줄 학습 맥락을 서버에서만 만든다 (브라우저가 보낸 자료는 쓰지 않는다).

넣는 것: 강좌·레슨 제목, 학생 난이도, 승인된 학습자료의 학습목표·핵심 개념·난이도별 설명·풀이 예제·SDG 사례·핵심 정리,
         확인된(verified) 출처의 '목록 정보'(id·제목·저자·발행처·날짜), 서버가 다시 계산해 저장한 본인의 시뮬레이션 결과.
넣지 않는 것: 승인되지 않은 초안, 확인되지 않은 출처, 출처의 본문(제3자 저작물 — 예: OpenStax 는 LLM 학습 이용을 서면 허락 없이
         금지한다고 고지), 평가 문항·정답 키, 학생의 이메일·이름.
"""
from econova import content
from econova.ai.client import AIError

LEVEL_TEXT_LIMIT = 3500
MAX_EXAMPLES = 2


def allowed_sources(material, sources):
    """레슨 자료가 인용한 출처 중 확인된 것만, 목록 정보만."""
    out = []
    for sid in material.source_ids:
        src = sources.get(sid)
        if src is not None and src.verified:
            out.append({"id": src.id, "title": src.title, "author": src.author, "container": src.container,
                        "published": src.published})
    return out


def _level_text(material, level):
    lv = material.levels[level]
    parts = [lv["summary"]]
    for section in lv["sections"]:
        parts.append(section["heading"] + ": " + " ".join(section["paragraphs"]))
    text = "\n".join(parts)
    return text[:LEVEL_TEXT_LIMIT]


def lesson_context(course, lesson, level, sources, sim_run=None):
    """승인된 학습자료로만 만든 튜터 맥락. 승인되지 않았으면 AIError('unavailable')."""
    material = lesson.content
    if material is None or not material.approved:
        raise AIError("unavailable", "승인된 학습자료 없음")
    if level not in content.DIFFICULTIES:
        level = "beginner"
    src = allowed_sources(material, sources)
    ok_ids = {s["id"] for s in src}
    ctx = {
        "course": course.title_ko, "lesson": lesson.title_ko, "level": level,
        "level_name": content.DIFFICULTY_NAMES[level],
        "objectives": list(lesson.objectives),
        "concepts": [{"id": c["id"], "term": c["term"], "definition": c["definition"],
                      "source_ids": [s for s in c.get("source_ids", ()) if s in ok_ids]} for c in material.concepts],
        "level_explanation": _level_text(material, level),
        "worked_examples": [{"title": ex["title"], "problem": ex["problem"], "steps": list(ex["steps"]),
                             "answer": ex["answer"]} for ex in material.examples_for(level)[:MAX_EXAMPLES]],
        "sdg_case": {"title": material.sdg_case["title"], "paragraphs": list(material.sdg_case["paragraphs"]),
                     "options": material.sdg_case["options"],
                     "source_ids": [s for s in material.sdg_case.get("source_ids", ()) if s in ok_ids]},
        "key_takeaways": list(material.key_takeaways),
        "sources": src,
        "simulation": None,
    }
    if sim_run is not None:
        ctx["simulation"] = {"simulation_id": sim_run["simulation_id"], "inputs": sim_run["inputs"],
                             "results": {k: v for k, v in sim_run["results"].items() if isinstance(v, (int, float, str))
                                         and k not in ("reason",)},
                             "note": "학생이 저장한 결과를 서버가 다시 계산한 값. 가상의 모형 계산이며 실제 통계가 아님."}
    return ctx


def concept_terms(course, lesson_id):
    """레슨의 승인된 개념 {id: (term, definition)} (피드백·추천 설명용)."""
    lesson = course.lesson(lesson_id) if course else None
    if lesson is None or lesson.content is None or not lesson.content.approved:
        return {}
    return {c["id"]: (c["term"], c["definition"]) for c in lesson.content.concepts}
