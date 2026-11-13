"""진단평가: 문항 검사, 정답 비노출, 결정적 채점, 수치 허용오차, 추천 기준, 저장·재응시, 학생 간 분리,
수강 난이도 추천(강제 아님), 마이그레이션 3. 화면·저장 테스트는 sqlite 와 가짜 Firestore 양쪽에서 돈다.
실제 정답 키는 저장소 밖에 있으므로, 여기서는 구조가 같은 개발용 합성 진단평가(가짜 문항·가짜 키)로 확인한다."""
import copy
import json
import sqlite3

import pytest

from econova import content, diagnostic, private_content, storage
from tests.conftest import CSRF, login, set_csrf, signup

TEST = diagnostic._load(diagnostic.FIXTURE_PATH, fixture=True)
ANSWERS = {q["id"]: str(q["answer"]) for q in TEST["questions"]}


def _raw():
    """합성 진단평가의 공개 정의 + 합성 키 (서버 전용 전체 데이터)."""
    with open(diagnostic.FIXTURE_PATH, encoding="utf-8") as f:
        public = json.load(f)
    return private_content.merge(public, private_content.read_keys(public["id"], fixture=True), "diagnostic")


def _answers(n_correct):
    """앞에서부터 n 문항만 맞힌 답안."""
    out = {}
    for i, q in enumerate(TEST["questions"]):
        if i < n_correct:
            out[q["id"]] = str(q["answer"])
        else:
            out[q["id"]] = next(c["id"] for c in q["choices"] if c["id"] != q["answer"]) if q["type"] == "mcq" else "-999"
    return out


# ------------------------------------------------------------- 문항 검사
def test_synthetic_diagnostic_is_valid():
    assert TEST["answer_keys"] is True and TEST["id"] == "dev-diagnostic"
    assert 10 <= len(TEST["questions"]) <= 12 == len(TEST["questions"])
    cats = {q["category"] for q in TEST["questions"]}
    assert cats == {"terminology", "scarcity", "supply_demand", "graph", "calculation", "policy"}
    assert {q["type"] for q in TEST["questions"]} == {"mcq", "numeric"}
    assert TEST["thresholds"]["provisional"] is True and TEST["review"]["status"] == "draft"


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["questions"].pop(), None),                                         # 11문항도 허용
    (lambda d: d.update(questions=d["questions"][:9]), "10-12 questions"),
    (lambda d: d["questions"].append(copy.deepcopy(d["questions"][0])), "10-12 questions"),
    (lambda d: d["questions"][1].update(id="q01"), "missing or duplicated"),
    (lambda d: d["questions"][0].update(answer="z"), "the answer is not one of the choices"),
    (lambda d: d["questions"][0].update(category="art"), "category"),
    (lambda d: d["questions"][0].update(type="essay"), "type"),
    (lambda d: d["questions"][8].update(tolerance=-1), "tolerance"),
    (lambda d: d["questions"][8].update(answer="40"), "must be a number"),
    (lambda d: d["questions"][8].update(answer=41), "does not match the calculated result"),                  # 균형 거래량 검증
    (lambda d: d["questions"][6].update(answer="c"), "does not match the calculated result"),                 # 그래프 균형 가격 검증
    (lambda d: d["questions"][9].update(answer=0.6), "does not match the calculated result"),
    (lambda d: d["questions"][0].update(explanation=""), "explanation"),
    (lambda d: d["thresholds"].update(provisional=False), "provisional"),
    (lambda d: d["thresholds"].update(intermediate=0.8), "intermediate < advanced"),
    (lambda d: d["graphs"]["market"].update(expected_equilibria=[{"demand": "D", "supply": "S", "price": 30, "quantity": 60}]), "would reveal the answer"),
    (lambda d: d["categories"].append({"id": "extra", "name": "Empty area"}), "has no questions"),
])
def test_invalid_diagnostic_is_rejected(mutate, message):
    data = _raw()
    mutate(data)
    if message is None:
        assert len(diagnostic.parse(data)["questions"]) == 11
    else:
        with pytest.raises(content.ContentError, match=message):
            diagnostic.parse(data)


# ------------------------------------------------------------- 정답 비노출
def test_public_questions_hide_answers():
    for q in diagnostic.public_questions():
        assert not {"answer", "tolerance", "explanation", "verify"} & set(q)


def test_take_page_does_not_leak_answers(logged_in):
    html = logged_in.get("/diagnostic/take").get_data(as_text=True)
    assert html.count('class="dg-question"') == 12 and html.count('type="radio"') > 20
    for q in TEST["questions"]:
        assert q["explanation"] not in html
    page = html.lower().replace("name=\"q_", "")
    for ui_text in ('data-overlay="grading your answers"', '<label class="dg-numeric">answer <input'):   # 화면 문구(영어)는 제외
        page = page.replace(ui_text, "")
    assert "answer" not in page   # 정답 속성·값이 없다
    assert "Equilibrium price</th>" not in html   # 그래프 문항에 균형점 표를 띄우지 않는다


# ------------------------------------------------------------- 채점
def test_scoring_is_deterministic():
    first = diagnostic.score(ANSWERS)
    assert first == diagnostic.score(dict(ANSWERS)) and first["score"] == 12 and first["recommended_level"] == "advanced"
    empty = diagnostic.score({})
    assert empty["score"] == 0 and empty["recommended_level"] == "beginner"
    assert empty["by_category"]["graph"] == {"correct": 0, "total": 2}
    assert diagnostic.score({**ANSWERS, "q99": "a"})["score"] == 12   # 모르는 문항 id 는 무시


@pytest.mark.parametrize("raw, ok", [
    ("60", True), ("60.0", True), (" 60 ", True), ("+60", True), ("60.01", True), ("59.99", True),
    ("60.02", False), ("6O", False), ("", False), ("sixty", False), ("nan", False), ("inf", False), ("6e1", False),
])
def test_numeric_tolerance_q09(raw, ok):
    q = next(q for q in TEST["questions"] if q["id"] == "q09")
    assert diagnostic.is_correct(q, raw) is ok


@pytest.mark.parametrize("raw, ok", [("0.25", True), (".25", True), ("0.24", True), ("0.26", True), ("0.23", False),
                                     ("1/4", False), ("25%", False)])
def test_numeric_tolerance_q10(raw, ok):
    q = next(q for q in TEST["questions"] if q["id"] == "q10")
    assert diagnostic.is_correct(q, raw) is ok


def test_number_parsing_rules():
    assert diagnostic.parse_number("1,000") == 1000 and diagnostic.parse_number("1,234.5") == 1234.5
    assert diagnostic.parse_number("12,5") is None   # 소수점 쉼표는 모호해서 받지 않는다
    assert diagnostic.parse_number("-3") == -3


@pytest.mark.parametrize("n, level", [(0, "beginner"), (4, "beginner"), (5, "intermediate"), (8, "intermediate"),
                                      (9, "advanced"), (12, "advanced")])
def test_recommendation_thresholds(n, level):
    # 12문항: 4/12=33% < 40%, 5/12=42%, 8/12=67% < 75%, 9/12=75% (경계는 위 단계)
    result = diagnostic.score(_answers(n))
    assert result["score"] == n and result["recommended_level"] == level


def test_threshold_boundaries_are_inclusive():
    th = {"intermediate": 0.4, "advanced": 0.75}
    assert diagnostic.recommend(4, 10, th) == "intermediate" and diagnostic.recommend(3, 10, th) == "beginner"
    assert diagnostic.recommend(3, 4, th) == "advanced" and diagnostic.recommend(0, 0, th) == "beginner"


def test_explanation_mentions_rule_and_provisional():
    reasons = diagnostic.explain(diagnostic.score(_answers(5)))
    assert reasons[0].startswith("Overall score: 42% (5/12") and "provisional" in reasons[1] and "→ Intermediate recommended" in reasons[1]


# ------------------------------------------------------------- 저장·재응시·분리 (양쪽 저장소)
def _submit(client, answers):
    return client.post("/diagnostic/take", data={"csrf_token": CSRF, **{f"q_{k}": v for k, v in answers.items()}})


def test_submit_persists_and_shows_result(app, logged_in):
    res = _submit(logged_in, _answers(5))
    assert res.status_code == 302 and "/diagnostic/attempts/" in res.headers["Location"]
    html = logged_in.get(res.headers["Location"]).get_data(as_text=True)
    assert "Recommended level" in html and '<span class="dg-rec">Intermediate</span>' in html and "5/12" in html and "provisional" in html
    assert TEST["questions"][0]["explanation"] in html   # 제출 뒤에는 해설을 보여준다
    with app.app_context():
        uid = storage.get_user_by_email("student@example.com")["id"]
        [attempt] = storage.list_diagnostic_attempts(uid)
    assert (attempt["score"], attempt["max_score"], attempt["recommended_level"]) == (5, 12, "intermediate")
    assert attempt["diagnostic_version"] == TEST["version"] and attempt["thresholds"]["provisional"] is True
    assert attempt["results"][0] == {"id": "q01", "answer": TEST["questions"][0]["answer"], "correct": True}


def test_retake_keeps_history(app, logged_in):
    first = _submit(logged_in, _answers(2)).headers["Location"]
    second = _submit(logged_in, ANSWERS).headers["Location"]
    assert first != second
    with app.app_context():
        uid = storage.get_user_by_email("student@example.com")["id"]
        attempts = storage.list_diagnostic_attempts(uid)
    assert [a["score"] for a in attempts] == [12, 2]   # 최신순, 예전 기록은 그대로
    html = logged_in.get("/diagnostic").get_data(as_text=True)
    assert html.count("View results") == 2 and "Take it again" in html
    assert logged_in.get(first).status_code == 200


def test_students_cannot_see_each_others_results(app, client):
    signup(client)
    login(client)
    set_csrf(client)
    mine = _submit(client, ANSWERS).headers["Location"]
    client.post("/logout", data={"csrf_token": CSRF})
    signup(client, email="other@example.com")
    login(client, email="other@example.com")
    set_csrf(client)
    assert client.get(mine).status_code == 404
    assert "You haven't taken it yet." in client.get("/diagnostic").get_data(as_text=True)
    assert client.get("/diagnostic/attempts/not-a-real-id").status_code == 404
    with app.app_context():
        assert storage.list_diagnostic_attempts(storage.get_user_by_email("other@example.com")["id"]) == []


def test_unanswered_and_garbage_input_are_wrong_not_errors(logged_in):
    res = logged_in.post("/diagnostic/take", data={"csrf_token": CSRF, "q_q01": "zzz", "q_q09": "x" * 500})
    assert res.status_code == 302
    assert "0/12" in logged_in.get(res.headers["Location"]).get_data(as_text=True)


def test_old_results_are_not_recomputed_when_test_changes(app, logged_in, monkeypatch):
    url = _submit(logged_in, _answers(5)).headers["Location"]
    changed = copy.deepcopy(TEST)
    changed["version"] = TEST["version"] + 1
    changed["thresholds"] = {**changed["thresholds"], "intermediate": 0.6}
    monkeypatch.setattr(diagnostic, "load", lambda: changed)
    html = logged_in.get(url).get_data(as_text=True)
    assert "5/12" in html and '<span class="dg-rec">Intermediate</span>' in html and f"based on version {TEST['version']} of the diagnostic assessment" in html   # 당시 기준(40%) 그대로


# ------------------------------------------------------------- 수강 난이도 추천 (강제 아님)
def test_recommendation_preselects_but_is_not_mandatory(app, logged_in, fixtures_on):
    assert "diagnostic assessment</a> to get a recommended level" in logged_in.get("/courses/dev-f1").get_data(as_text=True)
    _submit(logged_in, ANSWERS)   # 상(advanced) 추천
    html = logged_in.get("/courses/dev-f1").get_data(as_text=True)
    assert '<option value="advanced" selected>' in html and "the level your diagnostic assessment recommended (Advanced)" in html
    logged_in.post("/courses/dev-f1/enroll", data={"csrf_token": CSRF, "difficulty": "advanced"})
    logged_in.post("/courses/dev-f2/enroll", data={"csrf_token": CSRF, "difficulty": "beginner"})   # 추천과 다르게
    with app.app_context():
        uid = storage.get_user_by_email("student@example.com")["id"]
        a, b = storage.get_enrollment(uid, "dev-f1"), storage.get_enrollment(uid, "dev-f2")
    assert (a["selected_difficulty"], a["difficulty_source"]) == ("advanced", "diagnostic")
    assert (b["selected_difficulty"], b["difficulty_source"]) == ("beginner", "manual")
    logged_in.post("/courses/dev-f1/difficulty", data={"csrf_token": CSRF, "difficulty": "intermediate"})
    with app.app_context():
        a = storage.get_enrollment(uid, "dev-f1")
    assert (a["selected_difficulty"], a["difficulty_source"]) == ("intermediate", "manual")
    assert "chosen by you" in logged_in.get("/courses/dev-f1").get_data(as_text=True)


def test_dashboard_shows_latest_recommendation(logged_in):
    assert "Take the diagnostic assessment" in logged_in.get("/dashboard").get_data(as_text=True)
    _submit(logged_in, _answers(2))
    html = logged_in.get("/dashboard").get_data(as_text=True)
    assert "Level recommended by your latest diagnostic assessment: <strong>Beginner</strong>" in html


def test_diagnostic_works_when_catalog_is_broken(logged_in, tmp_path, monkeypatch):
    import shutil
    copy_dir = tmp_path / "content"
    shutil.copytree(content.CONTENT_DIR, copy_dir)
    (copy_dir / "courses" / "c05.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(content, "CONTENT_DIR", str(copy_dir))
    content.load_catalog.cache_clear()
    try:
        assert logged_in.get("/diagnostic").status_code == 200
        assert logged_in.get("/diagnostic/take").status_code == 200
    finally:
        content.load_catalog.cache_clear()


# ------------------------------------------------------------- 저장소 (마이그레이션 3, Firestore)
def test_migration_3_on_phase2_database(sqlite_app, tmp_path, monkeypatch):
    monkeypatch.setitem(sqlite_app.config, "DATABASE", str(tmp_path / "phase2.db"))
    full = storage.SQLITE_MIGRATIONS
    with sqlite_app.app_context():
        storage.SQLITE_MIGRATIONS = full[:2]
        try:
            storage.init_db()
            db = storage.get_db()
            storage.create_user("old@example.com", "Old", "h")
            uid = storage.get_user_by_email("old@example.com")["id"]
            db.execute("INSERT INTO econ_enrollments (user_id, course_id, selected_difficulty, enrolled_at, content_version)"
                       " VALUES (?, 'dev-f1', 'advanced', '2026-11-01 00:00:00', 1)", (uid,))
            db.commit()
            storage.update_lesson_progress(uid, "dev-f1", "dev-f1-l1", ("material",), material_reviewed=True)
        finally:
            storage.SQLITE_MIGRATIONS = full
        assert storage.migrate_sqlite() == [3, 4, 5, 6, 7, 8, 9]   # Phase 3~8B 의 마이그레이션
        e = storage.get_enrollment(uid, "dev-f1")
        assert (e["selected_difficulty"], e["difficulty_source"]) == ("advanced", "manual")   # 기존 행 보존
        assert storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]["status"] == "completed"
        assert storage.list_diagnostic_attempts(uid) == []
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO econ_diagnostic_attempts (user_id, diagnostic_id, diagnostic_version, score, max_score,"
                       " recommended_level, results_json, by_category_json, thresholds_json, created_at)"
                       " VALUES (?, 'x', 1, 0, 12, 'expert', '[]', '{}', '{}', '2026-11-03 00:00:00')", (uid,))


def test_firestore_layout_and_old_enrollment_docs(firestore_app, fake_fs):
    with firestore_app.app_context():
        storage.create_user("a@example.com", "A", "h")
        attempt_id = storage.save_diagnostic_attempt("a@example.com", diagnostic.score(ANSWERS))
        assert storage.get_diagnostic_attempt("a@example.com", attempt_id)["score"] == 12
        assert storage.get_diagnostic_attempt("b@example.com", attempt_id) is None
        # Phase 2 때 저장된 문서에는 difficulty_source 가 없다 → manual 로 읽는다
        fake_fs.collection("users").document("a@example.com").collection("econ_enrollments").document("dev-f1").set(
            {"course_id": "dev-f1", "selected_difficulty": "beginner", "status": "active", "enrolled_at": None,
             "completed_at": None, "content_version": 1})
        assert storage.get_enrollment("a@example.com", "dev-f1")["difficulty_source"] == "manual"
    assert ("users", "a@example.com", "econ_diagnostic_attempts", attempt_id) in fake_fs.docs


def test_invalid_difficulty_source_rejected(sqlite_app):
    with sqlite_app.app_context(), pytest.raises(ValueError):
        storage.enroll_course(1, "dev-f1", "beginner", 1, difficulty_source="ai")
