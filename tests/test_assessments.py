"""Phase 4: 평가 스키마, 정답 격리, 결정적 채점, 제출·중복 방지·재응시·최고 점수, 레슨 진도 연결,
최종 평가 잠금·수료 규칙, 학생 간 분리, 공개 통제, 버전 보존, 마이그레이션 4, Firestore 계약.
화면·저장 테스트는 sqlite 와 가짜 Firestore 양쪽에서 돈다."""
import copy
import dataclasses
import json
import os
import re
import sqlite3

import pytest

from econova import assessments, content, grading, learning, storage
from tests.conftest import CSRF, login, set_csrf, signup
from tests.synthetic_keys import synthetic_full, write_synthetic_keys
from tests.test_econova_routes import _enroll, _post, _uid, take

C02_ASSESSMENTS = ("c02-l1-quiz", "c02-l2-quiz", "c02-l3-quiz", "c02-final")


def _public(aid, fixture=False):
    base = os.path.join(content.CONTENT_DIR, "dev_fixtures" if fixture else "", "assessments", f"{aid}.json")
    with open(base, encoding="utf-8") as f:
        return json.load(f)


def _raw(aid, fixture=False):
    """서버가 합친 것과 같은 전체 데이터. 실제 c02 정답 키는 저장소에 없으므로 합성 키를 붙인다."""
    return synthetic_full(_public(aid, fixture))


def _lessons_map(course_id="c02", only=None):
    course = content.load_catalog(True).course(course_id)
    return {l.id: (l.objectives, tuple(c["id"] for c in l.content.concepts) if l.content else ())
            for l in course.lessons if only is None or l.id == only}


def _parse(raw, aid=None, lesson=None, fixture=False, course="c02"):
    return assessments.parse_assessment(raw, aid or raw["id"], course, _lessons_map(course, lesson), fixture=fixture)


def _approve(raw):
    raw = copy.deepcopy(raw)
    raw["review"].update(status="approved", reviewer={"name": "Teacher Kim", "role": "teacher"}, reviewed_at="2026-11-10",
                         approved_at="2026-11-10")
    raw["review"]["history"].append({"status": "approved", "at": "2026-11-10", "by": "Teacher Kim"})
    for q in raw["questions"]:
        q["review_status"] = "approved"
    return raw


def _complete_lessons(client, course_id):
    """수강 → 모든 레슨 자료 확인 + 필수 퀴즈 제출."""
    course = content.get_catalog().course(course_id)
    for lesson in course.lessons:
        _post(client, f"/learn/{course_id}/{lesson.id}/material-reviewed")
        if "quiz" in lesson.requirements:
            take(client, f"/learn/{course_id}/{lesson.id}/quiz", lesson.quiz_assessment)


# ------------------------------------------------------------- c02 초안 평가
def test_c02_assessments_are_complete_drafts():
    course = content.load_catalog(False).course("c02")
    assert course.status == "coming_soon" and course.final_assessment_status == "draft"
    quizzes = [l.quiz_assessment for l in course.lessons]
    assert [q.id for q in quizzes] == list(C02_ASSESSMENTS[:3]) and course.final.id == "c02-final"
    for a in quizzes + [course.final]:
        assert a.review_status == "draft" and not a.approved and a.review["history"][-1]["by"] == "Claude Code (AI)"
        assert all(q["review_status"] == "draft" for q in a.questions)
        assert {q["type"] for q in a.questions} == {"mcq", "numeric"}
        assert len({q["difficulty"] for q in a.questions}) >= 2
    assert not any(l.quiz_approved for l in course.lessons) and not course.final_ready
    assert course.final.passing == {"score_ratio": 0.7, "status": "proposed", "note": course.final.passing["note"]}
    assert {q["lesson_id"] for q in course.final.questions} == {"c02-l1", "c02-l2", "c02-l3"}


def test_question_ids_are_unique_and_stable():
    cat = content.load_catalog(True)
    ids = []
    for c in cat.courses:
        for a in [l.quiz_assessment for l in c.lessons if l.quiz_assessment] + ([c.final] if c.final else []):
            assert all(q["id"].startswith(a.id.replace("-quiz", "")) for q in a.questions), a.id
            ids += [q["id"] for q in a.questions]
    assert len(ids) == len(set(ids)) and len(ids) >= 23 + 9


@pytest.mark.parametrize("aid, mutate, message", [
    ("c02-l1-quiz", lambda d: d.update(id="c02-l9-quiz"), "id does not match"),
    ("c02-l1-quiz", lambda d: d.update(kind="exam"), "kind"),
    ("c02-l1-quiz", lambda d: d.update(course_id="c03"), "course_id"),
    ("c02-l1-quiz", lambda d: d["questions"][1].update(id=d["questions"][0]["id"]), "duplicate question id"),
    ("c02-l1-quiz", lambda d: d["questions"][0].update(objective=9), "objective"),
    ("c02-l1-quiz", lambda d: d["questions"][0].update(concept_ids=["ghost"]), "concept_ids"),
    ("c02-l1-quiz", lambda d: d["questions"][0].update(difficulty="expert"), "difficulty"),
    ("c02-l1-quiz", lambda d: d["questions"][0].update(answer="z"), "the answer is not one of the choices"),
    ("c02-l1-quiz", lambda d: d["questions"][4].update(tolerance=-1), "tolerance"),
    ("c02-l1-quiz", lambda d: d["questions"][4].update(answer=55), "does not match the calculated result"),
    ("c02-l2-quiz", lambda d: d["questions"][4].update(answer=21), "does not match the calculated result"),
    ("c02-l1-quiz", lambda d: d["questions"][0].update(lesson_id="c02-l2"), "lesson_id"),
    ("c02-l1-quiz", lambda d: d.update(passing={"score_ratio": 0.5, "status": "proposed"}), "lesson quizzes do not have a passing standard"),
    ("c02-l1-quiz", lambda d: d.update(retakes={"allowed": "yes"}), "retakes"),
    ("c02-l1-quiz", lambda d: d["questions"][0].update(review_status="approved"), "cannot be approved on their own"),
    ("c02-l1-quiz", lambda d: d.update(questions=[]), "at least one question"),
    ("c02-final", lambda d: d.pop("passing"), "passing.score_ratio"),
    ("c02-final", lambda d: d["passing"].update(score_ratio=1.5), "at most 1"),
    ("c02-final", lambda d: d["passing"].update(status="dev_provisional"), "cannot be used in a real course"),
    ("c02-final", lambda d: d["passing"].update(status="approved"), "the assessment itself must be teacher-approved"),
    ("c02-final", lambda d: d.update(questions=[q for q in d["questions"] if q["lesson_id"] != "c02-l3"]), "does not cover lessons"),
    ("c02-final", lambda d: d.update(lesson_id="c02-l1"), "lesson_id"),
])
def test_invalid_assessment_is_rejected(aid, mutate, message):
    raw = _raw(aid)
    mutate(raw)
    lesson = None if aid == "c02-final" else aid.replace("-quiz", "")
    with pytest.raises(content.ContentError, match=message):
        _parse(raw, aid=aid, lesson=lesson)


@pytest.mark.parametrize("change, message", [
    (lambda d: d["questions"][0].update(review_status="draft"), "cannot contain unapproved questions"),
    (lambda d: d["review"].update(reviewer=None), "must have a human reviewer"),
    (lambda d: d["review"]["history"][-1].update(by="Claude Code (AI)"), "AI cannot approve"),
    (lambda d: d["review"]["reviewer"].update(role="fixture"), "must have a human reviewer"),
])
def test_approval_metadata_cannot_be_fabricated(change, message):
    raw = _approve(_raw("c02-l1-quiz"))
    assert _parse(raw, lesson="c02-l1").approved
    change(raw)
    with pytest.raises(content.ContentError, match=message):
        _parse(raw, lesson="c02-l1")


def test_course_json_must_match_assessment_files(tmp_path):
    import shutil
    shutil.copytree(os.path.join(content.CONTENT_DIR, "lessons"), tmp_path / "lessons")
    shutil.copytree(os.path.join(content.CONTENT_DIR, "assessments"), tmp_path / "assessments")
    with open(os.path.join(content.CONTENT_DIR, "courses", "c02.json"), encoding="utf-8") as f:
        course = json.load(f)
    bad = copy.deepcopy(course)
    bad["lessons"][0]["quiz"]["status"] = "approved"
    with pytest.raises(content.ContentError, match="does not match the quiz file's review status"):
        content.parse_course(bad, base_dir=str(tmp_path))
    bad = copy.deepcopy(course)
    bad["lessons"][0]["quiz"]["assessment_id"] = "c02-l2-quiz"
    with pytest.raises(content.ContentError, match="lesson_id is not a lesson in this course|is not this lesson's lesson quiz"):
        content.parse_course(bad, base_dir=str(tmp_path))
    bad = copy.deepcopy(course)
    bad["final_assessment"] = {"status": "approved", "assessment_id": "c02-final"}
    with pytest.raises(content.ContentError, match="does not match the final assessment file's review status"):
        content.parse_course(bad, base_dir=str(tmp_path))
    bad = copy.deepcopy(course)
    bad["final_assessment"] = {"status": "draft", "assessment_id": "c02-l1-quiz"}
    with pytest.raises(content.ContentError, match="is not a final assessment|this lesson|lesson_id"):
        content.parse_course(bad, base_dir=str(tmp_path))


def _write_split(assess_dir, keys_dir, full):
    """공개 정의는 콘텐츠 폴더에, 정답 키는 비공개 폴더에 나눠 쓴다 (실제 배치와 같게)."""
    from econova import private_content
    public, keys = private_content.split(full, full["id"])
    (assess_dir / f"{full['id']}.json").write_text(json.dumps(public, ensure_ascii=False), encoding="utf-8")
    (keys_dir / f"{full['id']}.answers.json").write_text(json.dumps(keys, ensure_ascii=False), encoding="utf-8")


def test_publication_requires_approved_final_and_passing(tmp_path, monkeypatch):
    """자료·퀴즈·최종 평가가 모두 교사 승인되고 합격 기준도 승인돼야 공개할 수 있다."""
    lessons_dir, assess_dir, keys_dir = tmp_path / "lessons", tmp_path / "assessments", tmp_path.parent / f"{tmp_path.name}-keys"
    lessons_dir.mkdir()
    assess_dir.mkdir()
    keys_dir.mkdir()
    monkeypatch.setenv("ECONOVA_PRIVATE_CONTENT_DIR", str(keys_dir))
    for lid in ("c02-l1", "c02-l2", "c02-l3"):
        with open(os.path.join(content.CONTENT_DIR, "lessons", f"{lid}.json"), encoding="utf-8") as f:
            doc = json.load(f)
        doc["review"].update(status="approved", reviewer={"name": "Teacher Kim", "role": "teacher"}, approved_at="2026-11-10")
        doc["review"]["history"].append({"status": "approved", "at": "2026-11-10", "by": "Teacher Kim"})
        (lessons_dir / f"{lid}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    for aid in C02_ASSESSMENTS:
        _write_split(assess_dir, keys_dir, _approve(_raw(aid)))
    with open(os.path.join(content.CONTENT_DIR, "courses", "c02.json"), encoding="utf-8") as f:
        course = json.load(f)
    course["status"] = "published"
    for lesson in course["lessons"]:
        lesson.update(status="published")
        lesson["material"]["status"] = "approved"
        lesson["quiz"]["status"] = "approved"
    course["final_assessment"]["status"] = "approved"
    with pytest.raises(content.ContentError, match="passing criteria are not approved"):   # 합격 기준이 아직 proposed
        content.parse_course(copy.deepcopy(course), base_dir=str(tmp_path))
    final = _approve(_raw("c02-final"))
    final["passing"]["status"] = "approved"
    with pytest.raises(content.ContentError, match="passing.review_id"):   # 관리자 검토 기록 번호 없는 합격 기준 승인
        _write_split(assess_dir, keys_dir, final)
        content.parse_course(copy.deepcopy(course), base_dir=str(tmp_path))
    final["passing"]["review_id"] = "7"
    _write_split(assess_dir, keys_dir, final)
    parsed = content.parse_course(copy.deepcopy(course), base_dir=str(tmp_path))
    assert parsed.published and parsed.final_ready and parsed.final.passing_usable(False)
    course["final_assessment"] = {"status": "upcoming"}
    with pytest.raises(content.ContentError, match="no approved final assessment"):
        content.parse_course(course, base_dir=str(tmp_path))


def test_passing_policy_usability():
    final = content.load_catalog(True).course("dev-f1").final
    assert final.passing_usable(True) and not final.passing_usable(False)   # 개발용 기준은 실제 강좌에 못 씀
    proposed = dataclasses.replace(final, passing={**final.passing, "status": "proposed"})
    assert not proposed.passing_usable(True)


# ------------------------------------------------------------- 정답 격리
def test_public_questions_hide_answer_keys():
    for c in content.load_catalog(True).courses:
        for a in [l.quiz_assessment for l in c.lessons if l.quiz_assessment] + ([c.final] if c.final else []):
            for pq in a.public_questions():
                assert not {"answer", "tolerance", "explanation", "check", "concept_ids", "source_ids", "review_status"} & set(pq)


def test_quiz_page_does_not_leak_answers(logged_in, fixtures_on):
    _enroll(logged_in, "dev-f1")
    html = logged_in.get("/learn/dev-f1/dev-f1-l1/quiz").get_data(as_text=True)
    quiz = content.get_catalog().course("dev-f1").lesson("dev-f1-l1").quiz_assessment
    assert html.count('class="dg-question"') == len(quiz.questions)
    for q in quiz.questions:
        assert q["explanation"] not in html
    body = html.split("<form")[1].split("</form>")[0]
    assert "answer" not in body.replace('name="q_', "").lower() and "data-correct" not in body


# ------------------------------------------------------------- 채점
Q_MCQ = {"id": "m", "type": "mcq", "choices": ({"id": "a"}, {"id": "b"}), "answer": "a", "points": 1}
Q_NUM = {"id": "n", "type": "numeric", "answer": 0.58, "tolerance": 0.01, "points": 2}


@pytest.mark.parametrize("raw, ok", [("a", True), ("b", False), ("z", False), ("", False), (" a", False), ("A", False)])
def test_mcq_grading(raw, ok):
    assert grading.is_correct(Q_MCQ, raw) is ok


@pytest.mark.parametrize("raw, ok", [("0.58", True), ("0.57", True), ("0.59", True), ("0.5701", True), ("0.569", False),
                                     ("0.591", False), (".58", True), ("+0.58", True), ("0,58", False), ("58%", False),
                                     ("5.8e-1", False), ("inf", False), ("nan", False), ("1/2", False), ("", False)])
def test_numeric_tolerance_boundaries(raw, ok):
    assert grading.is_correct(Q_NUM, raw) is ok


def test_zero_tolerance_is_exact():
    q = {"id": "x", "type": "numeric", "answer": 54.0, "tolerance": 0.0}
    assert grading.is_correct(q, "54") and grading.is_correct(q, "54.000") and not grading.is_correct(q, "54.01")


def test_grade_is_deterministic_and_weighted():
    r1 = grading.grade([Q_MCQ, Q_NUM], {"m": "a", "n": "0.6", "zzz": "1"})
    assert r1 == grading.grade([Q_MCQ, Q_NUM], {"m": "a", "n": "0.6", "zzz": "1"})
    assert (r1["score"], r1["max_score"], round(r1["ratio"], 4)) == (1.0, 3.0, 0.3333)
    assert [r["id"] for r in r1["results"]] == ["m", "n"]
    assert grading.grade([Q_MCQ, Q_NUM], {})["score"] == 0
    assert grading.grade([Q_MCQ], {"m": "a" * 500})["results"][0]["answer"] == "a" * grading.MAX_ANSWER_LENGTH


# ------------------------------------------------------------- 제출·중복·재응시 (양쪽 저장소)
pytestmark = pytest.mark.usefixtures("fixtures_on")


def _token(client, url):
    return re.search(r'name="submission_token" value="([^"]+)"', client.get(url).get_data(as_text=True)).group(1)


def test_quiz_submission_records_attempt_and_progress(app, logged_in):
    _enroll(logged_in, "dev-f1")
    quiz = content.get_catalog().course("dev-f1").lesson("dev-f1-l1").quiz_assessment
    result_url = take(logged_in, "/learn/dev-f1/dev-f1-l1/quiz", quiz, correct=False)
    html = logged_in.get(result_url).get_data(as_text=True)
    assert "0 / 2.0 points (0%)" in html.replace("0.0", "0") or "(0%)" in html
    assert "This is a dev test question." in html and "Your score does not affect lesson completion" in html
    with app.app_context():
        uid = _uid(app)
        [a] = storage.list_assessment_attempts(uid)
        rec = storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]
    assert (a["kind"], a["assessment_version"], a["course_content_version"], a["ratio"], a["passed"]) == \
        ("lesson_quiz", quiz.version, 1, 0.0, None)
    assert a["results"][0]["version"] == quiz.questions[0]["version"] and a["status"] == "submitted"
    # 자료를 안 봤으므로 진행 중. 0점이어도 '제출'은 완료 조건으로 인정
    assert (rec["status"], rec["quiz_submitted"], rec["quiz_score"], rec["quiz_submission_id"]) == \
        ("in_progress", True, 0.0, a["id"])
    _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    with app.app_context():
        assert storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]["status"] == "completed"


def test_submission_requires_valid_token(app, logged_in):
    _enroll(logged_in, "dev-f1")
    url = "/learn/dev-f1/dev-f1-l1/quiz"
    assert logged_in.post(url, data={"csrf_token": CSRF}).status_code == 400            # 토큰 없음
    assert logged_in.post(url, data={"csrf_token": CSRF, "submission_token": "forged"}).status_code == 400   # 형식이 틀린 토큰
    res = logged_in.post(url, data={"csrf_token": CSRF, "submission_token": "forged-token-aaaaaaaa"})   # 발급하지 않은 토큰
    assert res.status_code == 303 and "This page was out of date" in logged_in.get(res.headers["Location"]).get_data(as_text=True)
    with app.app_context():
        assert storage.list_assessment_attempts(_uid(app)) == []


def test_duplicate_submission_is_saved_once(app, logged_in):
    _enroll(logged_in, "dev-f1")
    url = "/learn/dev-f1/dev-f1-l1/quiz"
    token = _token(logged_in, url)
    data = {"csrf_token": CSRF, "submission_token": token, "q_dev-f1-l1-q1": "a", "q_dev-f1-l1-q2": "6"}
    first = logged_in.post(url, data=data)
    second = logged_in.post(url, data={**data, "q_dev-f1-l1-q2": "7"})   # 같은 토큰으로 다시 (두 번 클릭)
    assert first.headers["Location"] == second.headers["Location"]
    with app.app_context():
        uid = _uid(app)
        attempts = storage.list_assessment_attempts(uid)
        assert len(attempts) == 1 and attempts[0]["ratio"] == 1.0
        with pytest.raises(storage.DuplicateSubmission):   # 저장소 수준에서도 한 번만
            storage.save_assessment_attempt(uid, {**attempts[0], "answers": {}, "results": [], "passing": None}, token)


def test_retakes_keep_best_score_without_inflating_progress(app, logged_in):
    _enroll(logged_in, "dev-f1")
    quiz = content.get_catalog().course("dev-f1").lesson("dev-f1-l1").quiz_assessment
    _post(logged_in, "/learn/dev-f1/dev-f1-l1/material-reviewed")
    take(logged_in, "/learn/dev-f1/dev-f1-l1/quiz", quiz, correct=False)
    with app.app_context():
        first = storage.list_lesson_progress(_uid(app), "dev-f1")["dev-f1-l1"]
    take(logged_in, "/learn/dev-f1/dev-f1-l1/quiz", quiz, correct=True)
    take(logged_in, "/learn/dev-f1/dev-f1-l1/quiz", quiz, correct=False)
    with app.app_context():
        uid = _uid(app)
        rec = storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]
        assert len(storage.list_assessment_attempts(uid, assessment_id=quiz.id)) == 3
        board = learning.dashboard(uid)
    assert rec["quiz_score"] == 1.0 and rec["status"] == "completed" and rec["completed_at"] == first["completed_at"]
    assert board["completed_lessons"] == 1


def test_quiz_progress_is_independent_between_courses(app, logged_in):
    _enroll(logged_in, "dev-f1")
    _enroll(logged_in, "dev-f2")
    take(logged_in, "/learn/dev-f2/dev-f2-l1/quiz", content.get_catalog().course("dev-f2").lesson("dev-f2-l1").quiz_assessment)
    with app.app_context():
        assert storage.list_lesson_progress(_uid(app), "dev-f1") == {}
        assert storage.list_assessment_attempts(_uid(app), course_id="dev-f1") == []


# ------------------------------------------------------------- 최종 평가와 수료
def test_final_is_locked_until_all_lessons_completed(app, logged_in):
    assert logged_in.get("/courses/dev-f1/final").status_code == 303                   # 수강 전
    _enroll(logged_in, "dev-f1")
    res = logged_in.get("/courses/dev-f1/final")
    assert res.status_code == 303 and "The final assessment opens once you complete all lessons" in logged_in.get(res.headers["Location"]).get_data(as_text=True)
    assert logged_in.post("/courses/dev-f1/final", data={"csrf_token": CSRF, "submission_token": "x"}).status_code == 303
    assert "Locked</span>" in logged_in.get("/courses/dev-f1").get_data(as_text=True)
    _complete_lessons(logged_in, "dev-f1")
    html = logged_in.get("/courses/dev-f1/final").get_data(as_text=True)
    assert "About this final assessment" in html and "Temporary development standard" in html and "up to 3 attempts" in html
    assert logged_in.get("/courses/c02/final").status_code == 403                        # 공개 전 강좌


def test_failing_then_passing_final_completes_course_once(app, logged_in):
    _enroll(logged_in, "dev-f2")
    _complete_lessons(logged_in, "dev-f2")
    final = content.get_catalog().course("dev-f2").final
    fail_url = take(logged_in, "/courses/dev-f2/final", final, correct=False)
    assert "You did not reach" in logged_in.get(fail_url).get_data(as_text=True)
    with app.app_context():
        assert storage.get_enrollment(_uid(app), "dev-f2")["status"] == "active"
    pass_url = take(logged_in, "/courses/dev-f2/final", final, correct=True)
    html = logged_in.get(pass_url).get_data(as_text=True)
    assert "You <strong>reached</strong>" in html and "test completion under the temporary development standard" in html
    with app.app_context():
        e = storage.get_enrollment(_uid(app), "dev-f2")
        first_completed = e["completed_at"]
    assert (e["status"], e["completion_policy"]) == ("completed", "dev_provisional")
    assert e["completion_attempt_id"] == pass_url.rsplit("/", 1)[1]
    take(logged_in, "/courses/dev-f2/final", final, correct=True)   # 3번째(마지막) 응시도 합격
    with app.app_context():
        e2 = storage.get_enrollment(_uid(app), "dev-f2")
    assert e2["completed_at"] == first_completed and e2["completion_attempt_id"] == e["completion_attempt_id"]
    assert "Course completed (test)" in logged_in.get("/dashboard").get_data(as_text=True)
    summary = logged_in.get("/courses/dev-f2/completion").get_data(as_text=True)
    assert "Course completed ·" in summary and "Best result: 100% (Passed) · 3 attempts" in summary


def test_final_attempt_limit(app, logged_in):
    _enroll(logged_in, "dev-f2")
    _complete_lessons(logged_in, "dev-f2")
    final = content.get_catalog().course("dev-f2").final
    tokens = []
    for _ in range(3):
        tokens.append(_token(logged_in, "/courses/dev-f2/final"))
        take(logged_in, "/courses/dev-f2/final", final, correct=False)
    res = logged_in.get("/courses/dev-f2/final")
    assert res.status_code == 302 and res.headers["Location"].endswith("/courses/dev-f2/assessments")
    with app.app_context():
        uid = _uid(app)
        assert learning.attempts_left(uid, final) == 0
        course = content.get_catalog().course("dev-f2")
        with pytest.raises(learning.LearningError, match="used all of your attempts"):
            learning.submit_assessment(uid, course, final, {}, "new-token")
        assert len(storage.list_assessment_attempts(uid, assessment_id=final.id)) == 3


def test_unapproved_passing_policy_never_awards_completion(app, logged_in):
    _enroll(logged_in, "dev-f2")
    _complete_lessons(logged_in, "dev-f2")
    course = content.get_catalog().course("dev-f2")
    proposed = dataclasses.replace(course.final, passing={**course.final.passing, "status": "proposed"})
    with app.app_context():
        uid = _uid(app)
        answers = {q["id"]: q["answer"] if q["type"] == "mcq" else f"{q['answer']:g}" for q in proposed.questions}
        attempt_id, created = learning.submit_assessment(uid, course, proposed, answers, "tok-1")
        assert created and storage.get_assessment_attempt(uid, attempt_id)["passed"] is True
        assert storage.get_enrollment(uid, "dev-f2")["status"] == "active"   # 합격해도 수료 아님


# ------------------------------------------------------------- 학생 간 분리
def test_students_cannot_see_each_others_attempts(app, client):
    signup(client)
    login(client)
    set_csrf(client)
    _enroll(client, "dev-f1")
    mine = take(client, "/learn/dev-f1/dev-f1-l1/quiz", content.get_catalog().course("dev-f1").lesson("dev-f1-l1").quiz_assessment)
    client.post("/logout", data={"csrf_token": CSRF})
    signup(client, email="other@example.com")
    login(client, email="other@example.com")
    set_csrf(client)
    assert client.get(mine).status_code == 404
    _enroll(client, "dev-f1")
    assert "You haven't submitted any assessments yet." in client.get("/courses/dev-f1/assessments").get_data(as_text=True)
    with app.app_context():
        assert storage.get_assessment_attempt(_uid(app, "other@example.com"), mine.rsplit("/", 1)[1]) is None


def test_no_route_modifies_attempts():
    import app as app_module
    # 예외는 AI 오답 설명 요청 하나뿐: AI 대화 기록만 쓰고 응시 기록은 바꾸지 않는다 (tests/test_ai_features.py 가 확인)
    read_only_posts = {"/assessments/attempts/<attempt_id>/explain"}
    for rule in app_module.app.url_map.iter_rules():
        if "attempt" in rule.rule and rule.rule not in read_only_posts:
            assert rule.methods - {"HEAD", "OPTIONS"} == {"GET"}, rule.rule


# ------------------------------------------------------------- 버전 보존
def test_results_keep_original_version(app, logged_in, monkeypatch):
    _enroll(logged_in, "dev-f1")
    lesson = content.get_catalog().course("dev-f1").lesson("dev-f1-l1")
    url = take(logged_in, "/learn/dev-f1/dev-f1-l1/quiz", lesson.quiz_assessment)
    qs = list(lesson.quiz_assessment.questions)
    old_version = lesson.quiz_assessment.version
    qs[0] = {**qs[0], "version": qs[0]["version"] + 1, "prompt": "Changed question"}
    new_quiz = dataclasses.replace(lesson.quiz_assessment, version=old_version + 1, questions=tuple(qs))
    new_course = dataclasses.replace(content.get_catalog().course("dev-f1"), lessons=tuple(
        dataclasses.replace(l, quiz_assessment=new_quiz) if l.id == "dev-f1-l1" else l
        for l in content.get_catalog().course("dev-f1").lessons))
    cat = content.get_catalog()
    patched = dataclasses.replace(cat, courses=tuple(new_course if c.id == "dev-f1" else c for c in cat.courses))
    monkeypatch.setattr(learning, "catalog", lambda: patched)
    html = logged_in.get(url).get_data(as_text=True)
    assert f"based on version {old_version} of the assessment" in html and "Changed question" not in html and "the question has changed" in html
    assert "100%" in html   # 저장된 점수는 다시 계산하지 않는다


# ------------------------------------------------------------- 저장소 (마이그레이션 4, Firestore)
def test_migration_4_on_phase3_database(sqlite_app, tmp_path, monkeypatch):
    monkeypatch.setitem(sqlite_app.config, "DATABASE", str(tmp_path / "phase3.db"))
    full = storage.SQLITE_MIGRATIONS
    with sqlite_app.app_context():
        storage.SQLITE_MIGRATIONS = full[:3]
        try:
            storage.init_db()
            storage.create_user("old@example.com", "Old", "h")
            uid = storage.get_user_by_email("old@example.com")["id"]
            storage.enroll_course(uid, "dev-f1", "advanced", 1)
            storage.update_lesson_progress(uid, "dev-f1", "dev-f1-l1", ("material",), material_reviewed=True)
            from econova import diagnostic
            storage.save_diagnostic_attempt(uid, diagnostic.score({}))
        finally:
            storage.SQLITE_MIGRATIONS = full
        assert storage.migrate_sqlite() == [4, 5, 6, 7, 8, 9, 10]   # Phase 4~8B 의 마이그레이션
        e = storage.get_enrollment(uid, "dev-f1")
        assert (e["selected_difficulty"], e["status"], e["completion_attempt_id"], e["completion_policy"]) == \
            ("advanced", "active", None, None)
        assert storage.list_lesson_progress(uid, "dev-f1")["dev-f1-l1"]["status"] == "completed"
        assert len(storage.list_diagnostic_attempts(uid)) == 1 and storage.list_assessment_attempts(uid) == []
        db = storage.get_db()
        for kind, ratio in (("exam", 0.5), ("final", 1.5)):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("INSERT INTO econ_assessment_attempts (user_id, enrollment_id, course_id, assessment_id,"
                           " assessment_version, course_content_version, kind, submission_token, answers_json, results_json,"
                           " score, max_score, ratio, created_at) VALUES (?, 1, 'dev-f1', 'x', 1, 1, ?, 't', '{}', '[]', 0, 1, ?,"
                           " '2026-11-03 00:00:00')", (uid, kind, ratio))
            db.rollback()


def test_attempt_requires_enrollment(app):
    with app.app_context():
        storage.create_user("a@example.com", "A", "h")
        uid = storage.get_user_by_email("a@example.com")["id"]
        record = {"course_id": "dev-f1", "lesson_id": None, "assessment_id": "dev-f1-final", "assessment_version": 1,
                  "course_content_version": 1, "kind": "final", "score": 1, "max_score": 1, "ratio": 1.0, "passed": True,
                  "answers": {}, "results": [], "passing": {}}
        with pytest.raises(storage.NotEnrolledError):
            storage.save_assessment_attempt(uid, record, "t1")
        with pytest.raises(storage.NotEnrolledError):
            storage.complete_enrollment(uid, "dev-f1", "1", "approved")
        storage.enroll_course(uid, "dev-f1", "beginner", 1)
        aid = storage.save_assessment_attempt(uid, record, "t1")
        assert storage.complete_enrollment(uid, "dev-f1", aid, "approved") is True
        assert storage.complete_enrollment(uid, "dev-f1", "other", "approved") is False
        assert storage.get_enrollment(uid, "dev-f1")["completion_attempt_id"] == aid


def test_firestore_attempt_layout(firestore_app, fake_fs):
    with firestore_app.app_context():
        storage.create_user("a@example.com", "A", "h")
        storage.enroll_course("a@example.com", "dev-f1", "beginner", 1)
        record = {"course_id": "dev-f1", "lesson_id": "dev-f1-l1", "assessment_id": "dev-f1-l1-quiz", "assessment_version": 1,
                  "course_content_version": 1, "kind": "lesson_quiz", "score": 2, "max_score": 2, "ratio": 1.0, "passed": None,
                  "answers": {"a": "b"}, "results": [{"id": "a"}], "passing": None}
        aid = storage.save_assessment_attempt("a@example.com", record, "tok-xyz")
        assert aid == "tok-xyz" and storage.find_attempt_by_token("a@example.com", "tok-xyz")["ratio"] == 1.0
    assert ("users", "a@example.com", "econ_assessment_attempts", "tok-xyz") in fake_fs.docs


# ------------------------------------------------------------- 교육 검토 문서
def test_review_package_needs_keys_and_private_location(app, tmp_path):
    out = tmp_path / "review.md"
    res = app.test_cli_runner().invoke(args=["review-package", "c02", "--output", str(out)])
    assert res.exit_code != 0 and "some assessments have no answer key" in res.output and not out.exists()   # 키 없이 만들지 않는다
    inside = os.path.join(content.CONTENT_DIR, "review-package.md")                       # 저장소 안, 무시되지 않는 곳
    res = app.test_cli_runner().invoke(args=["review-package", "c02", "--output", inside])
    assert res.exit_code != 0 and "where it could be committed" in res.output and not os.path.exists(inside)


def test_review_package_is_generated_and_not_served(app, logged_in, tmp_path, monkeypatch):
    keys_dir = tmp_path / "private"
    keys_dir.mkdir()
    for aid in C02_ASSESSMENTS:
        write_synthetic_keys(str(keys_dir), _public(aid))
    monkeypatch.setenv("ECONOVA_PRIVATE_CONTENT_DIR", str(keys_dir))
    content.load_catalog.cache_clear()
    try:
        res = app.test_cli_runner().invoke(args=["review-package", "c02"])   # 기본 위치: <비공개 폴더>/review/
        assert res.exit_code == 0, res.output
        out = keys_dir / "review" / "c02-review-package.md"
        text = out.read_text(encoding="utf-8")
        assert text.startswith("<!-- ECONOVA-TEACHER-ONLY")
        course = content.load_catalog(False).course("c02")
        assert all(a.answer_keys for a in [l.quiz_assessment for l in course.lessons] + [course.final])
    finally:
        content.load_catalog.cache_clear()
    for aid in C02_ASSESSMENTS:
        assert aid in text
    assert "proposed, not approved" in text and "unreviewed drafts" in text and "Correct answer" in text
    course = content.load_catalog(False).course("c02")
    for a in [l.quiz_assessment for l in course.lessons] + [course.final]:
        for q in a.questions:
            assert q["id"] in text and q["explanation"] in text
    for path in ("/docs/review/c02-review-package.md", "/static/../docs/review/c02-review-package.md", "/review/c02"):
        assert logged_in.get(path).status_code == 404
