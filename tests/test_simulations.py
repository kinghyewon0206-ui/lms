"""Phase 5 경제 시뮬레이션: 공식·입력 검사, Python/JS 일치, SVG·접근성, 저장(서버 재계산)·소유권, 레슨 연결,
마이그레이션 5, Firestore 계약. 화면·저장 테스트는 sqlite 와 가짜 Firestore 양쪽에서 돈다."""
import json
import math
import os
import random
import shutil
import subprocess

import pytest

from econova import content, simulations as sim, storage
from tests.conftest import CSRF, ROOT, login, set_csrf, signup
from tests.test_econova_routes import _enroll, _uid

VECTORS = json.load(open(os.path.join(ROOT, "tests", "data", "sim_vectors.json"), encoding="utf-8"))
NODE = shutil.which("node")


# ------------------------------------------------------------- 공식 (손으로 검증한 벡터)
@pytest.mark.parametrize("case", VECTORS["supply_demand"], ids=lambda c: c["name"])
def test_supply_demand_vectors(case):
    _, r = sim.run("supply-demand", case["inputs"])
    for k, v in case["expected"].items():
        assert (r[k] == v) if isinstance(v, str) else math.isclose(r[k], v, abs_tol=1e-6), (k, r[k], v)


@pytest.mark.parametrize("case", VECTORS["carbon_tax"], ids=lambda c: c["name"])
def test_carbon_tax_vectors(case):
    _, r = sim.run("carbon-tax", case["inputs"])
    for k, v in case["expected"].items():
        assert (r[k] == v) if isinstance(v, str) else math.isclose(r[k], v, abs_tol=1e-6), (k, r[k], v)


def test_shift_directions():
    base = sim.supply_demand(100, 2, 10, 1)
    for (a, c), (dp, dq) in {(130, 10): (1, 1), (70, 10): (-1, -1), (100, 40): (-1, 1), (100, -5): (1, -1)}.items():
        r = sim.supply_demand(a, 2, c, 1)
        assert math.copysign(1, r["price"] - base["price"]) == dp and math.copysign(1, r["quantity"] - base["quantity"]) == dq
    notes = sim.interpret({"a": 100, "b": 2, "c": 10, "d": 1}, {"a": 130, "b": 2, "c": 10, "d": 1})
    assert notes[0].startswith("Demand increases") and notes[-1] == "Result: the equilibrium price rises and the equilibrium quantity increases."
    assert sim.interpret({"a": 100, "b": 2, "c": 10, "d": 1}, {"a": 100, "b": 2, "c": 10, "d": 1}) == []


def test_tax_identities_hold_on_random_markets():
    rng = random.Random(7)
    checked = 0
    for _ in range(400):
        a, b, c, d = rng.uniform(1, 500), rng.uniform(0.1, 20), rng.uniform(-100, 100), rng.uniform(0.1, 20)
        t = rng.uniform(0, 30)
        r = sim.carbon_tax(a, b, c, d, t, md=rng.uniform(0, 30))
        if r["status"] != "interior":
            continue
        checked += 1
        base = r["baseline"]
        assert math.isclose(r["consumer_price"] - r["producer_price"], t, abs_tol=2e-6)              # 세금 쐐기
        assert math.isclose(r["consumer_burden_total"] + r["producer_burden_total"], r["revenue"], abs_tol=1e-4)
        assert math.isclose(r["consumer_share"] + r["producer_share"], 1, abs_tol=2e-6)
        assert r["consumer_price"] >= base["price"] - 1e-6 >= r["producer_price"] - 2e-6           # 세금은 가격을 갈라놓는다
        assert r["quantity"] <= base["quantity"] + 1e-6 and r["deadweight_loss_private"] >= 0
        assert math.isclose(r["social_welfare_change"], r["avoided_damage"] - r["deadweight_loss_private"], abs_tol=2e-6)
    assert checked > 100


def test_zero_tax_equals_baseline():
    for a, b, c, d in ((100, 2, 10, 1), (55, 1.5, 7, 0.7), (300, 0.3, -40, 4)):
        r, base = sim.carbon_tax(a, b, c, d, 0), sim.supply_demand(a, b, c, d)
        assert (r["consumer_price"], r["producer_price"], r["quantity"], r["revenue"], r["deadweight_loss_private"]) == \
            (base["price"], base["price"], base["quantity"], 0, 0)


def test_carbon_tax_never_claims_welfare_loss_without_assumption():
    r = sim.carbon_tax(100, 2, 10, 1, 6)
    assert "social_welfare_change" not in r and "avoided_damage" not in r   # md 를 모르면 사회적 후생을 말하지 않는다
    assert sim.carbon_tax(100, 2, 10, 1, 6, md=6)["social_welfare_change"] > 0


# ------------------------------------------------------------- 입력 검사
@pytest.mark.parametrize("field, value", [
    ("b", 0), ("d", 0), ("b", -1), ("a", 0), ("a", -5), ("a", 1001), ("c", -1001), ("d", 100.5),
    ("a", "inf"), ("a", "nan"), ("a", "1e3"), ("a", ""), ("a", "abc"), ("a", True), ("b", "1/2"), ("a", float("nan")),
])
def test_invalid_inputs_are_rejected(field, value):
    raw = {**sim.DEFAULTS["supply-demand"], field: value}
    with pytest.raises(sim.SimError) as err:
        sim.parse_inputs("supply-demand", raw)
    assert err.value.field == field


@pytest.mark.parametrize("field, value", [("t", -1), ("t", 1000.1), ("md", -0.5), ("e", "x"), ("t", "Infinity")])
def test_invalid_tax_inputs(field, value):
    with pytest.raises(sim.SimError) as err:
        sim.parse_inputs("carbon-tax", {**sim.DEFAULTS["carbon-tax"], field: value})
    assert err.value.field == field


def test_valid_edge_inputs():
    assert sim.parse_inputs("supply-demand", {"a": "1,000", "b": " 0.5 ", "c": "-1000", "d": "+2"}) == \
        {"a": 1000, "b": 0.5, "c": -1000, "d": 2}
    x = sim.parse_inputs("carbon-tax", {**sim.DEFAULTS["carbon-tax"], "md": "", "t": "0"})
    assert "md" not in x and x["t"] == 0
    with pytest.raises(sim.SimError):
        sim.parse_inputs("unknown", {})


def test_rounding_rule():
    assert sim.r6(0.1234565) == 0.123457 and sim.r6(-0.1234565) == -0.123457 and sim.r6(-0.0000001) == 0.0
    assert sim.r6(2.5e-7) == 0.0 and sim.r6(5e-7) == 1e-6


# ------------------------------------------------------------- Python / JavaScript 일치
def _node(cases, tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    res = subprocess.run([NODE, os.path.join(ROOT, "tests", "sim_node_runner.js"), str(path)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _same(py, js, where):
    if isinstance(py, dict):
        for k, v in py.items():
            if k == "inputs":
                continue
            assert k in js, (where, k)
            _same(v, js[k], f"{where}.{k}")
        assert set(js) - set(py) - {"inputs"} == set(), (where, set(js) - set(py))
    elif isinstance(py, (int, float)) and not isinstance(py, bool):
        assert math.isclose(py, js, abs_tol=1e-9), (where, py, js)   # 같은 반올림 규칙이므로 사실상 같은 값
    else:
        assert py == js, (where, py, js)


@pytest.mark.skipif(NODE is None, reason="node 가 없어 JS 계산을 실행할 수 없음")
def test_python_and_javascript_agree(tmp_path):
    rng = random.Random(2026)
    cases = [{"kind": "run", "sim": "supply-demand", "raw": c["inputs"]} for c in VECTORS["supply_demand"]]
    cases += [{"kind": "run", "sim": "carbon-tax", "raw": c["inputs"]} for c in VECTORS["carbon_tax"]]
    for _ in range(300):
        raw = {"a": round(rng.uniform(1, 1000), 3), "b": round(rng.uniform(0.01, 100), 3),
               "c": round(rng.uniform(-1000, 1000), 3), "d": round(rng.uniform(0.01, 100), 3)}
        cases.append({"kind": "run", "sim": "supply-demand", "raw": raw})
        cases.append({"kind": "run", "sim": "carbon-tax",
                      "raw": {**raw, "t": round(rng.uniform(0, 200), 3), "e": round(rng.uniform(0, 5), 3),
                              **({"md": round(rng.uniform(0, 200), 3)} if rng.random() < 0.7 else {})}})
    js = _node(cases, tmp_path)
    statuses = set()
    for case, out in zip(cases, js):
        inputs, py = sim.run(case["sim"], case["raw"])
        assert out["ok"] is True
        _same(py, out["results"], case["sim"])
        statuses.add(py["status"])
    assert {"interior", "no_positive_equilibrium", "no_trade_after_tax", "producer_price_negative"} <= statuses


@pytest.mark.skipif(NODE is None, reason="node 가 없어 JS 계산을 실행할 수 없음")
def test_python_and_javascript_validate_the_same_way(tmp_path):
    bad = [("b", 0), ("a", "1e3"), ("a", "inf"), ("c", -1001), ("a", ""), ("d", "abc"), ("a", "1,000"), ("b", "0.5")]
    cases = [{"kind": "parse", "sim": "supply-demand", "raw": {**sim.DEFAULTS["supply-demand"], f: v}} for f, v in bad]
    cases += [{"kind": "parse", "sim": "carbon-tax", "raw": {**sim.DEFAULTS["carbon-tax"], "md": ""}},
              {"kind": "interpret", "base": {"a": 100, "b": 2, "c": 10, "d": 1}, "now": {"a": 100, "b": 3, "c": 40, "d": 1}}]
    js = _node(cases, tmp_path)
    for case, out in zip(cases, js):
        if case["kind"] == "interpret":
            assert out == sim.interpret(case["base"], case["now"])
            continue
        try:
            py = sim.parse_inputs(case["sim"], case["raw"])
            assert out["ok"] is True and out["inputs"] == py
        except sim.SimError as exc:
            assert out["ok"] is False and out["field"] == exc.field and out["message"] == exc.message


# ------------------------------------------------------------- 화면 (SVG·접근성)
def test_lab_pages_render_accessible_svg(logged_in):
    html = logged_in.get("/lab").get_data(as_text=True)
    assert "Economics Lab" in html and "/lab/supply-demand" in html and "/lab/carbon-tax" in html
    html = logged_in.get("/lab/supply-demand").get_data(as_text=True)
    assert 'role="img"' in html and "<desc" in html and "Equilibrium price $30, equilibrium quantity 40 units." in html
    assert 'aria-live="polite"' in html and "<th scope=\"row\">Equilibrium price</th><td>$30</td>" in html
    for name in "abcd":
        assert f'for="supply-demand-{name}"' in html and f'id="supply-demand-{name}"' in html
    assert "These are not real statistics." in html and "econova-sim-ui.js" in html
    html = logged_in.get("/lab/carbon-tax").get_data(as_text=True)
    assert "consumer price $32, producer price $26" in html and "Model assumptions and how to read the results" in html
    assert "A carbon tax does not always reduce welfare." in html
    assert 'text-anchor="end" y="42.0">S+t</text>' in html   # 세금 붙은 공급곡선 이름표가 원래 S 이름표와 겹치지 않게
    assert logged_in.get("/lab/unknown").status_code == 404


def test_static_js_is_served(client):
    for path in ("/static/js/econova-sim.js", "/static/js/econova-sim-ui.js"):
        res = client.get(path)
        assert res.status_code == 200 and b"EconovaSim" in res.data
        res.close()


def test_lab_works_when_catalog_is_broken(logged_in, tmp_path, monkeypatch):
    copy_dir = tmp_path / "content"
    shutil.copytree(content.CONTENT_DIR, copy_dir)
    (copy_dir / "courses" / "c05.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(content, "CONTENT_DIR", str(copy_dir))
    content.load_catalog.cache_clear()
    try:
        assert logged_in.get("/lab").status_code == 200 and logged_in.get("/lab/carbon-tax").status_code == 200
    finally:
        content.load_catalog.cache_clear()


# ------------------------------------------------------------- 저장 (서버 재계산·소유권)
def _save(client, sim_id, **form):
    return client.post(f"/lab/{sim_id}/save", data={"csrf_token": CSRF, **form})


def test_saved_results_are_recalculated_on_server(app, logged_in):
    res = _save(logged_in, "carbon-tax", a="100", b="2", c="10", d="1", t="6", md="6", e="1",
                price="999", quantity="-1", results='{"revenue": 1e9}', consumer_price="0")   # 위조한 결과
    assert res.status_code == 302 and "/lab/saved/" in res.headers["Location"]
    with app.app_context():
        [run] = storage.list_simulation_runs(_uid(app))
    assert run["results"]["revenue"] == 216 and run["results"]["consumer_price"] == 32
    assert "price" not in run["inputs"] and run["inputs"] == {"a": 100, "b": 2, "c": 10, "d": 1, "t": 6, "md": 6, "e": 1}
    assert run["calc_version"] == sim.CALC_VERSION and run["lesson_id"] is None and run["created_at"] is not None
    html = logged_in.get(res.headers["Location"]).get_data(as_text=True)
    assert "<th scope=\"row\">Tax revenue</th><td>$216</td>" in html and "999" not in html


def test_invalid_inputs_are_not_saved(app, logged_in):
    res = _save(logged_in, "supply-demand", a="100", b="0", c="10", d="1")
    assert res.status_code == 303
    assert "We couldn&#39;t save it." in logged_in.get(res.headers["Location"]).get_data(as_text=True)
    assert _save(logged_in, "nope", a="1").status_code == 404
    with app.app_context():
        assert storage.list_simulation_runs(_uid(app)) == []


def test_students_cannot_see_each_others_runs(app, client):
    signup(client)
    login(client)
    set_csrf(client)
    mine = _save(client, "supply-demand", a="120", b="2", c="10", d="1").headers["Location"]
    client.post("/logout", data={"csrf_token": CSRF})
    signup(client, email="other@example.com")
    login(client, email="other@example.com")
    set_csrf(client)
    assert client.get(mine).status_code == 404 and client.get("/lab/saved/not-an-id").status_code == 404
    assert "You haven't saved any experiments yet." in client.get("/lab/saved").get_data(as_text=True)


def test_lesson_scoped_save_respects_access(app, logged_in, fixtures_on):
    form = {"a": "100", "b": "2", "c": "10", "d": "1"}
    assert _save(logged_in, "supply-demand", lesson_id="c02-l1", course_id="c02", **form).status_code == 403   # 공개 전
    assert _save(logged_in, "supply-demand", lesson_id="dev-f1-l1", course_id="dev-f1", **form).status_code == 403  # 수강 전
    _enroll(logged_in, "dev-f1")
    assert _save(logged_in, "carbon-tax", lesson_id="dev-f1-l1", course_id="dev-f1", t="1", e="1", **form).status_code == 403
    res = _save(logged_in, "supply-demand", lesson_id="dev-f1-l1", course_id="dev-f1", **form)
    assert res.status_code == 302
    with app.app_context():
        [run] = storage.list_simulation_runs(_uid(app))
    assert run["lesson_id"] == "dev-f1-l1"


# ------------------------------------------------------------- 레슨 연결
def test_lesson_embeds_simulation_only_when_accessible(logged_in, fixtures_on):
    assert logged_in.get("/learn/dev-f1/dev-f1-l1").status_code == 302   # 수강 전에는 레슨(과 시뮬레이션)에 못 들어감
    _enroll(logged_in, "dev-f1")
    html = logged_in.get("/learn/dev-f1/dev-f1-l1").get_data(as_text=True)
    assert 'class="sim-widget compact"' in html and 'name="lesson_id" value="dev-f1-l1"' in html
    assert "They are not verified real-world statistics." in html and "econova-sim-ui.js" in html
    html = logged_in.get("/learn/dev-f1/dev-f1-l2").get_data(as_text=True)
    assert 'data-sim="carbon-tax"' in html
    assert "This lesson has no simulation." in logged_in.get("/learn/dev-f1/dev-f1-l3").get_data(as_text=True)
    assert logged_in.get("/learn/c02/c02-l1").status_code == 403


def test_preview_shows_simulation_for_draft_lesson(logged_in, monkeypatch):
    monkeypatch.setenv("ECONOVA_CONTENT_PREVIEW", "1")
    html = logged_in.get("/preview/c02/c02-l2").get_data(as_text=True)
    assert 'data-sim="supply-demand"' in html and 'name="lesson_id"' not in html   # 미리보기 저장은 레슨과 연결하지 않음


def test_lesson_simulation_metadata_is_validated():
    cat = content.load_catalog(False)
    assert cat.course("c02").lesson("c02-l1").simulations == ("supply-demand",)
    assert cat.course("c03").lesson("c03-l3").simulations == ("carbon-tax",)
    assert cat.course("c02").status == "coming_soon" and cat.course("c03").status == "coming_soon"
    with open(os.path.join(content.CONTENT_DIR, "courses", "c03.json"), encoding="utf-8") as f:
        raw = json.load(f)
    raw["lessons"][0]["simulations"] = ["rocket-science"]
    with pytest.raises(content.ContentError, match="simulations"):
        content.parse_course(raw)
    raw["lessons"][0]["simulations"] = ["carbon-tax", "carbon-tax"]
    with pytest.raises(content.ContentError, match="simulations"):
        content.parse_course(raw)


def test_drafts_and_publication_unchanged():
    cat = content.load_catalog(False)
    assert {c.status for c in cat.courses} == {"coming_soon"} and cat.published() == []
    c02 = cat.course("c02")
    assert all(l.content.review_status == "draft" and l.quiz_assessment.review_status == "draft" for l in c02.lessons)
    assert c02.final.review_status == "draft" and c02.final.passing["status"] == "proposed"


# ------------------------------------------------------------- 저장소 (마이그레이션 5, Firestore)
def test_migration_5_on_phase4_database(sqlite_app, tmp_path, monkeypatch):
    monkeypatch.setitem(sqlite_app.config, "DATABASE", str(tmp_path / "phase4.db"))
    full = storage.SQLITE_MIGRATIONS
    with sqlite_app.app_context():
        storage.SQLITE_MIGRATIONS = full[:4]
        try:
            storage.init_db()
            storage.create_user("old@example.com", "Old", "h")
            uid = storage.get_user_by_email("old@example.com")["id"]
            storage.enroll_course(uid, "dev-f1", "beginner", 1)
            storage.save_assessment_attempt(uid, {"course_id": "dev-f1", "lesson_id": None, "assessment_id": "dev-f1-final",
                                                  "assessment_version": 1, "course_content_version": 1, "kind": "final",
                                                  "score": 1, "max_score": 1, "ratio": 1.0, "passed": True,
                                                  "answers": {}, "results": [], "passing": {}}, "tok")
        finally:
            storage.SQLITE_MIGRATIONS = full
        assert storage.migrate_sqlite() == [5, 6, 7, 8, 9]
        assert len(storage.list_assessment_attempts(uid)) == 1 and storage.get_enrollment(uid, "dev-f1") is not None
        assert storage.list_simulation_runs(uid) == []
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError):
            storage.get_db().execute("INSERT INTO econ_simulation_runs (user_id, simulation_id, calc_version, inputs_json,"
                                     " results_json, created_at) VALUES (?, 'evil', 'x', '{}', '{}', '2026-11-03 00:00:00')", (uid,))


def test_firestore_simulation_layout(firestore_app, fake_fs):
    with firestore_app.app_context():
        storage.create_user("a@example.com", "A", "h")
        inputs, results = sim.run("supply-demand", sim.DEFAULTS["supply-demand"])
        rid = storage.save_simulation_run("a@example.com", "supply-demand", None, inputs, results, sim.CALC_VERSION)
        assert storage.get_simulation_run("a@example.com", rid)["results"]["price"] == 30
        assert storage.get_simulation_run("b@example.com", rid) is None
    assert ("users", "a@example.com", "econ_simulation_runs", rid) in fake_fs.docs
