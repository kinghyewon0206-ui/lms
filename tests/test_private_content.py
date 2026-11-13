"""평가 정답 키 분리 (Phase 6 Stage B): 공개 파일에는 정답이 없다, 키는 서버에서만 합친다, 키가 없거나 맞지 않으면
그 평가만 닫는다(fail closed), 커밋 전 점검이 정답·검토 문서·키를 찾아낸다.
실제 정답 키의 정합성은 ECONOVA_REAL_PRIVATE_CONTENT_DIR 이 있을 때만 확인한다 (키는 저장소 밖에 있으므로)."""
import glob
import json
import os
import shutil

import pytest

from econova import config, content, diagnostic, learning, private_content, public_safety, storage
from tests.conftest import CSRF, ROOT
from tests.test_econova_routes import _enroll, _post, _uid

pytestmark = pytest.mark.usefixtures("fixtures_on")
PUBLIC_ASSESSMENT_FILES = sorted(glob.glob(os.path.join(ROOT, "content", "assessments", "*.json"))
                                 + glob.glob(os.path.join(ROOT, "content", "dev_fixtures", "assessments", "*.json"))
                                 + [os.path.join(ROOT, "content", "diagnostic.json"),
                                    os.path.join(ROOT, "content", "dev_fixtures", "diagnostic.json")])


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------- 공개 파일에는 정답이 없다
@pytest.mark.parametrize("path", PUBLIC_ASSESSMENT_FILES, ids=os.path.basename)
def test_public_assessment_files_have_no_answer_data(path):
    assert private_content.public_violations(_load(path)) == []
    assert public_safety.scan_text(os.path.relpath(path, ROOT), open(path, encoding="utf-8").read()) == []


def test_only_synthetic_keys_live_in_the_repository():
    keys = glob.glob(os.path.join(ROOT, "**", "*.answers.json"), recursive=True)
    keys = [k for k in keys if "/.venv/" not in k and "/.git/" not in k]
    assert keys and all(os.path.dirname(k) == private_content.FIXTURE_KEYS_DIR for k in keys)
    assert all(_load(k)["synthetic"] is True for k in keys)
    assert not os.path.exists(os.path.join(ROOT, "docs", "review"))


def test_public_question_payloads_never_carry_keys(logged_in):
    _enroll(logged_in, "dev-f1")
    _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    html = logged_in.get("/learn/dev-f1/dev-f1-l1/quiz").get_data(as_text=True)
    quiz = content.get_catalog().course("dev-f1").lesson("dev-f1-l1").quiz_assessment
    assert quiz.answer_keys and all(q["explanation"] not in html for q in quiz.questions)
    for q in quiz.public_questions():
        assert not set(q) & set(private_content.PRIVATE_QUESTION_KEYS)


# ------------------------------------------------------------- 합치기 규칙
def _fixture_pair(aid="dev-f1-l1-quiz"):
    public = _load(os.path.join(ROOT, "content", "dev_fixtures", "assessments", f"{aid}.json"))
    return public, private_content.read_keys(aid, fixture=True)


def test_merge_restores_server_data():
    public, keys = _fixture_pair()
    full = private_content.merge(public, keys, "t")
    assert all("answer" in q and "explanation" in q for q in full["questions"])
    assert "answer" not in public["questions"][0]   # 원본 공개 데이터는 바뀌지 않는다
    again_public, again_keys = private_content.split(full, keys["assessment_id"], synthetic=True)
    assert again_public == public and again_keys == keys


@pytest.mark.parametrize("tamper, message", [
    (lambda p, k: k.update(assessment_version=99), "평가 버전"),
    (lambda p, k: p["questions"][0].update(prompt=p["questions"][0]["prompt"] + " (수정)"), "공개 문항이 바뀌어"),
    (lambda p, k: p["questions"][0]["choices"].reverse(), "공개 문항이 바뀌어"),
    (lambda p, k: k["questions"].popitem(), "문항 목록"),
    (lambda p, k: next(iter(k["questions"].values())).update(question_version=7), "문항 버전"),
    (lambda p, k: next(iter(k["questions"].values())).update(score_override=1), "알 수 없는 항목"),
])
def test_mismatched_keys_fail_closed(tamper, message):
    public, keys = _fixture_pair()
    tamper(public, keys)
    with pytest.raises(private_content.KeysUnavailable, match=message):
        private_content.merge(public, keys, "t")


def test_public_file_with_answers_is_rejected(tmp_path):
    public, keys = _fixture_pair()
    full = private_content.merge(public, keys, "t")
    assert private_content.public_violations(full)
    with pytest.raises(content.ContentError, match="정답 정보"):
        diagnostic_like = dict(_load(diagnostic.FIXTURE_PATH))
        diagnostic_like["questions"][0]["answer"] = "a"
        path = tmp_path / "diag.json"
        path.write_text(json.dumps(diagnostic_like, ensure_ascii=False), encoding="utf-8")
        diagnostic._load(str(path), fixture=True)


# ------------------------------------------------------------- 키가 없으면 그 평가만 닫는다
def test_real_assessments_without_keys_are_closed_but_catalog_works(logged_in):
    course = content.get_catalog().course("c02")
    for a in [l.quiz_assessment for l in course.lessons] + [course.final]:
        assert a.answer_keys is False and a.keys_problem and all("answer" not in q for q in a.questions)
        assert a.public_questions()   # 문항 자체(공개 정의)는 그대로 검사·표시할 수 있다
    assert logged_in.get("/courses").status_code == 200 and logged_in.get("/courses/c02").status_code == 200


@pytest.fixture
def no_fixture_keys(tmp_path, monkeypatch):
    """dev-f1-l1-quiz 의 합성 키만 없는 상태."""
    keys = tmp_path / "keys"
    shutil.copytree(private_content.FIXTURE_KEYS_DIR, keys)
    (keys / "dev-f1-l1-quiz.answers.json").unlink()
    monkeypatch.setattr(private_content, "FIXTURE_KEYS_DIR", str(keys))
    content.load_catalog.cache_clear()
    yield
    content.load_catalog.cache_clear()


def test_quiz_without_keys_fails_closed(app, logged_in, no_fixture_keys):
    _enroll(logged_in, "dev-f1")
    _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    res = logged_in.get("/learn/dev-f1/dev-f1-l1/quiz")
    assert res.status_code == 503 and "평가를 지금 열 수 없어요" in res.get_data(as_text=True)
    with logged_in.session_transaction() as s:
        s["assess_tokens"] = {"dev-f1-l1-quiz": "tok-1-aaaaaaaaaaaaaa"}
    res = logged_in.post("/learn/dev-f1/dev-f1-l1/quiz", data={"csrf_token": CSRF, "submission_token": "tok-1-aaaaaaaaaaaaaa", "q_x": "a"})
    assert res.status_code == 503
    with app.app_context():
        uid = _uid(app)
        assert storage.list_assessment_attempts(uid) == []                        # 아무것도 채점·저장되지 않았다
        assert not storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"].get("quiz_submitted")
    assert logged_in.get("/learn/dev-f1/dev-f1-l1").status_code == 200           # 학습자료는 계속 볼 수 있다
    with pytest.raises(private_content.KeysUnavailable):
        learning.require_keys(content.get_catalog().course("dev-f1").lesson("dev-f1-l1").quiz_assessment)


def test_saved_attempt_recovers_without_keys(app, logged_in, monkeypatch, tmp_path):
    """이미 저장된 제출의 진도 복구(같은 토큰 재전송)는 정답 키 없이도 된다 (다시 채점하지 않으므로)."""
    from tests.test_econova_routes import take
    _enroll(logged_in, "dev-f1")
    _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    quiz = content.get_catalog().course("dev-f1").lesson("dev-f1-l1").quiz_assessment
    take(logged_in, "/learn/dev-f1/dev-f1-l1/quiz", quiz)
    with app.app_context():
        uid = _uid(app)
        [attempt] = storage.list_assessment_attempts(uid)
        token = storage.get_assessment_attempt(uid, attempt["id"]).get("submission_token") or None
    keys = tmp_path / "keys"
    shutil.copytree(private_content.FIXTURE_KEYS_DIR, keys)
    (keys / "dev-f1-l1-quiz.answers.json").unlink()
    monkeypatch.setattr(private_content, "FIXTURE_KEYS_DIR", str(keys))
    content.load_catalog.cache_clear()
    try:
        if token:
            res = logged_in.post("/learn/dev-f1/dev-f1-l1/quiz", data={"csrf_token": CSRF, "submission_token": token})
            assert res.status_code == 302 and attempt["id"] in res.headers["Location"]
        assert logged_in.get(f"/assessments/attempts/{attempt['id']}").status_code == 200   # 기록은 그대로 보인다
        with app.app_context():
            assert len(storage.list_assessment_attempts(uid)) == 1
    finally:
        content.load_catalog.cache_clear()


def test_diagnostic_without_keys_fails_closed(app, logged_in, monkeypatch):
    monkeypatch.setattr(diagnostic, "PATH", os.path.join(ROOT, "content", "diagnostic.json"))
    monkeypatch.setattr(diagnostic, "KEYS_FIXTURE", False)          # 실제 진단평가 + (테스트의) 빈 비공개 폴더
    assert diagnostic.load()["answer_keys"] is False
    assert logged_in.get("/diagnostic/take").status_code == 503
    assert logged_in.post("/diagnostic/take", data={"csrf_token": CSRF, "q_q01": "a"}).status_code == 503
    with pytest.raises(private_content.KeysUnavailable):
        diagnostic.score({})
    with app.app_context():
        assert storage.list_diagnostic_attempts(_uid(app)) == []
    assert logged_in.get("/diagnostic").status_code == 200


def test_wrong_keys_close_only_that_assessment(tmp_path, monkeypatch):
    keys = tmp_path / "keys"
    shutil.copytree(private_content.FIXTURE_KEYS_DIR, keys)
    data = _load(keys / "dev-f1-l1-quiz.answers.json")
    mcq = next(q for q in data["questions"].values() if "answer" in q and isinstance(q["answer"], str))
    mcq["answer"] = "zz"                                             # 선택지에 없는 정답
    (keys / "dev-f1-l1-quiz.answers.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(private_content, "FIXTURE_KEYS_DIR", str(keys))
    content.load_catalog.cache_clear()
    try:
        course = content.load_catalog(True).course("dev-f1")
        assert course.lesson("dev-f1-l1").quiz_assessment.answer_keys is False
        assert "정답 키 검사 실패" in course.lesson("dev-f1-l1").quiz_assessment.keys_problem
        assert course.lesson("dev-f1-l2").quiz_assessment.answer_keys is True
    finally:
        content.load_catalog.cache_clear()


def test_fixture_keys_must_be_marked_synthetic(tmp_path, monkeypatch):
    keys = tmp_path / "keys"
    shutil.copytree(private_content.FIXTURE_KEYS_DIR, keys)
    data = _load(keys / "dev-f1-l1-quiz.answers.json")
    data.pop("synthetic")
    (keys / "dev-f1-l1-quiz.answers.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(private_content, "FIXTURE_KEYS_DIR", str(keys))
    with pytest.raises(private_content.KeysUnavailable, match="synthetic"):
        private_content.read_keys("dev-f1-l1-quiz", fixture=True)


# ------------------------------------------------------------- 설정
def test_private_dir_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("ECONOVA_PRIVATE_CONTENT_DIR", os.path.join(ROOT, "content"))
    with pytest.raises(config.ConfigError, match="저장소 밖"):
        config.private_content_dir()
    monkeypatch.setenv("ECONOVA_PRIVATE_CONTENT_DIR", str(tmp_path))
    assert config.private_content_dir() == os.path.realpath(str(tmp_path))
    monkeypatch.delenv("ECONOVA_PRIVATE_CONTENT_DIR")
    assert config.private_content_dir().endswith("econova-private")          # 개발 기본값: 저장소 밖
    monkeypatch.setenv("RENDER", "1")
    assert config.private_content_dir() is None                              # 운영: 기본값 없음 → 평가는 닫힌다
    assert private_content.keys_path("c02-final") is None
    with pytest.raises(private_content.KeysUnavailable, match="설정되지 않았습니다"):
        private_content.read_keys("c02-final")


# ------------------------------------------------------------- 커밋 전 점검
@pytest.mark.parametrize("rel, text, expect", [
    ("content/assessments/x.json", json.dumps({"questions": [{"id": "q1", "answer": "a"}]}), "정답 정보"),
    ("content/assessments/x.json", json.dumps({"questions": [{"id": "q1", "choices": [{"id": "a", "correct": True}]}]}), "정답 정보"),
    ("content/x.answers.json", json.dumps({"synthetic": True}), "비공개 폴더"),
    ("content/dev_fixtures/private/x.answers.json", json.dumps({"kind": "assessment_keys"}), "synthetic"),
    ("docs/review/c02.md", "# 검토", "docs/review"),
    ("notes/anything.md", f"<!-- {public_safety.REVIEW_MARKER} -->", "교사용 검토 문서"),
    ("app.py", "KEY = 'sk-" + "a" * 30 + "'", "OpenAI"),
    ("cred.json", '{"type": "service_account", "private_key": "x"}', "서비스 계정"),
])
def test_scanner_finds_restricted_data(rel, text, expect):
    issues = public_safety.scan_text(rel, text)
    assert issues and any(expect in i for i in issues), issues


@pytest.mark.parametrize("rel, text", [
    ("content/dev_fixtures/private/x.answers.json", json.dumps({"synthetic": True, "questions": {"q": {"answer": "a"}}})),
    ("tests/data/x.json", json.dumps({"synthetic": True, "questions": [{"id": "q", "answer": "a"}]})),
    ("content/assessments/x.json", json.dumps({"questions": [{"id": "q", "prompt": "p", "choices": [{"id": "a"}]}]})),
])
def test_scanner_allows_public_and_synthetic_data(rel, text):
    assert public_safety.scan_text(rel, text) == []


def test_everything_git_add_would_include_is_clean():
    files = public_safety.candidate_files()
    assert "content/assessments/c02-final.json" in files and "content/diagnostic.json" in files
    assert public_safety.scan(files) == {}


def test_gitignore_blocks_private_material():
    for path in ("docs/review/c02-review-package.md", "content/assessments/c02-final.answers.json", "econova-private/x"):
        assert public_safety.is_ignored_inside_repo(os.path.join(ROOT, path)) == (True, True), path
    assert public_safety.is_ignored_inside_repo(os.path.join(ROOT, "content", "dev_fixtures", "private",
                                                             "dev-f1-final.answers.json")) == (True, False)


# ------------------------------------------------------------- 실제 정답 키 정합성 (저장소 밖 키가 있을 때만)
REAL_DIR = os.environ.get("ECONOVA_REAL_PRIVATE_CONTENT_DIR")


@pytest.mark.skipif(not REAL_DIR, reason="실제 정답 키 폴더(ECONOVA_REAL_PRIVATE_CONTENT_DIR)가 없어 건너뜀")
def test_real_keys_match_public_definitions(monkeypatch):
    monkeypatch.setenv("ECONOVA_PRIVATE_CONTENT_DIR", REAL_DIR)
    monkeypatch.setattr(diagnostic, "PATH", os.path.join(ROOT, "content", "diagnostic.json"))
    monkeypatch.setattr(diagnostic, "KEYS_FIXTURE", False)
    content.load_catalog.cache_clear()
    try:
        course = content.load_catalog(False).course("c02")
        for a in [l.quiz_assessment for l in course.lessons] + [course.final]:
            assert a.answer_keys, a.keys_problem          # 정답 키가 공개 문항과 맞고, 계산 검증(check)도 통과
        test = diagnostic.load()
        assert test["answer_keys"], test["keys_problem"]
        assert diagnostic.score({q["id"]: str(q["answer"]) for q in test["questions"]})["score"] == len(test["questions"])
    finally:
        content.load_catalog.cache_clear()


def test_cli_reports_closed_assessments_and_public_scan(sqlite_app):
    runner = sqlite_app.test_cli_runner()
    res = runner.invoke(args=["check-content"])
    assert res.exit_code == 0, res.output                     # 초안 평가에 키가 없는 것은 오류가 아니다 (응시 불가로 닫힘)
    assert "[정답 키 없음 → 응시 불가] c02-final" in res.output and "[정답 키 없음 → 응시 불가] c01-final" in res.output
    assert "열 수 없는 평가 8개" in res.output   # c01·c02 각 4개. 진단평가는 테스트에서 합성 키 사용
    res = runner.invoke(args=["check-public-files"])
    assert res.exit_code == 0 and "공개 저장소 점검 통과" in res.output
