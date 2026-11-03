"""ECONOVA 화면: 강좌 카탈로그, 강좌 상세, 수강 신청, 난이도, 레슨.

규칙은 econova/learning.py 에 있고, 여기서는 요청을 받아 그 결과를 화면에 넘긴다.
사용자는 항상 로그인한 본인(g.user)이다. 다른 학생의 id 를 받는 주소는 없다.
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from econova import content, learning, storage
from econova.auth import login_required

bp = Blueprint("econova", __name__)


@bp.app_context_processor
def _template_helpers():
    return {"difficulty_names": content.DIFFICULTY_NAMES, "sdg_info": learning.catalog().sdgs}


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
    return render_template(
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
    return render_template("econova/course_detail.html", course=course, **state)


@bp.route("/courses/<course_id>/enroll", methods=["POST"])
@login_required
def enroll(course_id):
    course = _course_or_404(course_id)
    try:
        created = learning.enroll(g.user["id"], course, request.form.get("difficulty", learning.DEFAULT_DIFFICULTY))
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
    return render_template(
        "econova/lesson.html", course=course, lesson=lesson_, enrollment=enrollment, record=record,
        status=state["progress"]["statuses"][lesson_.id], progress=state["progress"], sections=learning.LESSON_SECTIONS,
        prev_lesson=course.lessons[index - 1] if index > 0 else None,
        next_lesson=course.lessons[index + 1] if index + 1 < len(course.lessons) else None,
    )


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
