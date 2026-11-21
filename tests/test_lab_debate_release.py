"""Competition release: the nine-experiment Economics Lab and the production debate topics (27+, 3+ per course).
Checks routes, navigation, chart coordinates against calculated values, debate content and sources, access rules,
the AI debate flow, history persistence and student isolation."""
import glob
import html as htmllib
import json
import os
import re
import shutil
import subprocess

import pytest

from econova import content, debates, lab_models as L, simulations
from econova.ai import debate as ai_debate
from tests.conftest import CSRF, ROOT, login, set_csrf, signup
from tests.test_ai_features import mock_ai  # noqa: F401
from tests.test_econova_routes import _enroll, _uid

NODE = shutil.which("node")
COURSES = [f"c0{i}" for i in range(1, 10)]


# ================================================================== Economics Lab
def test_lab_catalog_has_exactly_nine_one_per_course():
    cat = L.catalog()
    assert [e["id"] for e in cat] == list(L.LAB_ORDER) and len(cat) == 9
    assert [e["course_id"] for e in cat] == COURSES
    assert {e["id"] for e in cat if e["kind"] == "classic"} == set(simulations.SIMULATIONS)   # the two originals are kept
    real = content.load_catalog(False)
    for e in cat:
        course = real.course(e["course_id"])
        assert course.title_ko == e["course_name"] and course.lesson(e["lesson_id"]) is not None, e["id"]


def test_lab_home_lists_all_nine(logged_in):
    html = logged_in.get("/lab").get_data(as_text=True)
    assert html.count('class="lab-card"') == 9 and html.count("Start experiment</a>") == 9
    for e in L.catalog():
        assert f'href="/lab/{e["id"]}"' in html and e["title"].replace("&", "&amp;") in html


@pytest.mark.parametrize("sim_id", L.LAB_ORDER)
def test_every_experiment_page_renders(logged_in, sim_id):
    res = logged_in.get(f"/lab/{sim_id}")
    html = res.get_data(as_text=True)
    assert res.status_code == 200
    assert 'class="lab-presets"' in html and "Reset to starting values" in html and "Use current values as baseline" in html
    assert "Hypothetical" in html and 'href="/discuss/' in html and 'href="/learn/' in html
    if sim_id in L.SPECS:
        assert f'data-lab="{sim_id}"' in html and "econova-lab-models.js" in html and "econova-lab-ui.js" in html
        for i in L.SPECS[sim_id]["inputs"]:
            assert f'name="{i["name"]}"' in html
        for a in L.SPECS[sim_id]["assumptions"]:
            assert a in htmllib.unescape(html)
    else:
        assert f'data-sim="{sim_id}"' in html and "econova-sim-ui.js" in html


def test_lab_requires_login(client):
    for sim_id in L.LAB_ORDER:
        assert client.get(f"/lab/{sim_id}").status_code in (302, 303)
    signup(client)
    login(client)
    assert client.get("/lab/not-a-sim").status_code == 404


def test_server_render_matches_the_model_and_links_prefill(logged_in):
    html = logged_in.get("/lab/minimum-wage?wmin=12").get_data(as_text=True)
    assert 'value="12"' in html and "$15 per hour" in html          # non-binding: wage stays at equilibrium
    html = logged_in.get("/lab/opportunity-cost").get_data(as_text=True)
    assert "<td>$96</td>" in html and "<td>1.5 tickets</td>" in html
    bad = logged_in.get("/lab/inflation?years=999").get_data(as_text=True)
    assert "couldn't use" in htmllib.unescape(bad) and 'value="10"' in bad        # invalid link values fall back to defaults
    assert 'value="2000000"' in logged_in.get("/lab/sdg-project?investment=2000000").get_data(as_text=True)   # no 2e+06


def test_course_and_lesson_pages_link_to_their_experiment(logged_in):
    for e in L.catalog():
        html = logged_in.get(f"/courses/{e['course_id']}").get_data(as_text=True)
        assert f'href="/lab/{e["id"]}"' in html and "Economics Lab:" in html, e["course_id"]
    _enroll(logged_in, "c04")
    html = logged_in.get("/learn/c04/c04-l3").get_data(as_text=True)
    assert 'href="/lab/inflation"' in html and "Open the experiment" in html
    _enroll(logged_in, "c02")
    assert 'data-sim="supply-demand"' in logged_in.get("/learn/c02/c02-l1").get_data(as_text=True)   # embedded widget unchanged


def test_classic_simulations_keep_validated_model_and_gain_efficient_output():
    _, r = simulations.run("carbon-tax", simulations.DEFAULTS["carbon-tax"])   # t = md = 6
    assert r["quantity"] == r["efficient_quantity"] == 36 and r["pigouvian_tax"] == 6
    _, zero = simulations.run("carbon-tax", {**simulations.DEFAULTS["carbon-tax"], "md": 0})
    assert zero["efficient_quantity"] == zero["baseline"]["quantity"] and zero["social_welfare_change"] < 0
    _, high = simulations.run("carbon-tax", {**simulations.DEFAULTS["carbon-tax"], "t": 15})
    assert high["quantity"] < high["efficient_quantity"]
    for sid, presets in simulations.PRESETS.items():
        for p in presets:
            simulations.run(sid, p["values"])
    _, sd = simulations.run("supply-demand", simulations.DEFAULTS["supply-demand"])
    assert (sd["price"], sd["quantity"]) == (30, 40)   # the original validated equilibrium


# ------------------------------------------------------------------ chart coordinates (JavaScript views)
@pytest.fixture(scope="module")
def views(tmp_path_factory):
    if NODE is None:
        pytest.skip("node is not installed")
    cases = []
    for sid, spec in L.SPECS.items():
        cases += [{"sim": sid, "raw": p["values"]} for p in spec["presets"]]
    path = tmp_path_factory.mktemp("views") / "cases.json"
    path.write_text(json.dumps({"specs": L.SPECS, "projects": L.PROJECTS, "cases": cases}), encoding="utf-8")
    res = subprocess.run([NODE, os.path.join(ROOT, "tests", "lab_view_runner.js"), str(path)], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout)
    return list(zip(cases, data["out"])), data["frame"]


def _px(frame, spec, x, y):
    X = frame["PL"] + (x - spec["x"][0]) / (spec["x"][1] - spec["x"][0]) * (frame["W"] - frame["PL"] - frame["PR"])
    Y = frame["H"] - frame["PB"] - (y - spec["y"][0]) / (spec["y"][1] - spec["y"][0]) * (frame["H"] - frame["PT"] - frame["PB"])
    return round(X, 1), round(Y, 1)


def test_chart_geometry_matches_calculated_values(views):
    cases, frame = views
    checked = set()
    for case, out in cases:
        sid, r = case["sim"], out["results"]
        _, py = L.run(sid, case["raw"])
        assert out["summary"] and out["notes"], sid
        for ch in out["charts"]:
            spec = ch["spec"]
            assert spec["x"][1] > spec["x"][0] and spec["y"][1] > spec["y"][0] and spec["xLabel"] and spec["yLabel"]
            for g in ch["geometry"]:
                if "data" in g and g["kind"] == "polyline":
                    for (dx, dy), (gx, gy) in zip(g["data"], g["pts"]):
                        ex, ey = _px(frame, spec, dx, dy)
                        assert abs(gx - ex) <= 0.11 and abs(gy - ey) <= 0.11, (sid, g)
                if g["kind"] == "dot":
                    ex, ey = _px(frame, spec, *g["data"])
                    assert abs(g["at"][0] - ex) <= 0.11 and abs(g["at"][1] - ey) <= 0.11, (sid, g)
                    assert spec["x"][0] <= g["data"][0] <= spec["x"][1] and spec["y"][0] <= g["data"][1] <= spec["y"][1], (sid, g)
        lines = {g.get("label"): g for ch in out["charts"] for g in ch["geometry"] if g["kind"] == "polyline"}
        dots = {g.get("label"): g["data"] for ch in out["charts"] for g in ch["geometry"] if g["kind"] == "dot"}
        if sid == "opportunity-cost":
            assert lines["Budget line"]["data"] == [[0, py["max_y"]], [py["max_x"], 0]] and dots["Your choice"] == [case["raw"]["x"], case["raw"]["y"]]
        elif sid == "inflation":
            assert lines["Nominal"]["data"] == [[p["t"], p["nominal"]] for p in py["series"]]
            assert lines["Real"]["data"] == [[p["t"], p["real"]] for p in py["series"]]
        elif sid == "minimum-wage" and py["status"] != "no_equilibrium":
            assert dots["Equilibrium"] == [py["eq_employment"], py["eq_wage"]]
            if case["raw"]["wmin"] > 0:
                assert lines["Minimum wage $" + f"{case['raw']['wmin']:g}"]["data"][0][1] == case["raw"]["wmin"]
            if py["status"] == "binding":
                assert dots["Jobs"] == [py["employment"], case["raw"]["wmin"]] and dots["Job seekers"] == [py["labor_supplied"], case["raw"]["wmin"]]
        elif sid == "inequality":
            assert lines["After"]["data"] == [[p["p"] * 100, p["s"] * 100] for p in py["lorenz_after"]]
            bars = [g for ch in out["charts"] for g in ch["geometry"] if g["kind"] == "rect"]
            assert [b["data"][1] for b in bars] == [v for pair in zip(py["pre"], py["post"]) for v in pair]
        elif sid == "compound-interest":
            assert lines["Balance"]["data"] == [[p["t"], p["balance"]] for p in py["series"]]
        elif sid == "comparative-advantage":
            assert lines["Alba"]["data"] == [[py["max_food_a"], 0], [0, py["max_cloth_a"]]]
            if "cons_food_a" in py:
                assert dots["Alba with trade"] == [py["cons_food_a"], py["cons_cloth_a"]]
        elif sid == "sdg-project":
            assert lines["Discounted"]["data"][-1][1] == py["npv"]
            assert len([g for ch in out["charts"] for g in ch["geometry"] if g["kind"] == "rect"]) == case["raw"]["years"] + 1
            assert out["extra"].count("<tr") == 1 + len(L.PROJECTS)
        checked.add(sid)
    assert checked == set(L.SPECS)


def test_views_explain_economics_correctly(views):
    cases, _ = views
    by = {}
    for case, out in cases:
        by.setdefault(case["sim"], []).append((case, out))
    mw = {o["results"]["status"]: " ".join(o["notes"]) for _, o in by["minimum-wage"]}
    assert "doesn't bind" in " ".join(o["summary"] for _, o in by["minimum-wage"] if o["results"]["status"] == "nonbinding")
    assert all("monopsony" in t for t in mw.values())                   # never implies universal job loss
    ineq = {o["results"]["status"] for _, o in by["inequality"]}
    assert {"more_equal", "unchanged", "less_equal"} <= ineq              # not every design reduces inequality
    trade = [o for c, o in by["comparative-advantage"] if o["results"]["status"] == "no_comparative_advantage"]
    assert trade and "no gains from trade" in trade[0]["summary"]


# ================================================================== Economics Debate
def _real_topics():
    cat = content.load_catalog(False)
    return {cid: debates.topics_for(cat.course(cid), cat.sources) for cid in COURSES}, cat


def test_production_debate_files_exist_and_parse():
    files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "content", "debates", "*.json")))
    assert files == [f"{c}.json" for c in COURSES]
    topics, cat = _real_topics()
    ids = [t["id"] for ts in topics.values() for t in ts]
    assert len(ids) >= 27 and len(set(ids)) == len(ids)
    for cid, ts in topics.items():
        assert len(ts) >= 3, cid
        for t in ts:
            assert len(t["perspectives"]) >= 2 and len({p["name"] for p in t["perspectives"]}) == len(t["perspectives"])
            assert all(p["reasoning"] and p["assumptions"] for p in t["perspectives"])
            assert len(t["background"]) >= 2 and t["guiding_questions"] and t["trade_offs"] and t["policy_question"].endswith("?")
            assert t["source_ids"] and all(cat.sources[s].verified and cat.sources[s].url.startswith("https://") for s in t["source_ids"])
            assert "[Dev" not in json.dumps(t) and "fixture" not in json.dumps(t).lower()


def test_debate_review_records_are_honest_drafts():
    for path in glob.glob(os.path.join(ROOT, "content", "debates", "*.json")):
        for t in json.load(open(path, encoding="utf-8"))["topics"]:
            assert t["review"]["status"] == "draft" and "reviewer" not in t["review"] and "approved_at" not in t["review"]


def test_no_obsolete_approval_wording():
    for rel in ("templates/econova/discuss/index.html", "templates/econova/discuss/course.html", "templates/econova/discuss/topic.html"):
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read().lower()
        assert "approved" not in text, rel
    import inspect
    assert "approved_only" not in inspect.signature(debates.topics_for).parameters


def test_enrolled_students_see_real_topics_and_others_do_not(app, client):
    signup(client)
    login(client)
    set_csrf(client)
    topics, cat = _real_topics()
    first = topics["c05"][0]
    assert client.get("/discuss/c05").status_code == 303                       # enrollment still required
    assert client.get(f"/discuss/c05/{first['id']}").status_code == 303
    assert "aren't enrolled" in client.get("/discuss").get_data(as_text=True)
    _enroll(client, "c05")
    html = client.get("/discuss").get_data(as_text=True)
    assert all(t["title"] in html.replace("&#39;", "'") for t in topics["c05"]) and topics["c06"][0]["title"] not in html
    html = client.get("/discuss/c05").get_data(as_text=True).replace("&#39;", "'")
    assert html.count('class="persp-card"') == len(topics["c05"])
    page = client.get(f"/discuss/c05/{first['id']}").get_data(as_text=True)
    assert "Sources to explore" in page and all(cat.sources[s].url in page for s in first["source_ids"])
    assert "Questions to guide your argument" in page and page.count('class="persp-card"') == len(first["perspectives"])
    assert client.get("/discuss/c05/not-a-topic").status_code == 404
    assert client.get(f"/discuss/c06/{topics['c06'][0]['id']}").status_code == 303   # not enrolled in c06


@pytest.mark.parametrize("course_id", COURSES)
def test_every_topic_page_renders_for_enrolled_student(logged_in, course_id):
    _enroll(logged_in, course_id)
    topics, _ = _real_topics()
    for t in topics[course_id]:
        res = logged_in.get(f"/discuss/{course_id}/{t['id']}")
        assert res.status_code == 200 and "Policy question:" in res.get_data(as_text=True), t["id"]


def test_real_topic_debate_flow_history_summary_and_isolation(app, client, mock_ai):  # noqa: F811
    topics, _ = _real_topics()
    t = topics["c03"][0]
    page = f"/discuss/c03/{t['id']}"
    signup(client)
    login(client)
    set_csrf(client)
    _enroll(client, "c03")
    for text in ("A carbon tax makes polluters pay for the damage they cause.", "But it could hurt low-income households."):
        assert client.post(page + "/respond", data={"csrf_token": CSRF, "message": text}).status_code == 303
    html = client.get(page).get_data(as_text=True)
    assert "But it could hurt low-income households." in html and html.count("Moderator") >= 2
    prompt = mock_ai.calls[-1]
    assert t["policy_question"] in json.dumps(prompt.__dict__ if hasattr(prompt, "__dict__") else str(prompt), ensure_ascii=False)
    assert client.post(page + "/summary", data={"csrf_token": CSRF}).status_code == 303
    assert "Debate summary" in client.get(page).get_data(as_text=True)
    with app.app_context():
        uid = _uid(app)
        [conv] = storage_convs(uid, t["id"])
        assert conv["stage"] == "summarized"
    client.post("/logout", data={"csrf_token": CSRF})
    login(client)                                                           # history survives a new login
    assert "A carbon tax makes polluters pay" in client.get(page).get_data(as_text=True)
    client.post("/logout", data={"csrf_token": CSRF})
    signup(client, email="other@example.com")
    login(client, email="other@example.com")
    set_csrf(client)
    _enroll(client, "c03")
    assert "A carbon tax makes polluters pay" not in client.get(page).get_data(as_text=True)
    assert client.post(page + "/respond", data={"csrf_token": CSRF, "message": "x", "conversation_id": conv["id"]}).status_code == 404


def storage_convs(uid, topic_id):
    from econova import storage
    return storage.find_ai_conversations(uid, "debate", topic_id=topic_id)


def test_debate_works_without_ai_for_real_topics(logged_in):
    topics, _ = _real_topics()
    t = topics["c08"][1]
    _enroll(logged_in, "c08")
    page = f"/discuss/c08/{t['id']}"
    logged_in.post(page + "/respond", data={"csrf_token": CSRF, "message": "Tariffs protect jobs in the short run."})
    html = logged_in.get(page).get_data(as_text=True)
    assert "Tariffs protect jobs in the short run." in html and "Prepared guiding question" in html
    assert ai_debate is not None
