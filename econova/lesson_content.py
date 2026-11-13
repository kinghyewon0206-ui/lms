"""레슨 학습자료(content/lessons/*.json)와 출처 레지스트리(content/sources.json) 로더·검사기.

검사 규칙 (어기면 ContentError):
- 검토 상태는 draft → in_review → approved → published. approved·published 는 교사 검토자 이름·역할·승인 시각과
  그 상태로 바뀐 기록이 있어야 하고, AI 가 승인한 기록은 인정하지 않는다.
- 하·중·상 세 난이도가 모두 있어야 하고, 세 난이도 모두 같은 핵심 개념을 빠짐없이 다뤄야 한다.
- 인용한 출처 id 는 레지스트리에 있어야 한다. 승인·공개된 자료는 확인(verified)된 출처만 인용할 수 있다.
- 풀이 예제의 계산(check)과 그래프의 균형점(expected_equilibria)은 코드로 다시 계산해 맞는지 확인한다.
"""
import hashlib
import json
import math
import re
from dataclasses import dataclass

REVIEW_STATUSES = ("draft", "in_review", "approved", "published")
APPROVED_STATUSES = ("approved", "published")
LEVELS = ("beginner", "intermediate", "advanced")
SOURCE_STATUSES = ("verified", "unverified", "rejected")
_AI_MARKERS = re.compile(r"claude|\(ai\)|\bai\b|chatgpt|\bgpt|openai|artificial intelligence|인공지능", re.I)  # i18n-allow
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?$")


class ContentError(ValueError):
    """content.ContentError 와 같은 예외 (content.py 가 이 클래스를 다시 내보낸다)."""


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    container: str
    author: str
    published: str
    url: str
    concepts: tuple
    lesson_ids: tuple
    license: str
    verification_status: str
    checked_at: str
    method: str

    @property
    def verified(self):
        return self.verification_status == "verified"


@dataclass(frozen=True)
class LessonMaterial:
    lesson_id: str
    content_version: int
    review: dict
    objectives: tuple
    concepts: tuple            # ({id, term, definition, source_ids}, ...)
    levels: dict               # {level: {summary, sections: [{heading, concept_ids, paragraphs}]}}
    worked_examples: tuple
    graphs: tuple
    real_world_examples: tuple
    sdg_case: dict
    key_takeaways: tuple
    source_ids: tuple
    fixture: bool = False

    @property
    def review_status(self):
        return self.review["status"]

    @property
    def approved(self):
        return self.review_status in APPROVED_STATUSES

    def examples_for(self, level):
        return [ex for ex in self.worked_examples if ex["level"] in (level, "all")]


# ------------------------------------------------------------------ 도우미
def _need(data, key, kind, where):
    if not isinstance(data, dict) or key not in data:
        raise ContentError(f"{where}: '{key}' is missing.")
    value = data[key]
    if kind in (int, float) and isinstance(value, bool) or not isinstance(value, kind):
        raise ContentError(f"{where}: '{key}' has the wrong type.")
    return value


def _text(data, key, where):
    value = _need(data, key, str, where).strip()
    if not value:
        raise ContentError(f"{where}: '{key}' is empty.")
    return value


def _texts(data, key, where, allow_empty=False):
    values = _need(data, key, list, where)
    if (not allow_empty and not values) or not all(isinstance(v, str) and v.strip() for v in values):
        raise ContentError(f"{where}: '{key}' must be a list of non-empty strings.")
    return tuple(v.strip() for v in values)


def _num(data, key, where):
    return float(_need(data, key, (int, float), where))


def _close(actual, expected, tol=1e-6):
    return abs(actual - expected) <= tol + 1e-9


# ------------------------------------------------------------------ 출처 레지스트리
def parse_sources(data, where="sources.json"):
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ContentError(f"{where}: unsupported format.")
    out = {}
    for item in _need(data, "sources", list, where):
        sid = _text(item, "id", where)
        w = f"{where} ({sid})"
        if sid in out:
            raise ContentError(f"{where}: duplicate source id {sid!r}.")
        url = _text(item, "url", w)
        if not url.startswith("https://"):
            raise ContentError(f"{w}: url must be an https address.")
        ver = _need(item, "verification", dict, w)
        status = ver.get("status")
        if status not in SOURCE_STATUSES:
            raise ContentError(f"{w}: verification.status must be one of {', '.join(SOURCE_STATUSES)}.")
        checked = str(ver.get("checked_at") or "")
        if status == "verified" and not (_DATE_RE.match(checked) and str(ver.get("method") or "").strip()):
            raise ContentError(f"{w}: a verified source must have a check date (checked_at) and a verification method (method).")
        out[sid] = Source(
            id=sid, title=_text(item, "title", w), container=str(item.get("container") or ""),
            author=_text(item, "author", w), published=str(item.get("published") or ""), url=url,
            concepts=_texts(item, "concepts", w), lesson_ids=_texts(item, "lesson_ids", w, allow_empty=True),
            license=_text(item, "license", w), verification_status=status, checked_at=checked,
            method=str(ver.get("method") or ""),
        )
    return out


# ------------------------------------------------------------------ 계산 검증
def _equilibrium(a, b, c, d):
    if b + d <= 0:
        raise ValueError("b + d must be greater than 0.")
    p = (a - c) / (b + d)
    return p, a - b * p


def check_example(check, where):
    """풀이 예제의 숫자 답을 다시 계산해 확인한다."""
    kind = check.get("type")
    try:
        if kind == "difference":
            ok = _close(check["a"] - check["b"], check["expected"])
        elif kind == "linear":
            ok = _close(check["intercept"] + check["slope"] * check["x"], check["expected"])
        elif kind == "ratio":
            ok = _close(check["numerator"] / check["denominator"], check["expected"], check.get("tolerance", 1e-6))
        elif kind == "product":
            ok = _close(math.prod(check["factors"]), check["expected"])
        elif kind == "midpoint_elasticity":
            dq = (check["q2"] - check["q1"]) / ((check["q1"] + check["q2"]) / 2)
            dp = (check["p2"] - check["p1"]) / ((check["p1"] + check["p2"]) / 2)
            ok = _close(abs(dq / dp), check["expected"], check["tolerance"])
        elif kind == "equilibrium":
            p, q = _equilibrium(check["a"], check["b"], check["c"], check["d"])
            ok = _close(p, check["price"]) and _close(q, check["quantity"])
            if ok and "ceiling" in check:
                pc = check["ceiling"]
                ok = _close((check["a"] - check["b"] * pc) - (check["c"] + check["d"] * pc), check["shortage"])
        else:
            raise ContentError(f"{where}: unknown check type {kind!r}.")
    except (KeyError, TypeError, ZeroDivisionError, ValueError) as exc:
        if isinstance(exc, ContentError):
            raise
        raise ContentError(f"{where}: invalid check value ({type(exc).__name__}).")
    if not ok:
        raise ContentError(f"{where}: the example's calculated result is incorrect.")


def parse_graph(g, where):
    """수요·공급 그래프 명세. 선형 수요 Q = a − bP, 공급 Q = c + dP. 적어 둔 균형점이 실제 계산과 같은지 확인한다."""
    gid = _text(g, "id", where)
    w = f"{where} graph {gid}"
    axis = _need(g, "axis", dict, w)
    p_max, q_max = _num(axis, "p_max", w), _num(axis, "q_max", w)
    if p_max <= 0 or q_max <= 0:
        raise ContentError(f"{w}: axis ranges must be greater than 0.")
    demand = {}
    for d in _need(g, "demand", list, w):
        if _num(d, "b", w) <= 0:
            raise ContentError(f"{w}: the demand curve's b must be greater than 0 (law of demand).")
        demand[_text(d, "label", w)] = (_num(d, "a", w), _num(d, "b", w))
    supply = {}
    for s in _need(g, "supply", list, w):
        if _num(s, "d", w) <= 0:
            raise ContentError(f"{w}: the supply curve's d must be greater than 0 (law of supply).")
        supply[_text(s, "label", w)] = (_num(s, "c", w), _num(s, "d", w))
    # 곡선 이동만 보여 주는 그래프(균형을 배우기 전 레슨)는 수요곡선 또는 공급곡선만 둘 수 있다. 균형점은 둘 다 있어야 한다.
    if not demand and not supply:
        raise ContentError(f"{w}: there must be at least one demand curve or supply curve.")
    for e in _need(g, "expected_equilibria", list, w):
        if e.get("demand") not in demand or e.get("supply") not in supply:
            raise ContentError(f"{w}: the equilibrium refers to a curve name that does not exist.")
        a, b = demand[e["demand"]]
        c, d = supply[e["supply"]]
        p, q = _equilibrium(a, b, c, d)
        if not (_close(p, _num(e, "price", w), 1e-6) and _close(q, _num(e, "quantity", w), 1e-6)):
            raise ContentError(f"{w}: the stated equilibrium does not match the calculated result.")
    for line in g.get("price_lines", []):
        _text(line, "label", w)
        _num(line, "price", w)
    return dict(g)


# ------------------------------------------------------------------ 검토 정보
REVIEWER_ROLES = ("teacher", "admin")   # teacher: Phase 2~6 의 예전 기록 호환, admin: 플랫폼 관리자 (Phase 7)


def content_digest(data):
    """검토 대상 내용의 지문: review 항목을 뺀 JSON 의 sha256. 승인은 이 지문에 묶인다.
    (승인 뒤에 내용을 고치면 지문이 달라져 승인이 무효가 된다.)"""
    body = {k: v for k, v in (data or {}).items() if k != "review"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


PASSING_POLICY_META = ("status", "note", "review_id")   # 합격 기준 승인 결과·설명 (기준 값이 아님)


def assessment_digest(data):
    """평가의 승인 지문. 합격 기준의 승인 상태·메모·검토 번호는 별도 정책 결정의 결과라 지문에서 뺀다
    (기준 값 score_ratio 가 바뀌면 지문이 달라진다). 그래서 합격 기준을 승인해도 평가 승인이 무효가 되지 않는다."""
    if isinstance((data or {}).get("passing"), dict):
        data = {**data, "passing": {k: v for k, v in data["passing"].items() if k not in PASSING_POLICY_META}}
    return content_digest(data)


def _parse_review(review, where, fixture, digest=None):
    """검토 상태 검사. 승인(approved·published)에는 사람 검토자가 필요하다:
    - role=teacher: 예전(Phase 6 이전) 형식. 새 승인은 쓰지 않는다 (기록 보존용).
    - role=admin: 플랫폼 관리자. 검토 기록 번호(review_id)와 내용 지문(content_digest)이 있어야 하고,
      지문이 지금 내용과 같아야 한다 (digest 를 계산할 수 없는 경우 — 정답 키가 없는 평가 — 에는 그 평가가 어차피 닫힌다).
    - role=fixture: 개발용 fixture 만."""
    status = review.get("status")
    if status not in REVIEW_STATUSES:
        raise ContentError(f"{where}: review.status must be one of {' → '.join(REVIEW_STATUSES)}.")
    history = _need(review, "history", list, where)
    if not history or history[-1].get("status") != status:
        raise ContentError(f"{where}: the last status in the review history must match the current status.")
    for h in history:
        if h.get("status") not in REVIEW_STATUSES or not _DATE_RE.match(str(h.get("at") or "")) \
                or not str(h.get("by") or "").strip():
            raise ContentError(f"{where}: every review history entry must have a status, a time (at), and an author (by).")
        if h["status"] in APPROVED_STATUSES and _AI_MARKERS.search(h["by"]):
            raise ContentError(f"{where}: AI cannot approve or publish learning materials.")
    if status in APPROVED_STATUSES:
        reviewer = review.get("reviewer")
        allowed_roles = REVIEWER_ROLES + (("fixture",) if fixture else ())
        if not isinstance(reviewer, dict) or not str(reviewer.get("name") or "").strip() \
                or reviewer.get("role") not in allowed_roles or _AI_MARKERS.search(str(reviewer.get("name"))):
            raise ContentError(f"{where}: approved materials must have a human reviewer (reviewer: name, role=admin, or teacher in older records).")
        if not _DATE_RE.match(str(review.get("approved_at") or "")):
            raise ContentError(f"{where}: approved materials must have an approval time (approved_at).")
        if reviewer["role"] == "admin":
            if not str(reviewer.get("review_id") or "").strip() or not re.fullmatch(r"[0-9a-f]{64}",
                                                                                   str(review.get("content_digest") or "")):
                raise ContentError(f"{where}: an admin approval must have a review record number (reviewer.review_id) and a content fingerprint (content_digest).")
            if digest is not None and review["content_digest"] != digest:
                raise ContentError(f"{where}: the content changed after approval (fingerprint mismatch). It must be reviewed again.")
    return dict(review)


# ------------------------------------------------------------------ 레슨 자료
def parse_material(data, lesson_id, sources, fixture=False, where=None):
    where = where or f"lessons/{lesson_id}.json"
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ContentError(f"{where}: unsupported schema_version.")
    if data.get("lesson_id") != lesson_id:
        raise ContentError(f"{where}: lesson_id does not match the lesson in the course JSON ({lesson_id}).")
    version = _need(data, "content_version", int, where)
    if version < 1:
        raise ContentError(f"{where}: content_version must be 1 or greater.")
    review = _parse_review(_need(data, "review", dict, where), where, fixture, digest=content_digest(data))

    cited = set()

    def cite(ids, w):
        ids = tuple(ids)
        for sid in ids:
            if sid not in sources:
                raise ContentError(f"{w}: cites source {sid!r}, which is not in the source registry.")
        cited.update(ids)
        return ids

    concepts, concept_ids = [], []
    for c in _need(data, "concepts", list, where):
        cid = _text(c, "id", where)
        if cid in concept_ids:
            raise ContentError(f"{where}: duplicate concept id {cid!r}.")
        concept_ids.append(cid)
        srcs = cite(_texts(c, "source_ids", f"{where} concept {cid}", allow_empty=fixture), f"{where} concept {cid}")
        concepts.append({"id": cid, "term": _text(c, "term", where), "definition": _text(c, "definition", where),
                         "source_ids": srcs})
    if not concepts:
        raise ContentError(f"{where}: there must be at least one key concept (concepts).")

    levels_raw = _need(data, "levels", dict, where)
    if set(levels_raw) != set(LEVELS):
        raise ContentError(f"{where}: levels must include all three difficulty levels: beginner, intermediate, and advanced.")
    levels = {}
    for level in LEVELS:
        lv = levels_raw[level]
        w = f"{where} [{level}]"
        covered, sections = set(), []
        for s in _need(lv, "sections", list, w):
            ids = _texts(s, "concept_ids", w)
            unknown = set(ids) - set(concept_ids)
            if unknown:
                raise ContentError(f"{w}: refers to undefined concepts {sorted(unknown)}.")
            covered.update(ids)
            sections.append({"heading": _text(s, "heading", w), "concept_ids": ids,
                             "paragraphs": _texts(s, "paragraphs", w)})
        missing = [c for c in concept_ids if c not in covered]
        if missing:
            raise ContentError(f"{w}: does not cover key concepts {missing}. All three difficulty levels must cover the same concepts.")
        levels[level] = {"summary": _text(lv, "summary", w), "sections": sections}

    examples = []
    for ex in _need(data, "worked_examples", list, where):
        eid = _text(ex, "id", where)
        w = f"{where} example {eid}"
        if ex.get("level") not in LEVELS + ("all",):
            raise ContentError(f"{w}: invalid level.")
        if "check" in ex:
            check_example(_need(ex, "check", dict, w), w)
        examples.append({"id": eid, "level": ex["level"], "title": _text(ex, "title", w),
                         "problem": _text(ex, "problem", w), "steps": _texts(ex, "steps", w),
                         "answer": _text(ex, "answer", w)})
    for level in LEVELS:
        if not any(ex["level"] in (level, "all") for ex in examples):
            raise ContentError(f"{where}: there is no worked example for the {level} level.")

    graphs = tuple(parse_graph(g, where) for g in data.get("graphs", []))

    rwe = []
    for r in data.get("real_world_examples", []):
        w = f"{where} real-world example"
        rwe.append({"title": _text(r, "title", w), "paragraphs": _texts(r, "paragraphs", w),
                    "source_ids": cite(_texts(r, "source_ids", w, allow_empty=fixture), w)})

    sdg = _need(data, "sdg_case", dict, where)
    w = f"{where} SDG case"
    sdg_numbers = _need(sdg, "sdgs", list, w)
    if not sdg_numbers or not all(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 17 for n in sdg_numbers):
        raise ContentError(f"{w}: sdgs must be a list of numbers 1-17.")
    options = []
    for o in _need(sdg, "options", list, w):
        options.append({"name": _text(o, "name", w), "benefits": _texts(o, "benefits", w),
                        "costs": _texts(o, "costs", w), "assumptions": _texts(o, "assumptions", w)})
    if len(options) < 2:
        raise ContentError(f"{w}: there must be at least two policy options (to compare trade-offs).")
    sdg_case = {"sdgs": tuple(sdg_numbers), "title": _text(sdg, "title", w), "paragraphs": _texts(sdg, "paragraphs", w),
                "options": options, "discussion": _texts(sdg, "discussion", w, allow_empty=True),
                "source_ids": cite(_texts(sdg, "source_ids", w, allow_empty=fixture), w)}

    source_ids = cite(_texts(data, "source_ids", where, allow_empty=fixture), where)
    if not cited <= set(source_ids):
        raise ContentError(f"{where}: sources cited in the text {sorted(cited - set(source_ids))} are missing from source_ids.")
    if review["status"] in APPROVED_STATUSES:
        unverified = [sid for sid in source_ids if not sources[sid].verified]
        if unverified:
            raise ContentError(f"{where}: approved or published materials may cite only verified sources (unverified: {unverified}).")

    return LessonMaterial(
        lesson_id=lesson_id, content_version=version, review=review,
        objectives=_texts(data, "objectives", where), concepts=tuple(concepts), levels=levels,
        worked_examples=tuple(examples), graphs=graphs, real_world_examples=tuple(rwe), sdg_case=sdg_case,
        key_takeaways=_texts(data, "key_takeaways", where), source_ids=source_ids, fixture=fixture,
    )


def read_json(path, rel):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ContentError(f"{rel}: file not found.")
    except json.JSONDecodeError as exc:
        raise ContentError(f"{rel}: JSON syntax error ({exc.msg}, line {exc.lineno})")

