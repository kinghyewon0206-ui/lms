"""진도 계산 순수 함수: 완료 규칙(자료 확인 + 퀴즈 제출), 퀴즈 없음 ≠ 통과, 진도율."""
import datetime

import pytest

from econova import content, progress

NOW = datetime.datetime(2026, 11, 3, 12, 0, 0)
BOTH = ("material", "quiz")


def rec(**kw):
    return {**progress.empty_record("c", "c-l1"), **kw}


@pytest.mark.parametrize("record, expected", [
    (None, "not_started"),
    (rec(), "not_started"),
    (rec(material_reviewed=True), "in_progress"),
    (rec(quiz_submitted=True), "in_progress"),
    (rec(material_reviewed=True, quiz_submitted=True), "completed"),
])
def test_lesson_status_requires_material_and_quiz(record, expected):
    assert progress.lesson_status(BOTH, record) == expected


def test_missing_quiz_is_not_treated_as_passed():
    # 퀴즈 제출 기록이 없으면 자료를 아무리 확인해도 완료가 아니다. 점수가 있어도 제출 기록이 없으면 마찬가지
    assert progress.lesson_status(BOTH, rec(material_reviewed=True, quiz_score=100)) == "in_progress"


def test_configurable_requirements():
    assert progress.lesson_status(("material",), rec(material_reviewed=True)) == "completed"
    with pytest.raises(ValueError):
        progress.lesson_status((), rec())


def test_apply_event_sets_times_and_is_idempotent():
    later = NOW + datetime.timedelta(hours=1)
    r1 = progress.apply_event(rec(), BOTH, NOW, material_reviewed=True)
    assert (r1["status"], r1["material_reviewed_at"], r1["completed_at"]) == ("in_progress", NOW, None)
    r2 = progress.apply_event(r1, BOTH, later, material_reviewed=True)   # 다시 눌러도 처음 확인 시각을 유지
    assert r2["material_reviewed_at"] == NOW and r2["updated_at"] == later
    r3 = progress.apply_event(r2, BOTH, later, quiz_submission_id="sub-1")
    assert (r3["status"], r3["completed_at"], r3["quiz_submission_id"]) == ("completed", later, "sub-1")
    r4 = progress.apply_event(r3, BOTH, later + datetime.timedelta(hours=1), quiz_submission_id="sub-2")
    assert r4["completed_at"] == later   # 완료 시각은 처음 완료됐을 때
    assert r1["quiz_submitted"] is False  # 원래 기록은 바뀌지 않는다


def test_course_progress_is_deterministic():
    course = content.load_catalog(False).course("c02")
    empty = progress.course_progress(course, {})
    assert (empty["completed"], empty["total"], empty["percent"], empty["status"]) == (0, 3, 0, "not_started")
    assert empty["next_lesson"].id == "c02-l1"

    done = rec(material_reviewed=True, quiz_submitted=True)
    one = progress.course_progress(course, {"c02-l2": done, "c02-l1": rec(material_reviewed=True),
                                            "c01-l1": done})   # 다른 강좌 기록은 무시
    assert (one["completed"], one["percent"], one["status"]) == (1, 33, "in_progress")
    assert one["statuses"] == {"c02-l1": "in_progress", "c02-l2": "completed", "c02-l3": "not_started"}
    assert one["next_lesson"].id == "c02-l1"

    two = progress.course_progress(course, {"c02-l1": done, "c02-l2": done})
    assert (two["percent"], two["next_lesson"].id) == (66, "c02-l3")
    allp = progress.course_progress(course, {lid: done for lid in course.lesson_ids})
    assert (allp["percent"], allp["next_lesson"], allp["status"]) == (100, None, "lessons_completed")


def test_course_progress_uses_current_requirements_not_stored_status():
    # 저장된 status 가 'completed' 여도 지금 규칙(퀴즈 필수)을 만족하지 않으면 완료로 세지 않는다
    course = content.load_catalog(False).course("c02")
    forged = rec(material_reviewed=True, status="completed")
    assert progress.course_progress(course, {"c02-l1": forged})["completed"] == 0
