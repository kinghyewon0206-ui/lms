"""ECONOVA 화면: 강좌 카탈로그, 강좌 상세, 수강 신청, 난이도, 레슨.

규칙은 econova/learning.py 에 있고, 여기서는 요청을 받아 그 결과를 화면에 넘긴다.
사용자는 항상 로그인한 본인(g.user)이다. 다른 학생의 id 를 받는 주소는 없다.

강좌 JSON 은 ECONOVA 화면(render_econova)에서만 읽는다. 로그인·기존 LMS 화면은 강좌 JSON 이 깨져 있어도 동작한다.
"""
import re
import secrets

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for

from econova import config, content, diagnostic, graphs, learning, private_content, quotas, simulations, storage
from econova.auth import login_required

bp = Blueprint("econova", __name__)


def render_econova(template, **context):
    """ECONOVA 템플릿 렌더링. SDG 이름·색과 난이도 이름을 함께 넘긴다 (예전에는 모든 화면에서 읽었다)."""
    return render_template(template, sdg_info=learning.catalog().sdgs, difficulty_names=content.DIFFICULTY_NAMES,
                           graph_geometry=graphs.geometry, **context)


def _view_level(default):
    """?level= 로 다른 난이도 설명을 볼 수 있다. 수강 정보의 난이도는 바뀌지 않는다."""
    level = request.args.get("level", "")
    return level if level in content.DIFFICULTIES else default


@bp.app_errorhandler(private_content.KeysUnavailable)
def _assessment_unavailable(exc):
    """정답 키가 없거나 맞지 않아 평가를 닫았을 때 (fail closed). 이유는 서버 로그에만 남긴다 (정답 값은 메시지에 없음)."""
    current_app.logger.error("ECONOVA 평가를 열 수 없습니다 (%s): %s", request.path, exc)
    return render_template("errors/assessment_unavailable.html"), 503


@bp.app_errorhandler(content.ContentError)
def _content_unavailable(exc):
    """강좌 JSON 이 잘못돼 ECONOVA 화면을 만들 수 없을 때. 자세한 이유는 서버 로그에만 남긴다."""
    current_app.logger.error("ECONOVA 강좌 콘텐츠를 불러오지 못했습니다 (%s): %s", request.path, exc)
    return render_template("errors/content_unavailable.html"), 503


def _course_or_404(course_id):
    course = learning.visible_course(course_id)
    if course is None:
        abort(404)
    return course


@bp.route("/courses")
@login_required
def catalog():
    cat = learning.catalog()
    enrolled = {e["course_id"] for e in storage.list_enrollments(g.user["id"])}
    visible = cat.visible()
    return render_econova(
        "econova/catalog.html",
        enrolled_courses=[c for c in visible if c.id in enrolled],
        available=[c for c in visible if c.published and c.id not in enrolled],
        upcoming=[c for c in visible if not c.published and c.id not in enrolled],
        enrolled_ids=enrolled,
    )


@bp.route("/courses/<course_id>")
@login_required
def course_detail(course_id):
    course = _course_or_404(course_id)
    state = learning.course_state(g.user["id"], course)
    return render_econova("econova/course_detail.html", course=course, diagnostic=learning.latest_diagnostic(g.user["id"]),
                          final_info=_final_info(course, state), **state)


@bp.route("/courses/<course_id>/enroll", methods=["POST"])
@login_required
def enroll(course_id):
    course = _course_or_404(course_id)
    try:
        latest = learning.latest_diagnostic(g.user["id"])
        created = learning.enroll(g.user["id"], course, request.form.get("difficulty", learning.DEFAULT_DIFFICULTY),
                                  recommended=latest["recommended_level"] if latest else None)
    except learning.LearningError as exc:
        flash(exc.message, "error")
        return redirect(url_for("econova.course_detail", course_id=course.id)), 303
    flash("수강 신청이 완료되었어요." if created else "이미 수강 중인 강좌예요.", "success")
    return redirect(url_for("econova.course_detail", course_id=course.id))


@bp.route("/courses/<course_id>/difficulty", methods=["POST"])
@login_required
def set_difficulty(course_id):
    course = _course_or_404(course_id)
    try:
        learning.change_difficulty(g.user["id"], course, request.form.get("difficulty", ""))
    except learning.LearningError as exc:
        flash(exc.message, "error")
        return redirect(url_for("econova.course_detail", course_id=course.id)), 303
    flash("난이도를 바꿨어요.", "success")
    return redirect(url_for("econova.course_detail", course_id=course.id))


@bp.route("/courses/<course_id>/continue")
@login_required
def continue_learning(course_id):
    """이어서 학습: 아직 완료하지 않은 첫 레슨으로. 모두 끝났거나 볼 수 없으면 강좌 상세로."""
    course = _course_or_404(course_id)
    state = learning.course_state(g.user["id"], course)
    nxt = state["progress"]["next_lesson"]
    if state["enrollment"] is None or not course.published or nxt is None:
        return redirect(url_for("econova.course_detail", course_id=course.id))
    return redirect(url_for("econova.lesson", course_id=course.id, lesson_id=nxt.id))


def _lesson_or_error(course_id, lesson_id):
    try:
        return learning.lesson_access(g.user["id"], course_id, lesson_id)
    except learning.LearningError as exc:
        if exc.code == "not_found":
            abort(404)
        if exc.code == "not_published":
            abort(403)
        flash(exc.message, "error")   # not_enrolled
        return None


@bp.route("/learn/<course_id>/<lesson_id>")
@login_required
def lesson(course_id, lesson_id):
    found = _lesson_or_error(course_id, lesson_id)
    if found is None:
        return redirect(url_for("econova.course_detail", course_id=course_id))
    course, lesson_, enrollment = found
    state = learning.course_state(g.user["id"], course)
    record = state["records"].get(lesson_.id)
    index = course.lessons.index(lesson_)
    quiz_attempts = storage.list_assessment_attempts(g.user["id"], assessment_id=lesson_.quiz_assessment.id) \
        if lesson_.quiz_approved else []
    return render_econova(
        "econova/lesson.html", course=course, lesson=lesson_, enrollment=enrollment, record=record,
        quiz_attempts=quiz_attempts,
        sim_widgets=[sim_context(sid, lesson=lesson_, course=course) for sid in lesson_.simulations],
        doc=lesson_.content if lesson_.material_approved else None,   # 승인·공개된 자료만 학생에게 보여준다
        level=_view_level(enrollment["selected_difficulty"]), sources=learning.catalog().sources,
        status=state["progress"]["statuses"][lesson_.id], progress=state["progress"], sections=learning.LESSON_SECTIONS,
        prev_lesson=course.lessons[index - 1] if index > 0 else None,
        next_lesson=course.lessons[index + 1] if index + 1 < len(course.lessons) else None,
        tutor=_tutor_panel(lesson_) if lesson_.material_approved else None,
    )


def _tutor_panel(lesson_):
    """레슨 화면의 AI 튜터: 본인 대화 기록(서버 저장분)과 추천 질문. AI 가 꺼져 있으면 안내만."""
    from econova import ai_web
    from econova.ai import tutor
    conv, messages = tutor.history(g.user["id"], lesson_)
    return {"enabled": ai_web.ai_enabled(), "conversation_id": conv["id"] if conv else "", "messages": messages,
            "suggested": tutor.SUGGESTED, "max_chars": ai_web._max_chars()}


@bp.route("/learn/<course_id>/<lesson_id>/material-reviewed", methods=["POST"])
@login_required
def material_reviewed(course_id, lesson_id):
    found = _lesson_or_error(course_id, lesson_id)
    if found is None:
        return redirect(url_for("econova.course_detail", course_id=course_id)), 303
    course, lesson_, _ = found
    try:
        learning.mark_material_reviewed(g.user["id"], course, lesson_)
    except learning.LearningError as exc:
        flash(exc.message, "error")
    return redirect(url_for("econova.lesson", course_id=course.id, lesson_id=lesson_.id))


@bp.route("/preview/<course_id>/<lesson_id>")
@login_required
def preview(course_id, lesson_id):
    """검토용 학습자료 미리보기. 검토 전 초안(draft·in_review)도 보여준다.
    ECONOVA_CONTENT_PREVIEW=1 인 개발 환경이거나 플랫폼 관리자일 때만 열리고, 그 밖에서는 없는 주소(404)처럼 동작한다."""
    from econova import roles
    if not (config.content_preview_enabled() or roles.is_admin(g.user)):   # 개발 스위치 또는 플랫폼 관리자만
        abort(404)
    course = learning.catalog().course(course_id)
    lesson_ = course.lesson(lesson_id) if course else None
    if lesson_ is None or lesson_.content is None:
        abort(404)
    resp = current_app.make_response(render_econova(
        "econova/preview.html", course=course, lesson=lesson_, doc=lesson_.content, level=_view_level("beginner"),
        sim_widgets=[sim_context(sid, lesson=None, course=None) for sid in lesson_.simulations],
        sections=learning.LESSON_SECTIONS, sources=learning.catalog().sources, record=None, allow_review=False))
    resp.headers["X-Robots-Tag"] = "noindex"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------------------------------------------------------------- 진단평가
# 강좌 JSON 과 별개로 동작한다 (render_econova 대신 필요한 값만 넘김). 채점은 diagnostic.score 의 규칙으로만 한다.
def _render_diagnostic(template, **context):
    return render_template(template, difficulty_names=content.DIFFICULTY_NAMES, graph_geometry=graphs.geometry,
                           test=diagnostic.load(), **context)


@bp.route("/diagnostic")
@login_required
def diagnostic_home():
    attempts = storage.list_diagnostic_attempts(g.user["id"])
    return _render_diagnostic("econova/diagnostic/index.html", attempts=attempts)


@bp.route("/diagnostic/take", methods=["GET", "POST"])
@login_required
def diagnostic_take():
    test = diagnostic.load()
    if not test["answer_keys"]:   # 정답 키 없이는 응시·채점하지 않는다
        raise private_content.KeysUnavailable(test["keys_problem"])
    if not diagnostic.servable(test):   # 운영에서는 사람 승인 전 진단평가를 열지 않는다
        raise private_content.KeysUnavailable("진단평가가 아직 사람 검토(승인) 전입니다.")
    if request.method == "POST":
        try:
            quotas.check("DIAGNOSTIC_ATTEMPTS", len(storage.list_diagnostic_attempts(g.user["id"])))
        except quotas.QuotaExceeded as exc:
            flash(exc.message, "error")
            return redirect(url_for("econova.diagnostic_home")), 303
        answers = {q["id"]: request.form.get(f"q_{q['id']}", "") for q in test["questions"]}
        attempt_id = storage.save_diagnostic_attempt(g.user["id"], diagnostic.score(answers, test))
        return redirect(url_for("econova.diagnostic_result", attempt_id=attempt_id))
    return _render_diagnostic("econova/diagnostic/take.html", questions=diagnostic.public_questions())


@bp.route("/diagnostic/attempts/<attempt_id>")
@login_required
def diagnostic_result(attempt_id):
    attempt = storage.get_diagnostic_attempt(g.user["id"], attempt_id)
    if attempt is None:   # 없거나 다른 학생의 기록
        abort(404)
    test = diagnostic.load()
    by_id = {q["id"]: q for q in test["questions"]} if test["answer_keys"] else {}   # 키가 없으면 해설도 없다
    return _render_diagnostic("econova/diagnostic/result.html", attempt=attempt, by_id=by_id,
                              reasons=diagnostic.explain(attempt, test))


# ---------------------------------------------------------------- 형성 퀴즈 · 최종 평가
# 정답·해설은 서버에만 있다. 화면에는 assessment.public_questions() 만 보낸다.
# 제출 화면을 열 때 일회용 토큰을 세션에 저장하고, 제출할 때 같은 토큰이어야 받는다. 저장소는 (학생, 토큰)을 한 번만 저장한다.
def _issue_token(assessment_id):
    tokens = dict(session.get("assess_tokens") or {})
    tokens[assessment_id] = secrets.token_urlsafe(16)
    session["assess_tokens"] = dict(list(tokens.items())[-10:])
    return tokens[assessment_id]


def _learning_error(exc, course_id):
    if exc.code in ("not_found", "unavailable"):
        abort(404)
    if exc.code == "not_published":
        abort(403)
    flash(exc.message, "error")   # not_enrolled, locked, no_attempts
    return redirect(url_for("econova.course_detail", course_id=course_id)), 303


def _final_info(course, state):
    """강좌 상세의 최종 평가 칸: 상태와 남은 횟수, 최고 결과."""
    if not course.published or not course.final_ready:
        return {"state": "upcoming"}
    enrollment = state["enrollment"]
    if enrollment is None:
        return {"state": "not_enrolled", "assessment": course.final}
    attempts = storage.list_assessment_attempts(g.user["id"], assessment_id=course.final.id)
    prog = state["progress"]
    info = {"assessment": course.final, "attempts": attempts, "best": learning.best_attempt(attempts),
            "left": learning.attempts_left(g.user["id"], course.final),
            "usable": course.final.passing_usable(course.fixture)}
    if enrollment["status"] == "completed":
        return {**info, "state": "completed"}
    if prog["completed"] < prog["total"]:
        return {**info, "state": "locked"}
    return {**info, "state": "open"}


def _handle_submission(course, assessment, lesson, page_url):
    token = request.form.get("submission_token", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", token):   # 발급 토큰 형식만 (Firestore 문서 id 로도 쓰이므로)
        abort(400)
    existing = storage.find_attempt_by_token(g.user["id"], token)
    if existing is not None:   # 다시 보낸 제출: 새로 저장하지 않고, 진도 반영만 맞춘 뒤(멱등) 처음 결과로
        learning.reconcile_attempt(g.user["id"], course, assessment, existing, lesson)
        return redirect(url_for("econova.assessment_result", attempt_id=existing["id"]))
    if (session.get("assess_tokens") or {}).get(assessment.id) != token:
        flash("제출 화면이 오래되어 다시 열었어요. 답을 확인하고 다시 제출해 주세요.", "error")
        return redirect(page_url), 303
    answers = {q["id"]: request.form.get(f"q_{q['id']}", "") for q in assessment.questions}
    try:
        attempt_id, _ = learning.submit_assessment(g.user["id"], course, assessment, answers, token, lesson=lesson)
    except learning.LearningError as exc:
        return _learning_error(exc, course.id)
    tokens = dict(session.get("assess_tokens") or {})
    tokens.pop(assessment.id, None)
    session["assess_tokens"] = tokens
    return redirect(url_for("econova.assessment_result", attempt_id=attempt_id))


def _render_take(course, assessment, lesson, action):
    learning.require_keys(assessment)   # 정답 키가 없으면 응시 화면을 열지 않는다 (제출 복구는 키 없이도 된다)
    return render_econova("econova/assessment/take.html", course=course, assessment=assessment, lesson=lesson,
                          questions=assessment.public_questions(), action=action, token=_issue_token(assessment.id),
                          left=learning.attempts_left(g.user["id"], assessment),
                          attempts=storage.list_assessment_attempts(g.user["id"], assessment_id=assessment.id))


@bp.route("/learn/<course_id>/<lesson_id>/quiz", methods=["GET", "POST"])
@login_required
def lesson_quiz(course_id, lesson_id):
    try:
        course, lesson_, _enrollment, quiz = learning.quiz_access(g.user["id"], course_id, lesson_id)
    except learning.LearningError as exc:
        return _learning_error(exc, course_id)
    page = url_for("econova.lesson_quiz", course_id=course.id, lesson_id=lesson_.id)
    if request.method == "POST":
        return _handle_submission(course, quiz, lesson_, page)
    if learning.attempts_left(g.user["id"], quiz) == 0:
        flash("응시할 수 있는 횟수를 모두 사용했어요.", "error")
        return redirect(url_for("econova.assessment_history", course_id=course.id))
    return _render_take(course, quiz, lesson_, page)


@bp.route("/courses/<course_id>/final", methods=["GET", "POST"])
@login_required
def final_assessment(course_id):
    try:
        course, _enrollment, final = learning.final_access(g.user["id"], course_id)
    except learning.LearningError as exc:
        return _learning_error(exc, course_id)
    page = url_for("econova.final_assessment", course_id=course.id)
    if request.method == "POST":
        return _handle_submission(course, final, None, page)
    if learning.attempts_left(g.user["id"], final) == 0:
        flash("최종 평가 응시 횟수를 모두 사용했어요.", "error")
        return redirect(url_for("econova.assessment_history", course_id=course.id))
    return _render_take(course, final, None, page)


@bp.route("/assessments/attempts/<attempt_id>")
@login_required
def assessment_result(attempt_id):
    attempt = storage.get_assessment_attempt(g.user["id"], attempt_id)
    if attempt is None:   # 없거나 다른 학생의 기록
        abort(404)
    course = learning.catalog().course(attempt["course_id"])
    assessment = None
    if course is not None:
        assessment = course.final if attempt["kind"] == "final" else \
            (course.lesson(attempt["lesson_id"]).quiz_assessment if course.lesson(attempt["lesson_id"]) else None)
    if assessment is not None and (assessment.id != attempt["assessment_id"] or not assessment.approved
                                   or not assessment.answer_keys):
        assessment = None   # 승인되지 않았거나, 다른 평가로 바뀌었거나, 정답 키가 없으면 해설을 보여주지 않는다
        # (평가 버전이 달라도 '당시 버전' 안내를 위해 평가는 넘긴다. 해설은 문항 버전이 같을 때만 템플릿이 보여준다)
    enrollment = storage.get_enrollment(g.user["id"], attempt["course_id"])
    from econova import ai_web
    reveal = learning.answers_revealable(g.user["id"], attempt, assessment)
    return render_econova("econova/assessment/result.html", attempt=attempt, course=course, assessment=assessment,
                          enrollment=enrollment, reveal=reveal,
                          **ai_web.result_extras(attempt, course, assessment if reveal else None))


@bp.route("/courses/<course_id>/assessments")
@login_required
def assessment_history(course_id):
    course = _course_or_404(course_id)
    if storage.get_enrollment(g.user["id"], course.id) is None:
        return redirect(url_for("econova.course_detail", course_id=course.id))
    return render_econova("econova/assessment/history.html", course=course,
                          attempts=storage.list_assessment_attempts(g.user["id"], course_id=course.id))


@bp.route("/courses/<course_id>/completion")
@login_required
def completion(course_id):
    course = _course_or_404(course_id)
    summary = learning.completion_summary(g.user["id"], course)
    if summary["enrollment"] is None:
        return redirect(url_for("econova.course_detail", course_id=course.id))
    return render_econova("econova/assessment/completion.html", course=course, **summary)


# ---------------------------------------------------------------- 경제 시뮬레이션 실험실
# 계산은 econova/simulations.py(서버)와 static/js/econova-sim.js(화면)가 같은 공식으로 한다.
# 실험실은 로그인만 하면 쓸 수 있다(강좌 수강 불필요). 레슨 안에 들어간 시뮬레이션은 레슨 접근 규칙을 그대로 따른다.
def _sim_or_404(sim_id):
    if sim_id not in simulations.SIMULATIONS:
        abort(404)
    return sim_id


def sim_context(sim_id, raw=None, lesson=None, course=None):
    """시뮬레이션 위젯에 넘길 값: 기본 입력, 서버 계산 결과, 첫 화면 그래프 명세."""
    inputs, results = simulations.run(sim_id, raw or simulations.DEFAULTS[sim_id])
    return {"sim_id": sim_id, "sim": simulations.SIMULATIONS[sim_id], "limits": simulations.LIMITS,
            "defaults": simulations.DEFAULTS[sim_id], "inputs": inputs, "results": results,
            "spec": simulations.graph_spec(sim_id, inputs, results), "lesson": lesson, "course": course,
            "rows": simulations.result_rows(sim_id, results),
            "calc_version": simulations.CALC_VERSION}


def _render_lab(template, **context):
    # 실험실은 강좌 JSON 에 의존하지 않는다 (콘텐츠 오류와 분리)
    return render_template(template, graph_geometry=graphs.geometry, **context)


@bp.route("/lab")
@login_required
def lab_home():
    return _render_lab("econova/lab/index.html", sims=simulations.SIMULATIONS,
                       runs=storage.list_simulation_runs(g.user["id"])[:5])


@bp.route("/lab/<sim_id>")
@login_required
def lab_sim(sim_id):
    return _render_lab("econova/lab/sim.html", **sim_context(_sim_or_404(sim_id)))


@bp.route("/lab/<sim_id>/save", methods=["POST"])
@login_required
def lab_save(sim_id):
    """저장: 입력만 받아 서버가 다시 계산한다. 화면이 보낸 결과 값은 무시한다."""
    _sim_or_404(sim_id)
    raw = {k: request.form.get(k, "") for k in simulations.SIMULATIONS[sim_id]["inputs"]}
    try:
        inputs, results = simulations.run(sim_id, raw)
    except simulations.SimError as exc:
        flash(f"저장하지 못했어요. {exc.message}", "error")
        return redirect(url_for("econova.lab_sim", sim_id=sim_id)), 303
    lesson_id, course_id = request.form.get("lesson_id") or None, request.form.get("course_id") or None
    if lesson_id or course_id:
        # 레슨 안에서 저장할 때는 그 레슨을 볼 수 있어야 하고, 레슨에 이 시뮬레이션이 있어야 한다
        try:
            _course, lesson_, _enrollment = learning.lesson_access(g.user["id"], course_id or "", lesson_id or "")
        except learning.LearningError:
            abort(403)
        if sim_id not in lesson_.simulations:
            abort(403)
    try:
        quotas.check("SIMULATION_RUNS", len(storage.list_simulation_runs(g.user["id"])))
    except quotas.QuotaExceeded as exc:
        flash(exc.message, "error")
        return redirect(url_for("econova.lab_sim", sim_id=sim_id)), 303
    run_id = storage.save_simulation_run(g.user["id"], sim_id, lesson_id, inputs, results, simulations.CALC_VERSION)
    flash("시뮬레이션 결과를 저장했어요. 결과는 서버가 다시 계산한 값이에요.", "success")
    return redirect(url_for("econova.lab_run", run_id=run_id))


@bp.route("/lab/saved")
@login_required
def lab_saved():
    return _render_lab("econova/lab/saved.html", runs=storage.list_simulation_runs(g.user["id"]),
                       sims=simulations.SIMULATIONS)


@bp.route("/lab/saved/<run_id>")
@login_required
def lab_run(run_id):
    run = storage.get_simulation_run(g.user["id"], run_id)
    if run is None:   # 없거나 다른 학생의 기록
        abort(404)
    ctx = sim_context(run["simulation_id"], run["inputs"])
    return _render_lab("econova/lab/run.html", run=run, **{k: v for k, v in ctx.items() if k not in ("results", "rows")},
                       results=run["results"], rows=simulations.result_rows(run["simulation_id"], run["results"]), notes=simulations.interpret(simulations.DEFAULTS["supply-demand"]
                                                                            if run["simulation_id"] == "supply-demand"
                                                                            else {k: simulations.DEFAULTS["carbon-tax"][k] for k in "abcd"},
                                                                            run["inputs"]))


# AI 화면·API 는 같은 Blueprint 에 붙는다 (앱에 등록되기 전에 import 해야 한다)
from econova import ai_web  # noqa: E402,F401
from econova import admin_web  # noqa: E402,F401
from econova import student_web  # noqa: E402,F401
