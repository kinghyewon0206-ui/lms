"""교사용 교육 검토 문서(Markdown) 생성. 학생 화면으로는 제공하지 않는다 (flask --app app review-package c02).

정답이 들어 있으므로 기본 저장 위치는 비공개 폴더(<ECONOVA_PRIVATE_CONTENT_DIR>/review/)다. 저장소 안에는 git 이 무시하는
곳(docs/review/ 등)에만 쓸 수 있다. 문서 첫 줄의 표시 문구로 커밋 전 점검(econova/public_safety.py)이 이 문서를 알아본다.

레슨 요약, 형성 퀴즈·최종 평가 문항과 정답·해설, 측정하는 학습목표, 난이도, 출처, 사람이 확인해야 할 항목,
승인되지 않은 합격 기준 제안값을 한 문서에 모은다. 문서를 만든다고 어떤 자료도 승인되지 않는다.
"""
from econova.content import DIFFICULTY_NAMES
from econova.public_safety import REVIEW_MARKER

STATUS_KO = {"draft": "검토 전 초안", "in_review": "검토 중", "approved": "승인됨", "published": "공개됨"}


def _q_lines(q, sources):
    lines = [f"#### {q['id']} (v{q['version']}) · {DIFFICULTY_NAMES[q['difficulty']]} · {q['points']:g}점 · 문항 상태: {STATUS_KO.get(q['review_status'], q['review_status'])}",
             "", q["prompt"], ""]
    if q["type"] == "mcq":
        for c in q["choices"]:
            mark = " ← **정답**" if c["id"] == q["answer"] else ""
            lines.append(f"- ({c['id']}) {c['text']}{mark}")
    else:
        lines.append(f"- 수치형 · **정답 {q['answer']:g}** · 허용 오차 ±{q['tolerance']:g}")
    lines += ["", f"- 해설: {q['explanation']}",
              f"- 측정하는 학습목표: {q['lesson_id']} 목표 {q['objective']} — {q['objective_text']}",
              f"- 핵심 개념: {', '.join(q['concept_ids'])}"]
    if q["source_ids"]:
        lines.append("- 출처: " + "; ".join(f"{sources[s].title} ({s})" if s in sources else s for s in q["source_ids"]))
    lines.append("")
    return lines


class KeysMissing(Exception):
    """정답 키가 없는 평가가 있어 검토 문서를 만들 수 없다."""


def build(course, sources, generated_on):
    missing = [a.id for a in [ls.quiz_assessment for ls in course.lessons] + [course.final] if a and not a.answer_keys]
    if missing:
        raise KeysMissing(f"정답 키가 없는 평가가 있어 검토 문서를 만들 수 없습니다: {', '.join(missing)}")
    out = [f"<!-- {REVIEW_MARKER} -->", "", f"# {course.id.upper()} {course.title_ko} ({course.title}) — 교육 검토 문서", "",
           f"> 생성일 {generated_on} · 교사용 내부 자료 · 학생에게 공개하지 않음 · 정답이 들어 있음", "",
           "이 문서는 AI(Claude Code)가 작성한 **검토 전 초안**을 모은 것입니다. 이 문서를 만들거나 읽는 것만으로는 어떤 자료도 승인되지 않습니다.",
           "승인하려면 각 JSON 파일의 `review` 에 교사 이름·날짜·기록을 남겨야 합니다 (README 의 검토 절차 참고).", "",
           f"- 강좌 상태: `{course.status}` · 강좌 콘텐츠 버전 {course.content_version}",
           f"- 강좌 설명·학습목표 검토 상태: `{course.review_status}`", ""]
    out += ["## 1. 레슨 요약", ""]
    for lesson in course.lessons:
        doc = lesson.content
        out.append(f"### {lesson.id} {lesson.title_ko} ({lesson.title})")
        out.append(f"- 학습자료 상태: {STATUS_KO.get(doc.review_status, doc.review_status) if doc else '없음'}")
        out.append("- 학습목표:")
        out += [f"  {i}. {o}" for i, o in enumerate(lesson.objectives, 1)]
        if doc:
            out.append("- 핵심 개념: " + ", ".join(c["term"] for c in doc.concepts))
            for level in ("beginner", "intermediate", "advanced"):
                out.append(f"- {DIFFICULTY_NAMES[level]} 요약: {doc.levels[level]['summary']}")
            out.append("- 출처: " + "; ".join(f"{sources[s].title} ({'확인됨' if sources[s].verified else '미확인'})" for s in doc.source_ids))
        out.append("")
    out += ["## 2. 레슨 형성 퀴즈", "",
            "형성 퀴즈는 '제출'이 레슨 완료 조건이고, 점수는 완료에 영향을 주지 않으며 최고 점수를 따로 기록한다.", ""]
    for lesson in course.lessons:
        a = lesson.quiz_assessment
        if a is None:
            out += [f"### {lesson.id}: 퀴즈 없음", ""]
            continue
        out += [f"### {a.title} (`{a.id}` v{a.version}) · 상태: {STATUS_KO.get(a.review_status, a.review_status)}",
                f"재응시: {'제한 없음' if not a.max_attempts else f'최대 {a.max_attempts}번'}", ""]
        for q in a.questions:
            out += _q_lines(q, sources)
    out += ["## 3. 최종 평가", ""]
    final = course.final
    if final is None:
        out += ["최종 평가 없음.", ""]
    else:
        p = final.passing
        out += [f"### {final.title} (`{final.id}` v{final.version}) · 상태: {STATUS_KO.get(final.review_status, final.review_status)}",
                f"재응시: 최대 {final.max_attempts}번 (가장 높은 결과 기록)" if final.max_attempts else "재응시: 제한 없음", ""]
        for q in final.questions:
            out += _q_lines(q, sources)
        out += ["## 4. 최종 평가 합격 기준 (승인되지 않은 제안값)", "",
                f"- 제안: 정답률 **{p['score_ratio'] * 100:g}% 이상** 합격 · 상태 `{p['status']}`",
                f"- 메모: {p['note']}",
                "- 이 값은 **승인되지 않은 제안값**입니다. 교사가 승인하기 전에는 이 기준으로 수료를 인정하지 않습니다.", ""]
    out += ["## 5. 사람이 확인해야 할 항목", "",
            "1. 각 문항의 정답과 해설이 경제학적으로 정확한가, 고등학생 수준에 맞는가.",
            "2. 문항이 표시된 학습목표·핵심 개념을 실제로 측정하는가. 난이도(하·중·상) 분류가 적절한가.",
            "3. 오답 선택지가 그럴듯하되 모호하지 않은가 (정답이 둘로 읽히지 않는가).",
            "4. 수치형 문항의 허용 오차가 적절한가 (반올림 방식 안내 포함).",
            "5. 정책 관련 문항이 특정 입장에 치우치지 않고 근거·가정·편익·비용으로 서술됐는가.",
            "6. 출처 연결이 맞는가. 교재 문항을 옮겨 쓰지 않았는가 (모든 문항은 새로 작성함).",
            "7. 최종 평가 합격 기준(제안값)과 재응시 횟수를 승인할지, 바꿀지.", ""]
    return "\n".join(out)
