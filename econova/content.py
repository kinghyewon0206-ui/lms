"""ECONOVA 커리큘럼(강좌·레슨) 로더.

정본은 Git 으로 관리하는 JSON 이다.
- content/catalog.json          : 실제 강좌 목록(순서)
- content/courses/<id>.json     : 강좌 하나와 그 레슨들
- content/dev_fixtures/         : 개발·자동 테스트 전용 가짜 강좌. ECONOVA_DEV_FIXTURES=1 일 때만 읽는다.
- content/sdgs.json             : SDG 번호·이름·색

읽을 때 형식을 검사하고, 잘못된 곳은 파일 이름과 함께 ContentError 로 알린다.
공개(published) 여부는 강좌 정보가 있는지와 별개다. 레슨의 필수 자료와 퀴즈가 모두 승인된 강좌만 published 가 될 수 있다.
"""
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache

from econova import config
from econova import assessments, lesson_content, private_content
from econova.lesson_content import ContentError  # noqa: F401  (예전처럼 content.ContentError 로도 쓴다)

CONTENT_DIR = os.path.join(config.BASE_DIR, "content")

COURSE_STATUSES = ("draft", "coming_soon", "published", "archived")
VISIBLE_STATUSES = ("coming_soon", "published")   # 카탈로그에 보이는 상태
LESSON_STATUSES = ("draft", "published")
RESOURCE_STATUSES = ("missing",) + lesson_content.REVIEW_STATUSES   # missing → draft → in_review → approved → published
READY_STATUSES = lesson_content.APPROVED_STATUSES                        # 학생에게 쓸 수 있는 자료·퀴즈 상태
ACTIVITIES = ("material", "quiz")                  # 레슨 완료 조건으로 쓸 수 있는 활동
DIFFICULTIES = ("beginner", "intermediate", "advanced")
DIFFICULTY_NAMES = {"beginner": "Beginner", "intermediate": "Intermediate", "advanced": "Advanced"}
STUDENT_SELECTED = "student_selected"              # SDG 를 학생이 고르는 강좌 (c09)

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Lesson:
    id: str
    course_id: str
    order: int
    title: str
    title_ko: str
    status: str
    objectives: tuple
    requirements: tuple
    material: dict
    quiz: dict
    content: object = None     # lesson_content.LessonMaterial (학습자료 파일이 있을 때)
    quiz_assessment: object = None   # assessments.Assessment (형성 퀴즈 파일이 있을 때)
    simulations: tuple = ()          # 이 레슨에 넣을 시뮬레이션 id (econova.simulations.SIMULATIONS)

    @property
    def material_approved(self):
        return self.material.get("status") in READY_STATUSES and self.content is not None

    @property
    def quiz_approved(self):
        return (self.quiz.get("status") in READY_STATUSES and self.quiz_assessment is not None
                and self.quiz_assessment.approved)

    def activity_available(self, activity):
        return {"material": self.material_approved, "quiz": self.quiz_approved}[activity]


@dataclass(frozen=True)
class Course:
    id: str
    slug: str
    title: str
    title_ko: str
    description: str
    objectives: tuple
    sdgs: tuple                # SDG 번호들. 학생이 고르는 강좌는 빈 튜플
    sdg_student_selected: bool
    review_status: str
    estimated_hours: int
    difficulty_levels: tuple
    status: str
    content_version: int
    final_assessment_status: str
    lessons: tuple
    fixture: bool = False
    final: object = None       # assessments.Assessment (최종 평가 파일이 있을 때)
    capstone: object = None    # capstone.Capstone (SDG 캡스톤 강좌, Phase 7)

    @property
    def capstone_ready(self):
        """학생이 쓸 수 있는 캡스톤이 있는가 (승인된 정의만)."""
        return self.capstone is not None and self.capstone.approved

    @property
    def final_ready(self):
        """학생이 볼 수 있는 최종 평가가 있는가 (승인·공개된 평가만)."""
        return self.final is not None and self.final.approved

    @property
    def published(self):
        return self.status == "published"

    @property
    def lesson_ids(self):
        return tuple(lesson.id for lesson in self.lessons)

    def lesson(self, lesson_id):
        return next((lesson for lesson in self.lessons if lesson.id == lesson_id), None)


@dataclass(frozen=True)
class Catalog:
    courses: tuple
    sdgs: dict                 # {번호: (이름, 색)}
    sources: dict = None       # {출처 id: lesson_content.Source}

    def course(self, course_id):
        return next((c for c in self.courses if c.id == course_id), None)

    def visible(self):
        """카탈로그에 보여줄 강좌 (draft·archived 제외), 정해진 순서대로."""
        return [c for c in self.courses if c.status in VISIBLE_STATUSES]

    def published(self):
        return [c for c in self.courses if c.published]


# ------------------------------------------------------------------ 검사 도우미
def _need(data, key, kind, where):
    if key not in data:
        raise ContentError(f"{where}: '{key}' is missing.")
    value = data[key]
    if kind is int and isinstance(value, bool) or not isinstance(value, kind):
        raise ContentError(f"{where}: '{key}' has the wrong type.")
    return value


def _text(data, key, where):
    value = _need(data, key, str, where).strip()
    if not value:
        raise ContentError(f"{where}: '{key}' is empty.")
    return value


def _texts(data, key, where, allow_empty=False):
    values = _need(data, key, list, where)
    if not allow_empty and not values or not all(isinstance(v, str) and v.strip() for v in values):
        raise ContentError(f"{where}: '{key}' must be a list of non-empty strings.")
    return tuple(v.strip() for v in values)


def _choice(value, allowed, where, key):
    if value not in allowed:
        raise ContentError(f"{where}: '{key}' value {value!r} must be one of {', '.join(allowed)}.")
    return value


def _resource(data, key, where):
    res = _need(data, key, dict, where)
    _choice(res.get("status"), RESOURCE_STATUSES, where, f"{key}.status")
    return dict(res)


# ------------------------------------------------------------------ 파싱
def _parse_lesson(data, course_id, where, fixture, sources, base_dir):
    where = f"{where} lesson {data.get('id', '?')}"
    lesson_id = _text(data, "id", where)
    if not _ID_RE.match(lesson_id) or not lesson_id.startswith(f"{course_id}-"):
        raise ContentError(f"{where}: lesson id must start with '{course_id}-' and use only lowercase letters, digits, and hyphens.")
    requirements = _texts(data, "requirements", where)
    for r in requirements:
        _choice(r, ACTIVITIES, where, "requirements")
    if "material" not in requirements or len(set(requirements)) != len(requirements):
        raise ContentError(f"{where}: requirements must include material and contain no duplicates.")
    material, quiz = _resource(data, "material", where), _resource(data, "quiz", where)
    if quiz["status"] in READY_STATUSES and not str(quiz.get("assessment_id") or "").strip():
        raise ContentError(f"{where}: an approved quiz must have an assessment_id.")
    doc = None
    if material["status"] != "missing":
        # 학습자료는 별도 파일에 있다. 강좌 JSON 의 상태는 파일의 검토 상태와 같아야 한다 (한쪽만 바꿔 공개하는 것을 막음)
        rel = str(material.get("file") or "").strip()
        if not rel or os.path.isabs(rel) or ".." in rel.split("/"):
            raise ContentError(f"{where}: when learning materials exist, material.file must be a relative path.")
        doc = lesson_content.parse_material(
            lesson_content.read_json(os.path.join(base_dir, rel), os.path.relpath(os.path.join(base_dir, rel), CONTENT_DIR)),
            lesson_id, sources, fixture=fixture, where=os.path.relpath(os.path.join(base_dir, rel), CONTENT_DIR))
        if doc.review_status != material["status"]:
            raise ContentError(f"{where}: material.status ({material['status']}) does not match the review status of the learning materials file "
                               f"({doc.review_status}).")
    objectives = _texts(data, "objectives", where, allow_empty=True) or (doc.objectives if doc else ())
    from econova.simulations import SIMULATIONS   # 지연 import (simulations → grading 만 쓰므로 순환 없음)
    sims = tuple(data.get("simulations") or ())
    if len(set(sims)) != len(sims) or any(s not in SIMULATIONS for s in sims):
        raise ContentError(f"{where}: simulations may only contain unique ids from {', '.join(SIMULATIONS)}.")
    quiz_doc = None
    if quiz["status"] != "missing":
        # 형성 퀴즈도 별도 파일(assessments/<id>.json). 상태는 파일의 검토 상태와 같아야 한다
        quiz_doc = _load_assessment(quiz.get("assessment_id"), course_id,
                                    {lesson_id: (objectives, tuple(c["id"] for c in doc.concepts) if doc else ())},
                                    fixture, base_dir, where)
        if quiz_doc.kind != "lesson_quiz" or quiz_doc.lesson_id != lesson_id:
            raise ContentError(f"{where}: quiz.assessment_id is not this lesson's lesson quiz.")
        if quiz_doc.review_status != quiz["status"]:
            raise ContentError(f"{where}: quiz.status ({quiz['status']}) does not match the quiz file's review status ({quiz_doc.review_status}).")
    return Lesson(
        id=lesson_id, course_id=course_id, order=_need(data, "order", int, where),
        title=_text(data, "title", where), title_ko=_text(data, "title_ko", where),
        status=_choice(data.get("status"), LESSON_STATUSES, where, "status"),
        objectives=objectives,
        requirements=requirements, material=material, quiz=quiz, content=doc, quiz_assessment=quiz_doc, simulations=sims,
    )


def _load_assessment(assessment_id, course_id, lessons, fixture, base_dir, where):
    aid = str(assessment_id or "").strip()
    if not _ID_RE.match(aid):
        raise ContentError(f"{where}: when an assessment exists, assessment_id must use only lowercase letters, digits, and hyphens.")
    path = os.path.join(base_dir, "assessments", f"{aid}.json")
    rel = os.path.relpath(path, CONTENT_DIR)
    public = lesson_content.read_json(path, rel)
    leaked = private_content.public_violations(public)
    if leaked:   # 공개 저장소의 파일에 정답 정보가 들어 있으면 안 된다
        raise ContentError(f"{rel}: the public assessment file contains answer information ({', '.join(leaked[:5])}). "
                           "Move it to the private answer key file.")
    try:
        merged = private_content.merge(public, private_content.read_keys(aid, fixture), rel)
    except private_content.KeysUnavailable as exc:
        return assessments.parse_assessment(public, aid, course_id, lessons, fixture=fixture, where=rel,
                                            keys_problem=str(exc))
    try:
        return assessments.parse_assessment(merged, aid, course_id, lessons, fixture=fixture, where=rel)
    except ContentError as exc:
        # 공개 정의는 맞는데 정답 키 쪽이 틀렸다면(정답이 선택지에 없음, 계산 검증 실패 등) 그 평가만 닫는다
        doc = assessments.parse_assessment(public, aid, course_id, lessons, fixture=fixture, where=rel,
                                           keys_problem=f"Answer key check failed: {exc}")
        return doc


FINAL_STATUSES = ("upcoming",) + lesson_content.REVIEW_STATUSES


def parse_course(data, where="course", fixture=False, sources=None, base_dir=None):
    """강좌 JSON(dict) 하나를 검사해서 Course 로 만든다. 학습자료 파일은 base_dir 기준으로 읽는다."""
    if sources is None:
        sources = read_sources()
    if base_dir is None:
        base_dir = os.path.join(CONTENT_DIR, "dev_fixtures") if fixture else CONTENT_DIR
    if not isinstance(data, dict):
        raise ContentError(f"{where}: a course must be a JSON object.")
    if data.get("schema_version") != 1:
        raise ContentError(f"{where}: unsupported schema_version.")
    if bool(data.get("fixture")) != fixture:
        raise ContentError(f"{where}: dev test courses must live only in content/dev_fixtures, with 'fixture': true.")
    course_id = _text(data, "id", where)
    if not _ID_RE.match(course_id):
        raise ContentError(f"{where}: course id {course_id!r} may only use lowercase letters, digits, and hyphens.")
    where = f"{where} ({course_id})"
    slug = _text(data, "slug", where)
    if not _ID_RE.match(slug):
        raise ContentError(f"{where}: invalid slug format.")

    sdgs = data.get("sdgs")
    if sdgs == STUDENT_SELECTED:
        sdg_numbers, selected = (), True
    elif isinstance(sdgs, list) and sdgs and all(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 17 for n in sdgs):
        if len(set(sdgs)) != len(sdgs):
            raise ContentError(f"{where}: sdgs contains duplicates.")
        sdg_numbers, selected = tuple(sdgs), False
    else:
        raise ContentError(f"{where}: sdgs must be a list of numbers 1-17 or '{STUDENT_SELECTED}'.")

    levels = _texts(data, "difficulty_levels", where)
    if tuple(levels) != DIFFICULTIES:
        raise ContentError(f"{where}: difficulty_levels must be {list(DIFFICULTIES)}.")
    version = _need(data, "content_version", int, where)
    hours = _need(data, "estimated_hours", int, where)
    if version < 1 or hours < 1:
        raise ContentError(f"{where}: content_version and estimated_hours must be 1 or greater.")
    review = _need(data, "review", dict, where)
    final = _need(data, "final_assessment", dict, where)

    lesson_ids = _texts(data, "lesson_ids", where)
    if len(set(lesson_ids)) != len(lesson_ids):
        raise ContentError(f"{where}: lesson_ids contains duplicates.")
    lessons = tuple(_parse_lesson(item, course_id, where, fixture, sources, base_dir)
                    for item in _need(data, "lessons", list, where))
    if [lesson.id for lesson in lessons] != list(lesson_ids):
        raise ContentError(f"{where}: the order or ids of lessons do not match lesson_ids.")
    if [lesson.order for lesson in lessons] != list(range(1, len(lessons) + 1)):
        raise ContentError(f"{where}: lesson order must run consecutively from 1 with no gaps.")

    final_status = _choice(final.get("status", "upcoming"), FINAL_STATUSES, where, "final_assessment.status")
    final_doc = None
    if final_status != "upcoming":
        final_doc = _load_assessment(
            final.get("assessment_id"), course_id,
            {lesson.id: (lesson.objectives, tuple(c["id"] for c in lesson.content.concepts) if lesson.content else ())
             for lesson in lessons}, fixture, base_dir, where)
        if not final_doc.is_final:
            raise ContentError(f"{where}: final_assessment.assessment_id is not a final assessment.")
        if final_doc.review_status != final_status:
            raise ContentError(f"{where}: final_assessment.status ({final_status}) does not match the final assessment file's review status "
                               f"({final_doc.review_status}).")

    capstone_doc = None
    cap = data.get("capstone")
    if cap is not None:
        # SDG 캡스톤 정의 (content/capstone/<id>.json). 상태는 정의 파일의 검토 상태와 같아야 한다.
        from econova import capstone as capstone_mod
        rel = str((cap or {}).get("file") or "").strip()
        if not isinstance(cap, dict) or not rel or os.path.isabs(rel) or ".." in rel.split("/"):
            raise ContentError(f"{where}: capstone must be {{status, file (relative path)}}.")
        path = os.path.join(base_dir, rel)
        capstone_doc = capstone_mod.parse_definition(
            lesson_content.read_json(path, os.path.relpath(path, CONTENT_DIR)), course_id, lesson_ids, fixture=fixture,
            where=os.path.relpath(path, CONTENT_DIR))
        if capstone_doc.review_status != cap.get("status"):
            raise ContentError(f"{where}: capstone.status ({cap.get('status')}) does not match the capstone definition file's review status "
                               f"({capstone_doc.review_status}).")

    status = _choice(data.get("status"), COURSE_STATUSES, where, "status")
    if status == "published":
        for lesson in lessons:
            missing = [a for a in lesson.requirements if not lesson.activity_available(a)]
            if lesson.status != "published" or missing:
                raise ContentError(f"{where}: lesson {lesson.id} has required materials/assessments ({', '.join(missing) or 'status'}) "
                                   "that are not approved, so the course cannot be published.")
        if final_doc is None and capstone_doc is not None:
            # 캡스톤 강좌(c09 처럼 최종 평가 없이 캡스톤으로 마치는 강좌): 캡스톤 정의와 루브릭이 승인돼야 공개할 수 있다
            if not capstone_doc.approved:
                raise ContentError(f"{where}: there is no approved capstone definition, so the course cannot be published.")
            if capstone_doc.rubric["status"] != "approved" and not fixture:
                raise ContentError(f"{where}: the capstone rubric is not approved, so the course cannot be published.")
        elif final_doc is None or not final_doc.approved:
            raise ContentError(f"{where}: there is no approved final assessment (final_assessment), so the course cannot be published.")
        elif not final_doc.passing_usable(fixture):
            raise ContentError(f"{where}: the final assessment's passing criteria are not approved, so the course cannot be published.")

    return Course(
        id=course_id, slug=slug, title=_text(data, "title", where), title_ko=_text(data, "title_ko", where),
        description=_text(data, "description", where), objectives=_texts(data, "objectives", where),
        sdgs=sdg_numbers, sdg_student_selected=selected, review_status=str(review.get("status", "")),
        estimated_hours=hours, difficulty_levels=levels, status=status, content_version=version,
        final_assessment_status=final_status, lessons=lessons, fixture=fixture, final=final_doc, capstone=capstone_doc,
    )


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ContentError(f"{os.path.relpath(path, CONTENT_DIR)}: file not found.")
    except json.JSONDecodeError as exc:
        raise ContentError(f"{os.path.relpath(path, CONTENT_DIR)}: JSON syntax error ({exc.msg}, line {exc.lineno})")


def read_sources():
    """출처 레지스트리(content/sources.json)."""
    return lesson_content.parse_sources(_read_json(os.path.join(CONTENT_DIR, "sources.json")))


def _read_catalog_file(directory, fixture, sources):
    index = _read_json(os.path.join(directory, "catalog.json"))
    if not isinstance(index, dict) or index.get("schema_version") != 1 or not isinstance(index.get("courses"), list):
        raise ContentError(f"{os.path.relpath(directory, CONTENT_DIR) or '.'}/catalog.json: invalid format.")
    courses = []
    for name in index["courses"]:
        path = os.path.join(directory, name)
        courses.append(parse_course(_read_json(path), where=os.path.relpath(path, CONTENT_DIR), fixture=fixture,
                                    sources=sources, base_dir=directory))
    return courses


def build_catalog(courses, sdgs, sources=None):
    """강좌 목록 전체를 검사한다: 강좌 id·slug·레슨 id 중복."""
    seen_courses, seen_slugs, seen_lessons = set(), set(), set()
    for c in courses:
        if c.id in seen_courses:
            raise ContentError(f"Duplicate course id {c.id!r}.")
        if c.slug in seen_slugs:
            raise ContentError(f"Duplicate course slug {c.slug!r}.")
        for lesson in c.lessons:
            if lesson.id in seen_lessons:
                raise ContentError(f"Duplicate lesson id {lesson.id!r}.")
            seen_lessons.add(lesson.id)
        seen_courses.add(c.id)
        seen_slugs.add(c.slug)
        for n in c.sdgs:
            if n not in sdgs:
                raise ContentError(f"{c.id}: SDG {n} is not defined in sdgs.json.")
        for lesson in c.lessons:
            if lesson.content:
                for n in lesson.content.sdg_case["sdgs"]:
                    if n not in sdgs:
                        raise ContentError(f"{lesson.id}: SDG {n} is not defined in sdgs.json.")
    return Catalog(courses=tuple(courses), sdgs=sdgs, sources=sources if sources is not None else read_sources())


def _read_sdgs():
    data = _read_json(os.path.join(CONTENT_DIR, "sdgs.json"))
    try:
        return {int(k): (str(v[0]), str(v[1])) for k, v in data["goals"].items()}
    except (KeyError, TypeError, ValueError, IndexError):
        raise ContentError("sdgs.json: invalid format.")


@lru_cache(maxsize=2)
def load_catalog(include_fixtures=False):
    """JSON 을 읽어 검사한 Catalog. 파일은 배포와 함께 바뀌므로 프로세스마다 한 번만 읽는다."""
    sources = read_sources()
    courses = _read_catalog_file(CONTENT_DIR, fixture=False, sources=sources)
    if include_fixtures:
        courses += _read_catalog_file(os.path.join(CONTENT_DIR, "dev_fixtures"), fixture=True, sources=sources)
    return build_catalog(courses, _read_sdgs(), sources)


def get_catalog():
    """현재 설정에 맞는 Catalog. 개발용 테스트 강좌는 ECONOVA_DEV_FIXTURES=1 (운영 아님) 일 때만 포함된다."""
    return load_catalog(include_fixtures=config.dev_fixtures_enabled())
