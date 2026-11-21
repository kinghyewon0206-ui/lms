"""Numeric scoring policy R1–R5 (owner-approved 2026-11-14) and boundary behavior.

R1 exact integer answers with no rounding instruction → tolerance 0
R2 explicit rounding precision → tolerance = half of the last requested unit (boundaries inclusive, like the grader)
R3 decimal answers always carry a rounding instruction
R4 approximate methods only when the prompt says so explicitly ("… is accepted")
R5 no blanket ±1 for compound/discount calculations; they instead say "round only at the final step"

The always-run part checks the grader's boundary rule. The real-key part needs the private answer keys
(ECONOVA_REAL_PRIVATE_CONTENT_DIR, outside the repository) and never prints answers.
"""
import glob
import json
import os
import re

import pytest

from econova import grading
from tests.conftest import ROOT


# ------------------------------------------------------------- grader boundary rule (always runs)
def _num(answer, tol):
    return {"type": "numeric", "answer": answer, "tolerance": tol}


@pytest.mark.parametrize("raw, ok", [("2.9", True), ("2.85", True), ("2.95", True), ("2.94", True),
                                     ("2.84", False), ("2.96", False), ("3", False), ("", False), ("abc", False)])
def test_half_unit_tolerance_is_inclusive_at_both_boundaries(raw, ok):
    assert grading.is_correct(_num(2.9, 0.05), raw) is ok


@pytest.mark.parametrize("raw, ok", [("60", True), ("60.0", True), ("59.99", False), ("60.01", False), ("61", False)])
def test_exact_integer_policy_rejects_any_difference(raw, ok):
    assert grading.is_correct(_num(60, 0.0), raw) is ok


@pytest.mark.parametrize("raw, ok", [("-1.9", True), ("-2.0", True), ("-2", True), ("-1.95", True), ("-1.905", True),
                                     ("-1.8", False), ("-2.1", False), ("1.9", False)])
def test_explicit_two_method_range_accepts_only_both_methods(raw, ok):
    # R4 shape: exact result −1.9 and stated shortcut −2.0 → centre −1.95, half-width 0.05
    assert grading.is_correct(_num(-1.95, 0.05), raw) is ok


def test_thousands_separators_are_accepted_but_symbols_are_not():
    q = _num(20000, 0.0)
    assert grading.is_correct(q, "20000") and grading.is_correct(q, "20,000")
    assert not grading.is_correct(q, "$20,000")      # prompts say "Enter a number only"


# ------------------------------------------------------------- real answer keys (private, optional)
REAL_DIR = os.environ.get("ECONOVA_REAL_PRIVATE_CONTENT_DIR")
real = pytest.mark.skipif(not REAL_DIR, reason="Skipped: no real answer key folder (ECONOVA_REAL_PRIVATE_CONTENT_DIR)")
ROUNDING = [(r"nearest cent|two decimal places|2 decimal places|hundredth", 2), (r"three decimal places|thousandth", 3),
            (r"one decimal place|nearest tenth", 1), (r"nearest (whole )?(dollar|number|percent|year|unit)|whole number", 0)]
MULTISTEP = re.compile(r"compound|grows .* per year|midpoint|years? from now|discount", re.I)


def _numeric_questions():
    out = []
    files = sorted(glob.glob(os.path.join(ROOT, "content", "assessments", "*.json"))) + [os.path.join(ROOT, "content", "diagnostic.json")]
    for path in files:
        with open(path, encoding="utf-8") as f:
            public = json.load(f)
        aid = public["id"]
        with open(os.path.join(REAL_DIR, f"{aid}.answers.json"), encoding="utf-8") as f:
            keys = json.load(f)["questions"]
        for q in public["questions"]:
            if q["type"] == "numeric":
                out.append({**q, **{k: v for k, v in keys[q["id"]].items() if k in ("answer", "tolerance")}})
    return out


def _precision(prompt):
    return next((k for rx, k in ROUNDING if re.search(rx, prompt, re.I)), None)


@real
def test_every_numeric_question_follows_the_policy():
    qs = _numeric_questions()
    assert len(qs) >= 70
    problems = []
    for q in qs:
        k, a, tol, p = _precision(q["prompt"]), q["answer"], q["tolerance"], q["prompt"]
        explicit_two_methods = "is accepted" in p
        if explicit_two_methods:                                          # R4
            continue
        if k is not None:                                                 # R2
            if abs(tol - 0.5 * 10 ** (-k)) > 1e-12:
                problems.append((q["id"], "R2 tolerance"))
            if MULTISTEP.search(p) and not re.search(r"round only at the final step", p, re.I):
                problems.append((q["id"], "R5 final-step instruction missing"))
        elif abs(a - round(a)) < 1e-12:                                   # R1
            if tol != 0:
                problems.append((q["id"], "R1 tolerance"))
        else:                                                             # R3
            problems.append((q["id"], "R3 rounding instruction missing"))
    assert not problems, problems


@real
def test_correct_answers_and_boundaries_are_accepted_and_neighbors_rejected():
    for q in _numeric_questions():
        a, tol = q["answer"], q["tolerance"]
        assert grading.is_correct(q, repr(a)), q["id"]
        assert grading.is_correct(q, repr(a + tol)) and grading.is_correct(q, repr(a - tol)), q["id"]
        k = _precision(q["prompt"])
        step = 10 ** (-k) if k is not None else 0.01
        assert not grading.is_correct(q, repr(a + tol + step)) and not grading.is_correct(q, repr(a - tol - step)), q["id"]


@real
def test_common_wrong_methods_are_rejected():
    path = os.environ.get("ECONOVA_WRONG_METHODS_FILE") or os.path.join(os.path.expanduser("~/econova-private/tools"), "wrong_methods.json")
    if not os.path.exists(path):
        pytest.skip("No private wrong-method list")
    with open(path, encoding="utf-8") as f:
        wrong = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    qs = {q["id"]: q for q in _numeric_questions()}
    for qid, values in wrong.items():
        for v in values:
            assert not grading.is_correct(qs[qid], repr(v)), (qid, "a wrong-method value is accepted")
