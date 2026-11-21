"""Whole-curriculum checks: 9 courses × 3 lessons drafted, c01–c08 end with a final assessment, c09 ends with the capstone.

Draft completeness is not approval. Under the competition policy (owner decision 2026-11-21) every course is open to students,
but no review record may be marked approved by these drafts.
"""
import json
import os

import pytest

from econova import capstone as cap
from econova import content

COURSES = [f"c0{n}" for n in range(1, 10)]
EXAM_COURSES = COURSES[:-1]


def _cat():
    return content.load_catalog(False)


def test_nine_courses_and_twenty_seven_lessons_are_drafted():
    cat = _cat()
    assert [c.id for c in cat.courses] == COURSES
    lessons = [lesson for c in cat.courses for lesson in c.lessons]
    assert len(lessons) == 27
    for lesson in lessons:
        assert lesson.content is not None, lesson.id
        assert lesson.content.review["status"] == "draft", lesson.id
        assert set(lesson.content.levels) == {"beginner", "intermediate", "advanced"}, lesson.id
        assert lesson.quiz_assessment is not None and len(lesson.quiz_assessment.questions) == 5, lesson.id
        assert lesson.quiz_assessment.review_status == "draft", lesson.id


def test_all_courses_are_open_but_nothing_is_approved():
    for course in _cat().courses:
        assert course.status == "published" and course.published, course.id       # open to students
        assert course.review_status == "draft", course.id                          # but never claimed reviewed
        for lesson in course.lessons:
            assert lesson.status == "published" and lesson.material_approved and lesson.quiz_approved, lesson.id
            assert not lesson.content.approved and not lesson.quiz_assessment.approved, lesson.id
        if course.final is not None:
            assert not course.final.approved and course.final.passing["status"] == "proposed", course.id


@pytest.mark.parametrize("course_id", EXAM_COURSES)
def test_exam_courses_end_with_a_ten_question_final(course_id):
    course = _cat().course(course_id)
    assert course.capstone is None
    final = course.final
    assert final is not None and len(final.questions) == 10 and final.max_attempts == 3
    assert final.passing["score_ratio"] == 0.7 and final.passing["status"] == "proposed"


# ------------------------------------------------------------- c09 capstone course
def test_c09_uses_capstone_completion_instead_of_a_final_exam():
    course = _cat().course("c09")
    assert course.final is None and course.final_assessment_status == "upcoming"
    assert not os.path.exists(os.path.join(content.CONTENT_DIR, "assessments", "c09-final.json"))
    defn = course.capstone
    assert defn is not None and defn.review_status == "draft" and not defn.approved
    assert defn.rubric["status"] == "provisional"
    assert course.capstone_ready                             # competition policy: the capstone is open without approval
    assert cap.completion_policy(course) == "capstone_self_directed"   # completion is recorded as self-directed, not approved
    lesson_ids = [lesson.id for lesson in course.lessons]
    assert {s["lesson_id"] for s in defn.steps} == set(lesson_ids)   # every lesson prepares at least one capstone step


def test_c09_capstone_step_mapping_is_unchanged():
    with open(os.path.join(content.CONTENT_DIR, "capstone", "c09.json"), encoding="utf-8") as f:
        data = json.load(f)
    assert [(s["id"], s["lesson_id"]) for s in data["steps"]] == [
        ("sdg", "c09-l1"), ("problem", "c09-l1"), ("concepts", "c09-l1"), ("stakeholders", "c09-l1"),
        ("incentives", "c09-l2"), ("solution", "c09-l2"), ("evaluation", "c09-l2"),
        ("proposal", "c09-l3"), ("reflection", "c09-l3")]


def _filled(defn):
    return {f["id"]: ("13" if f["type"] == "sdg" else "x" * max(f["min_chars"], 1)) for f in defn.fields}


def test_c09_completion_requires_lessons_submission_self_assessment_and_reflection():
    defn = _cat().course("c09").capstone
    sections = _filled(defn)
    versions = [{"version": 1, "sections": sections}]
    project = {"status": "submitted", "submitted_version": 1}
    scores = {c["id"]: 1 for c in defn.rubric["criteria"]}
    done = {"completed": 3, "total": 3}
    full = cap.completion_state(defn, done, project, versions, [{"version": 1, "scores": scores}])
    assert full["complete"] and full["submitted_version"] == 1

    assert not cap.completion_state(defn, {"completed": 2, "total": 3}, project, versions, [{"version": 1, "scores": scores}])["complete"]
    assert not cap.completion_state(defn, done, {"status": "draft"}, versions, [{"version": 1, "scores": scores}])["complete"]
    assert not cap.completion_state(defn, done, project, versions, [])["complete"]
    partial = dict(list(scores.items())[:-1])
    assert not cap.completion_state(defn, done, project, versions, [{"version": 1, "scores": partial}])["complete"]
    short = {**sections, "reflection": "too short"}
    assert not cap.completion_state(defn, done, project, [{"version": 1, "sections": short}], [{"version": 1, "scores": scores}])["complete"]


def test_c09_lessons_point_students_to_the_capstone():
    for lesson in _cat().course("c09").lessons:
        with open(os.path.join(content.CONTENT_DIR, "lessons", f"{lesson.id}.json"), encoding="utf-8") as f:
            assert "capstone" in f.read().lower(), lesson.id


# ------------------------------------------------------------- public files never carry answers
def test_public_assessment_files_have_no_answers():
    folder = os.path.join(content.CONTENT_DIR, "assessments")
    files = sorted(f for f in os.listdir(folder) if f.endswith(".json"))
    assert len(files) == 8 * 4 + 3                          # c01–c08: 3 quizzes + final; c09: 3 quizzes
    for name in files:
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            data = json.load(f)
        for q in data["questions"]:
            assert not {"answer", "explanation", "check", "tolerance_note"} & set(q), (name, q["id"])


def test_ai_checked_sources_are_not_shown_as_human_approved():
    """sources.json 'verified' means an AI (or author) opened the page; the admin screen must still treat it as awaiting human review."""
    from econova import admin_content
    targets = [t for t in admin_content.global_targets() if t.type == "source"]
    assert len(targets) >= 89
    for t in targets:
        state = admin_content.review_state(t, [])
        assert state["state"] == "draft", t.id
    assert admin_content.STATE_KO["verified"] == "AI-checked (not human-approved)"


def test_assessment_titles_follow_course_and_lesson_titles():
    for course in _cat().courses:
        for n, lesson in enumerate(course.lessons, start=1):
            assert lesson.quiz_assessment.title == f"Lesson {n} Quiz: {lesson.title}", lesson.id
        if course.final is not None:
            assert course.final.title == f"{course.title}: Final Assessment", course.id


def test_c07_us_financial_rules_are_labeled_wherever_they_appear():
    import re
    us_rule = re.compile(r"\b(FDIC|Regulation [A-Z]{1,2}|CFPB|Truth in Lending)\b")
    for n in (1, 2, 3):
        with open(os.path.join(content.CONTENT_DIR, "lessons", f"c07-l{n}.json"), encoding="utf-8") as f:
            doc = json.load(f)
        paragraphs = [p for lvl in doc["levels"].values() for s in lvl["sections"] for p in s["paragraphs"]]
        paragraphs += [p for r in doc.get("real_world_examples", []) for p in r["paragraphs"]]
        for p in paragraphs:
            if us_rule.search(p):
                assert "U.S." in p and "differ" in p, p[:120]


def test_c03_carbon_tax_numbers_are_framed_as_hypothetical_teaching_values():
    with open(os.path.join(content.CONTENT_DIR, "lessons", "c03-l3.json"), encoding="utf-8") as f:
        doc = json.load(f)
    text = json.dumps(doc)
    assert "not real carbon prices" in text and "teaching" in text
    assert all(e["problem"].startswith("Hypothetical example") for e in doc["worked_examples"])
