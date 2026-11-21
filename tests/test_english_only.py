"""ECONOVA is English-only: no Korean (Hangul) may reach a user.

Scope: rendered/visible text only. Developer comments, docstrings and Jinja comments may be in any language.
- Templates (outside {# ... #}), JavaScript string literals (outside comments), CSS `content:` values
- Python string constants in econova/ and app.py (docstrings excluded; a line may opt out with `# i18n-allow`
  when the Korean text is a detection pattern, never a message)
- Every string in content/ JSON (courses, lessons, assessments, diagnostic, sources, SDGs, capstone, dev fixtures)
- Rendered pages for the main student, admin and preview flows
"""
import ast
import json
import os
import re

import pytest

from econova import simulations
from tests.conftest import CSRF, ROOT, login, set_csrf, signup

HANGUL = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힣]")


def _rel(path):
    return os.path.relpath(path, ROOT)


def _walk(top, suffixes):
    for base, dirs, files in os.walk(os.path.join(ROOT, top)):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules")]
        for name in sorted(files):
            if name.endswith(suffixes):
                yield os.path.join(base, name)


def _lines_with_hangul(text):
    return [f"{i}: {line.strip()[:120]}" for i, line in enumerate(text.splitlines(), 1) if HANGUL.search(line)]


# ------------------------------------------------------------- static sources
def test_templates_render_no_korean():
    bad = {}
    for path in _walk("templates", (".html",)):
        text = re.sub(r"\{#.*?#\}", lambda m: "\n" * m.group(0).count("\n"), open(path, encoding="utf-8").read(), flags=re.S)
        text = _without_html_and_script_comments(text)
        if hits := _lines_with_hangul(text):
            bad[_rel(path)] = hits[:5]
    assert not bad, bad


def test_templates_declare_english():
    base = open(os.path.join(ROOT, "templates", "base.html"), encoding="utf-8").read()
    assert '<html lang="en"' in base


def _strip_js_comments(src):
    out, i, n, quote = [], 0, len(src), None
    while i < n:
        ch = src[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
            out.append(ch)
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
            continue
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            out.append("\n" * src[i:end].count("\n"))
            i = end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _without_html_and_script_comments(html):
    html = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), html, flags=re.S)
    return re.sub(r"(<script\b[^>]*>)(.*?)(</script>)", lambda m: m.group(1) + _strip_js_comments(m.group(2)) + m.group(3),
                  html, flags=re.S)


def test_javascript_shipped_to_browsers_is_english():
    """Static JS files are downloaded by every visitor, so even their comments must be English."""
    bad = {}
    for path in _walk(os.path.join("public", "static"), (".js",)):
        if hits := _lines_with_hangul(open(path, encoding="utf-8").read()):
            bad[_rel(path)] = hits[:5]
    assert not bad, bad


def test_css_generated_text_is_english():
    for path in _walk(os.path.join("public", "static"), (".css",)):
        css = re.sub(r"/\*.*?\*/", "", open(path, encoding="utf-8").read(), flags=re.S)
        assert not HANGUL.search(css), _rel(path)


def _python_strings_with_hangul(path):
    src = open(path, encoding="utf-8").read()
    lines = src.splitlines()
    tree = ast.parse(src)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings and HANGUL.search(node.value):
            span = lines[node.lineno - 1:(node.end_lineno or node.lineno)]
            if not any("# i18n-allow" in line for line in span):
                bad.append(f"{node.lineno}: {node.value[:80]!r}")
    return bad


def test_python_user_facing_strings_are_english():
    bad = {}
    for path in [*_walk("econova", (".py",)), os.path.join(ROOT, "app.py")]:
        if hits := _python_strings_with_hangul(path):
            bad[_rel(path)] = hits[:5]
    assert not bad, bad


def test_i18n_allow_is_only_used_for_detection_patterns():
    """`# i18n-allow` must stay rare: it is for regexes/keyword lists that detect Korean input, not for messages."""
    users = []
    for path in [*_walk("econova", (".py",)), os.path.join(ROOT, "app.py")]:
        users += [f"{_rel(path)}:{i}" for i, line in enumerate(open(path, encoding="utf-8"), 1) if "# i18n-allow" in line]
    assert len(users) <= 12, users


# ------------------------------------------------------------- content JSON
def _json_strings(value, where=""):
    if isinstance(value, str):
        yield where, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _json_strings(k, f"{where}/<key>")
            yield from _json_strings(v, f"{where}/{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _json_strings(v, f"{where}[{i}]")


def test_all_content_json_is_english():
    bad = {}
    for path in _walk("content", (".json",)):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        hits = [f"{w}: {s[:80]}" for w, s in _json_strings(data) if HANGUL.search(s)]
        if hits:
            bad[_rel(path)] = hits[:5]
    assert not bad, bad


def test_simulation_labels_are_english():
    texts = [s["title"] for s in simulations.SIMULATIONS.values()]
    texts += [lim[3] for lim in simulations.LIMITS.values()] + [lim[4] for lim in simulations.LIMITS.values()]
    for rows in simulations.ROW_LABELS.values():
        texts += [text for _, label, unit in rows for text in (label, unit)]
    res = simulations.supply_demand(10, 2, 20, 1)          # no positive equilibrium → reason text
    texts.append(res["reason"])
    texts += simulations.interpret(simulations.DEFAULTS["supply-demand"], {**simulations.DEFAULTS["supply-demand"], "a": 120})
    assert texts and not [t for t in texts if HANGUL.search(t)]


# ------------------------------------------------------------- rendered pages
STUDENT_PAGES = ["/", "/courses", "/courses/dev-f1", "/courses/dev-f2", "/courses/c01", "/courses/c02", "/courses/c03",
                 "/learn/dev-f1/dev-f1-l1", "/learn/dev-f1/dev-f1-l1/quiz", "/courses/dev-f1/final", "/courses/dev-f1/assessments",
                 "/diagnostic", "/diagnostic/take", "/lab", "/lab/supply-demand", "/lab/carbon-tax", "/lab/saved", "/report",
                 "/discuss", "/discuss/dev-f1", "/capstone/dev-f3", "/capstone/dev-f3/edit", "/courses/dev-f1/completion",
                 "/this-page-does-not-exist"]
ADMIN_PAGES = ["/admin", "/admin/content", "/admin/content/release"]
PREVIEW_PAGES = [f"/preview/{c}/{c}-l{n}?level={lvl}" for c in ("c01", "c02", "c03") for n in (1, 2, 3)
                 for lvl in ("beginner", "intermediate", "advanced")]


def _assert_english(client_, paths, minimum_ok):
    ok, bad = 0, {}
    for path in paths:
        res = client_.get(path, follow_redirects=True)
        html = res.get_data(as_text=True)          # everything sent to the browser, comments included
        if res.status_code == 200:
            ok += 1
        if hits := _lines_with_hangul(html):
            bad[f"{path} ({res.status_code})"] = hits[:3]
    assert not bad, bad
    assert ok >= minimum_ok, ok


def test_public_pages_are_english(client):
    _assert_english(client, ["/", "/login", "/signup", "/this-page-does-not-exist"], 3)
    set_csrf(client)
    res = client.post("/login", data={"email": "nobody@example.com", "password": "wrong-password", "csrf_token": CSRF})
    assert not HANGUL.search(res.get_data(as_text=True))
    res = client.post("/signup", data={"name": "", "email": "bad", "password": "x", "confirm": "y", "csrf_token": CSRF})
    assert not HANGUL.search(res.get_data(as_text=True))


def test_student_pages_are_english(app, client, fixtures_on):
    signup(client, name="Alex Student")
    login(client)
    set_csrf(client)
    client.post("/courses/dev-f1/enroll", data={"csrf_token": CSRF})
    _assert_english(client, STUDENT_PAGES, 12)


def test_admin_and_preview_pages_are_english(app, client, monkeypatch):
    from econova import storage
    monkeypatch.setenv("ECONOVA_CONTENT_PREVIEW", "1")
    signup(client, email="admin@example.test", name="Admin Tester")
    with app.app_context():
        storage.grant_admin(storage.get_user_by_email("admin@example.test")["id"], "Test operator", "Test account created in tests")
    login(client, email="admin@example.test")
    set_csrf(client)
    _assert_english(client, ADMIN_PAGES + PREVIEW_PAGES, len(ADMIN_PAGES + PREVIEW_PAGES) - 1)


# ------------------------------------------------------------- AI language
def test_every_ai_system_prompt_requires_english():
    from econova.ai import safety
    from econova.ai.language import ENGLISH_ONLY_INSTRUCTION
    assert "respond in English" in ENGLISH_ONLY_INSTRUCTION
    assert set(safety.TASK_RULES) == {"tutor", "feedback", "debate_turn", "debate_summary", "capstone", "recommendation"}
    for task in safety.TASK_RULES:
        prompt = safety.system_prompt(task)
        assert ENGLISH_ONLY_INSTRUCTION in prompt and not HANGUL.search(prompt), task


def test_ai_features_only_use_the_shared_system_prompt():
    """Every model request builds its system prompt with safety.system_prompt(), so none can skip the English rule."""
    calls = []
    for path in [*_walk(os.path.join("econova", "ai"), (".py",)), os.path.join(ROOT, "econova", "ai_web.py")]:
        for i, line in enumerate(open(path, encoding="utf-8"), 1):
            if re.search(r"\bsystem\s*=", line) and "def " not in line:
                calls.append((f"{_rel(path)}:{i}", line.strip()))
    assert len(calls) >= 6 and all("system=safety.system_prompt(" in line.replace(" ", "") for _, line in calls), calls
