"""커리큘럼 JSON 과 로더: 형식 검사, id 중복, 강좌-레슨 관계, 공개 여부, 개발용 테스트 강좌 분리."""
import copy
import json
import os

import pytest

from econova import config, content

SPEC = {  # 승인된 ECONOVA 커리큘럼 명세 (강좌 id: (영문 제목, SDG, 레슨 영문 제목))
    "c01": ("Economics & Choices", [12], ["Scarcity and Economic Choices", "Opportunity Cost and Rational Decisions",
                                          "Sustainable Consumption and Resource Allocation"]),
    "c02": ("Markets & Prices", [2, 12], ["Supply and Demand", "Market Equilibrium and Price Formation",
                                          "Price Elasticity and Food Markets"]),
    "c03": ("Market Failure", [7, 13], ["Externalities and Market Failure", "Public Goods and Common Resources",
                                        "Carbon Taxes and Government Intervention"]),
    "c04": ("Growth & Stability", [8], ["GDP and Measuring Economic Activity", "Economic Growth and Productivity",
                                        "Inflation, Purchasing Power, and Living Standards"]),
    "c05": ("Labor & Employment", [8], ["Labor Supply and Demand", "Employment, Unemployment, and Productivity",
                                        "Wages, Minimum Wage, and Labor Policy"]),
    "c06": ("Inequality & Policy", [1, 10], ["Income Distribution and Inequality", "Taxation and Redistribution",
                                             "Poverty, Social Protection, and Public Finance"]),
    "c07": ("Personal Finance", [1, 8], ["Income, Spending, and Budgeting", "Saving, Interest, and Compound Growth",
                                         "Financial Risk and Financial Inclusion"]),
    "c08": ("Global Economics", [8, 12, 17], ["Comparative Advantage and International Trade",
                                              "Exchange Rates and International Markets",
                                              "Global Supply Chains and Sustainable Production"]),
    "c09": ("SDG Economic Challenge", "student", ["Identify an Economic Problem",
                                                  "Analyze Evidence and Compare Policy Options",
                                                  "Develop and Present an Economic Policy Proposal"]),
}


def _raw(course_id="c02"):
    with open(os.path.join(content.CONTENT_DIR, "courses", f"{course_id}.json"), encoding="utf-8") as f:
        return json.load(f)


def _fixture_raw():
    with open(os.path.join(content.CONTENT_DIR, "dev_fixtures", "dev-f1.json"), encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------ 실제 커리큘럼
def test_real_catalog_matches_spec():
    cat = content.load_catalog(False)
    assert [c.id for c in cat.courses] == list(SPEC)
    assert sum(len(c.lessons) for c in cat.courses) == 27
    for c in cat.courses:
        title, sdgs, lessons = SPEC[c.id]
        assert c.title == title
        if sdgs == "student":
            assert c.sdg_student_selected and c.sdgs == ()
        else:
            assert list(c.sdgs) == sdgs and not c.sdg_student_selected
        assert [lesson.title for lesson in c.lessons] == lessons
        assert c.lesson_ids == tuple(f"{c.id}-l{i}" for i in (1, 2, 3))
        assert all(lesson.course_id == c.id for lesson in c.lessons)
        assert [lesson.order for lesson in c.lessons] == [1, 2, 3]
        assert c.difficulty_levels == content.DIFFICULTIES
        assert c.content_version >= 1 and c.estimated_hours >= 1 and c.slug and c.objectives


def test_real_courses_are_not_published_yet():
    # 검증된 학습자료와 평가가 없으므로 실제 강좌는 아직 공개하면 안 된다
    cat = content.load_catalog(False)
    assert cat.published() == []
    assert {c.status for c in cat.courses} == {"coming_soon"}
    assert all(c.review_status == "draft" and not c.fixture for c in cat.courses)
    for c in cat.courses:
        for lesson in c.lessons:
            assert lesson.requirements == ("material", "quiz")
            assert not lesson.material_approved and not lesson.quiz_approved


def test_course_and_lesson_ids_are_unique():
    cat = content.load_catalog(True)
    ids = [c.id for c in cat.courses]
    lesson_ids = [lesson.id for c in cat.courses for lesson in c.lessons]
    assert len(ids) == len(set(ids)) and len(lesson_ids) == len(set(lesson_ids))


# ------------------------------------------------------------ 개발용 테스트 강좌
def test_fixtures_are_off_by_default():
    assert not config.dev_fixtures_enabled()
    assert [c.id for c in content.get_catalog().courses if c.fixture] == []


def test_fixtures_when_enabled(fixtures_on):
    cat = content.get_catalog()
    fixtures = [c for c in cat.courses if c.fixture]
    assert [c.id for c in fixtures] == ["dev-f1", "dev-f2", "dev-f3"]   # dev-f3: 캡스톤 강좌 (Phase 7)
    assert [c.id for c in cat.published()] == ["dev-f1", "dev-f2", "dev-f3"]   # 공개된 것은 테스트 강좌뿐
    assert cat.course("dev-f2").lesson("dev-f2-l2").requirements == ("material",)


@pytest.mark.parametrize("name", ["RENDER", "APP_ENV"])
def test_fixtures_can_never_be_enabled_in_production(monkeypatch, fixtures_on, name):
    monkeypatch.setenv(name, "production" if name == "APP_ENV" else "true")
    with pytest.raises(config.ConfigError):
        content.get_catalog()


def _drop_materials(lesson):
    """c01 레슨 JSON 은 자기 lesson_id 에 묶여 있으므로, id 를 바꾼 복사본에서는 자료·퀴즈를 뗀다."""
    lesson["material"] = {"status": "missing"}
    lesson["quiz"] = {"status": "missing", "assessment_id": None}


def test_visible_and_published_filtering():
    base = content.load_catalog(True)
    draft = copy.deepcopy(_raw("c01"))
    draft["final_assessment"] = {"status": "upcoming"}
    draft.update(id="zz-draft", slug="zz-draft", status="draft", lesson_ids=[f"zz-draft-l{i}" for i in (1, 2, 3)])
    for i, lesson in enumerate(draft["lessons"], start=1):
        lesson["id"] = f"zz-draft-l{i}"
        _drop_materials(lesson)
    archived = copy.deepcopy(draft)
    archived.update(id="zz-old", slug="zz-old", status="archived", lesson_ids=[f"zz-old-l{i}" for i in (1, 2, 3)])
    for i, lesson in enumerate(archived["lessons"], start=1):
        lesson["id"] = f"zz-old-l{i}"
        _drop_materials(lesson)
    cat = content.build_catalog(list(base.courses) + [content.parse_course(draft), content.parse_course(archived)], base.sdgs)
    visible = [c.id for c in cat.visible()]
    assert "zz-draft" not in visible and "zz-old" not in visible
    assert {c.id for c in cat.published()} == {"dev-f1", "dev-f2", "dev-f3"}
    assert all(c.id in visible for c in base.courses)


# ------------------------------------------------------------ 형식 검사
def _bad(mutate, raw=None, fixture=False):
    data = copy.deepcopy(raw or _raw())
    mutate(data)
    with pytest.raises(content.ContentError) as err:
        content.parse_course(data, fixture=fixture)
    return str(err.value)


def test_valid_course_parses():
    assert content.parse_course(_raw()).id == "c02"


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d.pop("title"), "'title' is missing"),
    (lambda d: d.update(title="  "), "is empty"),
    (lambda d: d.update(id="C 02"), "lowercase letters"),
    (lambda d: d.update(schema_version=2), "schema_version"),
    (lambda d: d.update(status="live"), "'status'"),
    (lambda d: d.update(sdgs=[18]), "sdgs"),
    (lambda d: d.update(sdgs=[2, 2]), "sdgs contains duplicates"),
    (lambda d: d.update(sdgs=[]), "sdgs"),
    (lambda d: d.update(content_version=0), "1 or greater"),
    (lambda d: d.update(content_version=True), "wrong type"),
    (lambda d: d.update(difficulty_levels=["beginner"]), "difficulty_levels"),
    (lambda d: d.update(lesson_ids=["c02-l1", "c02-l1", "c02-l3"]), "lesson_ids contains duplicates"),
    (lambda d: d.update(lesson_ids=["c02-l2", "c02-l1", "c02-l3"]), "lesson_ids"),
    (lambda d: d["lessons"][1].update(order=3), "order"),
    (lambda d: d["lessons"][0].update(id="c03-l1"), "'c02-'"),
    (lambda d: d["lessons"][0].update(requirements=["quiz"]), "material"),
    (lambda d: d["lessons"][0].update(requirements=["material", "essay"]), "requirements"),
    (lambda d: d["lessons"][0].update(requirements=["material", "material"]), "no duplicates"),
    (lambda d: d["lessons"][0]["quiz"].update(status="approved", assessment_id=None), "assessment_id"),
    # 강좌 JSON 의 상태만 approved 로 바꿔도 학습자료 파일(draft)과 달라 거절된다 (Phase 2 의 '실제 자료 승인 금지'를 대체)
    (lambda d: d["lessons"][0]["material"].update(status="approved"), "review status of the learning materials file"),
    (lambda d: d["lessons"][0]["material"].pop("file"), "material.file"),
    (lambda d: d["lessons"][0]["material"].update(file="../../etc/passwd"), "material.file"),
    (lambda d: d["lessons"][0]["material"].update(status="ok"), "material.status"),
    (lambda d: d.update(fixture=True), "dev_fixtures"),
    (lambda d: d.update(status="published"), "published"),
])
def test_invalid_course_is_rejected(mutate, message):
    assert message in _bad(mutate)


def test_publish_requires_every_required_activity_approved():
    # 테스트 강좌에서 퀴즈 승인 하나만 빼도 published 가 거절된다
    def drop_quiz(d):
        d["lessons"][2]["quiz"] = {"status": "missing", "assessment_id": None}
    assert "quiz" in _bad(drop_quiz, raw=_fixture_raw(), fixture=True)

    def unpublish_lesson(d):
        d["lessons"][0]["status"] = "draft"
    assert "published" in _bad(unpublish_lesson, raw=_fixture_raw(), fixture=True)


def test_fixture_file_must_be_marked():
    def unmark(d):
        d.pop("fixture")
    assert "dev_fixtures" in _bad(unmark, raw=_fixture_raw(), fixture=True)


def test_catalog_level_duplicates_are_rejected():
    base = content.load_catalog(False)
    c02 = content.parse_course(_raw("c02"))
    with pytest.raises(content.ContentError, match="Duplicate course id"):
        content.build_catalog(list(base.courses) + [c02], base.sdgs)

    same_slug = copy.deepcopy(_raw("c01"))
    same_slug["final_assessment"] = {"status": "upcoming"}
    same_slug.update(id="c99", lesson_ids=[f"c99-l{i}" for i in (1, 2, 3)])
    for i, lesson in enumerate(same_slug["lessons"], start=1):
        lesson["id"] = f"c99-l{i}"
        _drop_materials(lesson)
    with pytest.raises(content.ContentError, match="slug"):
        content.build_catalog(list(base.courses) + [content.parse_course(same_slug)], base.sdgs)


def test_unknown_sdg_reference_is_rejected():
    base = content.load_catalog(False)
    sdgs = {k: v for k, v in base.sdgs.items() if k != 12}
    with pytest.raises(content.ContentError, match="SDG 12"):
        content.build_catalog(list(base.courses), sdgs)


def test_broken_json_reports_the_file(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text('{"id": "c02",', encoding="utf-8")
    with pytest.raises(content.ContentError, match="JSON syntax error"):
        content._read_json(str(bad))
    with pytest.raises(content.ContentError, match="file not found"):
        content._read_json(str(tmp_path / "missing.json"))
