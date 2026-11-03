"""Phase 2.1 안정성: 강좌 JSON 오류 격리, 운영 설정 fail-fast, 오류 페이지, 이전 LMS 보관함 안내,
sqlite 트랜잭션 보호, 보안 회귀(CSRF·로그인 필수)."""
import os
import shutil
import subprocess
import sys

import pytest

from econova import config, content, storage
from tests.conftest import CSRF, FAKE_CREDENTIALS, ROOT, login, set_csrf, signup

LEAK_MARKERS = ("Traceback", "c05.json", ".json", "content/", "ContentError", "JSON 문법", ROOT)


@pytest.fixture
def content_copy(tmp_path, monkeypatch):
    """content/ 를 임시 폴더로 복사해 그쪽을 읽게 한다. 실제 파일은 건드리지 않는다."""
    copy = tmp_path / "content"
    shutil.copytree(content.CONTENT_DIR, copy)
    monkeypatch.setattr(content, "CONTENT_DIR", str(copy))
    content.load_catalog.cache_clear()
    yield copy
    content.load_catalog.cache_clear()


@pytest.fixture
def broken_content(content_copy):
    (content_copy / "courses" / "c05.json").write_text('{"id": "c05", ', encoding="utf-8")
    return content_copy


def _no_leak(html):
    for marker in LEAK_MARKERS:
        assert marker not in html, marker


# ------------------------------------------------------------- 강좌 JSON 오류 격리
@pytest.mark.parametrize("path", ["/", "/login", "/signup"])
def test_public_pages_work_with_broken_content(client, broken_content, path):
    assert client.get(path).status_code == 200


def test_signup_and_login_work_with_broken_content(client, broken_content):
    assert signup(client).status_code == 302
    res = login(client)
    assert res.status_code == 302 and res.headers["Location"].endswith("/dashboard")


@pytest.mark.parametrize("path", ["/legacy", "/legacy/courses", "/course/econ-micro", "/watch/econ-micro", "/curriculum",
                                  "/curriculum/new", "/curriculum/quick"])
def test_legacy_pages_work_with_broken_content(logged_in, broken_content, path):
    assert logged_in.get(path).status_code == 200


def test_legacy_curriculum_creation_works_with_broken_content(logged_in, broken_content):
    res = logged_in.post("/curriculum/quick", data={"track": "econ", "level": "0", "hours": "5", "csrf_token": CSRF})
    assert res.status_code == 302 and logged_in.get(res.headers["Location"]).status_code == 200


@pytest.mark.parametrize("method, path", [("get", "/dashboard"), ("get", "/courses"), ("get", "/courses/c02"),
                                          ("get", "/learn/c02/c02-l1"), ("get", "/courses/c02/continue"),
                                          ("post", "/courses/c02/enroll")])
def test_econova_pages_show_controlled_error(logged_in, broken_content, caplog, method, path):
    kwargs = {"data": {"csrf_token": CSRF}} if method == "post" else {}
    res = getattr(logged_in, method)(path, **kwargs)
    html = res.get_data(as_text=True)
    assert res.status_code == 503
    assert "강좌 정보를 불러올 수 없어요" in html and "이전 LMS 보관함" in html
    _no_leak(html)
    assert "courses/c05.json" in caplog.text and "JSON 문법 오류" in caplog.text   # 원인은 서버 로그에만


def test_missing_course_file_is_controlled(logged_in, content_copy):
    os.remove(content_copy / "courses" / "c03.json")
    res = logged_in.get("/courses")
    assert res.status_code == 503
    _no_leak(res.get_data(as_text=True))


def test_fixing_content_recovers_without_restart(logged_in, broken_content):
    assert logged_in.get("/courses").status_code == 503
    shutil.copy(os.path.join(ROOT, "content", "courses", "c05.json"), broken_content / "courses" / "c05.json")
    assert logged_in.get("/courses").status_code == 200   # 실패한 읽기는 캐시하지 않는다


def test_invalid_schema_is_controlled(logged_in, content_copy):
    path = content_copy / "courses" / "c02.json"
    path.write_text(path.read_text(encoding="utf-8").replace('"status": "coming_soon"', '"status": "published"'),
                    encoding="utf-8")   # 자료·퀴즈 승인 없이 공개 → 로더가 거절
    res = logged_in.get("/dashboard")
    assert res.status_code == 503
    _no_leak(res.get_data(as_text=True))


# ------------------------------------------------------------- 운영 설정 fail-fast
def _import_app(**extra_env):
    env = {k: v for k, v in os.environ.items()
           if k not in ("DB_BACKEND", "FIREBASE_CREDENTIALS_JSON", "RENDER", "APP_ENV", "ECONOVA_DEV_FIXTURES")}
    env.update(extra_env)
    code = ("import os, sys; sys.path.insert(0, os.environ['LMS_ROOT']);"
            "from econova import config; config.DOTENV_PATH = '/nonexistent'; import app; print('started')")
    return subprocess.run([sys.executable, "-I", "-c", code], env={**env, "LMS_ROOT": ROOT},
                          capture_output=True, text=True, timeout=60)


def test_fixtures_in_production_stop_startup():
    res = _import_app(RENDER="true", DB_BACKEND="sqlite", ECONOVA_DEV_FIXTURES="1")
    assert res.returncode != 0 and "ConfigError" in res.stderr and "ECONOVA_DEV_FIXTURES" in res.stderr
    ok = _import_app(RENDER="true", DB_BACKEND="sqlite")
    assert ok.returncode == 0 and "started" in ok.stdout


def test_fixtures_allowed_outside_production():
    res = _import_app(ECONOVA_DEV_FIXTURES="1")
    assert res.returncode == 0 and "started" in res.stdout


def test_production_fixture_error_is_not_hidden_as_content_error(logged_in, monkeypatch, fixtures_on):
    # 기동 뒤 환경이 바뀌는 경우에도 보안 설정 오류를 '콘텐츠 점검 중' 화면으로 덮지 않는다
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(config.ConfigError):
        logged_in.get("/courses")


# ------------------------------------------------------------- check-content 명령
def test_check_content_command_ok(sqlite_app, content_copy):
    res = sqlite_app.test_cli_runner().invoke(args=["check-content"])
    assert res.exit_code == 0, res.output
    assert "실제 강좌 9개 (레슨 27개, 공개 0개), 개발용 테스트 강좌 2개" in res.output


def test_check_content_command_reports_errors(sqlite_app, broken_content):
    res = sqlite_app.test_cli_runner().invoke(args=["check-content"])
    assert res.exit_code != 0 and "courses/c05.json" in res.output


def test_check_content_also_checks_fixture_files(sqlite_app, content_copy):
    (content_copy / "dev_fixtures" / "dev-f2.json").write_text("[]", encoding="utf-8")
    res = sqlite_app.test_cli_runner().invoke(args=["check-content"])
    assert res.exit_code != 0 and "dev-f2.json" in res.output


# ------------------------------------------------------------- 오류 페이지
def test_404_page_anonymous(client):
    res = client.get("/no-such-page")
    html = res.get_data(as_text=True)
    assert res.status_code == 404 and "페이지를 찾을 수 없어요" in html and 'href="/login"' in html
    assert "Not Found" not in html and "<title>페이지를 찾을 수 없어요 · ECONOVA</title>" in html


def test_404_page_logged_in(logged_in):
    for path in ("/no-such-page", "/courses/nope", "/learn/dev-x/l1", "/watch/cip"):
        html = logged_in.get(path).get_data(as_text=True)
        assert "페이지를 찾을 수 없어요" in html and 'href="/dashboard"' in html and 'href="/legacy"' in html, path


def test_403_page_links_back_to_course(logged_in):
    res = logged_in.get("/learn/c02/c02-l1")
    html = res.get_data(as_text=True)
    assert res.status_code == 403 and "이 페이지에는 접근할 수 없어요" in html
    assert 'href="/courses/c02"' in html and "Forbidden" not in html


def test_error_pages_render_with_broken_content(logged_in, broken_content):
    res = logged_in.get("/no-such-page")
    assert res.status_code == 404 and "페이지를 찾을 수 없어요" in res.get_data(as_text=True)


def test_no_page_title_says_only_lms():
    for root, _, files in os.walk(os.path.join(ROOT, "templates")):
        for name in files:
            text = open(os.path.join(root, name), encoding="utf-8").read()
            assert "· LMS{%" not in text and ">LMS<" not in text, name


# ------------------------------------------------------------- 이전 LMS 보관함 안내
LEGACY_PAGES = ["/legacy", "/legacy/courses", "/course/econ-micro", "/watch/econ-micro", "/curriculum", "/curriculum/new",
                "/curriculum/quick"]


def test_legacy_banner_only_on_legacy_pages(logged_in):
    for path in LEGACY_PAGES:
        assert "이전 LMS 보관함</strong>" in logged_in.get(path).get_data(as_text=True), path
    for path in ("/dashboard", "/courses", "/courses/c02"):
        assert "legacy-banner" not in logged_in.get(path).get_data(as_text=True), path


def test_footer_links_to_archive(logged_in):
    html = logged_in.get("/dashboard").get_data(as_text=True)
    assert 'href="/legacy">이전 LMS 보관함 (내 커리큘럼 · 대학 공개 강의)</a>' in html


def test_dashboard_points_to_legacy_curricula(app, logged_in):
    assert "보관된 내 커리큘럼 보기" not in logged_in.get("/dashboard").get_data(as_text=True)
    for _ in range(2):
        logged_in.post("/curriculum/quick", data={"track": "econ", "level": "0", "hours": "5", "csrf_token": CSRF})
    html = logged_in.get("/dashboard").get_data(as_text=True)
    assert "커리큘럼 <strong>2개</strong>가 보관되어 있어요" in html and 'href="/curriculum"' in html
    with app.app_context():
        uid = storage.get_user_by_email("student@example.com")["id"]
        assert storage.count_curricula(uid) == 2 and storage.count_curricula("nobody") == 0
    assert "2/10" not in html   # 기존 커리큘럼은 ECONOVA 진도와 섞이지 않는다


def test_catalogs_are_clearly_distinguished(logged_in):
    econova = logged_in.get("/courses").get_data(as_text=True)
    legacy = logged_in.get("/legacy/courses").get_data(as_text=True)
    assert "SDG와 함께 배우는 경제 강좌" in econova and "이전 LMS 보관함" not in econova.split("<footer")[0]
    assert "대학 공개 강의 탐색 · 이전 LMS 보관함" in legacy and "이전 LMS 보관함</strong>" in legacy


# ------------------------------------------------------------- sqlite 트랜잭션
def test_progress_refuses_pending_transaction_without_discarding_it(sqlite_app):
    with sqlite_app.app_context():
        storage.create_user("a@example.com", "A", "h")
        uid = storage.get_user_by_email("a@example.com")["id"]
        storage.enroll_course(uid, "dev-f1", "beginner", 1)
        db = storage.get_db()
        db.execute("INSERT INTO course_views (slug, views) VALUES ('pending', 1)")   # 커밋하지 않은 쓰기
        with pytest.raises(RuntimeError, match="커밋하지 않은 변경"):
            storage.update_lesson_progress(uid, "dev-f1", "dev-f1-l1", ("material", "quiz"), material_reviewed=True)
        assert db.in_transaction   # 남의 변경을 지우지 않았다
        db.commit()
        assert db.execute("SELECT views FROM course_views WHERE slug = 'pending'").fetchone()[0] == 1
        assert storage.list_lesson_progress(uid, "dev-f1") == {}
        storage.update_lesson_progress(uid, "dev-f1", "dev-f1-l1", ("material", "quiz"), material_reviewed=True)
        assert not db.in_transaction
        assert storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]["status"] == "in_progress"


def test_progress_failure_rolls_back_its_own_write(sqlite_app, monkeypatch):
    with sqlite_app.app_context():
        storage.create_user("a@example.com", "A", "h")
        uid = storage.get_user_by_email("a@example.com")["id"]
        storage.enroll_course(uid, "dev-f1", "beginner", 1)
        monkeypatch.setattr(storage.progress, "apply_event", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
        with pytest.raises(ValueError):
            storage.update_lesson_progress(uid, "dev-f1", "dev-f1-l1", ("material",), material_reviewed=True)
        assert not storage.get_db().in_transaction and storage.list_lesson_progress(uid, "dev-f1") == {}


def test_progress_course_comes_from_enrollment(sqlite_app):
    with sqlite_app.app_context():
        storage.create_user("a@example.com", "A", "h")
        uid = storage.get_user_by_email("a@example.com")["id"]
        storage.enroll_course(uid, "dev-f1", "beginner", 1)
        storage.update_lesson_progress(uid, "dev-f1", "dev-f1-l1", ("material",), material_reviewed=True)
        db = storage.get_db()
        db.execute("UPDATE econ_lesson_progress SET course_id = 'wrong'")   # 복사본이 어긋나도
        db.commit()
        assert set(storage.list_all_lesson_progress(uid)) == {"dev-f1"}
        assert storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]["course_id"] == "dev-f1"


# ------------------------------------------------------------- 보안 회귀
def _sample_path(rule):
    import re
    return re.sub(r"<[^>]+>", "x", rule.rule)


def test_every_post_route_requires_csrf(app, logged_in):
    posts = [r for r in app.url_map.iter_rules() if "POST" in r.methods]
    assert len(posts) >= 9
    for rule in posts:
        with logged_in.session_transaction() as s:
            s["csrf_token"] = CSRF
        assert logged_in.post(_sample_path(rule)).status_code == 400, rule.rule
        assert logged_in.post(_sample_path(rule), data={"csrf_token": "wrong"}).status_code == 400, rule.rule


def test_every_private_get_route_requires_login(app, client):
    public = {"index", "login", "signup", "static"}
    for rule in app.url_map.iter_rules():
        if "GET" in rule.methods and rule.endpoint not in public:
            res = client.get(_sample_path(rule))
            assert res.status_code == 302 and res.headers["Location"].endswith("/login"), rule.rule
