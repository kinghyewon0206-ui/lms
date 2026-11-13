"""개인 학습 보고서 (Phase 7) — 학생 본인만 보는 화면. 교사·관리자용 분석이 아니다.

모든 값은 저장된 기록에서 정해진 규칙으로 계산한다 (점수·숙달도·기록을 지어내지 않는다).
- 진도: econova.progress (레슨 완료 = 필수 활동 완료)
- 평가: 응시 기록의 점수 그대로. 재응시 변화 = 마지막 − 처음 (%p). '숙달도' 같은 추정 퍼센트는 만들지 않는다.
- 개념: econova.recommendations.analyze 의 결정적 분석 (문항 수가 적으면 '잠정').
"""
from econova import content, diagnostic, progress, recommendations, storage

MAX_TIMELINE = 15


def _pct(ratio):
    return round(ratio * 100) if ratio is not None else None


def _assessment_lookup(catalog):
    out = {}
    for course in catalog.courses:
        for lesson in course.lessons:
            if lesson.quiz_assessment:
                out[lesson.quiz_assessment.id] = (course, lesson.quiz_assessment)
        if course.final:
            out[course.final.id] = (course, course.final)
    return out


def trend_points(ratios, width=220, height=60, pad=6):
    """점수 추세 SVG 좌표 (정답률 0~100% → 세로). 값이 하나면 점 하나."""
    n = len(ratios)
    pts = []
    for i, r in enumerate(ratios):
        x = pad + (width - 2 * pad) * (i / (n - 1) if n > 1 else 0.5)
        y = pad + (height - 2 * pad) * (1 - r)
        pts.append((round(x, 1), round(y, 1)))
    return pts


def build(user_id, catalog):
    enrollments = storage.list_enrollments(user_id)
    records = storage.list_all_lesson_progress(user_id)
    attempts = storage.list_assessment_attempts(user_id)
    diag_attempts = storage.list_diagnostic_attempts(user_id)
    sims = storage.list_simulation_runs(user_id)
    capstones = {p["course_id"]: p for p in storage.list_capstones(user_id)}

    courses, timeline = [], []
    for e in enrollments:
        course = catalog.course(e["course_id"])
        timeline.append((e["enrolled_at"], "Enrolled", course.title_ko if course else e["course_id"]))
        if course is None:
            courses.append({"enrollment": e, "course": None})
            continue
        recs = records.get(course.id, {})
        prog = progress.course_progress(course, recs)
        lessons = []
        for lesson in course.lessons:
            r = recs.get(lesson.id) or {}
            lessons.append({"lesson": lesson, "status": prog["statuses"][lesson.id], "record": r})
            if r.get("material_reviewed_at"):
                timeline.append((r["material_reviewed_at"], "Reviewed learning materials", f"{course.title_ko} · {lesson.title_ko}"))
            if r.get("completed_at"):
                timeline.append((r["completed_at"], "Completed lesson", f"{course.title_ko} · {lesson.title_ko}"))
        if e.get("completed_at"):
            timeline.append((e["completed_at"], "Course completed", course.title_ko))
        courses.append({"enrollment": e, "course": course, "progress": prog, "lessons": lessons,
                        "completed": e["status"] == "completed", "policy": e.get("completion_policy"),
                        "capstone": capstones.get(course.id)})

    lookup = _assessment_lookup(catalog)
    groups = {}
    for a in sorted(attempts, key=lambda a: (a["created_at"], a["id"])):
        groups.setdefault(a["assessment_id"], []).append(a)
        title = lookup.get(a["assessment_id"], (None, None))[1]
        timeline.append((a["created_at"], "Took final assessment" if a["kind"] == "final" else "Submitted lesson quiz",
                         f"{title.title if title else a['assessment_id']} · {_pct(a['ratio'])}%"))
    assessments = []
    for aid, rows in groups.items():
        course, assessment = lookup.get(aid, (None, None))
        ratios = [a["ratio"] for a in rows]
        assessments.append({
            "id": aid, "title": assessment.title if assessment else aid, "kind": rows[0]["kind"],
            "course_title": course.title_ko if course else rows[0]["course_id"],
            "attempts": [{"n": i + 1, "percent": _pct(a["ratio"]), "score": a["score"], "max_score": a["max_score"],
                          "created_at": a["created_at"], "passed": a.get("passed"), "version": a.get("assessment_version")}
                         for i, a in enumerate(rows)],
            "first": _pct(ratios[0]), "latest": _pct(ratios[-1]), "best": _pct(max(ratios)),
            "change": _pct(ratios[-1]) - _pct(ratios[0]) if len(ratios) > 1 else None,
            "points": trend_points(ratios), "mixed_versions": len({a.get("assessment_version") for a in rows}) > 1})
    assessments.sort(key=lambda x: (x["course_title"], x["kind"] != "lesson_quiz", x["title"]))

    test = diagnostic.load()
    names = test["category_names"]
    diag = [{"id": d["id"], "created_at": d["created_at"], "score": d["score"], "max_score": d["max_score"],
             "level": d["recommended_level"], "version": d.get("diagnostic_version")} for d in diag_attempts]
    for d in diag_attempts:
        timeline.append((d["created_at"], "Diagnostic assessment", f"{d['score']}/{d['max_score']}"))
    diag_areas = []
    if diag_attempts:
        for area, v in sorted(diag_attempts[0]["by_category"].items()):
            diag_areas.append({"area": names.get(area, area), "correct": v["correct"], "total": v["total"],
                               "review": bool(v["total"]) and v["correct"] / v["total"] < recommendations.REVIEW_BELOW})
    for s in sims:
        timeline.append((s["created_at"], "Saved simulation", s["simulation_id"]))
    for course_id in capstones:
        for v in storage.list_capstone_versions(user_id, course_id):
            timeline.append((v["created_at"], "Submitted Capstone project" if v["kind"] == "submitted" else "Saved Capstone project",
                             f"{course_id} version {v['version']}"))

    analysis = recommendations.analyze(user_id, catalog)
    timeline = [t for t in timeline if t[0] is not None]
    timeline.sort(key=lambda t: t[0], reverse=True)
    totals = {"courses": len([c for c in courses if c["course"]]),
              "completed_courses": sum(1 for c in courses if c.get("completed")),
              "lessons_completed": sum(c["progress"]["completed"] for c in courses if c["course"]),
              "lessons_in_progress": sum(1 for c in courses if c["course"] for l in c["lessons"]
                                         if l["status"] == progress.IN_PROGRESS),
              "lessons_total": sum(c["progress"]["total"] for c in courses if c["course"])}
    return {"totals": totals, "courses": courses, "assessments": assessments, "diagnostic": diag,
            "diagnostic_areas": diag_areas, "analysis": analysis, "timeline": timeline[:MAX_TIMELINE],
            "simulations": len(sims), "difficulty_names": content.DIFFICULTY_NAMES,
            "evidence_rule": {"min": recommendations.MIN_EVIDENCE, "below": round(recommendations.REVIEW_BELOW * 100)}}
