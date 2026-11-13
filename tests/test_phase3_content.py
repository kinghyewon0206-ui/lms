"""Phase 3 학습자료: c02 초안 구조, 난이도 일관성, 출처 무결성, 검토·공개 통제, 레슨 렌더링, 교사용 미리보기."""
import copy
import json
import os
import subprocess
import sys

import pytest

from econova import content, lesson_content
from tests.conftest import CSRF, ROOT

C02_LESSONS = ("c02-l1", "c02-l2", "c02-l3")


def _doc_raw(lesson_id="c02-l1"):
    with open(os.path.join(content.CONTENT_DIR, "lessons", f"{lesson_id}.json"), encoding="utf-8") as f:
        return json.load(f)


def _sources():
    return content.read_sources()


UNVERIFIED = "test-unverified-source"


def _sources_with_unverified():
    """실제 레지스트리에는 미확인 출처가 없으므로(확인 못 한 출처는 삭제) 검사용 미확인 출처 하나를 더한다."""
    with open(os.path.join(content.CONTENT_DIR, "sources.json"), encoding="utf-8") as f:
        data = json.load(f)
    data["sources"].append({"id": UNVERIFIED, "title": "Unverified test source", "author": "Test", "url": "https://example.org/x",
                            "concepts": ["food_waste"], "lesson_ids": [], "license": "Not verified",
                            "verification": {"status": "unverified", "checked_at": "2026-11-13", "method": "For tests"}})
    return lesson_content.parse_sources(data)


def _parse(raw, lesson_id="c02-l1", fixture=False):
    return lesson_content.parse_material(raw, lesson_id, _sources(), fixture=fixture)


def _approve(raw, by="Ms. Kim", role="teacher"):
    raw = copy.deepcopy(raw)
    raw["review"].update(status="approved", reviewer={"name": by, "role": role}, reviewed_at="2026-11-10",
                         approved_at="2026-11-10")
    raw["review"]["history"].append({"status": "approved", "at": "2026-11-10", "by": by, "note": "Review complete"})
    return raw


# ------------------------------------------------------------- c02 초안 구조
def test_c02_lessons_have_complete_draft_material():
    course = content.load_catalog(False).course("c02")
    assert course.status == "coming_soon" and not course.published and course.content_version >= 2
    for lesson in course.lessons:
        doc = lesson.content
        assert doc is not None and doc.lesson_id == lesson.id
        assert doc.review_status == "draft" and doc.review["reviewer"] is None and doc.review["approved_at"] is None
        assert doc.review["history"][-1]["by"] == "Claude Code (AI)"
        assert not lesson.material_approved   # 초안은 학생용 자료로 쓰지 않는다
        assert lesson.objectives == doc.objectives and len(doc.objectives) >= 3
        assert set(doc.levels) == set(lesson_content.LEVELS)
        assert len(doc.concepts) >= 4 and all(c["source_ids"] for c in doc.concepts)
        for level in lesson_content.LEVELS:
            assert doc.levels[level]["summary"] and doc.levels[level]["sections"]
            assert doc.examples_for(level)
        assert doc.graphs and doc.real_world_examples and doc.key_takeaways
        assert len(doc.sdg_case["options"]) >= 2
        assert all(o["benefits"] and o["costs"] and o["assumptions"] for o in doc.sdg_case["options"])
        assert set(doc.sdg_case["sdgs"]) <= {2, 12}   # c02 의 SDG 와 맞음


def test_every_level_covers_every_concept():
    for lid in C02_LESSONS:
        doc = content.load_catalog(False).course("c02").lesson(lid).content
        concept_ids = {c["id"] for c in doc.concepts}
        for level in lesson_content.LEVELS:
            covered = {cid for s in doc.levels[level]["sections"] for cid in s["concept_ids"]}
            assert covered == concept_ids, (lid, level)


def test_levels_differ_in_depth():
    doc = content.load_catalog(False).course("c02").lesson("c02-l1").content
    text = {lv: " ".join(p for s in doc.levels[lv]["sections"] for p in s["paragraphs"]) for lv in lesson_content.LEVELS}
    assert "Qd = a − bP" in text["advanced"] and "Qd = a − bP" not in text["beginner"]
    assert len(set(text.values())) == 3


def test_numbers_in_content_are_machine_checked():
    # 예제의 계산·그래프 균형점이 틀리면 로더가 거절한다
    raw = _doc_raw("c02-l2")
    raw["worked_examples"][2]["check"]["shortage"] = 17
    with pytest.raises(content.ContentError, match="calculated result is incorrect"):
        _parse(raw, "c02-l2")
    raw = _doc_raw("c02-l2")
    raw["graphs"][0]["expected_equilibria"][0]["price"] = 31
    with pytest.raises(content.ContentError, match="stated equilibrium does not match"):
        _parse(raw, "c02-l2")
    raw = _doc_raw("c02-l3")
    raw["worked_examples"][1]["check"]["expected"] = 0.7
    with pytest.raises(content.ContentError, match="calculated result is incorrect"):
        _parse(raw, "c02-l3")
    raw = _doc_raw("c02-l2")   # 사중손실 예제
    next(e for e in raw["worked_examples"] if e["id"] == "c02-l2-we5")["check"]["expected"] = 28
    with pytest.raises(content.ContentError, match="calculated result is incorrect"):
        _parse(raw, "c02-l2")


def test_shift_only_graphs_cannot_claim_an_equilibrium():
    """균형을 배우기 전 레슨(L1)은 곡선 이동만 보여 준다. 한쪽 곡선만 있는 그래프에 균형점을 적으면 거절한다."""
    raw = _doc_raw("c02-l1")
    assert all(not g["expected_equilibria"] for g in raw["graphs"])
    assert {bool(g["demand"]) for g in raw["graphs"]} == {True, False}   # 수요 이동 그림, 공급 이동 그림
    raw["graphs"][0]["expected_equilibria"] = [{"demand": "D1", "supply": "S", "price": 30, "quantity": 40}]
    with pytest.raises(content.ContentError, match="curve name that does not exist"):
        _parse(raw)
    raw = _doc_raw("c02-l1")
    raw["graphs"][0]["demand"] = []
    with pytest.raises(content.ContentError, match="at least one demand curve or supply curve"):
        _parse(raw)


# ------------------------------------------------------------- 출처
def test_source_registry_integrity():
    sources = _sources()
    assert len(sources) >= 10 and all(s.url.startswith("https://") for s in sources.values())
    unverified = [s.id for s in sources.values() if not s.verified]
    assert unverified == []                    # 확인하지 못한 출처(UNEP 보고서)는 레지스트리에서 뺐다
    cat = content.load_catalog(False)
    cited = {sid for cid in ("c01", "c02") for lesson in cat.course(cid).lessons for sid in lesson.content.source_ids}
    assert cited and all(sources[sid].verified for sid in cited)   # c01·c02 는 확인된 출처만 인용
    for s in sources.values():
        if s.verified:
            assert s.checked_at and s.method and s.license


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["sources"].append(copy.deepcopy(d["sources"][0])), "duplicate source id"),
    (lambda d: d["sources"][0].update(url="http://openstax.org/x"), "https"),
    (lambda d: d["sources"][0]["verification"].update(checked_at=""), "check date"),
    (lambda d: d["sources"][0]["verification"].update(status="ok"), "verification.status"),
])
def test_invalid_source_registry(mutate, message):
    with open(os.path.join(content.CONTENT_DIR, "sources.json"), encoding="utf-8") as f:
        data = json.load(f)
    mutate(data)
    with pytest.raises(content.ContentError, match=message):
        lesson_content.parse_sources(data)


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["concepts"][0].update(source_ids=["no-such-source"]), "not in the source registry"),
    (lambda d: d["real_world_examples"][0].update(source_ids=["un-sdg-12"]), "are missing from source_ids"),
    (lambda d: d.update(source_ids=d["source_ids"] + [UNVERIFIED]), None),   # 초안은 미확인 출처 허용
])
def test_source_references(mutate, message):
    raw = _doc_raw()
    mutate(raw)
    if message is None:
        assert lesson_content.parse_material(raw, "c02-l1", _sources_with_unverified()).source_ids[-1] == UNVERIFIED
    else:
        with pytest.raises(content.ContentError, match=message):
            _parse(raw)


# ------------------------------------------------------------- 형식·난이도 검사
@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["levels"].pop("advanced"), "levels must include all three difficulty levels"),
    (lambda d: d["levels"]["intermediate"]["sections"].pop(), "does not cover key concepts"),
    (lambda d: d["levels"]["beginner"]["sections"][0]["concept_ids"].append("ghost"), "refers to undefined concepts"),
    (lambda d: d["concepts"].append(copy.deepcopy(d["concepts"][0])), "duplicate concept id"),
    (lambda d: d.update(worked_examples=[e for e in d["worked_examples"] if e["level"] != "advanced"]), "no worked example for the advanced level"),
    (lambda d: d["worked_examples"][0].update(level="expert"), "level"),
    (lambda d: d["graphs"][0]["demand"][0].update(b=-2), "law of demand"),
    (lambda d: d["sdg_case"].update(options=d["sdg_case"]["options"][:1]), "at least two policy options"),
    (lambda d: d["sdg_case"].update(sdgs=[18]), "1-17"),
    (lambda d: d.update(lesson_id="c02-l9"), "lesson_id"),
    (lambda d: d["review"].update(status="live"), "review.status"),
    (lambda d: d["review"]["history"].append({"status": "in_review", "at": "2026-11-04", "by": "Ms. Kim"}), "last status in the review history"),
])
def test_invalid_material_is_rejected(mutate, message):
    raw = _doc_raw()
    mutate(raw)
    with pytest.raises(content.ContentError, match=message):
        _parse(raw)


# ------------------------------------------------------------- 검토·승인 규칙
def test_review_workflow_states():
    raw = _doc_raw()
    in_review = copy.deepcopy(raw)
    in_review["review"]["status"] = "in_review"
    in_review["review"]["history"].append({"status": "in_review", "at": "2026-11-05", "by": "Ms. Kim", "note": "Review started"})
    assert _parse(in_review).review_status == "in_review"
    approved = _parse(_approve(raw))
    assert approved.approved and approved.review["reviewer"]["name"] == "Ms. Kim"
    published = _approve(raw)
    published["review"]["status"] = "published"
    published["review"]["history"].append({"status": "published", "at": "2026-11-11", "by": "Ms. Kim"})
    assert _parse(published).review_status == "published"


@pytest.mark.parametrize("change, message", [
    (lambda d: d["review"].update(reviewer=None), "must have a human reviewer"),
    (lambda d: d["review"].update(approved_at=None), "approved_at"),
    (lambda d: d["review"]["reviewer"].update(role="student"), "must have a human reviewer"),
    (lambda d: d["review"]["reviewer"].update(role="fixture"), "must have a human reviewer"),          # fixture 역할은 실제 강좌에 못 씀
    (lambda d: d["review"]["reviewer"].update(name="Claude Code"), "must have a human reviewer"),
    (lambda d: d["review"]["history"][-1].update(by="Claude Code (AI)"), "AI cannot approve"),
    (lambda d: d["review"]["history"][-1].update(by="AI review"), "AI cannot approve"),
])
def test_ai_or_incomplete_approval_is_rejected(change, message):
    raw = _approve(_doc_raw())
    change(raw)
    with pytest.raises(content.ContentError, match=message):
        _parse(raw)


def test_approved_material_cannot_cite_unverified_source():
    raw = _approve(_doc_raw())
    raw["source_ids"].append(UNVERIFIED)
    with pytest.raises(content.ContentError, match="may cite only verified sources"):
        lesson_content.parse_material(raw, "c02-l1", _sources_with_unverified())


def test_course_publication_still_requires_approved_quiz(tmp_path, monkeypatch):
    # 자료를 승인해도 퀴즈(Phase 4)가 없으면 c02 를 published 로 둘 수 없다
    lessons = tmp_path / "lessons"
    lessons.mkdir()
    for lid in C02_LESSONS:
        (lessons / f"{lid}.json").write_text(json.dumps(_approve(_doc_raw(lid)), ensure_ascii=False), encoding="utf-8")
    import shutil
    shutil.copytree(os.path.join(content.CONTENT_DIR, "assessments"), tmp_path / "assessments")   # 퀴즈·최종 평가(draft)
    with open(os.path.join(content.CONTENT_DIR, "courses", "c02.json"), encoding="utf-8") as f:
        course = json.load(f)
    for lesson in course["lessons"]:
        lesson["status"] = "published"
        lesson["material"]["status"] = "approved"
    parsed = content.parse_course(copy.deepcopy(course), base_dir=str(tmp_path))
    assert all(lesson.material_approved for lesson in parsed.lessons) and not parsed.published
    course["status"] = "published"
    with pytest.raises(content.ContentError, match="quiz"):
        content.parse_course(course, base_dir=str(tmp_path))


# ------------------------------------------------------------- 학생 화면: 공개 통제와 렌더링
def test_draft_c02_content_never_reaches_students(logged_in, fixtures_on):
    paragraph = _doc_raw("c02-l1")["levels"]["beginner"]["sections"][0]["paragraphs"][0][:30]
    for path in ("/courses", "/courses/c02", "/dashboard", "/learn/c02/c02-l1", "/learn/c02/c02-l1?level=advanced"):
        html = logged_in.get(path).get_data(as_text=True)
        assert paragraph not in html and "Qd = a − bP" not in html, path
    assert logged_in.get("/learn/c02/c02-l1").status_code == 403


def test_lesson_page_renders_material_sections(logged_in, fixtures_on):
    logged_in.post("/courses/dev-f1/enroll", data={"csrf_token": CSRF, "difficulty": "intermediate"})
    html = logged_in.get("/learn/dev-f1/dev-f1-l1").get_data(as_text=True)
    assert "[Intermediate] Fake material for development and automated tests only" in html            # 수강 난이도(중) 설명이 기본
    assert "Verified material · Key concepts" in html and "Test concept 1" in html
    assert '<svg viewBox="0 0 520 340"' in html and "Equilibrium price" in html   # 그래프와 접근성 표
    assert "Development test material" in html and "No sources cited." in html
    assert "The AI Tutor explains things based on this lesson's" in html and "AI features are turned off right now." in html   # 기본값: AI 꺼짐
    for title in ("Worked examples", "Real-world examples", "SDG case and policy trade-offs", "Key takeaways", "Sources"):
        assert title in html


def test_level_tabs_do_not_change_enrollment(app, logged_in, fixtures_on):
    from econova import storage
    logged_in.post("/courses/dev-f1/enroll", data={"csrf_token": CSRF, "difficulty": "beginner"})
    html = logged_in.get("/learn/dev-f1/dev-f1-l1?level=advanced").get_data(as_text=True)
    assert "[Advanced] Fake material for development" in html and "Now reading: Advanced" in html
    assert "[Beginner] Fake material for development" in logged_in.get("/learn/dev-f1/dev-f1-l1?level=bogus").get_data(as_text=True)
    with app.app_context():
        uid = storage.get_user_by_email("student@example.com")["id"]
        assert storage.get_enrollment(uid, "dev-f1")["selected_difficulty"] == "beginner"


# ------------------------------------------------------------- 교사용 미리보기
def test_preview_is_off_by_default(logged_in):
    assert logged_in.get("/preview/c02/c02-l1").status_code == 404


def test_preview_shows_draft_when_enabled(logged_in, monkeypatch):
    monkeypatch.setenv("ECONOVA_CONTENT_PREVIEW", "1")
    res = logged_in.get("/preview/c02/c02-l2?level=advanced")
    html = res.get_data(as_text=True)
    assert res.status_code == 200 and res.headers["X-Robots-Tag"] == "noindex" and "no-store" in res.headers["Cache-Control"]
    assert "Not visible to students" in html and "Draft, not yet reviewed (AI-written)" in html
    assert "P* = (a − c)/(b + d)" in html and "price ceiling of 24" in html
    assert "Source verified · 2026-11-13" in html and "openstax.org/books/principles-economics-3e" in html
    assert "I have read all the learning materials" not in html   # 미리보기에서는 진도를 남기지 않는다
    assert logged_in.get("/preview/c02/c02-l9").status_code == 404
    assert logged_in.get("/preview/c05/c05-l1").status_code == 404   # 자료가 없는 레슨


def test_preview_requires_login(client, monkeypatch):
    monkeypatch.setenv("ECONOVA_CONTENT_PREVIEW", "1")
    assert client.get("/preview/c02/c02-l1").headers["Location"].endswith("/login")


def test_preview_flag_stops_startup_in_production():
    env = {k: v for k, v in os.environ.items() if k not in ("DB_BACKEND", "FIREBASE_CREDENTIALS_JSON", "ECONOVA_DEV_FIXTURES")}
    env.update(RENDER="true", DB_BACKEND="sqlite", ECONOVA_CONTENT_PREVIEW="1", LMS_ROOT=ROOT, SECRET_KEY="s" * 40)
    code = ("import os, sys; sys.path.insert(0, os.environ['LMS_ROOT']);"
            "from econova import config; config.DOTENV_PATH = '/nonexistent'; import app")
    res = subprocess.run([sys.executable, "-I", "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert res.returncode != 0 and "ECONOVA_CONTENT_PREVIEW" in res.stderr


def test_check_content_includes_lesson_material(sqlite_app):
    res = sqlite_app.test_cli_runner().invoke(args=["check-content"])
    assert res.exit_code == 0 and "9 real course(s)" in res.output
