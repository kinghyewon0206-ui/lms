"""SDG 경제 캡스톤 (Phase 7) — 자기주도 프로젝트. 교사가 내주는 과제나 공식 평가가 아니다.

정의 파일: content/capstone/<course_id>.json (개발용: content/dev_fixtures/capstone/<id>.json). 강좌 JSON 의
"capstone": {"status", "file"} 이 가리키고, 상태는 정의 파일의 검토 상태와 같아야 한다.

- steps: 9단계(SDG 고르기 → … → 되돌아보기). 각 단계는 강좌의 레슨 하나에 연결되고, 입력 칸(fields)을 가진다.
- rubric: 기준·가중치·수준 설명. status 는 'provisional'(사람 검토 전) 또는 'approved'. 자기 점검용이며 공식 점수가 아니다.
- 완료(결정적 규칙): 모든 레슨 완료 + 필수 칸을 모두 채운 버전을 제출 + 그 버전의 자기평가 + 되돌아보기.
  AI 의견은 완료에 영향을 주지 않는다. 실제 강좌는 정의(루브릭 포함)가 사람 승인을 받아야 수료로 인정한다
  (개발용 fixture 는 fixture 승인으로 시험). 수료는 '자기주도 프로젝트 제출 완료'이며 공식 학업 성취·자격 인증이 아니다.
"""
from dataclasses import dataclass

from econova import lesson_content
from econova.lesson_content import APPROVED_STATUSES, ContentError

FIELD_TYPES = ("sdg", "text", "long_text")
RUBRIC_STATUSES = ("provisional", "approved")


@dataclass(frozen=True)
class Capstone:
    course_id: str
    version: int
    review: dict
    title: str
    intro: tuple
    steps: tuple          # ({id, lesson_id, title, guidance, fields: ({id, label, help, type, min_chars, max_chars, required},)},)
    rubric: dict          # {version, status, note, levels: [...], criteria: [...]}
    completion: dict
    digest: str
    fixture: bool = False

    @property
    def review_status(self):
        return self.review["status"]

    @property
    def approved(self):
        return self.review_status in APPROVED_STATUSES

    @property
    def fields(self):
        return [f for s in self.steps for f in s["fields"]]

    def steps_for_lesson(self, lesson_id):
        return [s for s in self.steps if s["lesson_id"] == lesson_id]


def capstone_digest(data):
    """캡스톤 정의의 승인 지문. 루브릭의 승인 상태(rubric.status)는 승인 결과이므로 지문에서 뺀다."""
    if isinstance((data or {}).get("rubric"), dict):
        data = {**data, "rubric": {k: v for k, v in data["rubric"].items() if k != "status"}}
    return lesson_content.content_digest(data)


def parse_definition(data, course_id, lesson_ids, fixture=False, where="capstone"):
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("course_id") != course_id:
        raise ContentError(f"{where}: invalid format (expected schema_version 1, course_id={course_id}).")
    if bool(data.get("fixture")) != fixture:
        raise ContentError(f"{where}: only a development capstone may use 'fixture': true.")
    version = lesson_content._need(data, "version", int, where)
    digest = capstone_digest(data)
    review = lesson_content._parse_review(lesson_content._need(data, "review", dict, where), where, fixture, digest=digest)
    steps, step_ids, field_ids = [], set(), set()
    for s in lesson_content._need(data, "steps", list, where):
        sid = lesson_content._text(s, "id", where)
        w = f"{where} step {sid}"
        if sid in step_ids:
            raise ContentError(f"{w}: duplicate step id.")
        step_ids.add(sid)
        if s.get("lesson_id") not in lesson_ids:
            raise ContentError(f"{w}: lesson_id is not a lesson in this course.")
        fields = []
        for f in lesson_content._need(s, "fields", list, w):
            fid = lesson_content._text(f, "id", w)
            if fid in field_ids:
                raise ContentError(f"{w}: duplicate field id {fid!r}.")
            field_ids.add(fid)
            if f.get("type") not in FIELD_TYPES:
                raise ContentError(f"{w} field {fid}: type must be one of {', '.join(FIELD_TYPES)}.")
            mn, mx = int(f.get("min_chars") or 0), int(f.get("max_chars") or 0)
            if f["type"] != "sdg" and not 0 <= mn < mx <= 10000:
                raise ContentError(f"{w} field {fid}: must satisfy 0 <= min_chars < max_chars <= 10000.")
            fields.append({"id": fid, "label": lesson_content._text(f, "label", w), "help": str(f.get("help") or ""),
                           "type": f["type"], "min_chars": mn, "max_chars": mx, "required": bool(f.get("required"))})
        if not fields:
            raise ContentError(f"{w}: there must be at least one field.")
        steps.append({"id": sid, "lesson_id": s["lesson_id"], "title": lesson_content._text(s, "title", w),
                      "guidance": lesson_content._text(s, "guidance", w), "fields": tuple(fields)})
    if not any(f["type"] == "sdg" for st in steps for f in st["fields"]) or "reflection" not in field_ids:
        raise ContentError(f"{where}: an SDG choice field (type=sdg) and a reflection field (id=reflection) are required.")
    missing_lessons = [lid for lid in lesson_ids if not any(st["lesson_id"] == lid for st in steps)]
    if missing_lessons:
        raise ContentError(f"{where}: no step is linked to lessons {missing_lessons}.")
    rubric = _parse_rubric(lesson_content._need(data, "rubric", dict, where), step_ids, review, where)
    return Capstone(course_id=course_id, version=version, review=review, title=lesson_content._text(data, "title", where),
                    intro=lesson_content._texts(data, "intro", where), steps=tuple(steps), rubric=rubric,
                    completion=dict(data.get("completion") or {}), digest=digest, fixture=fixture)


def _parse_rubric(r, step_ids, review, where):
    w = f"{where} rubric"
    if r.get("status") not in RUBRIC_STATUSES:
        raise ContentError(f"{w}: status must be provisional or approved.")
    if r["status"] == "approved" and review["status"] not in APPROVED_STATUSES:
        raise ContentError(f"{w}: the rubric cannot be approved on its own before the capstone definition is human-approved.")
    levels = lesson_content._need(r, "levels", list, w)
    scores = [lv.get("score") for lv in levels]
    if scores != list(range(1, len(levels) + 1)) or len(levels) < 2:
        raise ContentError(f"{w}: level scores must run in order starting from 1.")
    criteria, seen = [], set()
    for c in lesson_content._need(r, "criteria", list, w):
        cid = lesson_content._text(c, "id", w)
        if cid in seen:
            raise ContentError(f"{w}: duplicate criterion id.")
        seen.add(cid)
        weight = c.get("weight")
        if not isinstance(weight, int) or isinstance(weight, bool) or weight <= 0:
            raise ContentError(f"{w} criterion {cid}: weight must be a positive integer.")
        if set(c.get("related_steps") or ()) - step_ids:
            raise ContentError(f"{w} criterion {cid}: related_steps includes a step that does not exist.")
        desc = c.get("descriptors") or {}
        if set(desc) != {str(s) for s in scores} or not all(str(v).strip() for v in desc.values()):
            raise ContentError(f"{w} criterion {cid}: every level needs a description (descriptors).")
        criteria.append({"id": cid, "name": lesson_content._text(c, "name", w),
                         "description": lesson_content._text(c, "description", w), "weight": weight,
                         "related_steps": tuple(c.get("related_steps") or ()), "descriptors": dict(desc)})
    if sum(c["weight"] for c in criteria) != 100:
        raise ContentError(f"{w}: weights must add up to 100.")
    return {"version": lesson_content._need(r, "version", int, w), "status": r["status"], "note": str(r.get("note") or ""),
            "levels": tuple({"score": lv["score"], "label": str(lv.get("label") or lv["score"])} for lv in levels),
            "criteria": tuple(criteria)}


# ------------------------------------------------------------------ 학생 입력 검사 (결정적)
def clean_sections(defn, form):
    """폼 값 → 저장할 sections dict. 길이를 넘는 값은 자르지 않고 오류로 돌려준다 (학생 글을 몰래 자르지 않음).
    반환: (sections, errors{field_id: 메시지})"""
    sections, errors = {}, {}
    for f in defn.fields:
        raw = str(form.get(f["id"], "") or "").replace("\r\n", "\n").strip()
        if f["type"] == "sdg":
            if raw and not (raw.isdigit() and 1 <= int(raw) <= 17):
                errors[f["id"]] = "Please choose an SDG from 1 to 17."
                continue
            sections[f["id"]] = raw
            continue
        if len(raw) > f["max_chars"]:
            errors[f["id"]] = f"Please shorten this to {f['max_chars']} characters or fewer (currently {len(raw)})."
            continue
        sections[f["id"]] = raw
    return sections, errors


def missing_fields(defn, sections):
    """제출하려면 더 채워야 하는 필수 칸 [(field, 이유)] — 비어 있거나 최소 글자 수 미만."""
    out = []
    for f in defn.fields:
        if not f["required"]:
            continue
        value = str((sections or {}).get(f["id"], "") or "").strip()
        if not value:
            out.append((f, "It's empty"))
        elif f["type"] != "sdg" and len(value) < f["min_chars"]:
            out.append((f, f"Needs at least {f['min_chars']} characters (currently {len(value)})"))
    return out


def step_status(defn, sections):
    """단계별 채움 상태 {step_id: 'done' | 'partial' | 'empty'}."""
    out = {}
    for s in defn.steps:
        filled = [bool(str((sections or {}).get(f["id"], "") or "").strip()) for f in s["fields"]]
        missing = missing_fields(type("D", (), {"fields": list(s["fields"])})(), sections)
        out[s["id"]] = "done" if not missing and all(filled) else ("partial" if any(filled) else "empty")
    return out


def clean_self_assessment(defn, form):
    """자기평가: 기준마다 수준(1~N) 선택 + 선택 메모. 반환: (scores dict, errors). 모두 골라야 저장된다."""
    max_score = len(defn.rubric["levels"])
    scores, errors = {}, {}
    for c in defn.rubric["criteria"]:
        raw = str(form.get(f"score_{c['id']}", "") or "")
        if not (raw.isdigit() and 1 <= int(raw) <= max_score):
            errors[c["id"]] = "Please choose a level."
            continue
        note = str(form.get(f"note_{c['id']}", "") or "").strip()
        if len(note) > 500:
            errors[c["id"]] = "Please keep your note to 500 characters or fewer."
            continue
        scores[c["id"]] = {"level": int(raw), "note": note}
    return scores, errors


def weighted_summary(defn, scores):
    """자기평가 요약 (결정적): 가중 평균 수준(1~N, 소수 1자리)과 보완할 기준(수준 2 이하). 공식 점수가 아니다."""
    if not scores:
        return None
    total = sum(c["weight"] * scores[c["id"]]["level"] for c in defn.rubric["criteria"] if c["id"] in scores)
    weight = sum(c["weight"] for c in defn.rubric["criteria"] if c["id"] in scores)
    return {"average_level": round(total / weight, 1) if weight else None, "max_level": len(defn.rubric["levels"]),
            "improve": [c["name"] for c in defn.rubric["criteria"] if c["id"] in scores and scores[c["id"]]["level"] <= 2],
            "complete": len(scores) == len(defn.rubric["criteria"])}


# ------------------------------------------------------------------ 프로젝트 상태와 완료 (결정적)
def latest_sections(versions):
    return dict(versions[-1]["sections"]) if versions else {}


def self_assessment_for(assessments, version):
    found = [a for a in assessments if a["version"] == version]
    return found[-1] if found else None


def completion_state(defn, course_progress, project, versions, assessments):
    """완료 조건 점검표. 반환 dict 의 complete 가 True 여야 수료를 기록한다. AI 의견은 들어가지 않는다."""
    submitted = project is not None and project.get("status") == "submitted" and project.get("submitted_version")
    sub_version = next((v for v in versions if submitted and v["version"] == int(project["submitted_version"])), None)
    sections = sub_version["sections"] if sub_version else {}
    sa = self_assessment_for(assessments, sub_version["version"]) if sub_version else None
    reflection = next((f for f in defn.fields if f["id"] == "reflection"), None)
    checks = {
        "lessons": course_progress["completed"] == course_progress["total"] and course_progress["total"] > 0,
        "submitted": sub_version is not None and not missing_fields(defn, sections),
        "self_assessment": sa is not None and len(sa["scores"] or {}) == len(defn.rubric["criteria"]),
        "reflection": bool(sub_version) and reflection is not None and
                      len(str(sections.get("reflection", "")).strip()) >= reflection["min_chars"],
    }
    return {**checks, "complete": all(checks.values()), "submitted_version": sub_version["version"] if sub_version else None}


def completion_policy(course):
    """수료를 기록해도 되는 정책 이름, 기록하면 안 되면 None.
    실제 강좌는 캡스톤 정의와 루브릭이 사람 승인을 받았을 때만, 개발용 강좌는 fixture 승인으로 시험."""
    defn = course.capstone
    if defn is None or not defn.approved or not course.published:
        return None
    if course.fixture:
        return "dev_capstone"
    return "capstone_self_directed" if defn.rubric["status"] == "approved" else None
