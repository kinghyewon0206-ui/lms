"""경제 토론 주제 (content/debates/<course_id>.json, 개발용은 content/dev_fixtures/debates/<course_id>.json).

주제마다: 배경(검토된 글), 정책 질문, 서로 다른 관점(2개 이상, 각 관점의 근거·가정), 안내 질문, 상충관계, 출처.
검토 규칙은 학습자료와 같다 (교사 승인 필요, AI 승인 불가). 학생에게는 승인된 주제만, 공개·수강 중인 강좌에서만 보인다.
"""
import os

from econova import content, lesson_content
from econova.lesson_content import ContentError

CLAIM_TYPES = {"model": "Economic model", "evidence": "Empirical evidence", "assumption": "Assumption", "value_judgment": "Value judgment",
               "trade_off": "Trade-off"}


def _path(course):
    base = os.path.join(content.CONTENT_DIR, "dev_fixtures") if course.fixture else content.CONTENT_DIR
    return os.path.join(base, "debates", f"{course.id}.json")


def parse_topics(data, course, sources, where):
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("course_id") != course.id:
        raise ContentError(f"{where}: invalid format (expected schema_version 1 and course_id).")
    topics, seen = [], set()
    for t in lesson_content._need(data, "topics", list, where):
        tid = lesson_content._text(t, "id", where)
        w = f"{where} topic {tid}"
        if tid in seen:
            raise ContentError(f"{w}: duplicate topic id.")
        seen.add(tid)
        review = lesson_content._parse_review(lesson_content._need(t, "review", dict, w), w, course.fixture,
                                              digest=lesson_content.content_digest(t))
        perspectives = []
        for p in lesson_content._need(t, "perspectives", list, w):
            perspectives.append({"id": lesson_content._text(p, "id", w), "name": lesson_content._text(p, "name", w),
                                 "summary": lesson_content._text(p, "summary", w),
                                 "reasoning": lesson_content._texts(p, "reasoning", w),
                                 "assumptions": lesson_content._texts(p, "assumptions", w)})
        if len(perspectives) < 2 or len({p["id"] for p in perspectives}) != len(perspectives):
            raise ContentError(f"{w}: there must be at least 2 distinct perspectives.")
        source_ids = lesson_content._texts(t, "source_ids", w, allow_empty=course.fixture)
        bad = [s for s in source_ids if s not in sources or not sources[s].verified]
        if bad:
            raise ContentError(f"{w}: cannot use unverified or missing sources {bad}.")
        topics.append({"id": tid, "title": lesson_content._text(t, "title", w), "review": review,
                       "approved": review["status"] in lesson_content.APPROVED_STATUSES,
                       "background": lesson_content._texts(t, "background", w),
                       "policy_question": lesson_content._text(t, "policy_question", w),
                       "perspectives": perspectives,
                       "guiding_questions": lesson_content._texts(t, "guiding_questions", w),
                       "trade_offs": lesson_content._texts(t, "trade_offs", w),
                       "source_ids": source_ids, "max_turns": int(t.get("max_turns") or 6)})
    return topics


def topics_for(course, sources, approved_only=True):
    path = _path(course)
    if not os.path.exists(path):
        return []
    rel = os.path.relpath(path, content.CONTENT_DIR)
    topics = parse_topics(lesson_content.read_json(path, rel), course, sources, rel)
    return [t for t in topics if t["approved"] or not approved_only]


def topic(course, sources, topic_id):
    return next((t for t in topics_for(course, sources) if t["id"] == topic_id), None)
