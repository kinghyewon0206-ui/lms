"""진도 계산. 저장소와 상관없이 같은 결과를 내는 순수 함수만 둔다 (sqlite·Firestore 가 같이 쓴다).

레슨 완료 규칙: 레슨에 설정된 필수 활동(requirements)을 모두 마쳐야 완료다.
- material : 필수 학습자료를 확인했다 (material_reviewed)
- quiz     : 필수 형성 퀴즈를 "제출"했다 (quiz_submitted). 점수와는 별개이고, 퀴즈가 없다고 통과로 치지 않는다.
퀴즈 점수(quiz_score)와 진도율은 따로 관리한다.
"""

NOT_STARTED, IN_PROGRESS, COMPLETED = "not_started", "in_progress", "completed"
LESSON_STATUSES = (NOT_STARTED, IN_PROGRESS, COMPLETED)

_DONE_FIELD = {"material": "material_reviewed", "quiz": "quiz_submitted"}


def empty_record(course_id, lesson_id):
    return {"course_id": course_id, "lesson_id": lesson_id, "material_reviewed": False, "material_reviewed_at": None,
            "quiz_submitted": False, "quiz_submission_id": None, "quiz_submitted_at": None, "quiz_score": None,
            "status": NOT_STARTED, "completed_at": None, "updated_at": None}


def activity_done(record, activity):
    return bool((record or {}).get(_DONE_FIELD[activity]))


def lesson_status(requirements, record):
    """필수 활동이 모두 끝났으면 completed, 하나라도 했으면 in_progress, 아니면 not_started."""
    if not requirements:
        raise ValueError("레슨에는 필수 활동이 하나 이상 있어야 합니다.")
    done = [activity_done(record, a) for a in requirements]
    if all(done):
        return COMPLETED
    if any(activity_done(record, a) for a in _DONE_FIELD):
        return IN_PROGRESS
    return NOT_STARTED


def apply_event(record, requirements, now, *, material_reviewed=False, quiz_submission_id=None):
    """레슨 진도 기록에 이벤트(자료 확인, 퀴즈 제출)를 반영한 새 기록을 돌려준다. (원래 기록은 바꾸지 않는다)"""
    rec = dict(record)
    if material_reviewed and not rec.get("material_reviewed"):
        rec["material_reviewed"], rec["material_reviewed_at"] = True, now
    if quiz_submission_id:
        rec["quiz_submitted"], rec["quiz_submission_id"], rec["quiz_submitted_at"] = True, str(quiz_submission_id), now
    rec["status"] = lesson_status(requirements, rec)
    if rec["status"] == COMPLETED:
        rec["completed_at"] = rec.get("completed_at") or now
    else:
        rec["completed_at"] = None
    rec["updated_at"] = now
    return rec


def course_progress(course, records):
    """강좌 하나의 진도. records = {lesson_id: 기록}. 다른 강좌의 기록은 섞여 있어도 무시한다.

    반환: completed(완료 레슨 수), total, percent(내림 정수), statuses({lesson_id: 상태}),
          next_lesson(처음으로 완료되지 않은 레슨, 없으면 None), status(강좌 학습 상태)
    """
    statuses = {}
    for lesson in course.lessons:
        rec = records.get(lesson.id)
        statuses[lesson.id] = lesson_status(lesson.requirements, rec) if rec else NOT_STARTED
    total = len(course.lessons)
    completed = sum(1 for s in statuses.values() if s == COMPLETED)
    next_lesson = next((lesson for lesson in course.lessons if statuses[lesson.id] != COMPLETED), None)
    if completed == total and total:
        status = "lessons_completed"     # 수료는 최종 평가(Phase 4)까지 끝나야 한다
    elif any(s != NOT_STARTED for s in statuses.values()):
        status = IN_PROGRESS
    else:
        status = NOT_STARTED
    return {"completed": completed, "total": total, "percent": completed * 100 // total if total else 0,
            "statuses": statuses, "next_lesson": next_lesson, "status": status}
