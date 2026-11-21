"""경제 기초 진단평가: 문항 로딩·검사, 결정적 채점, 난이도 추천.

- 채점은 코드 규칙으로만 한다 (AI 사용 안 함). 같은 답이면 언제나 같은 점수.
- 객관식은 선택지 id 가 정답과 같으면 정답. 수치형은 |입력 − 정답| ≤ 허용오차 이면 정답.
  수치 입력은 앞뒤 공백을 지우고, 천 단위 쉼표(1,000)는 없앤 뒤 소수점(.)으로 읽는다. 읽을 수 없거나 빈 답은 오답.
- 추천: 정답률 < intermediate 기준이면 beginner, < advanced 기준이면 intermediate, 그 이상이면 advanced.
  기준은 content/diagnostic.json 에 있고 '임시(provisional)' 값이다. 추천은 참고일 뿐, 학생이 난이도를 직접 고를 수 있다.
- 학생 화면에는 정답·해설을 제출 전까지 보내지 않는다 (public_questions).
- 공개 파일(content/diagnostic.json)에는 정답이 없다. 정답·허용오차·해설·검증식은 비공개 정답 키
  (<비공개 폴더>/econ-diagnostic.answers.json)에 있고, 서버에서만 합친다. 키가 없으면 응시·채점하지 않는다 (fail closed).
"""
import math
import os
import re
from functools import lru_cache

from econova import config, private_content
from econova.grading import is_correct, is_plain_number as _is_number, parse_number  # noqa: F401 (diagnostic.* 로도 쓴다)
from econova.content import DIFFICULTY_NAMES
from econova.lesson_content import ContentError, _equilibrium, parse_graph, read_json

PATH = os.path.join(config.BASE_DIR, "content", "diagnostic.json")
KEYS_FIXTURE = False   # 테스트는 개발용 합성 진단평가(content/dev_fixtures/diagnostic.json)와 그 합성 키를 쓴다
FIXTURE_PATH = os.path.join(config.BASE_DIR, "content", "dev_fixtures", "diagnostic.json")
QUESTION_TYPES = ("mcq", "numeric")


def _fail(msg):
    raise ContentError(f"diagnostic.json: {msg}")


def _check_verify(q, graphs):
    """정답을 코드로 다시 계산해 문항 작성 실수를 막는다."""
    v = q.get("verify")
    if not v:
        return
    kind = v.get("type")
    if kind in ("equilibrium_price", "ceiling_shortage"):
        g = graphs[q["graph"]]
        a, b = g["demand"][0]["a"], g["demand"][0]["b"]
        c, d = g["supply"][0]["c"], g["supply"][0]["d"]
        p, _ = _equilibrium(a, b, c, d)
        answer_text = next(ch["text"] for ch in q["choices"] if ch["id"] == q["answer"])
        if kind == "equilibrium_price":
            ok = _is_number(answer_text) and math.isclose(float(answer_text), p)
        else:
            ceiling = g["price_lines"][0]["price"]
            ok = ceiling < p and (a - b * ceiling) > (c + d * ceiling) and "shortage" in answer_text.lower()
    elif kind == "equilibrium_quantity":
        _, qty = _equilibrium(v["a"], v["b"], v["c"], v["d"])
        ok = math.isclose(qty, q["answer"])
    elif kind == "ratio":
        ok = math.isclose(v["numerator"] / v["denominator"], q["answer"])
    else:
        _fail(f"{q['id']}: unknown verify type {kind!r}")
    if not ok:
        _fail(f"{q['id']}: the answer does not match the calculated result.")


def parse(data, keys_problem=None):
    """data: 정답 키를 합친 서버 전용 데이터. keys_problem 이 있으면 공개 정의만 검사하고 응시할 수 없는 상태로 만든다."""
    has_keys = keys_problem is None
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        _fail("Unsupported format.")
    for key in ("id", "title", "description"):
        if not str(data.get(key) or "").strip():
            _fail(f"'{key}' is missing.")
    if not isinstance(data.get("version"), int) or isinstance(data.get("version"), bool) or data["version"] < 1:
        _fail("version must be an integer of 1 or greater.")
    th = data.get("thresholds") or {}
    try:
        lo, hi = float(th["intermediate"]), float(th["advanced"])
    except (KeyError, TypeError, ValueError):
        _fail("thresholds must include intermediate and advanced values.")
    if not 0 < lo < hi <= 1:
        _fail("Thresholds must satisfy 0 < intermediate < advanced <= 1.")
    if th.get("provisional") is not True:
        _fail("The thresholds are not validated yet, so thresholds.provisional must be true.")
    categories = data.get("categories") or []
    cat_ids = [c.get("id") for c in categories]
    if not cat_ids or len(set(cat_ids)) != len(cat_ids) or not all(c.get("name") for c in categories):
        _fail("Each category must have an id and a name, and ids must be unique.")
    graphs = {k: parse_graph(g, f"diagnostic.json graph {k}") for k, g in (data.get("graphs") or {}).items()}
    for k, g in graphs.items():
        if g.get("expected_equilibria"):
            _fail(f"Graph {k}: diagnostic graphs must not show the equilibrium point (it would reveal the answer).")

    questions = data.get("questions") or []
    if not 10 <= len(questions) <= 12:
        _fail("There must be 10-12 questions.")
    seen = set()
    for q in questions:
        qid = q.get("id")
        if not qid or qid in seen:
            _fail(f"Question id {qid!r} is missing or duplicated.")
        seen.add(qid)
        if q.get("category") not in cat_ids:
            _fail(f"{qid}: unknown category.")
        if q.get("type") not in QUESTION_TYPES:
            _fail(f"{qid}: type must be mcq or numeric.")
        if not str(q.get("prompt") or "").strip() or (has_keys and not str(q.get("explanation") or "").strip()):
            _fail(f"{qid}: prompt and explanation are required.")
        if "graph" in q and q["graph"] not in graphs:
            _fail(f"{qid}: refers to a graph that does not exist: {q['graph']!r}.")
        if q["type"] == "mcq":
            ids = [c.get("id") for c in q.get("choices") or []]
            if len(ids) < 2 or len(set(ids)) != len(ids) or not all(c.get("text") for c in q["choices"]):
                _fail(f"{qid}: there must be at least 2 choices with unique ids.")
            if not has_keys:
                continue
            if q.get("answer") not in ids:
                _fail(f"{qid}: the answer is not one of the choices.")
        elif not has_keys:
            continue
        else:
            if not isinstance(q.get("answer"), (int, float)) or isinstance(q.get("answer"), bool):
                _fail(f"{qid}: the answer to a numeric question must be a number.")
            tol = q.get("tolerance")
            if not isinstance(tol, (int, float)) or isinstance(tol, bool) or tol < 0:
                _fail(f"{qid}: tolerance must be a number of 0 or greater.")
        _check_verify(q, graphs)
    for cid in cat_ids:
        if not any(q["category"] == cid for q in questions):
            _fail(f"Category {cid!r} has no questions.")
    return {**data, "graphs": graphs, "category_names": {c["id"]: c["name"] for c in categories},
            "answer_keys": has_keys, "keys_problem": keys_problem or ""}


def _load(path, fixture=False):
    public = read_json(path, "diagnostic.json")
    leaked = private_content.public_violations(public)
    if leaked:
        _fail(f"The public diagnostic assessment file contains answer information ({', '.join(leaked[:5])}). Move it to the private answer key.")
    try:
        merged = private_content.merge(public, private_content.read_keys(public.get("id"), fixture), "diagnostic.json")
    except private_content.KeysUnavailable as exc:
        return parse(public, keys_problem=str(exc))
    try:
        return parse(merged)
    except ContentError as exc:
        return parse(public, keys_problem=f"Answer key check failed: {exc}")


@lru_cache(maxsize=4)
def _cached(path, fixture, private_dir):
    return _load(path, fixture)


def load():
    """진단평가(정답 키가 있으면 합친 서버 전용 데이터). 키가 없으면 answer_keys=False — 응시·채점 불가."""
    return _cached(PATH, KEYS_FIXTURE, None if KEYS_FIXTURE else config.private_content_dir())


def servable(test):
    """학생에게 응시시켜도 되는가: 정답 키가 있으면 (대회판: 사람 승인 여부와 무관)."""
    return bool(test.get("answer_keys"))


def public_questions(test=None):
    """학생 화면에 보낼 문항. 정답·허용오차·해설·검증 정보는 뺀다."""
    test = test or load()
    out = []
    for q in test["questions"]:
        pq = {k: q[k] for k in ("id", "category", "type", "prompt") if k in q}
        pq["category_name"] = test["category_names"][q["category"]]
        if q["type"] == "mcq":
            pq["choices"] = [{"id": c["id"], "text": c["text"]} for c in q["choices"]]
        else:
            pq["unit"] = q.get("unit", "")
        if "graph" in q:
            pq["graph"] = test["graphs"][q["graph"]]
        out.append(pq)
    return out


def recommend(correct, total, thresholds):
    ratio = correct / total if total else 0.0
    if ratio < thresholds["intermediate"]:
        return "beginner"
    if ratio < thresholds["advanced"]:
        return "intermediate"
    return "advanced"


def score(answers, test=None):
    """answers = {문항 id: 학생 입력(문자열)}. 결정적 채점 결과(dict)를 돌려준다. 모르는 문항 id 는 무시한다."""
    test = test or load()
    if not test.get("answer_keys", True):
        raise private_content.KeysUnavailable("The diagnostic assessment cannot be scored because its answer key is missing.")
    answers = {k: str(v)[:50] for k, v in (answers or {}).items()}
    results, by_cat = [], {cid: [0, 0] for cid in test["category_names"]}
    for q in test["questions"]:
        raw = answers.get(q["id"], "")
        ok = is_correct(q, raw)
        results.append({"id": q["id"], "answer": raw, "correct": ok})
        by_cat[q["category"]][1] += 1
        by_cat[q["category"]][0] += int(ok)
    correct, total = sum(r["correct"] for r in results), len(results)
    th = test["thresholds"]
    level = recommend(correct, total, th)
    return {
        "diagnostic_id": test["id"], "diagnostic_version": test["version"],
        "score": correct, "max_score": total, "results": results,
        "by_category": {cid: {"correct": c, "total": t} for cid, (c, t) in by_cat.items()},
        "recommended_level": level,
        "thresholds": {"intermediate": th["intermediate"], "advanced": th["advanced"], "provisional": True},
    }


def explain(attempt, test=None):
    """추천 이유를 사람이 읽을 문장으로. 저장된 결과(당시 기준)를 그대로 쓴다."""
    test = test or load()
    th = attempt["thresholds"]
    pct = round(attempt["score"] * 100 / attempt["max_score"]) if attempt["max_score"] else 0
    lo, hi = round(th["intermediate"] * 100), round(th["advanced"] * 100)
    rule = {"beginner": f"below {lo}%", "intermediate": f"{lo}% to below {hi}%", "advanced": f"{hi}% or higher"}
    level = attempt["recommended_level"]
    reasons = [f"Overall score: {pct}% ({attempt['score']}/{attempt['max_score']} questions correct).",
               f"Rule: {rule[level]} → {DIFFICULTY_NAMES[level]} recommended. These cutoffs are provisional and have not been validated yet."]
    names = test["category_names"]
    weak = [names.get(c, c) for c, v in attempt["by_category"].items() if v["total"] and v["correct"] == 0]
    strong = [names.get(c, c) for c, v in attempt["by_category"].items() if v["total"] and v["correct"] == v["total"]]
    if strong:
        reasons.append("Areas you got fully right: " + ", ".join(strong) + ".")
    if weak:
        reasons.append("Areas to review (all answers wrong): " + ", ".join(weak) + ".")
    return reasons

