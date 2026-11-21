"""Economics Lab models 3–9: formulas checked by hand, economic edge cases, input validation,
and Python/JavaScript agreement on random inputs."""
import json
import math
import os
import random
import shutil
import subprocess

import pytest

from econova import lab_models as L
from tests.conftest import ROOT

NODE = shutil.which("node")


def run(sim_id, **over):
    return L.run(sim_id, {**L.defaults(sim_id), **over})[1]


def close(a, b, tol=1e-6):
    return math.isclose(a, b, abs_tol=tol)


# ------------------------------------------------------------------ registry
def test_seven_new_models_with_complete_specs():
    assert L.ORDER == tuple(L.SPECS) and len(L.ORDER) == 7
    courses = {s["course_id"] for s in L.SPECS.values()}
    assert courses == {"c01", "c04", "c05", "c06", "c07", "c08", "c09"}
    for sid, spec in L.SPECS.items():
        names = [i["name"] for i in spec["inputs"]]
        assert len(names) == len(set(names)) >= 5, sid
        assert spec["presets"] and spec["assumptions"] and spec["rows"], sid
        for p in spec["presets"]:
            assert set(p["values"]) == set(names), (sid, p["label"])
            L.run(sid, p["values"])   # every preset is a valid input
        for i in spec["inputs"]:
            if i["kind"] == "number":
                assert i["min"] <= i["default"] <= i["max"] and i["step"] > 0, (sid, i["name"])
        _, res = L.run(sid, L.defaults(sid))
        assert L.result_rows(sid, res), sid


# ------------------------------------------------------------------ LAB 01
def test_opportunity_cost_budget_line():
    r = run("opportunity-cost")   # budget 120, books $12, tickets $8, 4 books + 6 tickets
    assert r["status"] == "inside" and r["spending"] == 96 and r["leftover"] == 24
    assert r["max_x"] == 10 and r["max_y"] == 15 and r["oc_x_in_y"] == 1.5 and close(r["oc_y_in_x"], 2 / 3)
    assert r["forgone_y"] == 6 and r["max_y_given_x"] == 9   # (120 - 48) / 8
    on = run("opportunity-cost", x=4, y=9)
    assert on["status"] == "on_line" and on["leftover"] == 0
    over = run("opportunity-cost", x=8, y=6)
    assert over["status"] == "infeasible" and over["over_budget"] == 24 and over["leftover"] == 0
    # A more expensive book raises its opportunity cost in tickets
    assert run("opportunity-cost", px=20)["oc_x_in_y"] == 2.5


# ------------------------------------------------------------------ LAB 04
def test_inflation_nominal_and_real():
    r = run("inflation", income0=40000, inflation=3, wage_growth=2, years=10)
    assert close(r["nominal_end"], 40000 * 1.02 ** 10) and close(r["price_index_end"], 100 * 1.03 ** 10)
    assert close(r["real_end"], 40000 * (1.02 / 1.03) ** 10, 1e-5)
    assert close(r["real_growth"], (1.02 / 1.03 - 1) * 100) and r["real_growth_approx"] == -1
    assert r["status"] == "real_loss" and r["real_change"] < 0 < r["nominal_change"]
    assert len(r["series"]) == 11 and r["series"][0] == {"t": 0, "nominal": 40000, "real": 40000, "price_index": 100, "basket": 50}
    for row in r["series"]:
        assert math.isclose(row["real"], row["nominal"] / (row["price_index"] / 100), rel_tol=1e-8)
        assert close(row["basket"], 50 * row["price_index"] / 100, 1e-5)


def test_inflation_zero_and_negative():
    z = run("inflation", inflation=0, wage_growth=0)
    assert z["status"] == "real_flat" and z["price_index_end"] == 100 and z["real_end"] == z["nominal_end"] == 40000
    assert z["value_of_100"] == 100
    d = run("inflation", inflation=-2, wage_growth=0, years=10)
    assert d["status"] == "real_gain" and d["price_index_end"] < 100 and d["real_end"] > d["nominal_end"] == 40000
    assert d["value_of_100"] > 100
    # equal growth keeps real income flat
    assert run("inflation", inflation=3, wage_growth=3)["status"] == "real_flat"


# ------------------------------------------------------------------ LAB 05
def test_minimum_wage_binding_and_nonbinding():
    r = run("minimum-wage", a=200, b=8, c=20, d=4, wmin=18)
    assert r["eq_wage"] == 15 and r["eq_employment"] == 80
    assert r["status"] == "binding" and r["employment"] == 56 and r["labor_supplied"] == 92 and r["excess_supply"] == 36
    assert r["employment_change"] == -24 and r["wage_bill"] == 18 * 56 and r["wage_bill_before"] == 15 * 80
    for w in (0, 12, 15):
        n = run("minimum-wage", wmin=w)
        assert n["status"] == "nonbinding" and n["employment"] == 80 and n["excess_supply"] == 0 and n["wage"] == 15
    top = run("minimum-wage", wmin=30)   # above the wage at which demand reaches 0 (200/8 = 25)
    assert top["status"] == "binding_no_jobs" and top["employment"] == 0
    assert run("minimum-wage", a=100, c=150)["status"] == "no_equilibrium"


def test_minimum_wage_text_does_not_claim_universal_job_loss():
    text = " ".join(L.SPECS["minimum-wage"]["assumptions"]).lower()
    assert "competitive" in text and "monopsony" in text and "range of effects" in text


# ------------------------------------------------------------------ LAB 06
def test_gini_matches_lorenz_area_and_known_values():
    assert L.gini([50] * 5) == 0
    assert close(L.gini([0, 0, 0, 0, 100]), 0.8)   # maximum for 5 equal-sized groups
    rng = random.Random(3)
    for _ in range(200):
        v = [rng.uniform(0, 300) for _ in range(5)]
        pts = L.lorenz(v)
        area = sum((pts[k]["s"] + pts[k + 1]["s"]) / 2 * 0.2 for k in range(5))
        assert close(L.gini(v), 1 - 2 * area, 1e-5)
    assert L.gini([0] * 5) is None


def test_redistribution_designs():
    eq = run("inequality")
    assert eq["revenue"] == 31.6 and close(sum(eq["post"]), sum(eq["pre"]))   # revenue is fully paid out
    assert eq["status"] == "more_equal" and eq["gini_after"] < eq["gini_before"] == 0.3792
    assert run("inequality", mode="bottom_two")["gini_after"] < eq["gini_after"]
    prop = run("inequality", exemption=0, mode="proportional")
    assert prop["status"] == "unchanged" and prop["gini_after"] == prop["gini_before"]
    reg = run("inequality", exemption=0, mode="top_two")
    assert reg["status"] == "less_equal" and reg["gini_after"] > reg["gini_before"]   # not every redistribution equalizes
    same = run("inequality", h1=50, h2=50, h3=50, h4=50, h5=50)
    assert same["gini_before"] == same["gini_after"] == 0 and same["ratio_before"] == 1
    none = run("inequality", h1=0, h2=0, h3=0, h4=0, h5=0)
    assert none["status"] == "no_income" and "gini_after" not in none
    zero_bottom = run("inequality", h1=0, tax_rate=0)
    assert zero_bottom["ratio_before"] is None


# ------------------------------------------------------------------ LAB 07
def test_compound_interest_closed_form_and_apy():
    for n in (1, 4, 12, 365):
        r = run("compound-interest", principal=1000, monthly=100, rate=4, compounding=n, years=20)
        i = (1 + 0.04 / n) ** (n / 12) - 1
        m = 240
        closed = 1000 * (1 + i) ** m + 100 * ((1 + i) ** m - 1) / i
        assert close(r["balance_end"], closed, 1e-4), n
        assert close(r["apy"], ((1 + 0.04 / n) ** n - 1) * 100)
        assert r["contributions_end"] == 1000 + 100 * 240 and close(r["interest_end"], r["balance_end"] - r["contributions_end"], 2e-6)
    assert run("compound-interest", compounding=365)["apy"] > run("compound-interest", compounding=1)["apy"] == 4


def test_compound_interest_edges_and_loan():
    z = run("compound-interest", rate=0)
    assert z["balance_end"] == z["contributions_end"] == 25000 and z["interest_end"] == 0 and z["apy"] == 0
    neg = run("compound-interest", principal=5000, monthly=0, rate=1, inflation=3)
    assert neg["real_return"] < 0 and neg["real_balance_end"] < 5000 < neg["balance_end"]
    loan = run("compound-interest", loan=10000, loan_apr=7, payment=200)
    assert loan["loan_status"] == "repaid" and loan["loan_months"] == 60
    assert close(loan["loan_total_paid"] - loan["loan_total_interest"], 10000, 1e-5)
    assert close(loan["loan_ear"], ((1 + 0.07 / 12) ** 12 - 1) * 100) and loan["loan_first_interest"] == 58.333333
    assert loan["loan_series"][-1]["balance"] == 0
    never = run("compound-interest", loan=5000, loan_apr=24, payment=100)   # payment equals the first month's interest
    assert never["loan_status"] == "never_repaid" and "loan_months" not in never
    assert run("compound-interest", loan=0)["loan_status"] == "no_loan"
    free = run("compound-interest", loan=1200, loan_apr=0, payment=100)
    assert free["loan_months"] == 12 and free["loan_total_interest"] == 0
    slow = run("compound-interest", loan=100000, loan_apr=10, payment=834)   # barely above interest: longer than 50 years
    assert slow["loan_status"] == "not_repaid_in_50_years" and slow["loan_remaining"] > 0


# ------------------------------------------------------------------ LAB 08
def test_comparative_advantage_mutual_gain():
    r = run("comparative-advantage")
    assert r["oc_a"] == 0.5 and r["oc_b"] == 2 and r["food_exporter"] == "A" and r["status"] == "mutual_gain"
    assert (r["cons_food_a"], r["cons_cloth_a"], r["cons_food_b"], r["cons_cloth_b"]) == (65, 35, 35, 65)
    assert r["world_food_after"] > r["world_food_before"] and r["world_cloth_after"] > r["world_cloth_before"]
    assert r["reach_a"] > 1 and r["reach_b"] > 1
    # trade at any price strictly inside (0.5, 2) puts both beyond their own frontiers
    for p in (0.55, 1, 1.5, 1.95):
        q = run("comparative-advantage", price=p, exported=20)
        assert q["status"] == "mutual_gain" and q["reach_a"] > 1 and q["reach_b"] > 1, p


def test_comparative_advantage_edges():
    absolute = run("comparative-advantage", b_food=6, b_cloth=3, labor_b=300, exported=30)
    assert absolute["abs_food"] == "A" and absolute["abs_cloth"] == "A" and absolute["status"] == "mutual_gain"
    at_edge = run("comparative-advantage", price=0.5, exported=20)
    assert at_edge["status"] == "one_side_no_gain" and close(at_edge["reach_a"], 1)
    outside = run("comparative-advantage", price=3, exported=20)
    assert outside["status"] == "one_side_loses" and outside["reach_b"] < 1
    none = run("comparative-advantage", b_food=2, b_cloth=4)
    assert none["status"] == "no_comparative_advantage" and "cons_food_a" not in none
    flip = run("comparative-advantage", a_food=4, a_cloth=2, b_food=1, b_cloth=2, labor_a=200, labor_b=100)
    assert flip["food_exporter"] == "B" and flip["status"] == "mutual_gain"
    assert run("comparative-advantage", exported=150)["status"] == "infeasible_trade"
    assert run("comparative-advantage", exported=0)["status"] == "no_trade"


# ------------------------------------------------------------------ LAB 09
def test_project_npv_matches_annuity_formula():
    r = run("sdg-project")   # energy project: 120000 now, (18000 - 2000) per year for 15 years at 4%
    annuity = (1 - 1.04 ** -15) / 0.04
    assert close(r["npv"], -120000 + 16000 * annuity, 1e-4)
    assert close(r["pv_benefits"], 18000 * annuity, 1e-4) and close(r["pv_costs"], 120000 + 2000 * annuity, 1e-4)
    assert close(r["bcr"], r["pv_benefits"] / r["pv_costs"]) and r["payback"] == 7.5
    assert 7.5 < r["discounted_payback"] < 15 and r["status"] == "npv_positive"
    assert close(r["series"][-1]["dcum"], r["npv"], 1e-5) and r["env_total"] == 900
    assert len(r["alternatives"]) == 4 and r["alternatives"][0]["npv"] == r["npv"]


def test_project_edges():
    zero = run("sdg-project", discount=0)
    assert zero["npv"] == zero["undiscounted_net"] == -120000 + 16000 * 15 and zero["discounted_payback"] == zero["payback"]
    neg = run("sdg-project", benefit=5000)
    assert neg["status"] == "npv_negative" and neg["payback"] is None and neg["discounted_payback"] is None
    valued = run("sdg-project", benefit=5000, env_value=100)   # + 60 units × $100 per year
    assert valued["npv_with_env"] > neg["npv"] and "npv_with_env" not in neg
    free = run("sdg-project", investment=0, op_cost=0, benefit=0)
    assert free["bcr"] is None and free["payback"] == 0
    # a higher discount rate lowers the NPV of a project whose benefits come later
    assert run("sdg-project", discount=10)["npv"] < run("sdg-project", discount=2)["npv"]


# ------------------------------------------------------------------ validation
@pytest.mark.parametrize("sim_id,field,value,msg", [
    ("opportunity-cost", "px", 0, "must be between 1 and 50"),
    ("opportunity-cost", "x", 2.5, "whole number"),
    ("inflation", "inflation", "abc", "enter a number"),
    ("inflation", "inflation", "inf", "enter a number"),
    ("inflation", "years", 41, "must be between 1 and 40"),
    ("minimum-wage", "b", 0.1, "must be between 0.5 and 50"),
    ("inequality", "mode", "everyone", "choose one of the listed options"),
    ("compound-interest", "compounding", 7, "choose one of the listed options"),
    ("compound-interest", "rate", -1, "must be between 0 and 15"),
    ("comparative-advantage", "price", "", "enter a number"),
    ("sdg-project", "discount", 16, "must be between 0 and 15"),
    ("sdg-project", "project", "rocket", "choose one of the listed options"),
])
def test_invalid_inputs_rejected(sim_id, field, value, msg):
    with pytest.raises(L.LabError) as exc:
        L.run(sim_id, {**L.defaults(sim_id), field: value})
    assert exc.value.field == field and msg in exc.value.message


def test_select_values_from_forms_are_typed():
    inputs, _ = L.run("compound-interest", {**L.defaults("compound-interest"), "compounding": "365"})
    assert inputs["compounding"] == 365


# ------------------------------------------------------------------ Python / JavaScript
def _random_raw(rng, sim_id):
    raw = {}
    for i in L.SPECS[sim_id]["inputs"]:
        if i["kind"] == "select":
            raw[i["name"]] = rng.choice(i["options"])[0]
        elif i["integer"]:
            raw[i["name"]] = rng.randint(int(i["min"]), int(i["max"]))
        else:
            raw[i["name"]] = round(rng.uniform(i["min"], i["max"]) / i["step"]) * i["step"] if rng.random() < 0.5 \
                else round(rng.uniform(i["min"], i["max"]), 3)
            raw[i["name"]] = min(max(raw[i["name"]], i["min"]), i["max"])
    return raw


def _same(py, js, where):
    if isinstance(py, dict):
        assert set(py) == set(js), (where, set(py) ^ set(js))
        for k in py:
            _same(py[k], js[k], f"{where}.{k}")
    elif isinstance(py, list):
        assert len(py) == len(js), where
        for k, (a, b) in enumerate(zip(py, js)):
            _same(a, b, f"{where}[{k}]")
    elif isinstance(py, (int, float)) and not isinstance(py, bool):
        assert isinstance(js, (int, float)) and math.isclose(py, js, rel_tol=1e-9, abs_tol=2e-6), (where, py, js)
    else:
        assert py == js, (where, py, js)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_python_and_javascript_agree(tmp_path):
    rng = random.Random(2026)
    cases = []
    for sid, spec in L.SPECS.items():
        cases += [{"sim": sid, "raw": p["values"]} for p in spec["presets"]]
        cases += [{"sim": sid, "raw": _random_raw(rng, sid)} for _ in range(150)]
    bad = [{"sim": "inflation", "raw": {**L.defaults("inflation"), "years": 2.5}},
           {"sim": "opportunity-cost", "raw": {**L.defaults("opportunity-cost"), "px": "1e3"}},
           {"sim": "inequality", "raw": {**L.defaults("inequality"), "mode": "x"}},
           {"sim": "sdg-project", "raw": {**L.defaults("sdg-project"), "investment": 2000001}}]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"specs": L.SPECS, "projects": L.PROJECTS, "cases": cases + bad}), encoding="utf-8")
    res = subprocess.run([NODE, os.path.join(ROOT, "tests", "lab_node_runner.js"), str(path)], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    js = json.loads(res.stdout)
    statuses = {}
    for case, out in zip(cases, js):
        inputs, py = L.run(case["sim"], case["raw"])
        assert out["ok"] is True, (case, out)
        assert out["inputs"] == inputs
        _same(py, out["results"], case["sim"])
        statuses.setdefault(case["sim"], set()).add(py["status"])
    for case, out in zip(bad, js[len(cases):]):
        with pytest.raises(L.LabError) as exc:
            L.run(case["sim"], case["raw"])
        assert out["ok"] is False and out["field"] == exc.value.field and out["message"] == exc.value.message
    assert {"inside", "infeasible"} <= statuses["opportunity-cost"]
    assert {"binding", "nonbinding"} <= statuses["minimum-wage"]
    assert {"npv_positive", "npv_negative"} <= statuses["sdg-project"]
    assert {"mutual_gain", "one_side_loses"} <= statuses["comparative-advantage"]
