"""플랫폼 콘텐츠 관리 (Phase 7). 학생을 감독하는 기능이 아니라 교육 콘텐츠의 품질을 관리하는 기능이다.

세 가지를 분리한다.
1. 검토 결정: 관리자가 웹에서 남기는 기록 (DB, econ_content_reviews — 추가만 하고 고치거나 지우지 않음).
   각 기록은 검토한 내용의 버전과 지문(content_digest)에 묶인다. 내용이 바뀌면 그 기록은 '지난 내용' 이 되어
   현재 상태 계산에서 빠진다 (다시 검토해야 함).
2. 정본 콘텐츠: Git 으로 관리하는 JSON. 웹 요청은 이 파일을 절대 바꾸지 않는다.
3. 릴리스 준비: 승인 기록 중 지금 내용과 지문이 같은 것만 모아 '릴리스 계획(JSON)'을 만든다. 개발자가 로컬에서
   `flask content-release-apply 계획.json` 으로 정본 JSON 의 review 블록에 반영하고, 검사·커밋·배포는 평소 절차를 따른다.
   승인했다고 자동으로 공개·배포되지 않는다.

검토 상태 흐름: draft → in_review → approved (→ published 는 정본 파일·강좌 공개 절차로만).
"""
import copy
import datetime
import hashlib
import json
import os
from dataclasses import dataclass, field

from econova import content, lesson_content, private_content
from econova.capstone import capstone_digest
from econova.lesson_content import ContentError

TARGET_TYPES = {"course": "강좌 설명·학습목표", "material": "레슨 학습자료", "assessment": "형성 퀴즈·최종 평가",
                "passing": "최종 평가 합격 기준", "diagnostic": "진단평가", "source": "출처", "debate": "토론 주제",
                "capstone": "캡스톤 안내·루브릭"}
TRANSITIONS = {("draft", "start_review"): "in_review", ("in_review", "approve"): "approved",
               ("in_review", "request_changes"): "draft", ("approved", "reopen"): "in_review"}
DECISION_KO = {"start_review": "검토 시작", "approve": "승인", "request_changes": "수정 요청", "reopen": "다시 검토"}
STATE_KO = {"draft": "초안", "in_review": "검토 중", "approved": "승인됨", "published": "공개됨", "missing": "없음",
            "upcoming": "예정", "verified": "확인됨", "unverified": "미확인", "fixture": "개발용"}
# 릴리스 계획으로 정본 파일에 반영할 수 있는 대상 (review 블록이 있고 검사기가 지문을 확인하는 것)
RELEASABLE = ("material", "assessment", "passing", "debate", "capstone")


@dataclass
class Target:
    type: str
    id: str
    title: str
    course_id: str
    file: str                  # content/ 기준 상대 경로
    version: str
    file_state: str            # 정본 파일에 적힌 상태
    digest: str = ""           # 검토 지문 (계산할 수 없으면 "")
    data: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)
    fixture: bool = False
    refs: dict = field(default_factory=dict)

    @property
    def key(self):
        return f"{self.type}:{self.id}"


def _read(rel):
    path = os.path.join(content.CONTENT_DIR, rel)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _base(fixture):
    return "dev_fixtures/" if fixture else ""


def _assessment_target(aid, course_id, fixture):
    rel = f"{_base(fixture)}assessments/{aid}.json"
    try:
        public = _read(rel)
    except (OSError, ValueError):
        return Target("assessment", aid, aid, course_id, rel, "?", "missing", problems=["평가 파일이 없거나 읽을 수 없어요."],
                      fixture=fixture)
    t = Target("assessment", aid, public.get("title") or aid, course_id, rel, str(public.get("version")),
               (public.get("review") or {}).get("status", "?"), fixture=fixture)
    try:
        merged = private_content.merge(public, private_content.read_keys(aid, fixture), rel)
        t.data, t.digest = merged, lesson_content.assessment_digest(merged)
        t.refs = {"assessment_version": public.get("version"),
                  "question_versions": {q["id"]: q.get("version") for q in public.get("questions", [])},
                  "keys_digest": hashlib.sha256(json.dumps(private_content.read_keys(aid, fixture), sort_keys=True,
                                                           ensure_ascii=False).encode()).hexdigest()}
    except private_content.KeysUnavailable as exc:
        t.data = public
        t.problems.append(f"정답 키 없음 — 검토·승인할 수 없어요 ({exc}).")
    return t


def _passing_target(final):
    passing = {k: v for k, v in (final.data.get("passing") or {}).items() if k not in lesson_content.PASSING_POLICY_META}
    state = (final.data.get("passing") or {}).get("status", "?")
    digest = lesson_content.content_digest({"assessment_id": final.id, "passing": passing}) if passing else ""
    t = Target("passing", final.id, f"{final.title} 합격 기준", final.course_id, final.file, final.version,
               "approved" if state == "approved" else ("draft" if state in ("proposed", "dev_provisional") else state),
               digest=digest, data={"passing": final.data.get("passing"), "assessment_id": final.id},
               fixture=final.fixture, refs={"assessment_digest": final.digest,
                                            "assessment_approved": final.file_state in ("approved", "published")})
    if state == "dev_provisional":
        t.problems.append("개발용 임시 기준")
    return t


def course_targets(course_file, fixture=False):
    """강좌 JSON 하나에서 검토 대상들. 파일이 잘못돼도 가능한 만큼 모은다 (관리 화면은 깨진 콘텐츠도 보여줘야 한다)."""
    rel = f"{_base(fixture)}{course_file}"   # catalog.json 의 항목은 이미 'courses/c01.json' 처럼 상대 경로다
    data = _read(rel)
    cid = data.get("id", course_file)
    out = [Target("course", cid, data.get("title_ko") or cid, cid, rel, str(data.get("content_version")),
                  (data.get("review") or {}).get("status", "?"), digest=lesson_content.content_digest(data), data=data,
                  fixture=fixture, refs={"lesson_ids": data.get("lesson_ids")})]
    for lesson in data.get("lessons") or []:
        mat = lesson.get("material") or {}
        if mat.get("status") != "missing" and mat.get("file"):
            mrel = f"{_base(fixture)}{mat['file']}"
            try:
                doc = _read(mrel)
                out.append(Target("material", lesson["id"], lesson.get("title_ko") or lesson["id"], cid, mrel,
                                  str(doc.get("content_version")), (doc.get("review") or {}).get("status", "?"),
                                  digest=lesson_content.content_digest(doc), data=doc, fixture=fixture,
                                  refs={"source_ids": doc.get("source_ids", [])}))
            except (OSError, ValueError):
                out.append(Target("material", lesson["id"], lesson["id"], cid, mrel, "?", "missing",
                                  problems=["학습자료 파일이 없거나 읽을 수 없어요."], fixture=fixture))
        quiz = lesson.get("quiz") or {}
        if quiz.get("status") != "missing" and quiz.get("assessment_id"):
            out.append(_assessment_target(quiz["assessment_id"], cid, fixture))
    final = data.get("final_assessment") or {}
    if final.get("status", "upcoming") != "upcoming" and final.get("assessment_id"):
        ft = _assessment_target(final["assessment_id"], cid, fixture)
        out.append(ft)
        if ft.data.get("passing"):
            out.append(_passing_target(ft))
    cap = data.get("capstone") or {}
    if cap.get("file"):
        crel = f"{_base(fixture)}{cap['file']}"
        try:
            doc = _read(crel)
            out.append(Target("capstone", cid, doc.get("title") or cid, cid, crel, str(doc.get("version")),
                              (doc.get("review") or {}).get("status", "?"), digest=capstone_digest(doc),
                              data=doc, fixture=fixture, refs={"rubric_version": (doc.get("rubric") or {}).get("version")}))
        except (OSError, ValueError):
            out.append(Target("capstone", cid, cid, cid, crel, "?", "missing", problems=["캡스톤 정의 파일이 없어요."],
                              fixture=fixture))
    drel = f"{_base(fixture)}debates/{cid}.json"
    if os.path.exists(os.path.join(content.CONTENT_DIR, drel)):
        for topic in _read(drel).get("topics") or []:
            out.append(Target("debate", f"{cid}/{topic.get('id')}", topic.get("title") or topic.get("id"), cid, drel,
                              "1", (topic.get("review") or {}).get("status", "?"),
                              digest=lesson_content.content_digest(topic), data=topic, fixture=fixture))
    return out


def global_targets():
    out = []
    try:
        public = _read("diagnostic.json")
        t = Target("diagnostic", public.get("id", "diagnostic"), public.get("title") or "진단평가", "", "diagnostic.json",
                   str(public.get("version")), (public.get("review") or {}).get("status", "?"))
        try:
            merged = private_content.merge(public, private_content.read_keys(public.get("id")), "diagnostic.json")
            t.data, t.digest = merged, lesson_content.content_digest(merged)
        except private_content.KeysUnavailable as exc:
            t.data = public
            t.problems.append(f"정답 키 없음 — 검토·승인할 수 없어요 ({exc}).")
        if (public.get("thresholds") or {}).get("provisional"):
            t.problems.append("난이도 추천 기준은 임시(provisional) 값이에요.")
        out.append(t)
    except (OSError, ValueError):
        pass
    for s in (_read("sources.json").get("sources") or []):
        status = (s.get("verification") or {}).get("status", "?")
        t = Target("source", s.get("id"), s.get("title") or s.get("id"), "", "sources.json", "1", status,
                   digest=lesson_content.content_digest(s), data=s)
        if status != "verified":
            t.problems.append("확인되지 않은 출처 — 학습자료에서 인용할 수 없어요.")
        out.append(t)
    return out


def course_files(fixture=False):
    index = _read(f"{_base(fixture)}catalog.json")
    return list(index.get("courses") or [])


def find_target(target_type, target_id, include_fixtures=False):
    if target_type in ("diagnostic", "source"):
        return next((t for t in global_targets() if t.type == target_type and t.id == target_id), None)
    for fixture in (False, True) if include_fixtures else (False,):
        for name in course_files(fixture):
            try:
                for t in course_targets(name, fixture):
                    if t.type == target_type and t.id == target_id:
                        return t
            except (OSError, ValueError):
                continue
    return None


# ------------------------------------------------------------------ 상태 계산
def review_state(target, reviews):
    """정본 파일 상태 + 지금 내용(지문)에 대한 DB 검토 기록으로 현재 상태를 정한다.
    반환: {state, source('file'|'db'), latest(지금 내용의 마지막 기록), stale(지난 내용에 대한 기록 수)}"""
    current = [r for r in reviews if r["content_digest"] == target.digest and target.digest]
    stale = [r for r in reviews if r["content_digest"] != target.digest]
    file_state = target.file_state
    if file_state == "fixture":
        file_state = "approved"
    if current:
        return {"state": current[-1]["to_state"], "source": "db", "latest": current[-1], "stale": len(stale)}
    base = file_state if file_state in ("draft", "in_review", "approved", "published") else "draft"
    if target.type == "source":
        base = "approved" if file_state == "verified" else "draft"
    return {"state": base, "source": "file", "latest": None, "stale": len(stale)}


def allowed_decisions(target, state):
    s = "approved" if state == "published" else state
    return [d for (frm, d) in TRANSITIONS if frm == s]


class ReviewRefused(Exception):
    pass


def validate_decision(target, state, decision, posted_digest, comment, confirmed, reviewer_name):
    """검토 결정을 받아도 되는지 확인한다 (서버 규칙). 문제가 있으면 ReviewRefused(한국어 이유)."""
    if not target.digest:
        raise ReviewRefused("이 대상은 지금 내용 지문을 계산할 수 없어 검토할 수 없어요 (정답 키 없음 등).")
    if posted_digest != target.digest:
        raise ReviewRefused("화면을 연 뒤에 내용이 바뀌었어요. 새로 고친 내용을 다시 확인해 주세요.")
    if decision not in allowed_decisions(target, state["state"]):
        raise ReviewRefused(f"지금 상태({STATE_KO.get(state['state'], state['state'])})에서는 "
                            f"'{DECISION_KO.get(decision, decision)}' 을 할 수 없어요.")
    if lesson_content._AI_MARKERS.search(str(reviewer_name or "")):
        raise ReviewRefused("AI 는 콘텐츠를 승인할 수 없어요. 사람 관리자 계정 이름으로 검토해 주세요.")
    if decision in ("approve", "request_changes") and len(str(comment or "").strip()) < 5:
        raise ReviewRefused("승인·수정 요청에는 검토 의견을 5자 이상 남겨 주세요.")
    if decision == "approve" and not confirmed:
        raise ReviewRefused("직접 내용을 검토했다는 확인란을 체크해 주세요.")
    if decision == "approve" and any("정답 키 없음" in p for p in target.problems):
        raise ReviewRefused("정답 키가 없는 평가는 승인할 수 없어요.")
    if decision == "approve" and target.type == "passing" and not target.refs.get("assessment_approved"):
        raise ReviewRefused("합격 기준은 최종 평가 자체가 승인된 뒤에 승인할 수 있어요 (평가 → 합격 기준 순서).")


def new_state(state, decision):
    s = "approved" if state == "published" else state
    return TRANSITIONS[(s, decision)]


# ------------------------------------------------------------------ 강좌별 개요
def overview(include_fixtures=False):
    """강좌별 공개 준비 상태. 정본 카탈로그를 강좌 파일마다 따로 읽어 한 파일의 오류가 전체를 가리지 않게 한다."""
    rows = []
    sources = {}
    try:
        sources = content.read_sources()
    except ContentError as exc:
        rows.append({"error": f"sources.json: {exc}"})
    for fixture in (False, True) if include_fixtures else (False,):
        for name in course_files(fixture):
            row = {"file": name, "fixture": fixture, "error": None, "blockers": [], "targets": []}
            try:
                row["targets"] = course_targets(name, fixture)
                data = row["targets"][0].data
                row.update(id=data.get("id"), title=data.get("title_ko"), status=data.get("status"),
                           lessons=len(data.get("lessons") or []))
            except (OSError, ValueError) as exc:
                row.update(id=name, title=name, error=f"강좌 파일을 읽을 수 없어요 ({type(exc).__name__}).")
                rows.append(row)
                continue
            base = os.path.join(content.CONTENT_DIR, "dev_fixtures") if fixture else content.CONTENT_DIR
            try:
                content.parse_course(data, where=row["targets"][0].file, fixture=fixture, sources=sources or None,
                                     base_dir=base)
            except ContentError as exc:
                row["error"] = str(exc)
            row["blockers"] = publication_blockers(data, row["targets"], sources)
            rows.append(row)
    return rows


def publication_blockers(data, targets, sources):
    """이 강좌를 공개(published)하려면 해결해야 할 것들 (사람이 읽는 이유 목록)."""
    out = []
    for lesson in data.get("lessons") or []:
        lid = lesson.get("id")
        if (lesson.get("material") or {}).get("status") not in ("approved", "published"):
            out.append(f"{lid}: 학습자료가 승인되지 않았어요 ({STATE_KO.get((lesson.get('material') or {}).get('status'), '?')}).")
        if "quiz" in (lesson.get("requirements") or []) and (lesson.get("quiz") or {}).get("status") not in ("approved", "published"):
            out.append(f"{lid}: 필수 형성 퀴즈가 승인되지 않았어요 ({STATE_KO.get((lesson.get('quiz') or {}).get('status'), '?')}).")
    final = data.get("final_assessment") or {}
    cap = data.get("capstone") or {}
    if final.get("status", "upcoming") == "upcoming" and not cap:
        out.append("최종 평가가 아직 없어요.")
    elif final.get("status", "upcoming") != "upcoming" and final.get("status") not in ("approved", "published"):
        out.append("최종 평가가 승인되지 않았어요.")
    for t in targets:
        if t.type == "passing" and t.file_state != "approved" and not t.fixture:
            out.append("최종 평가 합격 기준이 승인되지 않았어요 (제안값).")
        if t.type == "capstone" and t.file_state not in ("approved", "published"):
            out.append("캡스톤 안내·루브릭이 승인되지 않았어요.")
        if t.type in ("assessment",) and any("정답 키 없음" in p for p in t.problems):
            out.append(f"{t.id}: 정답 키가 없어 평가를 열 수 없어요.")
        if t.type == "material":
            unverified = [s for s in t.data.get("source_ids", []) if s in sources and not sources[s].verified]
            if unverified:
                out.append(f"{t.id}: 확인되지 않은 출처 인용 {unverified}.")
    return out


# ------------------------------------------------------------------ 릴리스 계획
def release_plan(targets, reviews_by_key, reviewer_active=None):
    """지금 내용과 지문이 같은 '승인' 기록 중 아직 정본 파일에 반영되지 않은 것들.
    reviewer_active(user_id) 가 False 인 검토자(관리자 권한이 취소된 사람)의 승인은 넣지 않는다."""
    items = []
    for t in targets:
        if t.type not in RELEASABLE:
            continue
        state = review_state(t, reviews_by_key.get(t.key, []))
        latest = state["latest"]
        if state["source"] != "db" or state["state"] != "approved" or latest is None or latest["decision"] != "approve":
            continue
        if reviewer_active is not None and not reviewer_active(latest["reviewer_user_id"]):
            continue   # 승인한 관리자의 권한이 취소됐다 → 다시 검토해야 한다
        if t.file_state in ("approved", "published") and t.type != "passing":
            continue
        items.append({"target_type": t.type, "target_id": t.id, "course_id": t.course_id, "file": t.file,
                      "content_version": t.version, "content_digest": t.digest, "review_id": latest["id"],
                      "reviewer_name": latest["reviewer_name"], "comment": latest["comment"],
                      "approved_at": latest["created_at"].strftime("%Y-%m-%d") if latest["created_at"] else ""})
    return {"schema_version": 1, "kind": "econova_release_plan",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "items": items,
            "note": "정본 JSON 의 review 블록에만 반영한다. 강좌 공개(status=published)와 배포는 사람이 따로 결정한다."}


def _approved_review_block(old, item):
    history = list((old or {}).get("history") or [])
    history.append({"status": "approved", "at": item["approved_at"], "by": item["reviewer_name"],
                    "note": f"플랫폼 관리자 승인 (검토 기록 #{item['review_id']})"})
    return {"status": "approved",
            "reviewer": {"name": item["reviewer_name"], "role": "admin", "review_id": str(item["review_id"])},
            "reviewed_at": item["approved_at"], "approved_at": item["approved_at"],
            "content_digest": item["content_digest"], "history": history}


def apply_release(plan, verify_record=None, dry_run=False):
    """릴리스 계획을 정본 JSON 에 반영한다 (CLI 전용 — 웹 요청에서는 부르지 않는다).
    항목마다 지금 파일의 지문을 다시 계산해 계획과 다르면 건너뛴다. verify_record(item) 가 있으면 DB 의 검토 기록과도 대조한다.
    반환: [(item, 결과 문자열)]"""
    if not isinstance(plan, dict) or plan.get("kind") != "econova_release_plan":
        raise ValueError("릴리스 계획 파일이 아닙니다.")
    results = []
    for item in plan.get("items") or []:
        t = find_target(item["target_type"], item["target_id"], include_fixtures=True)
        if t is None:
            results.append((item, "건너뜀: 대상을 찾을 수 없음"))
            continue
        if t.digest != item["content_digest"]:
            results.append((item, "건너뜀: 승인 뒤 내용이 바뀜 (지문 불일치) — 다시 검토 필요"))
            continue
        if verify_record is not None:
            problem, authoritative = verify_record(item)
            if problem:
                results.append((item, f"건너뜀: {problem}"))
                continue
            item = {**item, **(authoritative or {})}   # 검토자·날짜·번호는 계획이 아니라 DB 기록을 따른다
        path = os.path.join(content.CONTENT_DIR, t.file)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if t.type == "debate":
            topic = next(x for x in data["topics"] if f"{t.course_id}/{x['id']}" == t.id)
            topic["review"] = _approved_review_block(topic.get("review"), item)
        elif t.type == "passing":
            data["passing"]["status"] = "approved"
            data["passing"]["review_id"] = str(item["review_id"])
            data["passing"]["note"] = (f"{item['approved_at']} 플랫폼 관리자 {item['reviewer_name']} 승인 "
                                       f"(검토 기록 #{item['review_id']})")
        else:
            data["review"] = _approved_review_block(data.get("review"), item)
            if t.type == "capstone" and isinstance(data.get("rubric"), dict):
                data["rubric"]["status"] = "approved"   # 정의 승인 = 루브릭(기준·가중치) 승인
        if dry_run:
            results.append((item, "확인됨 (dry-run, 파일은 그대로)"))
            continue
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        results.append((item, "반영함"))
    return results


# ------------------------------------------------------------------ 계획 서명·정본 승인 검증
def _plan_body(plan):
    return json.dumps({k: v for k, v in plan.items() if k != "signature"}, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sign_plan(plan, key):
    """릴리스 계획에 HMAC 서명을 붙인다 (내보낸 서버의 ECONOVA_RELEASE_SIGNING_KEY). 키가 없으면 서명하지 않는다."""
    import hmac
    if not key:
        return plan
    return {**plan, "signature": {"alg": "HMAC-SHA256",
                                  "value": hmac.new(key.encode("utf-8"), _plan_body(plan), hashlib.sha256).hexdigest()}}


def plan_signature_ok(plan, key):
    import hmac
    sig = (plan.get("signature") or {}) if isinstance(plan, dict) else {}
    if not key or len(key) < 32 or sig.get("alg") != "HMAC-SHA256" or not isinstance(sig.get("value"), str):
        return False
    return hmac.compare_digest(sig["value"], hmac.new(key.encode("utf-8"), _plan_body(plan), hashlib.sha256).hexdigest())


def canonical_admin_approvals(include_fixtures=False):
    """정본 파일에 반영된 관리자 승인 [(target, review_id)]. 합격 기준 승인도 포함한다."""
    out = []
    for fixture in (False, True) if include_fixtures else (False,):
        for name in course_files(fixture):
            try:
                targets = course_targets(name, fixture)
            except (OSError, ValueError):
                continue
            for t in targets:
                if t.type == "passing":
                    passing = t.data.get("passing") or {}
                    if passing.get("status") == "approved" and not t.fixture:
                        out.append((t, str(passing.get("review_id") or "")))
                    continue
                reviewer = (t.data.get("review") or {}).get("reviewer") or {}
                if reviewer.get("role") == "admin":
                    out.append((t, str(reviewer.get("review_id") or "")))
    return out


def superseded_by(record, reviews_for_target):
    """이 승인 기록 뒤에 같은 대상에 대한 다른 결정(다시 검토·수정 요청 등)이 있으면 그 기록, 없으면 None."""
    later = [r for r in reviews_for_target if r["seq"] > record["seq"] and r["id"] != record["id"]]
    return later[-1] if later else None


def verify_canonical_approvals(get_record, include_fixtures=False, list_reviews=None, reviewer_active=None):
    """정본의 관리자 승인마다 DB 의 검토 기록이 있고 (승인 결정·같은 대상·같은 지문·그 뒤 다른 결정 없음) 맞는지 확인한다.
    예전 형식(role=teacher) 승인은 DB 기록으로 확인할 수 없으므로 문제로 알린다 (실제 강좌에는 아직 없음).
    반환: [(target, 문제)] — 비어 있으면 모든 승인이 DB 기록으로 뒷받침된다. 배포 직후 운영 DB 로 실행한다."""
    problems = []
    for t, review_id in canonical_admin_approvals(include_fixtures):
        record = get_record(review_id) if review_id else None
        if record is None:
            problems.append((t, f"검토 기록 #{review_id or '?'} 이 DB 에 없어요."))
        elif (record["decision"], record["target_type"], record["target_id"]) != ("approve", t.type, t.id):
            problems.append((t, f"검토 기록 #{review_id} 이 이 대상의 승인이 아니에요."))
        elif record["content_digest"] != t.digest:
            problems.append((t, f"검토 기록 #{review_id} 의 지문이 지금 내용과 달라요."))
        elif reviewer_active is not None and not reviewer_active(record["reviewer_user_id"]):
            problems.append((t, f"검토 기록 #{review_id} 을 남긴 관리자의 권한이 취소됐어요. 다시 검토하세요."))
        elif list_reviews is not None and superseded_by(record, list_reviews(t.type, t.id)):
            later = superseded_by(record, list_reviews(t.type, t.id))
            problems.append((t, f"검토 기록 #{review_id} 뒤에 '{DECISION_KO.get(later['decision'], later['decision'])}'"
                                f"(#{later['id']}) 이 기록돼 이 승인은 더 이상 유효하지 않아요."))
    for fixture in (False, True) if include_fixtures else (False,):
        for name in course_files(fixture):
            try:
                targets = course_targets(name, fixture)
            except (OSError, ValueError):
                continue
            for t in targets:
                reviewer = (t.data.get("review") or {}).get("reviewer") or {}
                if reviewer.get("role") == "teacher" and (t.data.get("review") or {}).get("status") in ("approved", "published"):
                    problems.append((t, "예전 형식(role=teacher) 승인 — DB 검토 기록·내용 지문으로 확인할 수 없어요. 다시 검토하세요."))
    return problems


def public_view(target):
    """화면에 보여줄 원본 JSON (관리자 전용 화면). 평가·진단평가에는 정답 키가 합쳐져 있다."""
    return json.dumps(copy.deepcopy(target.data), ensure_ascii=False, indent=2)
