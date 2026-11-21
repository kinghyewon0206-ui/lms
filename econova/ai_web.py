"""ECONOVA AI 화면·API (Phase 6). econova.web 의 같은 Blueprint 에 붙는다 (엔드포인트 이름 econova.*).

- POST /api/tutor                         레슨 AI 튜터 (JSON 응답)
- POST /assessments/attempts/<id>/explain 오답 AI 설명 (폼 → 결과 화면)
- /discuss, /discuss/<course>, /discuss/<course>/<topic>  경제 토론
- POST /api/recommendations/explain       추천 결과의 AI 설명 (JSON 응답)

모든 요청은 로그인한 본인(g.user) 기준이며, 강좌·레슨 접근 규칙(learning)을 그대로 따른다. 공개되지 않은 강좌의
레슨·토론에는 AI 기능도 열리지 않는다. AI 는 점수·진도·수료·수강 정보를 바꾸지 않는다. CSRF 는 앱 전체 규칙
(폼 csrf_token 또는 X-CSRF-Token 헤더)으로 검사한다.
"""
from flask import abort, flash, g, jsonify, redirect, request, url_for

from econova import content, debates, learning, quotas, recommendations, storage
from econova.ai import client as ai_client, debate as ai_debate, feedback as ai_feedback
from econova.ai import recommendations as ai_recs, tutor as ai_tutor
from econova.ai.client import AIError
from econova.auth import login_required
from econova.web import bp, render_econova

STATUS = {"disabled": 503, "feedback_off": 503, "rate_limited": 429, "global_limit": 429, "duplicate": 429, "busy": 429, "empty": 400,
          "too_long": 400, "timeout": 504, "provider_error": 502, "invalid_response": 502, "unavailable": 409}


def ai_enabled():
    try:
        return ai_client.settings().enabled
    except Exception:
        return False


def _ai_error_json(exc):
    return jsonify({"ok": False, "code": exc.code, "error": exc.message}), STATUS.get(exc.code, 500)


def _level(enrollment):
    level = request.form.get("level", "")
    return level if level in content.DIFFICULTIES else enrollment["selected_difficulty"]


# ---------------------------------------------------------------- 튜터
@bp.route("/api/tutor", methods=["POST"])
@login_required
def tutor_api():
    """폼 필드: course_id, lesson_id, message, (conversation_id), (level). 그 밖의 필드(system·assistant 메시지,
    자료, 출처)는 받아도 쓰지 않는다."""
    try:
        course, lesson, enrollment = learning.lesson_access(g.user["id"], request.form.get("course_id", ""),
                                                            request.form.get("lesson_id", ""))
    except learning.LearningError as exc:
        status = {"not_found": 404, "not_published": 403, "not_enrolled": 403}.get(exc.code, 403)
        return jsonify({"ok": False, "code": exc.code, "error": exc.message}), status
    try:
        out = ai_tutor.ask(g.user["id"], course, lesson, _level(enrollment), request.form.get("message", ""),
                           learning.catalog().sources, conv_id=request.form.get("conversation_id") or None)
    except LookupError:
        return jsonify({"ok": False, "code": "not_found", "error": "We couldn't find that conversation."}), 404
    except quotas.QuotaExceeded as exc:
        return jsonify({"ok": False, "code": "quota", "error": exc.message}), 409
    except AIError as exc:
        return _ai_error_json(exc)
    return jsonify({"ok": True, **out})


# ---------------------------------------------------------------- 오답 설명
@bp.route("/assessments/attempts/<attempt_id>/explain", methods=["POST"])
@login_required
def explain_attempt(attempt_id):
    attempt = storage.get_assessment_attempt(g.user["id"], attempt_id)
    if attempt is None:   # 없거나 다른 학생의 기록
        abort(404)
    course = learning.catalog().course(attempt["course_id"])
    assessment = _attempt_assessment(course, attempt)
    enrollment = storage.get_enrollment(g.user["id"], attempt["course_id"])
    level = enrollment["selected_difficulty"] if enrollment else "beginner"
    if not learning.answers_revealable(g.user["id"], attempt, assessment):   # 재응시가 남은 최종 평가: 정답을 보내지 않는다
        flash("You can see explanations of wrong answers on the final assessment after you pass it or use all of your attempts.", "error")
        return redirect(url_for("econova.assessment_result", attempt_id=attempt["id"]), 303)
    try:
        ai_feedback.explain(g.user["id"], attempt, assessment, course, level)
        flash("AI explanation of your wrong answers is ready. Your score and progress do not change.", "success")
    except quotas.QuotaExceeded as exc:
        flash(exc.message, "error")
    except AIError as exc:
        flash(exc.message, "error")
    return redirect(url_for("econova.assessment_result", attempt_id=attempt["id"]) + "#ai-feedback", 303)


def _attempt_assessment(course, attempt):
    if course is None:
        return None
    if attempt["kind"] == "final":
        return course.final
    lesson = course.lesson(attempt.get("lesson_id") or "")
    return lesson.quiz_assessment if lesson else None


def result_extras(attempt, course, assessment):
    """결과 화면에 붙일 결정적 복습 안내와 저장된 AI 설명 (web.assessment_result 가 부른다)."""
    if not ai_feedback.eligible(attempt, assessment):
        return {"review": [], "ai_feedback": None, "ai_enabled": _feedback_enabled(), "feedback_allowed": False}
    review, seen = [], set()
    for q in ai_feedback.wrong_questions(attempt, assessment, course):   # 같은 학습목표는 한 번만
        if (q["lesson_id"], q["objective_text"]) not in seen:
            seen.add((q["lesson_id"], q["objective_text"]))
            review.append(q)
    return {"review": review,
            "ai_feedback": ai_feedback.latest(g.user["id"], attempt["id"]), "ai_enabled": _feedback_enabled(),
            "feedback_allowed": True}


def _feedback_enabled():
    try:
        return ai_client.feedback_enabled()
    except Exception:
        return False


# ---------------------------------------------------------------- 토론
def _debate_course(course_id):
    """토론은 공개된 강좌를 수강 중인 학생에게만. (공개 전 강좌는 학생 주소로 열리지 않는다)"""
    course = learning.visible_course(course_id)
    if course is None:
        abort(404)
    if not course.published:
        abort(403)
    if storage.get_enrollment(g.user["id"], course.id) is None:
        flash("Please enroll in the course first.", "error")
        return None
    return course


@bp.route("/discuss")
@login_required
def discuss_home():
    cat = learning.catalog()
    rows = []
    for e in storage.list_enrollments(g.user["id"]):
        course = cat.course(e["course_id"])
        if course is not None and course.published:
            rows.append({"course": course, "topics": debates.topics_for(course, cat.sources)})
    return render_econova("econova/discuss/index.html", rows=rows, ai_enabled=ai_enabled())


@bp.route("/discuss/<course_id>")
@login_required
def discuss_course(course_id):
    course = _debate_course(course_id)
    if course is None:
        return redirect(url_for("econova.course_detail", course_id=course_id), 303)
    return render_econova("econova/discuss/course.html", course=course,
                          topics=debates.topics_for(course, learning.catalog().sources), ai_enabled=ai_enabled())


def _topic_or_404(course, topic_id):
    topic = debates.topic(course, learning.catalog().sources, topic_id)
    if topic is None:   # 없는 주제
        abort(404)
    return topic


@bp.route("/discuss/<course_id>/<topic_id>")
@login_required
def discuss_topic(course_id, topic_id):
    course = _debate_course(course_id)
    if course is None:
        return redirect(url_for("econova.course_detail", course_id=course_id), 303)
    topic = _topic_or_404(course, topic_id)
    conv = ai_debate.conversation(g.user["id"], course, topic)
    messages = storage.list_ai_messages(g.user["id"], conv["id"]) if conv else []
    return render_econova("econova/discuss/topic.html", course=course, topic=topic, conv=conv, messages=messages,
                          turns=ai_debate.student_turns(messages), ai_enabled=ai_enabled(),
                          perspective_names={p["id"]: p["name"] for p in topic["perspectives"]},
                          sources=[learning.catalog().sources[sid] for sid in topic["source_ids"] if sid in learning.catalog().sources],
                          max_chars=_max_chars())


def _max_chars():
    try:
        return ai_client.settings().max_input_chars
    except Exception:
        return 600


@bp.route("/discuss/<course_id>/<topic_id>/respond", methods=["POST"])
@login_required
def discuss_respond(course_id, topic_id):
    course = _debate_course(course_id)
    if course is None:
        return redirect(url_for("econova.course_detail", course_id=course_id), 303)
    topic = _topic_or_404(course, topic_id)
    page = url_for("econova.discuss_topic", course_id=course.id, topic_id=topic["id"])
    try:
        conv = ai_debate.conversation(g.user["id"], course, topic, request.form.get("conversation_id") or None, create=True)
        meta = ai_debate.respond(g.user["id"], course, topic, conv, request.form.get("message", ""))
        if meta.get("ai_error"):
            flash(f"Your response was saved. {meta['ai_error']} We'll continue with a prepared guiding question instead.", "error")
    except LookupError:
        abort(404)
    except quotas.QuotaExceeded as exc:
        flash(exc.message, "error")
    except AIError as exc:
        flash(exc.message if exc.code != "unavailable" else "This debate has already been summarized. Please start a new debate.", "error")
    return redirect(page + "#latest", 303)


@bp.route("/discuss/<course_id>/<topic_id>/summary", methods=["POST"])
@login_required
def discuss_summary(course_id, topic_id):
    course = _debate_course(course_id)
    if course is None:
        return redirect(url_for("econova.course_detail", course_id=course_id), 303)
    topic = _topic_or_404(course, topic_id)
    conv = ai_debate.conversation(g.user["id"], course, topic)
    if conv is None or conv["stage"] != "open":
        abort(409)
    try:
        summary = ai_debate.summarize(g.user["id"], course, topic, conv)
        if summary.get("ai_error"):
            flash(f"{summary['ai_error']} Showing an automatic summary instead.", "error")
    except AIError as exc:
        flash(exc.message, "error")
    return redirect(url_for("econova.discuss_topic", course_id=course.id, topic_id=topic["id"]) + "#summary", 303)


@bp.route("/discuss/<course_id>/<topic_id>/new", methods=["POST"])
@login_required
def discuss_new(course_id, topic_id):
    course = _debate_course(course_id)
    if course is None:
        return redirect(url_for("econova.course_detail", course_id=course_id), 303)
    topic = _topic_or_404(course, topic_id)
    try:
        ai_debate.new_conversation(g.user["id"], course, topic)
    except quotas.QuotaExceeded as exc:
        flash(exc.message, "error")
    return redirect(url_for("econova.discuss_topic", course_id=course.id, topic_id=topic["id"]), 303)


# ---------------------------------------------------------------- 추천
def dashboard_recommendations(user_id):
    """대시보드용 결정적 추천 (AI 꺼져 있어도 동작)."""
    return recommendations.analyze(user_id, learning.catalog())


@bp.route("/api/recommendations/explain", methods=["POST"])
@login_required
def recommendations_explain():
    analysis = dashboard_recommendations(g.user["id"])
    if not analysis["items"]:
        return jsonify({"ok": False, "code": "unavailable", "error": "There are no recommendations to explain yet."}), 409
    try:
        return jsonify({"ok": True, **ai_recs.explain(g.user["id"], analysis)})
    except AIError as exc:
        return _ai_error_json(exc)
