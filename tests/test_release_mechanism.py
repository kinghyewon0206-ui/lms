"""Release mechanism (found in the 2026-11-21 publication rehearsal).

1. Approving a lesson/quiz/final/capstone must also update the status that the course JSON mirrors for it, or the
   catalog refuses to load right after a release plan is applied.
2. Approving an assessment approves the questions it contains (there is no per-question approval screen).
3. Neither the mirrored statuses, the publication decision, nor per-question review_status may change the approval
   fingerprints, otherwise applying one approval would invalidate another.
"""
import copy
import json
import os

from econova import lesson_content
from tests.conftest import ROOT


def _course(cid="c01"):
    with open(os.path.join(ROOT, "content", "courses", f"{cid}.json"), encoding="utf-8") as f:
        return json.load(f)


def test_course_digest_ignores_publication_and_mirrored_statuses():
    data = _course("c09")
    base = lesson_content.course_digest(data)
    changed = copy.deepcopy(data)
    changed["status"] = "published"
    for lesson in changed["lessons"]:
        lesson["status"] = "published"
        lesson["material"]["status"] = "approved"
        lesson["quiz"]["status"] = "approved"
    changed["capstone"]["status"] = "approved"
    assert lesson_content.course_digest(changed) == base
    changed["description"] += " Changed."
    assert lesson_content.course_digest(changed) != base


def test_assessment_digest_ignores_question_review_status_but_not_content():
    with open(os.path.join(ROOT, "content", "assessments", "c01-final.json"), encoding="utf-8") as f:
        data = json.load(f)
    base = lesson_content.assessment_digest(data)
    approved = copy.deepcopy(data)
    for q in approved["questions"]:
        q["review_status"] = "approved"
    assert lesson_content.assessment_digest(approved) == base
    approved["questions"][0]["prompt"] += " (edited)"
    assert lesson_content.assessment_digest(approved) != base
