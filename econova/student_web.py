"""학생 본인 화면 (Phase 7): 개인 학습 보고서, SDG 캡스톤. 같은 Blueprint(econova.*)에 붙는다.

모든 화면은 로그인한 본인(g.user)의 기록만 다룬다. 다른 학생의 id 를 받는 주소는 없다.
캡스톤은 공개된 강좌를 수강 중이고, 승인된 캡스톤 정의가 있을 때만 열린다 (c09 는 아직 공개 전이라 열리지 않는다).
"""
from flask import abort, flash, g, redirect, request, url_for

from econova import capstone as cap
from econova import learning, progress, quotas, report as report_mod, storage
from econova.ai import capstone as ai_capstone
from econova.ai.client import AIError
from econova.auth import login_required
from econova.web import bp, render_econova


@bp.route("/report")
@login_required
def report():
    from econova import ai_web
    return render_econova("econova/report.html", report=report_mod.build(g.user["id"], learning.catalog()),
                          ai_enabled=ai_web.ai_enabled())


# ---------------------------------------------------------------- SDG 캡스톤
def _capstone_access(course_id):
    course = learning.visible_course(course_id)
    if course is None or course.capstone is None:
        abort(404)
    if not course.published or not course.capstone_ready:
        abort(403)   # 공개 전 강좌(c09 포함)·승인 전 캡스톤
    enrollment = storage.get_enrollment(g.user["id"], course.id)
    if enrollment is None:
        flash("Please enroll in the course first.", "error")
        return None
    return course


def _state(course):
    uid = g.user["id"]
    project = storage.get_capstone(uid, course.id)
    versions = storage.list_capstone_versions(uid, course.id)
    assessments = storage.list_capstone_self_assessments(uid, course.id)
    prog = progress.course_progress(course, storage.list_lesson_progress(uid, course.id))
    return project, versions, assessments, prog


def reconcile_completion(course, project, versions, assessments, prog):
    """완료 조건을 모두 갖췄고 정책이 허용하면 수료를 기록한다 (멱등). 반환: 점검표."""
    state = cap.completion_state(course.capstone, prog, project, versions, assessments)
    policy = cap.completion_policy(course)
    state["policy"] = policy
    if state["complete"] and policy:
        enrollment = storage.get_enrollment(g.user["id"], course.id)
        if enrollment and enrollment["status"] != "completed":
            storage.complete_enrollment(g.user["id"], course.id, f"capstone-v{state['submitted_version']}", policy)
    return state


@bp.route("/capstone/<course_id>")
@login_required
def capstone_home(course_id):
    course = _capstone_access(course_id)
    if course is None:
        return redirect(url_for("econova.course_detail", course_id=course_id), 303)
    project, versions, assessments, prog = _state(course)
    sections = cap.latest_sections(versions)
    state = reconcile_completion(course, project, versions, assessments, prog)
    latest_sa = cap.self_assessment_for(assessments, versions[-1]["version"]) if versions else None
    from econova import ai_web
    return render_econova(
        "econova/capstone/home.html", course=course, defn=course.capstone, project=project, versions=versions,
        sections=sections, steps=cap.step_status(course.capstone, sections), missing=cap.missing_fields(course.capstone, sections),
        state=state, latest_sa=latest_sa, sa_summary=cap.weighted_summary(course.capstone, latest_sa["scores"]) if latest_sa else None,
        feedback=storage.list_capstone_feedback(g.user["id"], course.id)[-3:], ai_enabled=ai_web.ai_enabled(),
        enrollment=storage.get_enrollment(g.user["id"], course.id), sdg_names=learning.catalog().sdgs)


@bp.route("/capstone/<course_id>/edit", methods=["GET", "POST"])
@login_required
def capstone_edit(course_id):
    course = _capstone_access(course_id)
    if course is None:
        return redirect(url_for("econova.course_detail", course_id=course_id), 303)
    defn = course.capstone
    versions = storage.list_capstone_versions(g.user["id"], course.id)
    sections = cap.latest_sections(versions)
    errors = {}
    if request.method == "POST":
        new, errors = cap.clean_sections(defn, request.form)
        if not errors and new != sections:
            try:
                quotas.check("CAPSTONE_VERSIONS", len(versions))
            except quotas.QuotaExceeded as exc:   # 글은 지우지 않고 화면에 그대로 둔다
                errors["_quota"] = exc.message
        if not errors:
            if new != sections:
                version = storage.save_capstone_version(g.user["id"], course.id, new, defn.version)
                flash(f"Saved (version {version}). Your earlier versions are still kept.", "success")
            else:
                flash("Nothing changed, so no new version was created.", "success")
            step = request.form.get("next_step") or ""
            return redirect(url_for("econova.capstone_edit", course_id=course.id) + (f"#step-{step}" if step else ""), 303)
        flash(errors["_quota"] if "_quota" in errors else
              "We couldn't save your work. Please fix the highlighted fields. Everything you typed is still on the page.", "error")
        sections = {**sections, **{f["id"]: request.form.get(f["id"], "") for f in defn.fields}}
    return render_econova("econova/capstone/edit.html", course=course, defn=defn, sections=sections, errors=errors,
                          version=versions[-1]["version"] if versions else 0, sdg_names=learning.catalog().sdgs,
                          focus=request.args.get("step", ""))


@bp.route("/capstone/<course_id>/self-assessment", methods=["GET", "POST"])
@login_required
def capstone_self_assessment(course_id):
    course = _capstone_access(course_id)
    if course is None:
        return redirect(url_for("econova.course_detail", course_id=course_id), 303)
    defn = course.capstone
    versions = storage.list_capstone_versions(g.user["id"], course.id)
    if not versions:
        flash("Please write and save your project first.", "error")
        return redirect(url_for("econova.capstone_edit", course_id=course.id), 303)
    version = versions[-1]["version"]
    assessments = storage.list_capstone_self_assessments(g.user["id"], course.id)
    current = cap.self_assessment_for(assessments, version)
    errors = {}
    if request.method == "POST":
        if str(request.form.get("version")) != str(version):
            flash("A new version of your project was saved while you were doing your self-assessment. Please assess the latest version again.", "error")
            return redirect(url_for("econova.capstone_self_assessment", course_id=course.id), 303)
        scores, errors = cap.clean_self_assessment(defn, request.form)
        if not errors:
            storage.save_capstone_self_assessment(g.user["id"], course.id, version, defn.rubric["version"], scores)
            flash("Your self-assessment was saved. It's your own check, not an official score.", "success")
            return redirect(url_for("econova.capstone_home", course_id=course.id) + "#self-assessment", 303)
        flash("Please choose a level for every criterion.", "error")
        current = {"scores": {c["id"]: {"level": int(request.form.get(f"score_{c['id']}") or 0),
                                         "note": request.form.get(f"note_{c['id']}", "")} for c in defn.rubric["criteria"]}}
    return render_econova("econova/capstone/self_assessment.html", course=course, defn=defn, version=version,
                          current=current, errors=errors, sections=versions[-1]["sections"])


@bp.route("/capstone/<course_id>/submit", methods=["POST"])
@login_required
def capstone_submit(course_id):
    course = _capstone_access(course_id)
    if course is None:
        return redirect(url_for("econova.course_detail", course_id=course_id), 303)
    defn = course.capstone
    versions = storage.list_capstone_versions(g.user["id"], course.id)
    home = url_for("econova.capstone_home", course_id=course.id)
    if not versions:
        flash("Please write your project first.", "error")
        return redirect(home, 303)
    latest = versions[-1]
    missing = cap.missing_fields(defn, latest["sections"])
    if missing:
        flash(f"You still have {len(missing)} required field(s) to fill in.", "error")
        return redirect(home + "#checklist", 303)
    if latest["kind"] == "submitted":
        flash("You've already submitted this version.", "success")
        return redirect(home, 303)
    assessments = storage.list_capstone_self_assessments(g.user["id"], course.id)
    sa = cap.self_assessment_for(assessments, latest["version"])
    if sa is None:
        flash("Please complete a self-assessment for this version before you submit.", "error")
        return redirect(url_for("econova.capstone_self_assessment", course_id=course.id), 303)
    try:
        quotas.check("CAPSTONE_VERSIONS", len(versions))
    except quotas.QuotaExceeded as exc:
        flash(exc.message, "error")
        return redirect(home, 303)
    version = storage.save_capstone_version(g.user["id"], course.id, latest["sections"], defn.version, kind="submitted")
    storage.save_capstone_self_assessment(g.user["id"], course.id, version, sa["rubric_version"], sa["scores"])
    project, versions, assessments, prog = _state(course)
    state = reconcile_completion(course, project, versions, assessments, prog)
    flash(f"Your project was submitted (version {version}). " + ("You've met all the course completion requirements." if state["complete"] else
                                                  "Check the remaining completion requirements in the checklist below."), "success")
    return redirect(home + "#checklist", 303)


@bp.route("/capstone/<course_id>/versions/<int:version>")
@login_required
def capstone_version(course_id, version):
    course = _capstone_access(course_id)
    if course is None:
        return redirect(url_for("econova.course_detail", course_id=course_id), 303)
    v = storage.get_capstone_version(g.user["id"], course.id, version)
    if v is None:
        abort(404)
    sa = cap.self_assessment_for(storage.list_capstone_self_assessments(g.user["id"], course.id), version)
    return render_econova("econova/capstone/version.html", course=course, defn=course.capstone, v=v, sa=sa,
                          sa_summary=cap.weighted_summary(course.capstone, sa["scores"]) if sa else None,
                          sdg_names=learning.catalog().sdgs)


@bp.route("/capstone/<course_id>/feedback", methods=["POST"])
@login_required
def capstone_feedback(course_id):
    course = _capstone_access(course_id)
    if course is None:
        return redirect(url_for("econova.course_detail", course_id=course_id), 303)
    versions = storage.list_capstone_versions(g.user["id"], course.id)
    home = url_for("econova.capstone_home", course_id=course.id)
    if not versions:
        flash("Please write and save your project first.", "error")
        return redirect(home, 303)
    focus = request.form.get("step", "")
    if focus and focus not in {s["id"] for s in course.capstone.steps}:
        abort(400)
    try:
        quotas.check("CAPSTONE_FEEDBACK", len(storage.list_capstone_feedback(g.user["id"], course.id)))
        ai_capstone.feedback(g.user["id"], course, course.capstone, versions[-1]["version"], versions[-1]["sections"],
                             learning.catalog().sdgs, focus_step=focus or None)
        flash("The AI coach sent you questions and suggestions. This is not a score or a grade.", "success")
    except quotas.QuotaExceeded as exc:
        flash(exc.message, "error")
    except AIError as exc:
        flash(exc.message, "error")
    return redirect(home + "#ai-coach", 303)
