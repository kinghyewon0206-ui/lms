"""Glass UI rollout (approved 2026-11-21): rules the redesign must keep.

- dashboards show only real data (no invented streaks, badges or progress)
- the diagnostic radar is computed from the attempt's own per-area results
- styled error pages never leak internals
- backdrop-filter stays limited to floating/sticky chrome (mobile GPU cost)
- the Google button keeps Google's light theme
"""
import os
import re

import pytest

from econova import ui_charts
from tests.conftest import CSRF, ROOT, set_csrf

pytestmark = pytest.mark.usefixtures("fixtures_on")


def _css():
    with open(os.path.join(ROOT, "public", "static", "style.css"), encoding="utf-8") as f:
        return f.read()


def test_dashboard_shows_no_invented_achievements_or_streaks(logged_in):
    html = logged_in.get("/dashboard").get_data(as_text=True).lower()
    for word in ("streak", "achievement", "badge earned", "sample data"):
        assert word not in html, word


def test_dashboard_progress_numbers_come_from_enrollments(logged_in):
    set_csrf(logged_in)
    logged_in.post("/courses/dev-f1/enroll", data={"csrf_token": CSRF})
    html = logged_in.get("/dashboard").get_data(as_text=True)
    assert "1 course enrolled" in html and "0% of lessons in your enrolled courses completed" in html


def test_radar_uses_real_per_area_results():
    attempt = {"by_category": {"a": {"correct": 2, "total": 2}, "b": {"correct": 1, "total": 2}, "c": {"correct": 0, "total": 2}}}
    rd = ui_charts.diagnostic_radar(attempt, {"a": "Scarcity, choices, and trade", "b": "Markets and prices", "c": "When markets fall short"})
    assert [lab["pct"] for lab in rd["labels"]] == [100, 50, 0]
    assert all(len(line) <= 20 for lab in rd["labels"] for line in lab["lines"])
    assert ui_charts.diagnostic_radar(None, {}) is None
    assert ui_charts.radar([("a", 1), ("b", 1)]) is None, "a radar needs at least three axes"


def test_dashboard_radar_after_diagnostic(logged_in):
    from tests.test_diagnostic import _answers, _submit
    _submit(logged_in, _answers(2))
    html = logged_in.get("/dashboard").get_data(as_text=True)
    assert 'class="radar"' in html and "share correct by area" in html


@pytest.mark.parametrize("method,path,code", [("get", "/logout", 405), ("get", "/no-such-page", 404)])
def test_error_pages_are_styled_and_plain(client, method, path, code):
    res = getattr(client, method)(path)
    html = res.get_data(as_text=True)
    assert res.status_code == code and 'class="err-page"' in html and "Traceback" not in html


def test_server_error_page_hides_internals(app, client, monkeypatch):
    from econova import learning

    def boom(*a, **k):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr(learning, "catalog", boom)
    monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)
    res = client.get("/")
    html = res.get_data(as_text=True)
    assert res.status_code == 500 and "secret internal detail" not in html and "Something went wrong" in html


def test_backdrop_filter_only_on_floating_chrome():
    css = re.sub(r"/\*.*?\*/", "", _css(), flags=re.S)
    rules = re.findall(r"([^{}]+)\{[^{}]*backdrop-filter:\s*(?!none)[^;]+;[^{}]*\}", css)
    selectors = {s.strip() for r in rules for s in r.split(",")}
    allowed = {".nav", ".glass.blur", ".lesson-toc", ".assess-progress", ".cap-save", ".busy", ".btn.secondary"}
    assert selectors <= allowed | {s for s in selectors if s.startswith("@")}, selectors - allowed


def test_reduced_transparency_and_motion_fallbacks_exist():
    css = _css()
    assert "@media (prefers-reduced-transparency: reduce)" in css and "@media (prefers-reduced-motion: reduce)" in css
    assert "@supports not ((backdrop-filter: blur(1px))" in css


def test_google_button_light_theme():
    css = _css()
    rule = css[css.index(".btn-google {"):css.index("}", css.index(".btn-google {"))]
    for token in ("#FFFFFF", "#747775", "#1F1F1F", "Google Sans"):
        assert token in rule
    assert "backdrop-filter" not in rule


def test_long_reading_surfaces_are_near_opaque():
    css = _css()
    paper = re.search(r"--paper:\s*rgba\(255, 255, 255, ([0-9.]+)\)", css)
    assert paper and float(paper.group(1)) >= 0.94
    section = css[css.index(".ec-section {"):css.index("}", css.index(".ec-section {"))]
    assert "var(--paper)" in section
