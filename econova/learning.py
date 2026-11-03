"""ECONOVA 학습 규칙: 수강 신청, 접근 권한, 진도 이벤트, 화면에 넘길 요약.

라우트(econova/web.py)는 이 모듈만 부르고, 규칙은 여기 한곳에 둔다.
"""
from econova import content, progress, storage

DEFAULT_DIFFICULTY = "beginner"


class LearningError(Exception):
    """학습 규칙 위반. code 로 이유를 구분한다."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


# 레슨 페이지의 구역. 지금은 틀만 있고, 각 기능이 들어올 단계를 함께 적어 둔다.
LESSON_SECTIONS = (
    ("objectives", "학습 목표", None),
    ("concept", "검증된 개념 설명", "Phase 3"),
    ("leveled", "난이도별 학습 내용", "Phase 3"),
    ("examples", "풀이 예제", "Phase 3"),
    ("visual", "경제 그래프", "Phase 5"),
    ("sdg_case", "SDG 사례", "Phase 3"),
    ("simulation", "인터랙티브 시뮬레이션", "Phase 5"),
    ("tutor", "AI 튜터", "Phase 6"),
    ("quiz", "형성 퀴즈", "Phase 4"),
    ("reflection", "되돌아보기와 피드백", "Phase 4"),
)


def catalog():
    return content.get_catalog()


def visible_course(course_id):
    """카탈로그에 보이는 강좌(coming_soon·published)만. 없거나 draft·archived 면 None."""
    course = catalog().course(course_id)
    return course if course and course.status in content.VISIBLE_STATUSES else None


def enroll(user_id, course, difficulty=DEFAULT_DIFFICULTY):
    """수강 신청. 공개된 강좌만 가능. 새로 신청했으면 True, 이미 수강 중이면 False."""
    if not course.published:
        raise LearningError("not_published", "아직 공개되지 않은 강좌라 수강 신청할 수 없어요.")
    if difficulty not in content.DIFFICULTIES:
        raise LearningError("bad_difficulty", "난이도를 다시 골라 주세요.")
    return storage.enroll_course(user_id, course.id, difficulty, course.content_version)


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


def record_quiz_submission(user_id, course, lesson, assessment_id, submission_id):
    """필수 형성 퀴즈 제출을 진도에 반영한다.

    Phase 2 에는 이 함수를 부르는 화면이 없다. Phase 4 의 퀴즈 기능이 실제 제출을 저장한 뒤 이 함수를 부른다.
    지금은 테스트가 '올바른 제출 이벤트'를 흉내 낼 때만 쓴다. 승인된 퀴즈의 id 와 맞는 제출만 받는다.
    """
    if "quiz" not in lesson.requirements or not lesson.quiz_approved:
        raise LearningError("unavailable", "이 레슨에는 제출할 수 있는 필수 퀴즈가 없어요.")
    if assessment_id != lesson.quiz.get("assessment_id"):
        raise LearningError("wrong_assessment", "이 레슨의 퀴즈가 아니에요.")
    if not str(submission_id or "").strip():
        raise LearningError("invalid_submission", "퀴즈 제출 기록이 올바르지 않아요.")
    return storage.update_lesson_progress(user_id, course.id, lesson.id, lesson.requirements,
                                          quiz_submission_id=str(submission_id).strip())


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
