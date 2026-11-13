"""교사용 교육 검토 문서(Markdown) 생성. 학생 화면으로는 제공하지 않는다 (flask --app app review-package c02).

정답이 들어 있으므로 기본 저장 위치는 비공개 폴더(<ECONOVA_PRIVATE_CONTENT_DIR>/review/)다. 저장소 안에는 git 이 무시하는
곳(docs/review/ 등)에만 쓸 수 있다. 문서 첫 줄의 표시 문구로 커밋 전 점검(econova/public_safety.py)이 이 문서를 알아본다.

레슨 요약, 형성 퀴즈·최종 평가 문항과 정답·해설, 측정하는 학습목표, 난이도, 출처, 사람이 확인해야 할 항목,
승인되지 않은 합격 기준 제안값을 한 문서에 모은다. 문서를 만든다고 어떤 자료도 승인되지 않는다.
"""
from econova.content import DIFFICULTY_NAMES
from econova.public_safety import REVIEW_MARKER

STATUS_KO = {"draft": "Draft (not yet reviewed)", "in_review": "In review", "approved": "Approved", "published": "Published"}


def _q_lines(q, sources):
    lines = [f"#### {q['id']} (v{q['version']}) · {DIFFICULTY_NAMES[q['difficulty']]} · {q['points']:g} pt · Question status: {STATUS_KO.get(q['review_status'], q['review_status'])}",
             "", q["prompt"], ""]
    if q["type"] == "mcq":
        for c in q["choices"]:
            mark = " ← **Correct answer**" if c["id"] == q["answer"] else ""
            lines.append(f"- ({c['id']}) {c['text']}{mark}")
    else:
        lines.append(f"- Numeric · **Answer {q['answer']:g}** · Tolerance ±{q['tolerance']:g}")
    lines += ["", f"- Explanation: {q['explanation']}",
              f"- Learning objective measured: {q['lesson_id']} objective {q['objective']} — {q['objective_text']}",
              f"- Key concepts: {', '.join(q['concept_ids'])}"]
    if q["source_ids"]:
        lines.append("- Sources: " + "; ".join(f"{sources[s].title} ({s})" if s in sources else s for s in q["source_ids"]))
    lines.append("")
    return lines


class KeysMissing(Exception):
    """정답 키가 없는 평가가 있어 검토 문서를 만들 수 없다."""


def build(course, sources, generated_on):
    missing = [a.id for a in [ls.quiz_assessment for ls in course.lessons] + [course.final] if a and not a.answer_keys]
    if missing:
        raise KeysMissing(f"Cannot build the review document because some assessments have no answer key: {', '.join(missing)}")
    out = [f"<!-- {REVIEW_MARKER} -->", "", f"# {course.id.upper()} {course.title_ko} ({course.title}) — Educational review document", "",
           f"> Generated {generated_on} · Internal teacher material · Not for students · Contains answer keys", "",
           "This document collects **unreviewed drafts** written by AI (Claude Code). Creating or reading this document does not approve any material.",
           "To approve, record the reviewer's name, date, and notes in each JSON file's `review` block (see the review process in the README).", "",
           f"- Course status: `{course.status}` · Course content version {course.content_version}",
           f"- Course description and learning objectives review status: `{course.review_status}`", ""]
    out += ["## 1. Lesson summaries", ""]
    for lesson in course.lessons:
        doc = lesson.content
        out.append(f"### {lesson.id} {lesson.title_ko} ({lesson.title})")
        out.append(f"- Learning materials status: {STATUS_KO.get(doc.review_status, doc.review_status) if doc else 'None'}")
        out.append("- Learning objectives:")
        out += [f"  {i}. {o}" for i, o in enumerate(lesson.objectives, 1)]
        if doc:
            out.append("- Key concepts: " + ", ".join(c["term"] for c in doc.concepts))
            for level in ("beginner", "intermediate", "advanced"):
                out.append(f"- {DIFFICULTY_NAMES[level]} summary: {doc.levels[level]['summary']}")
            out.append("- Sources: " + "; ".join(f"{sources[s].title} ({'verified' if sources[s].verified else 'unverified'})" for s in doc.source_ids))
        out.append("")
    out += ["## 2. Lesson quizzes", "",
            "Submitting the lesson quiz is what completes the lesson; the score does not affect completion, and the best score is recorded separately.", ""]
    for lesson in course.lessons:
        a = lesson.quiz_assessment
        if a is None:
            out += [f"### {lesson.id}: No quiz", ""]
            continue
        out += [f"### {a.title} (`{a.id}` v{a.version}) · Status: {STATUS_KO.get(a.review_status, a.review_status)}",
                f"Retakes: {'unlimited' if not a.max_attempts else f'up to {a.max_attempts}'}", ""]
        for q in a.questions:
            out += _q_lines(q, sources)
    out += ["## 3. Final assessment", ""]
    final = course.final
    if final is None:
        out += ["No final assessment.", ""]
    else:
        p = final.passing
        out += [f"### {final.title} (`{final.id}` v{final.version}) · Status: {STATUS_KO.get(final.review_status, final.review_status)}",
                f"Retakes: up to {final.max_attempts} (best result recorded)" if final.max_attempts else "Retakes: unlimited", ""]
        for q in final.questions:
            out += _q_lines(q, sources)
        out += ["## 4. Final assessment passing criteria (proposed, not approved)", "",
                f"- Proposal: pass with **{p['score_ratio'] * 100:g}% or more** correct · Status `{p['status']}`",
                f"- Note: {p['note']}",
                "- This value is a **proposal that has not been approved**. Course completion is not granted on this basis until a reviewer approves it.", ""]
    out += ["## 5. Items for human review", "",
            "1. Is each answer and explanation economically accurate and right for high school students?",
            "2. Does each question actually measure its listed learning objective and key concepts? Is the difficulty (beginner/intermediate/advanced) appropriate?",
            "3. Are the wrong choices plausible but unambiguous (no question reads as having two correct answers)?",
            "4. Is the tolerance for numeric questions appropriate (including rounding instructions)?",
            "5. Are policy questions neutral and framed in terms of evidence, assumptions, benefits, and costs?",
            "6. Are the source links correct? Were no textbook questions copied (all questions are newly written)?",
            "7. Should the proposed final assessment passing criteria and retake limit be approved or changed?", ""]
    return "\n".join(out)
