"""Glass design prototypes (owner review only).

Served under /prototype/glass/ ONLY when ECONOVA_DESIGN_PROTOTYPES=1 and not in production (config refuses it there).
The lesson prototype renders real draft lesson material, so these pages must never be reachable on a public deployment.
The dashboard uses clearly labeled sample data; nothing here reads or writes user records.
"""
from flask import Blueprint, abort, render_template, request

from econova import config, content, graphs

bp = Blueprint("glass_proto", __name__, url_prefix="/prototype/glass")

COURSE_ACCENTS = {
    "c01": "#2F5BFF", "c02": "#0A9DA0", "c03": "#1FA968", "c04": "#E39B21", "c05": "#E0517A",
    "c06": "#7C5CF0", "c07": "#0B8FD6", "c08": "#E86F2E", "c09": "#C04BD9",
}
LEVELS = ("beginner", "intermediate", "advanced")


@bp.before_request
def _only_when_enabled():
    if not config.design_prototypes_enabled():
        abort(404)


def _courses():
    cat = content.get_catalog()
    out = []
    for c in cat.courses:
        if c.fixture:
            continue
        out.append({"id": c.id, "number": c.id[1:], "title": c.title, "description": c.description,
                    "lessons": len(c.lessons), "hours": c.estimated_hours, "accent": COURSE_ACCENTS.get(c.id, "#2F5BFF"),
                    "sdgs": [{"n": n, "name": cat.sdgs.get(n, ("", ""))[0], "color": cat.sdgs.get(n, ("", "#888"))[1]}
                             for n in c.sdgs]})
    return out


def _render(template, **ctx):
    return render_template(f"prototype/glass/{template}", courses=_courses(), accents=COURSE_ACCENTS,
                           graph_geometry=graphs.geometry, **ctx)


@bp.route("/")
def landing():
    return _render("landing.html", page="landing")


# Sample data for the dashboard prototype (shown with a "Sample data" label; not any real student's record).
SAMPLE_DIAGNOSTIC = (("scarcity", "Choices", 1.0), ("supply_demand", "Markets", .5), ("market_failure", "Market failure", .5),
                     ("macroeconomy", "Whole economy", 0.0), ("income_money", "Income & saving", 1.0), ("policy", "SDG policy", .5))


def _radar(values):
    from econova import ui_charts
    return ui_charts.radar([(label, v) for _, label, v in values])


@bp.route("/dashboard")
def dashboard():
    week = [("Mon", 25), ("Tue", 40), ("Wed", 0), ("Thu", 55), ("Fri", 30), ("Sat", 70), ("Sun", 15)]
    return _render("dashboard.html", page="dashboard", radar=_radar(SAMPLE_DIAGNOSTIC), week=week,
                   week_max=max(m for _, m in week))


@bp.route("/components")
def components():
    return _render("components.html", page="components")


@bp.route("/lesson")
@bp.route("/lesson/<course_id>/<lesson_id>")
def lesson(course_id="c02", lesson_id="c02-l1"):
    cat = content.get_catalog()
    course = cat.course(course_id)
    if course is None or course.fixture:
        abort(404)
    item = next((ls for ls in course.lessons if ls.id == lesson_id), None)
    if item is None or item.content is None:
        abort(404)
    level = request.args.get("level", "intermediate")
    if level not in LEVELS:
        level = "intermediate"
    mat = item.content
    concepts = {c["id"]: c for c in mat.concepts}
    sources = [cat.sources[sid] for sid in mat.source_ids if sid in cat.sources]
    sdgs = [{"n": n, "name": cat.sdgs.get(n, ("", ""))[0], "color": cat.sdgs.get(n, ("", "#888"))[1]}
            for n in mat.sdg_case.get("sdgs", ())]
    return _render("lesson.html", page="lesson", course=course, item=item, mat=mat, level=level, levels=LEVELS,
                   body=mat.levels[level], concepts=concepts, examples=mat.examples_for(level), sources=sources,
                   sdgs=sdgs, accent=COURSE_ACCENTS.get(course.id, "#2F5BFF"),
                   lesson_index=[ls.id for ls in course.lessons].index(item.id) + 1)
