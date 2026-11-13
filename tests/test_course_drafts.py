"""Every course that has lesson materials must be a complete, unpublished, AI-drafted course with the agreed assessment rules.

Applies to c01–c05 today and to every later course as soon as its lesson files exist.
"""
import json
import os

import pytest

from econova import content

DRAFTED = ("c01", "c02", "c03", "c04", "c05")


def _catalog():
    return content.load_catalog(False)


@pytest.mark.parametrize("course_id", DRAFTED)
def test_drafted_course_is_complete_and_unpublished(course_id):
    course = _catalog().course(course_id)
    assert course.status == "coming_soon" and not course.published and course.content_version >= 2
    assert len(course.lessons) == 3
    for lesson in course.lessons:
        doc = lesson.content
        assert doc is not None and doc.review["status"] == "draft", lesson.id
        assert len(doc.objectives) >= 3, lesson.id
        assert {e["level"] for e in doc.worked_examples} == {"beginner", "intermediate", "advanced"}, lesson.id
        assert set(doc.sdg_case["sdgs"]) <= set(course.sdgs) | {2, 12} and len(doc.sdg_case["options"]) >= 2, lesson.id
        quiz = lesson.quiz_assessment
        assert quiz is not None and len(quiz.questions) == 5, lesson.id
        assert {q["type"] for q in quiz.questions} >= {"mcq", "numeric"}, lesson.id
    final = course.final
    assert len(final.questions) == 10 and final.max_attempts == 3
    assert final.passing["score_ratio"] == 0.7 and final.passing["status"] == "proposed"
    assert {q["lesson_id"] for q in final.questions} == {lesson.id for lesson in course.lessons}


@pytest.mark.parametrize("course_id", DRAFTED)
def test_mcq_answer_positions_are_balanced(course_id):
    """Answer positions are checked from the private keys in the QA step; publicly we check the choices are always a–d."""
    course = _catalog().course(course_id)
    for assessment in [*(lesson.quiz_assessment for lesson in course.lessons), course.final]:
        for q in assessment.questions:
            if q["type"] == "mcq":
                assert [c["id"] for c in q["choices"]] == ["a", "b", "c", "d"], q["id"]


@pytest.mark.parametrize("course_id", ("c04", "c05"))
def test_new_courses_cite_only_verified_sources(course_id):
    cat = _catalog()
    for lesson in cat.course(course_id).lessons:
        for sid in lesson.content.source_ids:
            assert cat.sources[sid].verified, (lesson.id, sid)


def test_c05_does_not_attach_the_price_quantity_simulator():
    """The supply-and-demand lab is labeled price/quantity; using it for wages and employment would mislead (owner decision 2026-11-13)."""
    assert all(not lesson.simulations for lesson in _catalog().course("c05").lessons)


def test_c05_labor_graphs_use_labor_market_axis_labels():
    graphs = []
    for n in (1, 2, 3):
        with open(os.path.join(content.CONTENT_DIR, "lessons", f"c05-l{n}.json"), encoding="utf-8") as f:
            graphs += json.load(f).get("graphs", [])
    assert graphs, "c05 should explain the labor market with lesson graphs"
    for g in graphs:
        assert "wage" in g["axis"]["p_label"].lower(), g["id"]
