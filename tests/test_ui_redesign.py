"""UI redesign (2026-11): the new layout must keep every functional guarantee.

These tests pin down the parts of the redesign that touch behavior or trust:
- shared layout: skip link, landmark, mobile menu wiring, progressive-enhancement script
- landing page: real courses only (never development fixtures), still opens when content is broken
- admin review screens: "AI-checked" is styled differently from human approval
- assessment pages: the new progress UI adds no answer data
- motion: reduced-motion support exists
"""
import os
import re

import pytest

from tests.conftest import ROOT, login, set_csrf, signup
from tests.test_phase7 import _make_admin

pytestmark = pytest.mark.usefixtures("fixtures_on")


def _css():
    with open(os.path.join(ROOT, "public", "static", "style.css"), encoding="utf-8") as f:
        return f.read()


def test_layout_has_skip_link_main_landmark_and_ui_script(client):
    html = client.get("/login").get_data(as_text=True)
    assert 'class="skip-link" href="#main"' in html and '<main id="main"' in html
    assert "js/econova-ui.js" in html and 'class="no-js"' in html
    assert client.get("/static/js/econova-ui.js").status_code == 200


def test_mobile_menu_button_controls_the_menu(logged_in):
    html = logged_in.get("/dashboard").get_data(as_text=True)
    assert 'aria-controls="main-menu"' in html and 'id="main-menu"' in html and 'aria-expanded="false"' in html
    # every main section is still reachable from the menu
    for label in ("Dashboard", "Courses", "Diagnostic assessment", "Economics Lab", "Debate", "My report", "Log out"):
        assert label in html


def test_landing_lists_real_courses_but_never_fixtures(client):
    html = client.get("/").get_data(as_text=True)
    for n in range(1, 10):
        assert f'data-course-id="c0{n}"' in html
    assert "Dev Test Course" not in html and "DEV-F" not in html


def test_auth_pages_keep_their_form_fields(client):
    signup_html = client.get("/signup").get_data(as_text=True)
    for name in ("name", "email", "password", "confirm", "csrf_token"):
        assert f'name="{name}"' in signup_html
    login_html = client.get("/login").get_data(as_text=True)
    for name in ("email", "password", "csrf_token"):
        assert f'name="{name}"' in login_html


def test_signup_and_login_flow_still_works(client):
    assert signup(client).status_code == 302
    r = login(client)
    assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard")


def test_admin_marks_ai_checked_sources_differently_from_human_approval(app, client):
    _make_admin(app, client)
    html = client.get("/admin/content").get_data(as_text=True)
    chips = re.findall(r'<span class="st st-(\w+)">([^<]+)</span>', html)
    assert chips, "review states are shown as status chips"
    for state, label in chips:
        if state == "verified":
            assert label == "AI-checked (not human-approved)"
        if state in ("approved", "published"):
            assert "AI" not in label
    css = _css()
    assert ".st-verified" in css and "dashed" in css.split(".st-verified", 1)[1].split("}", 1)[0]


def test_quiz_progress_ui_adds_no_answer_data(logged_in):
    set_csrf(logged_in)
    logged_in.post("/courses/dev-f1/enroll", data={"csrf_token": "test-csrf-token"})
    html = logged_in.get("/learn/dev-f1/dev-f1-l1/quiz").get_data(as_text=True)
    assert "data-assessment" in html and "data-qcount" in html
    assert "data-answer" not in html and "tolerance" not in html.lower()


def test_dashboard_shows_continue_learning_after_enrolling(logged_in):
    set_csrf(logged_in)
    logged_in.post("/courses/dev-f1/enroll", data={"csrf_token": "test-csrf-token"})
    html = logged_in.get("/dashboard").get_data(as_text=True)
    assert "continue-card" in html and "Next: Lesson 1" in html


def test_reduced_motion_and_focus_styles_exist():
    css = _css()
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ":focus-visible" in css
