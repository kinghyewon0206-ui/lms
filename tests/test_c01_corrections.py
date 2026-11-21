"""c01 correction pass (2026-11-21) and the shared source-label fix.

- c01 defects found during human-review preparation must not come back.
- Source labels: 'verified' in sources.json only means the link was checked (AI or author). Only a human approval in the
  review database may show the green "Teacher-verified source" label, on every course.
- Inactive placeholders and empty graph sections are hidden from lesson pages.
"""
import json
import os
import re

import pytest

from tests.conftest import CSRF, ROOT, set_csrf
from tests.test_phase7 import _make_admin

REAL_DIR = os.environ.get("ECONOVA_REAL_PRIVATE_CONTENT_DIR")


def _lesson(lid):
    with open(os.path.join(ROOT, "content", "lessons", f"{lid}.json"), encoding="utf-8") as f:
        return json.load(f)


def _assessment(aid):
    with open(os.path.join(ROOT, "content", "assessments", f"{aid}.json"), encoding="utf-8") as f:
        return json.load(f)


def _texts(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k not in ("review", "check"):
                yield from _texts(v)
    elif isinstance(o, list):
        for v in o:
            yield from _texts(v)


ALL_LESSONS = [f"c0{c}-l{n}" for c in range(1, 10) for n in (1, 2, 3)]


# ------------------------------------------------------------------ c01 lesson defects
def test_no_lesson_says_any_cost_difference_causes_overconsumption():
    bad = re.compile(r"(differs? from|is different from)[^.]{0,60}(social|society)[^.]{0,80}(more than|overconsum)", re.I)
    bad2 = re.compile(r"when the two differ, people use more", re.I)
    hits = [(lid, t[:80]) for lid in ALL_LESSONS for t in _texts(_lesson(lid)) if bad.search(t) or bad2.search(t)]
    assert not hits, hits


def test_c01_l3_uses_marginal_social_vs_private_cost():
    l3 = _lesson("c01-l3")
    adv = " ".join(l3["levels"]["advanced"]["sections"][1]["paragraphs"])
    assert "marginal social cost" in adv.lower() and "marginal private cost" in adv.lower()
    assert "private benefit equals private cost" not in adv
    assert "higher than" in l3["concepts"][2]["definition"] and "higher than" in l3["key_takeaways"][1]


def test_c01_bag_fee_example_has_one_answer_per_part():
    we = _lesson("c01-l3")["worked_examples"][2]
    assert "(1)" in we["problem"] and "(2)" in we["problem"] and "additional fee" in we["problem"]
    assert we["check"]["expected"] == 3 and "2 + 3 = 5" in we["answer"]


def test_c01_budget_constraint_states_when_the_trade_off_binds():
    adv = _lesson("c01-l1")["levels"]["advanced"]["sections"][0]["paragraphs"][0]
    assert "When the whole budget is already spent" in adv and "still unspent" in adv


def test_c01_economics_definition_is_not_circular():
    beginner = " ".join(_lesson("c01-l1")["levels"]["beginner"]["sections"][0]["paragraphs"])
    assert "when everyone has to choose" not in beginner and "scarce resources" in beginner


def test_c01_marginal_rule_is_consistent():
    l2 = _lesson("c01-l2")
    text = " ".join(_texts(l2))
    assert "MB ≥ MC" not in text and "indifferent" in l2["concepts"][3]["definition"]


def test_c01_price_ratio_example_explains_indivisible_units():
    we = _lesson("c01-l1")["worked_examples"][2]
    assert "rate of exchange" in we["answer"] and "gives up 3 packs" in we["answer"]


# ------------------------------------------------------------------ c01 assessment defects (public files)
def test_c01_final_q6_has_no_contradictory_assumption():
    q6 = next(q for q in _assessment("c01-final")["questions"] if q["id"] == "c01-final-q6")
    assert "no other use" not in q6["prompt"] and "other school needs" in q6["prompt"]


def test_c01_deposit_question_matches_its_mechanism():
    q4 = next(q for q in _assessment("c01-l3-quiz")["questions"] if q["id"] == "c01-l3-q4")
    assert "disposable" in q4["prompt"]
    assert not any("reuse" in c["text"] for c in q4["choices"])


def test_c01_percentage_question_says_how_to_enter_percent():
    q5 = next(q for q in _assessment("c01-l1-quiz")["questions"] if q["id"] == "c01-l1-q5")
    assert "enter 25 for 25%" in q5["prompt"]


def test_c01_l3_q1_is_not_copied_from_the_lesson():
    q1 = next(q for q in _assessment("c01-l3-quiz")["questions"] if q["id"] == "c01-l3-q1")
    lesson = " ".join(_texts(_lesson("c01-l3")))
    assert "bakery" in q1["prompt"] and q1["prompt"] not in lesson


@pytest.mark.skipif(not REAL_DIR, reason="Skipped: no real answer key folder (ECONOVA_REAL_PRIVATE_CONTENT_DIR)")
def test_corrected_c01_keys_match_the_new_questions():
    from econova import grading, private_content  # noqa: F401
    def keys(aid):
        with open(os.path.join(REAL_DIR, f"{aid}.answers.json"), encoding="utf-8") as f:
            return json.load(f)["questions"]
    fin, l3 = keys("c01-final"), keys("c01-l3-quiz")
    assert fin["c01-final-q6"]["answer"] == "a" and fin["c01-final-q9"]["answer"] == "b"
    assert l3["c01-l3-q1"]["answer"] == "a" and l3["c01-l3-q4"]["answer"] == "c"
    for aid in ("c01-l1-quiz", "c01-l2-quiz", "c01-l3-quiz", "c01-final"):
        public = {q["id"]: q for q in _assessment(aid)["questions"]}
        for qid, k in keys(aid).items():
            q = public[qid]
            if q["type"] == "mcq":
                assert k["answer"] in {c["id"] for c in q["choices"]}, qid


# ------------------------------------------------------------------ shared source labels (all courses)
def test_admin_preview_never_shows_ai_checked_sources_as_approved(app, client):
    _make_admin(app, client)
    for lid in ALL_LESSONS:
        html = client.get(f"/preview/{lid.split('-')[0]}/{lid}?level=beginner").get_data(as_text=True)
        sources = html.split('id="sec-sources"', 1)[1]
        assert "Source verified" not in sources and "Teacher-verified source" not in sources, lid
        n = sources.count("<li id=\"src-")
        assert n and sources.count("AI-checked (not human-approved)") == n and sources.count("Human verification pending") == n, lid


def test_human_approval_of_a_source_shows_the_teacher_verified_label(app, client):
    _make_admin(app, client)
    sid = _lesson("c01-l1")["source_ids"][0]
    page = client.get(f"/admin/content/source/{sid}").get_data(as_text=True)
    digest = re.search(r'name="content_digest" value="([^"]+)"', page).group(1)
    set_csrf(client)
    for decision, comment in (("start_review", ""), ("approve", "Opened and checked the page myself.")):
        client.post(f"/admin/content/source/{sid}/review", data={"csrf_token": CSRF, "content_digest": digest, "decision": decision,
                                                                   "comment": comment, "confirm_reviewed": "1"})
    html = client.get("/preview/c01/c01-l1?level=beginner").get_data(as_text=True).split('id="sec-sources"', 1)[1]
    assert html.count("Teacher-verified source") == 1
    assert html.count("AI-checked (not human-approved)") == html.count("<li id=\"src-") - 1


def test_student_lesson_uses_a_neutral_label_for_link_checked_sources(logged_in, fixtures_on):
    logged_in.post("/courses/dev-f2/enroll", data={"csrf_token": CSRF, "difficulty": "beginner"})
    html = logged_in.get("/learn/dev-f2/dev-f2-l1").get_data(as_text=True)
    assert "Source verified" not in html and "pill pill-done\">Teacher-verified" not in html


# ------------------------------------------------------------------ placeholders
def test_empty_graph_and_inactive_sections_are_hidden(app, client):
    _make_admin(app, client)
    html = client.get("/preview/c01/c01-l1?level=beginner").get_data(as_text=True)   # c01 has no graphs
    assert 'id="sec-visual"' not in html and "This lesson has no graphs." not in html
    assert "Reflection and feedback" not in html and "Coming later" not in html
    assert "Verified material" not in html and "Lesson material · Key concepts" in html
    with_graph = client.get("/preview/c02/c02-l1?level=beginner").get_data(as_text=True)
    assert 'id="sec-visual"' in with_graph
