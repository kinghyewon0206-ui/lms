"""c03 「시장 실패」 초안: 구조, 탄소세 시뮬레이션과의 수치 일관성, 교사용 미리보기에 시뮬레이션이 붙는지."""
import json
import os
import re

import pytest

from econova import content, simulations

C03_LESSONS = ("c03-l1", "c03-l2", "c03-l3")


def _course():
    return content.load_catalog(False).course("c03")


def test_c03_is_a_complete_unpublished_draft():
    course = _course()
    assert course.status == "coming_soon" and not course.published and course.content_version >= 2
    for lesson in course.lessons:
        doc = lesson.content
        assert doc is not None and doc.review["status"] == "draft"
        assert len(doc.objectives) == 3 and {e["level"] for e in doc.worked_examples} == {"beginner", "intermediate", "advanced"}
        assert set(doc.sdg_case["sdgs"]) <= {7, 13} and len(doc.sdg_case["options"]) >= 2
        assert lesson.quiz_assessment is not None and len(lesson.quiz_assessment.questions) == 5
    final = course.final
    assert len(final.questions) == 10 and final.max_attempts == 3
    assert final.passing["score_ratio"] == 0.7 and final.passing["status"] == "proposed"
    assert {q["lesson_id"] for q in final.questions} == set(C03_LESSONS)


def test_only_lesson_3_embeds_the_existing_carbon_tax_simulation():
    course = _course()
    assert [lesson.simulations for lesson in course.lessons] == [(), (), ("carbon-tax",)]
    assert "carbon-tax" in simulations.SIMULATIONS


def test_lesson_3_numbers_match_the_simulator_defaults():
    """레슨 3 예제·그래프는 위젯이 처음 보여 주는 값과 같아야 한다. 시뮬레이터 공식이나 기본값이 바뀌면 이 테스트가 알려 준다."""
    d = simulations.DEFAULTS["carbon-tax"]
    r = simulations.carbon_tax(d["a"], d["b"], d["c"], d["d"], d["t"], md=d["md"], e=d["e"])
    with open(os.path.join(content.CONTENT_DIR, "lessons", "c03-l3.json"), encoding="utf-8") as f:
        raw = json.load(f)                       # 화면용으로 읽은 자료에는 검산값(check)이 없으므로 원본 JSON 을 본다
    ex = {e["id"]: e for e in raw["worked_examples"]}
    assert ex["c03-l3-we1"]["check"] == {"type": "difference", "a": r["consumer_price"], "b": r["baseline"]["price"], "expected": 2}
    assert ex["c03-l3-we2"]["check"]["expected"] == r["revenue"] == 216
    assert ex["c03-l3-we3"]["check"] == {"type": "difference", "a": r["avoided_damage"], "b": r["deadweight_loss_private"],
                                         "expected": r["social_welfare_change"]}
    graph = raw["graphs"][0]
    taxed = graph["expected_equilibria"][1]
    assert (taxed["price"], taxed["quantity"]) == (r["consumer_price"], r["quantity"])
    s_t = next(s for s in graph["supply"] if s["label"] == "S+t")
    assert s_t["c"] == d["c"] - d["d"] * d["t"]     # 시뮬레이터 graph_spec 과 같은 S+t
    # 레슨이 말하는 '세율 = 외부 피해일 때 후생 변화 최대' 가 시뮬레이터 계산으로도 성립
    best = max((simulations.carbon_tax(100, 2, 10, 1, t / 2, md=6, e=1)["social_welfare_change"], t / 2) for t in range(0, 41))
    assert best[1] == d["md"]


def test_lesson_texts_name_only_real_simulator_outputs():
    """레슨이 안내하는 결과표 항목 이름은 실제 시뮬레이터 결과표에 있는 이름이어야 한다 (없는 기능을 지어내지 않기)."""
    labels = {label for _, label, _ in simulations.ROW_LABELS["carbon-tax"]}
    text = " ".join(p for lvl in _course().lesson("c03-l3").content.levels.values() for s in lvl["sections"] for p in s["paragraphs"])
    quoted = {q for q in re.findall(r"'([^']+)'", text) if "(" in q or q in labels or "가격" in q or "배출" in q or "세수" in q}
    assert quoted and quoted <= labels | {"인터랙티브 시뮬레이션"}, quoted - labels


def test_c03_lesson_3_preview_shows_the_simulation(logged_in, monkeypatch):
    monkeypatch.setenv("ECONOVA_CONTENT_PREVIEW", "1")
    res = logged_in.get("/preview/c03/c03-l3?level=advanced")
    html = res.get_data(as_text=True)
    assert res.status_code == 200 and "검토 전 초안 (AI 작성)" in html
    assert "탄소세와 시장" in html and "사회적 후생 변화 (가정)" in html and "피구세" in html


@pytest.mark.parametrize("lesson_id", ["c03-l1", "c03-l2"])
def test_c03_other_previews_render(logged_in, monkeypatch, lesson_id):
    monkeypatch.setenv("ECONOVA_CONTENT_PREVIEW", "1")
    res = logged_in.get(f"/preview/c03/{lesson_id}?level=beginner")
    assert res.status_code == 200 and "이 레슨에는 시뮬레이션이 없어요" in res.get_data(as_text=True)
