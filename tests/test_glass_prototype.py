"""Glass design prototypes: dev-only pages that must never be reachable on a deployment, and never show answer keys."""
import json
import os
import re

import pytest

from econova import config
from tests.conftest import ROOT

PAGES = ("/prototype/glass/", "/prototype/glass/dashboard", "/prototype/glass/lesson", "/prototype/glass/components")


def test_prototypes_are_404_unless_enabled(client, monkeypatch):
    monkeypatch.delenv("ECONOVA_DESIGN_PROTOTYPES", raising=False)
    for path in PAGES:
        assert client.get(path).status_code == 404, path


def test_prototypes_cannot_be_enabled_in_production(monkeypatch):
    monkeypatch.setenv("ECONOVA_DESIGN_PROTOTYPES", "1")
    for env, value in (("VERCEL_ENV", "production"), ("VERCEL_ENV", "preview"), ("APP_ENV", "production")):
        monkeypatch.setenv(env, value)
        with pytest.raises(config.ConfigError, match="DESIGN_PROTOTYPES"):
            config.design_prototypes_enabled()
        monkeypatch.delenv(env)


@pytest.fixture
def proto(sqlite_app, monkeypatch, tmp_path):
    monkeypatch.setenv("ECONOVA_DESIGN_PROTOTYPES", "1")
    monkeypatch.setenv("ECONOVA_PRIVATE_CONTENT_DIR", str(tmp_path / "no-keys"))   # no answer keys anywhere near these pages
    return sqlite_app.test_client()


def test_prototype_pages_render_in_english(proto):
    hangul = re.compile(r"[가-힣]")
    for path in PAGES + ("/prototype/glass/lesson?level=beginner", "/prototype/glass/lesson?level=advanced",
                         "/prototype/glass/lesson/c03/c03-l1"):
        res = proto.get(path)
        html = res.get_data(as_text=True)
        assert res.status_code == 200, path
        assert not hangul.search(re.sub(r"<!--.*?-->", "", html, flags=re.S)), path
        assert 'name="robots" content="noindex"' in html and "Design prototype" in html


def test_lesson_prototype_shows_draft_label_and_no_answer_keys(proto):
    html = proto.get("/prototype/glass/lesson").get_data(as_text=True)
    assert "AI-reviewed, not yet approved by a person" in html and "AI-checked (not human-approved)" in html
    with open(os.path.join(ROOT, "content", "assessments", "c02-l1-quiz.json"), encoding="utf-8") as f:
        quiz = json.load(f)
    for q in quiz["questions"]:            # the public file has no answers; the prompts are not shown either
        assert q["prompt"] not in html
        assert "answer" not in q and "explanation" not in q


def test_unknown_or_fixture_lessons_404(proto):
    assert proto.get("/prototype/glass/lesson/c02/nope").status_code == 404
    assert proto.get("/prototype/glass/lesson/dev-f1/dev-f1-l1").status_code == 404
    assert proto.get("/prototype/glass/lesson?level=<script>").status_code == 200   # falls back to intermediate


def test_google_button_follows_light_theme(proto):
    css = open(os.path.join(ROOT, "public", "static", "glass", "glass.css"), encoding="utf-8").read()
    rule = css[css.index(".gsi {"):css.index("}", css.index(".gsi {"))]
    for token in ("#FFFFFF", "#747775", "#1F1F1F", "Google Sans"):
        assert token in rule
    assert "backdrop-filter" not in rule
