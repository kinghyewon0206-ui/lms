"""개인별 학습 추천 — 결정적 분석 (AI 아님). 같은 기록이면 언제나 같은 결과.

근거:
- 수강 중인 강좌의 레슨 진도
- 형성 퀴즈·최종 평가: 평가마다 '가장 최근 응시'의 문항별 정오. 지금 문항과 버전이 같은 문항만 개념(concept_ids)에 연결한다.
- 진단평가: 가장 최근 결과의 영역별 정답 수 (기초 영역 참고용)
- 시뮬레이션: 레슨에 연결된 시뮬레이션을 저장해 본 적이 있는가 (활동 여부만)

규칙 (ECONOVA_* 상수):
- 개념 정답률 = 맞힌 문항 수 / 확인한 문항 수.
- 확인한 문항이 MIN_EVIDENCE 개 미만이면 '잠정(provisional)': 진단이라고 하기엔 근거가 부족하다고 표시한다.
- 정답률이 REVIEW_BELOW 미만이면 '복습 권장', 근거가 부족하면 '잠정 복습 권장'.
- 자료는 봤는데 평가로 확인한 적이 없는 개념은 '아직 확인 안 함'.
- 정렬: 복습 권장(근거 충분) → 잠정 → 확인 안 함, 같은 단계에서는 정답률 낮은 순 → 근거 많은 순 → 강좌·레슨 순서 → 개념 id.
수강·난이도·점수는 바꾸지 않는다. AI 는 이 결과를 쉬운 말로 풀어 쓰기만 한다 (econova/ai/recommendations.py).
"""
from econova import progress, storage

MIN_EVIDENCE = 3
REVIEW_BELOW = 0.6
MAX_ITEMS = 6


def _latest_per_assessment(attempts):
    latest = {}
    for a in attempts:   # list_assessment_attempts 는 최신순
        latest.setdefault(a["assessment_id"], a)
    return latest


def _assessment_of(course, attempt):
    if attempt["kind"] == "final":
        return course.final
    lesson = course.lesson(attempt.get("lesson_id") or "")
    return lesson.quiz_assessment if lesson else None


def analyze(user_id, catalog):
    enrollments = storage.list_enrollments(user_id)
    all_records = storage.list_all_lesson_progress(user_id)
    attempts = storage.list_assessment_attempts(user_id)
    sims = storage.list_simulation_runs(user_id)
    sim_lessons = {(r["lesson_id"], r["simulation_id"]) for r in sims if r.get("lesson_id")}
    concepts, next_lessons, seen_material = {}, [], set()
    used_attempts = 0
    for enrollment in enrollments:
        course = catalog.course(enrollment["course_id"])
        if course is None or not course.published:
            continue   # 공개되지 않은(또는 사라진) 강좌는 분석하지 않는다
        records = all_records.get(course.id, {})
        prog = progress.course_progress(course, records)
        if prog["next_lesson"] is not None:
            nl = prog["next_lesson"]
            next_lessons.append({"course_id": course.id, "course_title": course.title_ko, "lesson_id": nl.id,
                                 "lesson_title": nl.title_ko, "order": nl.order, "status": prog["statuses"][nl.id]})
        lesson_order = {l.id: (i, l) for i, l in enumerate(course.lessons)}
        for lesson in course.lessons:
            if (records.get(lesson.id) or {}).get("material_reviewed") and lesson.content is not None:
                for c in lesson.content.concepts:
                    seen_material.add((course.id, lesson.id, c["id"]))
            if lesson.content is not None:
                for c in lesson.content.concepts:
                    concepts.setdefault((course.id, c["id"]), {
                        "course_id": course.id, "course_title": course.title_ko, "concept_id": c["id"],
                        "term": c["term"], "lesson_id": lesson.id, "lesson_title": lesson.title_ko,
                        "course_rank": enrollments.index(enrollment), "lesson_rank": lesson_order[lesson.id][0],
                        "correct": 0, "total": 0, "assessments": set(), "simulations": list(lesson.simulations),
                        "has_quiz": "quiz" in lesson.requirements and lesson.quiz_approved,
                        "simulated": any((lesson.id, s) in sim_lessons for s in lesson.simulations)})
        for aid, attempt in _latest_per_assessment([a for a in attempts if a["course_id"] == course.id]).items():
            assessment = _assessment_of(course, attempt)
            if assessment is None or assessment.id != aid:
                continue
            used_attempts += 1
            for r in attempt.get("results") or []:
                q = assessment.question(r["id"])
                if q is None or q.get("version") != r.get("version"):
                    continue   # 바뀐 문항은 지금 개념과 연결하지 않는다
                for cid in q["concept_ids"]:
                    item = concepts.get((course.id, cid))
                    if item is None:
                        continue
                    item["total"] += 1
                    item["correct"] += int(bool(r.get("correct")))
                    item["assessments"].add(assessment.title)
    items, measured = [], []
    for (course_id, cid), it in concepts.items():
        if it["total"]:
            measured.append({k: it[k] for k in ("course_id", "course_title", "concept_id", "term", "lesson_id",
                                                 "lesson_title", "correct", "total")}
                            | {"provisional": it["total"] < MIN_EVIDENCE,
                               "strength": it["total"] >= MIN_EVIDENCE and it["correct"] / it["total"] >= REVIEW_BELOW})
        if it["total"]:
            ratio = it["correct"] / it["total"]
            if ratio >= REVIEW_BELOW and it["total"] >= MIN_EVIDENCE:
                continue   # 충분히 확인했고 잘하고 있다
            provisional = it["total"] < MIN_EVIDENCE
            if ratio >= REVIEW_BELOW:
                continue   # 근거는 적지만 맞혔다 — 추천하지 않는다
            status = "provisional" if provisional else "review"
            pct = round(ratio * 100)
            reason = (f"최근 응시에서 이 개념 문항 {it['total']}개 중 {it['correct']}개를 맞혔어요 (정답률 {pct}%). "
                      + ("아직 문항 수가 적어 확실한 진단은 아니에요." if provisional else
                         f"정답률이 {round(REVIEW_BELOW * 100)}% 미만이라 복습을 권해요."))
        elif (course_id, it["lesson_id"], cid) in seen_material and it["has_quiz"]:   # 확인할 퀴즈가 있는 레슨만
            ratio, pct, status = None, None, "unpracticed"
            reason = "학습자료는 봤지만 아직 퀴즈로 확인한 적이 없어요."
        else:
            continue
        actions = [{"kind": "lesson", "label": "레슨 자료 다시 보기"}]
        if it["has_quiz"]:
            actions.append({"kind": "quiz", "label": "형성 퀴즈로 확인하기" if status == "unpracticed" else "형성 퀴즈 다시 풀어 보기"})
        if it["simulations"]:
            actions.append({"kind": "simulation", "label": "시뮬레이션으로 확인하기" + (" (해 본 적 있음)" if it["simulated"] else "")})
        items.append({**{k: it[k] for k in ("course_id", "course_title", "concept_id", "term", "lesson_id",
                                             "lesson_title", "correct", "total")},
                      "ratio": ratio, "percent": pct, "status": status, "provisional": status != "review",
                      "reason": reason, "assessments": sorted(it["assessments"]), "actions": actions,
                      "_key": ({"review": 0, "provisional": 1, "unpracticed": 2}[status],
                               ratio if ratio is not None else 1.0, -it["total"], it["course_rank"],
                               it["lesson_rank"], cid)})
    items.sort(key=lambda x: x["_key"])
    for it in items:
        it.pop("_key")
    diag = storage.list_diagnostic_attempts(user_id)
    weak_areas = []
    if diag:
        latest = diag[0]
        for area, v in sorted(latest["by_category"].items()):
            if v["total"] and v["correct"] / v["total"] < REVIEW_BELOW:
                weak_areas.append({"area": area, "correct": v["correct"], "total": v["total"],
                                   "provisional": v["total"] < MIN_EVIDENCE})
    evidence = {"enrolled_courses": len(enrollments), "assessments_used": used_attempts,
                "diagnostic": bool(diag), "simulation_runs": len(sims)}
    measured.sort(key=lambda m: (m["course_id"], m["lesson_id"], m["concept_id"]))
    return {"items": items[:MAX_ITEMS], "more": max(0, len(items) - MAX_ITEMS), "next_lessons": next_lessons,
            "measured": measured,
            "weak_areas": weak_areas, "evidence": evidence,
            "insufficient": used_attempts == 0,
            "rules": {"min_evidence": MIN_EVIDENCE, "review_below_percent": round(REVIEW_BELOW * 100)}}
