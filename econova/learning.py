"""ECONOVA 학습 규칙: 수강 신청, 접근 권한, 진도 이벤트, 화면에 넘길 요약.

라우트(econova/web.py)는 이 모듈만 부르고, 규칙은 여기 한곳에 둔다.
"""
from econova import content, grading, private_content, progress, quotas, storage

DEFAULT_DIFFICULTY = "beginner"


class LearningError(Exception):
    """학습 규칙 위반. code 로 이유를 구분한다."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


# 레슨 페이지의 구역. 검증 자료가 있는 구역과, 이후 단계에서 들어올 구역(단계 표시)을 구분한다.
LESSON_SECTIONS = (
    ("objectives", "학습 목표", None),
    ("concept", "검증된 개념 설명", None),
    ("leveled", "난이도별 학습 내용", None),
    ("examples", "풀이 예제", None),
    ("visual", "경제 그래프", None),
    ("real_world", "실제 경제 사례", None),
    ("sdg_case", "SDG 사례와 정책 상충관계", None),
    ("simulation", "인터랙티브 시뮬레이션", None),
    ("tutor", "AI 튜터", None),
    ("quiz", "형성 퀴즈", None),
    ("reflection", "되돌아보기와 피드백", "이후 단계"),
    ("takeaways", "핵심 정리", None),
    ("sources", "출처", None),
)


def catalog():
    return content.get_catalog()


def visible_course(course_id):
    """카탈로그에 보이는 강좌(coming_soon·published)만. 없거나 draft·archived 면 None."""
    course = catalog().course(course_id)
    return course if course and course.status in content.VISIBLE_STATUSES else None


def latest_diagnostic(user_id):
    """가장 최근 진단평가 결과 (없으면 None). 난이도 추천의 근거."""
    attempts = storage.list_diagnostic_attempts(user_id)
    return attempts[0] if attempts else None


def enroll(user_id, course, difficulty=DEFAULT_DIFFICULTY, recommended=None):
    """수강 신청. 공개된 강좌만 가능. 새로 신청했으면 True, 이미 수강 중이면 False.
    학생이 고른 난이도가 진단평가 추천과 같으면 출처를 diagnostic 으로, 다르면 manual 로 기록한다 (추천은 강제가 아니다)."""
    if not course.published:
        raise LearningError("not_published", "아직 공개되지 않은 강좌라 수강 신청할 수 없어요.")
    if difficulty not in content.DIFFICULTIES:
        raise LearningError("bad_difficulty", "난이도를 다시 골라 주세요.")
    source = "diagnostic" if recommended and difficulty == recommended else "manual"
    return storage.enroll_course(user_id, course.id, difficulty, course.content_version, difficulty_source=source)


def change_difficulty(user_id, course, difficulty):
    if difficulty not in content.DIFFICULTIES:
        raise LearningError("bad_difficulty", "난이도를 다시 골라 주세요.")
    if not storage.set_enrollment_difficulty(user_id, course.id, difficulty):
        raise LearningError("not_enrolled", "수강 중인 강좌만 난이도를 바꿀 수 있어요.")


def course_state(user_id, course):
    """강좌 상세용: 내 수강 정보와 진도. 수강 전이면 enrollment 가 None."""
    enrollment = storage.get_enrollment(user_id, course.id)
    records = storage.list_lesson_progress(user_id, course.id) if enrollment else {}
    return {"enrollment": enrollment, "progress": progress.course_progress(course, records), "records": records}


def lesson_access(user_id, course_id, lesson_id):
    """레슨을 볼 수 있는지 검사하고 (course, lesson, enrollment) 를 돌려준다.
    순서: 강좌가 보이는가 → 레슨이 이 강좌 것인가 → 강좌가 공개됐는가 → 본인이 수강 중인가."""
    course = visible_course(course_id)
    lesson = course.lesson(lesson_id) if course else None
    if lesson is None:
        raise LearningError("not_found", "레슨을 찾을 수 없어요.")
    if not course.published or lesson.status != "published":
        raise LearningError("not_published", "아직 공개되지 않은 레슨이에요.")
    enrollment = storage.get_enrollment(user_id, course.id)
    if enrollment is None:
        raise LearningError("not_enrolled", "먼저 수강 신청을 해 주세요.")
    return course, lesson, enrollment


def mark_material_reviewed(user_id, course, lesson):
    """필수 학습자료 확인. 승인된 자료가 있는 레슨에서만 기록한다."""
    if "material" not in lesson.requirements or not lesson.material_approved:
        raise LearningError("unavailable", "확인할 승인된 학습자료가 없어요.")
    return storage.update_lesson_progress(user_id, course.id, lesson.id, lesson.requirements, material_reviewed=True)


def record_quiz_submission(user_id, course, lesson, attempt_id):
    """저장된 형성 퀴즈 응시 기록을 근거로 레슨 진도에 '퀴즈 제출'을 반영한다.

    화면이 보낸 완료 표시는 믿지 않는다. 서버에 저장된 본인의 응시 기록이 이 레슨의 승인된 퀴즈와 맞을 때만 반영하고,
    점수(ratio)는 완료 판정과 별개로 최고 점수만 남긴다.
    """
    if "quiz" not in lesson.requirements or not lesson.quiz_approved:
        raise LearningError("unavailable", "이 레슨에는 제출할 수 있는 필수 퀴즈가 없어요.")
    attempt = storage.get_assessment_attempt(user_id, attempt_id)
    if attempt is None:
        raise LearningError("invalid_submission", "퀴즈 제출 기록을 찾을 수 없어요.")
    if (attempt["kind"] != "lesson_quiz" or attempt["assessment_id"] != lesson.quiz_assessment.id
            or attempt["lesson_id"] != lesson.id or attempt["course_id"] != course.id):
        raise LearningError("wrong_assessment", "이 레슨의 퀴즈가 아니에요.")
    return storage.update_lesson_progress(user_id, course.id, lesson.id, lesson.requirements,
                                          quiz_submission_id=attempt["id"], quiz_score=attempt["ratio"],
                                          event_time=attempt["created_at"])


# ---------------------------------------------------------------- 퀴즈·최종 평가
def quiz_access(user_id, course_id, lesson_id):
    """형성 퀴즈를 볼 수 있는지: 레슨 접근 규칙 + 승인된 퀴즈가 있는가."""
    course, lesson, enrollment = lesson_access(user_id, course_id, lesson_id)
    if "quiz" not in lesson.requirements or not lesson.quiz_approved:
        raise LearningError("not_found", "이 레슨에는 형성 퀴즈가 없어요.")
    return course, lesson, enrollment, lesson.quiz_assessment


def final_access(user_id, course_id):
    """최종 평가: 공개된 강좌, 본인 수강, 승인된 최종 평가, 그리고 모든 레슨 완료 후에만 열린다."""
    course = visible_course(course_id)
    if course is None:
        raise LearningError("not_found", "강좌를 찾을 수 없어요.")
    if not course.published or not course.final_ready:
        raise LearningError("not_published", "아직 공개되지 않은 최종 평가예요.")
    enrollment = storage.get_enrollment(user_id, course.id)
    if enrollment is None:
        raise LearningError("not_enrolled", "먼저 수강 신청을 해 주세요.")
    prog = progress.course_progress(course, storage.list_lesson_progress(user_id, course.id))
    if prog["completed"] < prog["total"]:
        raise LearningError("locked", f"레슨을 모두 완료하면 최종 평가가 열려요. (현재 {prog['completed']}/{prog['total']})")
    return course, enrollment, course.final


def require_keys(assessment):
    """정답 키 없이 응시·채점하지 않는다 (fail closed). 이미 저장된 응시 기록의 복구는 키 없이도 된다."""
    if not assessment.answer_keys:
        raise private_content.KeysUnavailable(f"{assessment.id}: {assessment.keys_problem}")


def attempts_left(user_id, assessment):
    """남은 응시 횟수. 제한이 없으면 None."""
    if not assessment.max_attempts:
        return None
    used = len(storage.list_assessment_attempts(user_id, assessment_id=assessment.id))
    return max(0, assessment.max_attempts - used)


def answers_revealable(user_id, attempt, assessment):
    """결과 화면에 정답·해설을 보여줘도 되는가. 형성 퀴즈는 제출 뒤 바로. 최종 평가는 같은 문항으로 다시 응시할 수 있으므로,
    합격했거나 남은 응시 기회가 없을 때만 보여준다 (재응시 전에 정답을 보고 합격하는 것을 막는다)."""
    if attempt["kind"] != "final":
        return True
    if any(a.get("passed") for a in storage.list_assessment_attempts(user_id, assessment_id=attempt["assessment_id"])):
        return True
    return assessment is not None and attempts_left(user_id, assessment) == 0


def best_attempt(attempts):
    """가장 높은 점수의 응시 (같으면 먼저 낸 것)."""
    best = None
    for a in sorted(attempts, key=lambda a: (a["created_at"] or 0, a["id"])):
        if best is None or a["ratio"] > best["ratio"]:
            best = a
    return best


def reconcile_attempt(user_id, course, assessment, attempt, lesson=None):
    """저장된 응시 기록이 진도·수료에 반영되도록 맞춘다. 몇 번 실행해도 결과가 같다(멱등).

    응시 기록 저장 뒤 진도 반영이 실패했더라도, 같은 제출을 다시 보내면 여기서 마저 반영된다.
    기록이 이 평가의 것이 아니면 아무것도 하지 않는다. 시각은 응시의 제출 시각을 쓴다."""
    if attempt is None or attempt["assessment_id"] != assessment.id or attempt["course_id"] != course.id:
        return
    if lesson is not None:
        if attempt["kind"] == "lesson_quiz" and attempt["lesson_id"] == lesson.id:
            record_quiz_submission(user_id, course, lesson, attempt["id"])
    elif attempt["kind"] == "final" and attempt["passed"] and assessment.passing_usable(course.fixture):
        policy = "approved" if assessment.passing["status"] == "approved" else "dev_provisional"
        storage.complete_enrollment(user_id, course.id, attempt["id"], policy, at=attempt["created_at"])


def submit_assessment(user_id, course, assessment, answers, token, lesson=None):
    """제출을 채점·저장하고 (attempt_id, 새로 저장됐는가) 를 돌려준다.
    같은 토큰으로 다시 제출되면 새로 저장하지 않고, 저장된 기록을 근거로 진도·수료 반영만 다시 맞춘다 (멱등)."""
    existing = storage.find_attempt_by_token(user_id, token)
    if existing is not None:
        reconcile_attempt(user_id, course, assessment, existing, lesson)
        return existing["id"], False
    left = attempts_left(user_id, assessment)
    if left == 0:
        raise LearningError("no_attempts", "응시할 수 있는 횟수를 모두 사용했어요.")
    if not assessment.max_attempts:   # 재응시 무제한 형성 퀴즈: 아주 넉넉한 저장 한도만 둔다 (기존 기록은 지우지 않음)
        try:
            quotas.check("QUIZ_ATTEMPTS", len(storage.list_assessment_attempts(user_id, assessment_id=assessment.id)))
        except quotas.QuotaExceeded as exc:
            raise LearningError("no_attempts", exc.message)
    require_keys(assessment)
    result = grading.grade(assessment.questions, answers)
    passed = result["ratio"] >= assessment.passing["score_ratio"] - 1e-9 if assessment.is_final else None
    record = {"course_id": course.id, "lesson_id": lesson.id if lesson else None, "assessment_id": assessment.id,
              "assessment_version": assessment.version, "course_content_version": course.content_version,
              "kind": assessment.kind, "score": result["score"], "max_score": result["max_score"], "ratio": result["ratio"],
              "passed": passed, "answers": {k: str(v)[:grading.MAX_ANSWER_LENGTH] for k, v in (answers or {}).items()
                                            if assessment.question(k)},
              "results": [{**r, "version": assessment.question(r["id"])["version"]} for r in result["results"]],
              "passing": dict(assessment.passing) if assessment.is_final else None}
    try:
        attempt_id = storage.save_assessment_attempt(user_id, record, token, max_attempts=assessment.max_attempts)
        created = True
    except storage.DuplicateSubmission as dup:   # 동시에 같은 토큰으로 두 번 저장하려 한 경우
        attempt_id, created = dup.attempt_id, False
    except storage.AttemptLimitReached:          # 다른 토큰으로 동시에 제출해 횟수를 넘으려 한 경우
        raise LearningError("no_attempts", "응시할 수 있는 횟수를 모두 사용했어요.")
    reconcile_attempt(user_id, course, assessment, storage.get_assessment_attempt(user_id, attempt_id), lesson)
    return attempt_id, created


def completion_summary(user_id, course):
    """강좌 수료 요약: 레슨별 진도·퀴즈 최고 점수, 최종 평가 최고 결과, 수료 여부."""
    enrollment = storage.get_enrollment(user_id, course.id)
    records = storage.list_lesson_progress(user_id, course.id) if enrollment else {}
    prog = progress.course_progress(course, records)
    finals = storage.list_assessment_attempts(user_id, course_id=course.id, assessment_id=course.final.id) \
        if enrollment and course.final else []
    return {"enrollment": enrollment, "progress": prog, "records": records, "final_attempts": finals,
            "final_best": best_attempt(finals),
            "completed": bool(enrollment and enrollment["status"] == "completed")}


def dashboard(user_id):
    """대시보드용: 수강 강좌 카드들과 합계. 강좌마다 진도를 따로 계산한다."""
    cat = catalog()
    all_records = storage.list_all_lesson_progress(user_id)
    cards = []
    for enrollment in storage.list_enrollments(user_id):
        course = cat.course(enrollment["course_id"])
        if course is None:   # 강좌 정보가 사라짐 (예: 개발용 테스트 강좌를 끈 경우). 기록은 지우지 않고 표시만 한다
            cards.append({"enrollment": enrollment, "course": None, "progress": None, "available": False})
            continue
        prog = progress.course_progress(course, all_records.get(course.id, {}))
        cards.append({"enrollment": enrollment, "course": course, "progress": prog, "available": course.published})
    known = [c for c in cards if c["course"]]
    return {
        "cards": cards,
        "enrolled": len(cards),
        "completed_lessons": sum(c["progress"]["completed"] for c in known),
        "total_lessons": sum(c["progress"]["total"] for c in known),
    }
