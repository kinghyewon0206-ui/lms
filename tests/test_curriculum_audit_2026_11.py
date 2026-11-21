"""Comprehensive curriculum audit (2026-11-21): corrections that must not come back.

Every course was re-audited by an AI editor and checked by a separate AI reviewer who re-solved every question.
This is AI review, not human approval: all content stays draft. These tests pin the economic corrections and the
cross-course terminology decisions (see docs/content/review/changes/<course>.md).
"""
import glob
import json
import os
import re

from tests.conftest import ROOT

CONTENT = os.path.join(ROOT, "content")
COURSES = [f"c0{n}" for n in range(1, 10)]


def _load(*parts):
    with open(os.path.join(CONTENT, *parts), encoding="utf-8") as f:
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


def _lesson_text(lid):
    return " ".join(_texts(_load("lessons", f"{lid}.json")))


def _all_student_text():
    files = glob.glob(os.path.join(CONTENT, "lessons", "c0*.json")) + glob.glob(os.path.join(CONTENT, "assessments", "c0*.json"))
    files += [os.path.join(CONTENT, "diagnostic.json"), os.path.join(CONTENT, "capstone", "c09.json")]
    out = []
    for p in files:
        with open(p, encoding="utf-8") as f:
            out.append((os.path.basename(p), " ".join(_texts(json.load(f)))))
    return out


# ------------------------------------------------------------------ shared terminology decisions
def test_one_marginal_rule_everywhere():
    hits = [name for name, text in _all_student_text() if re.search(r"MB\s*(≥|>=)\s*MC", text)]
    assert not hits, hits


def test_slope_is_never_called_elasticity_and_midpoint_is_not_called_exact():
    for name, text in _all_student_text():
        assert not re.search(r"slopes? \(elasticit", text, re.I), name
        assert not re.search(r"exact[^.]{0,40}midpoint|midpoint[^.]{0,40}\bexact\b", text, re.I), name


def test_real_value_formula_divides_by_index_over_100():
    for name, text in _all_student_text():
        assert not re.search(r"÷ (the )?price index(?! ÷)", text), name


def test_deposits_use_apy_and_credit_uses_apr():
    text = _lesson_text("c07-l2")
    assert "compare savings accounts by APY and loans by APR" in text
    for name, t in _all_student_text():
        assert not re.search(r"(savings? account|deposit)s?[^.]{0,40}\bAPR of\b", t), name


# ------------------------------------------------------------------ course-specific corrections
def test_c02_deadweight_loss_states_its_allocation_assumption():
    assert "value them most" in _lesson_text("c02-l2")
    q7 = next(q for q in _load("assessments", "c02-final.json")["questions"] if q["id"] == "c02-final-q7")
    assert "value them most" in q7["prompt"] and "openstax-pe3-3-5" in q7.get("source_ids", [])


def test_c03_property_rights_taught_and_private_surplus_labeled():
    l3 = _load("lessons", "c03-l3.json")
    assert any(c["id"] == "property_rights" for c in l3["concepts"])
    text = _lesson_text("c03-l3")
    assert "lost private surplus" in text and "Q₀" in text
    l1 = _lesson_text("c03-l1")
    assert re.search(r"marginal benefit[^.]{0,80}marginal cost", l1)


def test_c04_deflator_is_not_a_fixed_basket():
    assert "actual output" in _lesson_text("c04-l3")


def test_c05_monopsony_floor_conditions():
    text = _lesson_text("c05-l3")
    assert "does not bind" in text and "In a competitive labor market" in text


def test_c06_average_rate_condition():
    assert "rise from bracket to bracket" in _lesson_text("c06-l2")


def test_c08_large_importer_terms_of_trade():
    assert "terms-of-trade gain" in _lesson_text("c08-l1")


def test_c09_capstone_structure_and_rubric_status_unchanged():
    cap = _load("capstone", "c09.json")
    assert len(cap["steps"]) == 9 and cap["rubric"]["status"] == "provisional"
    assert sum(c["weight"] for c in cap["rubric"]["criteria"]) == 100
    assert "× 100" in _lesson_text("c09-l1")


# ------------------------------------------------------------------ review status and provenance
def test_audit_edits_are_marked_as_ai_work_and_nothing_is_approved():
    for p in glob.glob(os.path.join(CONTENT, "lessons", "c0*.json")) + glob.glob(os.path.join(CONTENT, "assessments", "c0*.json")):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        assert d["review"]["status"] == "draft", p
        for h in d["review"]["history"]:
            if h.get("at") == "2026-11-21":
                assert h["by"] == "Claude Code (AI)" and "not reviewed or approved by a human" in h["note"].lower(), p
    for cid in COURSES:
        c = _load("courses", f"{cid}.json")
        assert c["status"] == "published", cid   # competition policy: open to students; review records above stay draft
