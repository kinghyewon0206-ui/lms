"""플랫폼 콘텐츠 관리 화면 (Phase 7, 관리자 전용). 같은 Blueprint(econova.*)에 붙는다.

- /admin/content                      강좌별 공개 준비 상태, 검토 대기, 검사 오류, 운영 집계(숫자만)
- /admin/content/<type>/<id>          대상 내용·검토 기록·검토 결정
- /admin/content/release              릴리스 계획 (승인 기록 → 정본 JSON 반영 목록, JSON 내려받기)
- /admin/diagnostics/request          프록시 홉 수 확인 (ECONOVA_PROXY_DIAGNOSTICS=1 일 때만, 관리자 본인 요청의 헤더만)

학생 개인의 학습 기록·대화·평가 기록을 보는 화면은 없다. 정본 JSON 은 웹 요청으로 바꾸지 않는다.
"""
import json

from flask import abort, current_app, flash, g, redirect, request, url_for

from econova import admin_content as ac
from econova import config, content, login_guard, storage
from econova.ai import usage as ai_usage
from econova.roles import admin_required
from econova.web import bp, render_econova


def _no_store(resp):
    resp = current_app.make_response(resp)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


def _reviewer_active(user_id):
    """검토자가 지금도 유효한 관리자인가 (권한이 취소되면 그 사람의 승인은 다시 검토해야 한다)."""
    return storage.get_admin_grant(user_id) is not None


def _reviews_by_key():
    out = {}
    for r in storage.list_content_reviews():
        out.setdefault(f"{r['target_type']}:{r['target_id']}", []).append(r)
    return out


@bp.route("/admin")
@admin_required
def admin_home():
    return redirect(url_for("econova.admin_content"))


@bp.route("/admin/content")
@admin_required
def admin_content():
    reviews = _reviews_by_key()
    fixtures = config.dev_fixtures_enabled()
    rows = ac.overview(include_fixtures=fixtures)
    for row in rows:
        row["states"] = {t.key: ac.review_state(t, reviews.get(t.key, [])) for t in row.get("targets", [])}
    globals_ = ac.global_targets()
    gstates = {t.key: ac.review_state(t, reviews.get(t.key, [])) for t in globals_}
    pending = [(t, s) for row in rows for t in row.get("targets", []) for s in [row["states"][t.key]]
               if s["state"] == "in_review"] + [(t, gstates[t.key]) for t in globals_ if gstates[t.key]["state"] == "in_review"]
    stale = [(t, s) for row in rows for t in row.get("targets", []) for s in [row["states"][t.key]] if s["stale"]]
    unverified = ac.verify_canonical_approvals(storage.get_content_review, include_fixtures=fixtures,
                                               list_reviews=storage.list_content_reviews, reviewer_active=_reviewer_active)
    return _no_store(render_econova("econova/admin/content.html", rows=rows, globals_=globals_, gstates=gstates,
                                    pending=pending, stale=stale, unverified=unverified, fixtures=fixtures, state_ko=ac.STATE_KO,
                                    type_ko=ac.TARGET_TYPES, metrics=storage.aggregate_counts(ai_usage.today())))


def _target_or_404(target_type, target_id):
    if target_type not in ac.TARGET_TYPES:
        abort(404)
    t = ac.find_target(target_type, target_id, include_fixtures=config.dev_fixtures_enabled())
    if t is None:
        abort(404)
    return t


@bp.route("/admin/content/<target_type>/<path:target_id>")
@admin_required
def admin_target(target_type, target_id):
    t = _target_or_404(target_type, target_id)
    reviews = storage.list_content_reviews(t.type, t.id)
    state = ac.review_state(t, reviews)
    return _no_store(render_econova(
        "econova/admin/target.html", t=t, reviews=reviews, state=state, decisions=ac.allowed_decisions(t, state["state"]),
        decision_ko=ac.DECISION_KO, state_ko=ac.STATE_KO, type_ko=ac.TARGET_TYPES, raw=ac.public_view(t),
        sources=content.read_sources()))


@bp.route("/admin/content/<target_type>/<path:target_id>/review", methods=["POST"])
@admin_required
def admin_review(target_type, target_id):
    t = _target_or_404(target_type, target_id)
    reviews = storage.list_content_reviews(t.type, t.id)
    state = ac.review_state(t, reviews)
    decision = request.form.get("decision", "")
    comment = request.form.get("comment", "").strip()[:2000]
    if t.type == "passing" and not t.refs.get("assessment_approved"):
        # 정본에는 아직 없어도, 같은 내용의 최종 평가가 DB 에서 현재 승인 상태면 순서를 지킨 것으로 본다
        final = ac.find_target("assessment", t.id, include_fixtures=config.dev_fixtures_enabled())
        if final is not None and ac.review_state(final, storage.list_content_reviews("assessment", final.id))["state"] == "approved":
            t.refs["assessment_approved"] = True
    page = url_for("econova.admin_target", target_type=t.type, target_id=t.id)
    try:
        ac.validate_decision(t, state, decision, request.form.get("content_digest", ""), comment,
                             request.form.get("confirm_reviewed") == "1", g.user["name"])
    except ac.ReviewRefused as exc:
        flash(str(exc), "error")
        return redirect(page, 303)
    to_state = ac.new_state(state["state"], decision)
    storage.add_content_review({
        "target_type": t.type, "target_id": t.id, "content_version": t.version, "content_digest": t.digest,
        "decision": decision, "from_state": state["state"] if state["state"] != "published" else "approved",
        "to_state": to_state, "reviewer_user_id": g.user["id"], "reviewer_name": g.user["name"], "comment": comment,
        "refs": {**t.refs, "file": t.file, "course_id": t.course_id}})
    flash(f"'{ac.DECISION_KO[decision]}' 결정을 기록했어요 (정본 파일은 바뀌지 않아요. 반영은 릴리스 준비에서).", "success")
    return redirect(page, 303)


@bp.route("/admin/content/release")
@admin_required
def admin_release():
    reviews = _reviews_by_key()
    fixtures = config.dev_fixtures_enabled()
    targets = [t for row in ac.overview(include_fixtures=fixtures) for t in row.get("targets", [])]
    plan = ac.sign_plan(ac.release_plan(targets, reviews, reviewer_active=_reviewer_active),
                        config.env("ECONOVA_RELEASE_SIGNING_KEY"))
    if request.args.get("download") == "1":
        resp = current_app.response_class(json.dumps(plan, ensure_ascii=False, indent=2), mimetype="application/json")
        resp.headers["Content-Disposition"] = "attachment; filename=econova-release-plan.json"
        return _no_store(resp)
    return _no_store(render_econova("econova/admin/release.html", plan=plan, type_ko=ac.TARGET_TYPES))


# 진단 화면에 보여 줄 프록시 관련 헤더 (값은 관리자 본인 요청의 것. 저장·기록하지 않는다)
PROXY_HEADERS = ("X-Forwarded-For", "X-Forwarded-Proto", "X-Forwarded-Host", "X-Real-IP", "Forwarded",
                 "True-Client-IP", "CF-Connecting-IP")


@bp.route("/admin/diagnostics/request")
@admin_required
def admin_request_diagnostics():
    """ECONOVA_TRUSTED_PROXY_HOPS 를 정하기 위한 확인 화면. 기본으로 꺼져 있다 (켜져 있지 않으면 404).
    확인이 끝나면 ECONOVA_PROXY_DIAGNOSTICS 를 지운다 (docs/phase-8b2-integration.md 의 프록시 확인 절차)."""
    if config.env("ECONOVA_PROXY_DIAGNOSTICS") != "1":
        abort(404)
    info = login_guard.ip_candidates()
    headers = [(h, request.headers.get(h)) for h in PROXY_HEADERS if request.headers.get(h) is not None]
    return _no_store(render_econova("econova/admin/request_diagnostics.html", info=info, headers=headers,
                                    scheme=request.scheme, secure_cookie=current_app.config["SESSION_COOKIE_SECURE"]))
