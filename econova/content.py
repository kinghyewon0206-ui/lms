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

CONTENT_DIR = os.path.join(config.BASE_DIR, "content")

COURSE_STATUSES = ("draft", "coming_soon", "published", "archived")
VISIBLE_STATUSES = ("coming_soon", "published")   # 카탈로그에 보이는 상태
LESSON_STATUSES = ("draft", "published")
RESOURCE_STATUSES = ("missing", "draft", "in_review", "approved")
ACTIVITIES = ("material", "quiz")                  # 레슨 완료 조건으로 쓸 수 있는 활동
DIFFICULTIES = ("beginner", "intermediate", "advanced")
DIFFICULTY_NAMES = {"beginner": "하 (Beginner)", "intermediate": "중 (Intermediate)", "advanced": "상 (Advanced)"}
STUDENT_SELECTED = "student_selected"              # SDG 를 학생이 고르는 강좌 (c09)

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ContentError(ValueError):
    """커리큘럼 JSON 이 잘못됐을 때."""


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

    @property
    def material_approved(self):
        return self.material.get("status") == "approved"

    @property
    def quiz_approved(self):
        return self.quiz.get("status") == "approved"

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
        raise ContentError(f"{where}: '{key}' 항목이 없습니다.")
    value = data[key]
    if kind is int and isinstance(value, bool) or not isinstance(value, kind):
        raise ContentError(f"{where}: '{key}' 의 형식이 잘못됐습니다.")
    return value


def _text(data, key, where):
    value = _need(data, key, str, where).strip()
    if not value:
        raise ContentError(f"{where}: '{key}' 가 비어 있습니다.")
    return value


def _texts(data, key, where, allow_empty=False):
    values = _need(data, key, list, where)
    if not allow_empty and not values or not all(isinstance(v, str) and v.strip() for v in values):
        raise ContentError(f"{where}: '{key}' 는 비어 있지 않은 문자열 목록이어야 합니다.")
    return tuple(v.strip() for v in values)


def _choice(value, allowed, where, key):
    if value not in allowed:
        raise ContentError(f"{where}: '{key}' 값 {value!r} 는 {', '.join(allowed)} 중 하나여야 합니다.")
    return value


def _resource(data, key, where):
    res = _need(data, key, dict, where)
    _choice(res.get("status"), RESOURCE_STATUSES, where, f"{key}.status")
    return dict(res)


# ------------------------------------------------------------------ 파싱
def _parse_lesson(data, course_id, where, fixture):
    where = f"{where} 레슨 {data.get('id', '?')}"
    lesson_id = _text(data, "id", where)
    if not _ID_RE.match(lesson_id) or not lesson_id.startswith(f"{course_id}-"):
        raise ContentError(f"{where}: 레슨 id 는 '{course_id}-' 로 시작하는 소문자·숫자·하이픈이어야 합니다.")
    requirements = _texts(data, "requirements", where)
    for r in requirements:
        _choice(r, ACTIVITIES, where, "requirements")
    if "material" not in requirements or len(set(requirements)) != len(requirements):
        raise ContentError(f"{where}: requirements 에는 material 이 반드시 있어야 하고 중복이 없어야 합니다.")
    material, quiz = _resource(data, "material", where), _resource(data, "quiz", where)
    if quiz["status"] == "approved" and not str(quiz.get("assessment_id") or "").strip():
        raise ContentError(f"{where}: 승인된 퀴즈에는 assessment_id 가 있어야 합니다.")
    if material["status"] == "approved" and not fixture:
        # Phase 3 에서 검증 자료(출처·하중상 본문) 형식이 정해지기 전까지 실제 강좌의 자료 승인은 막는다
        raise ContentError(f"{where}: 실제 강좌 자료의 승인 형식은 아직 정해지지 않았습니다 (Phase 3).")
    return Lesson(
        id=lesson_id, course_id=course_id, order=_need(data, "order", int, where),
        title=_text(data, "title", where), title_ko=_text(data, "title_ko", where),
        status=_choice(data.get("status"), LESSON_STATUSES, where, "status"),
        objectives=_texts(data, "objectives", where, allow_empty=True),
        requirements=requirements, material=material, quiz=quiz,
    )


def parse_course(data, where="course", fixture=False):
    """강좌 JSON(dict) 하나를 검사해서 Course 로 만든다."""
    if not isinstance(data, dict):
        raise ContentError(f"{where}: 강좌는 JSON 객체여야 합니다.")
    if data.get("schema_version") != 1:
        raise ContentError(f"{where}: 지원하지 않는 schema_version 입니다.")
    if bool(data.get("fixture")) != fixture:
        raise ContentError(f"{where}: 개발용 테스트 강좌는 content/dev_fixtures 에만, 'fixture': true 로 둬야 합니다.")
    course_id = _text(data, "id", where)
    if not _ID_RE.match(course_id):
        raise ContentError(f"{where}: 강좌 id {course_id!r} 는 소문자·숫자·하이픈만 쓸 수 있습니다.")
    where = f"{where} ({course_id})"
    slug = _text(data, "slug", where)
    if not _ID_RE.match(slug):
        raise ContentError(f"{where}: slug 형식이 잘못됐습니다.")

    sdgs = data.get("sdgs")
    if sdgs == STUDENT_SELECTED:
        sdg_numbers, selected = (), True
    elif isinstance(sdgs, list) and sdgs and all(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 17 for n in sdgs):
        if len(set(sdgs)) != len(sdgs):
            raise ContentError(f"{where}: sdgs 에 중복이 있습니다.")
        sdg_numbers, selected = tuple(sdgs), False
    else:
        raise ContentError(f"{where}: sdgs 는 1~17 번호 목록이거나 '{STUDENT_SELECTED}' 여야 합니다.")

    levels = _texts(data, "difficulty_levels", where)
    if tuple(levels) != DIFFICULTIES:
        raise ContentError(f"{where}: difficulty_levels 는 {list(DIFFICULTIES)} 여야 합니다.")
    version = _need(data, "content_version", int, where)
    hours = _need(data, "estimated_hours", int, where)
    if version < 1 or hours < 1:
        raise ContentError(f"{where}: content_version 과 estimated_hours 는 1 이상이어야 합니다.")
    review = _need(data, "review", dict, where)
    final = _need(data, "final_assessment", dict, where)

    lesson_ids = _texts(data, "lesson_ids", where)
    if len(set(lesson_ids)) != len(lesson_ids):
        raise ContentError(f"{where}: lesson_ids 에 중복이 있습니다.")
    lessons = tuple(_parse_lesson(item, course_id, where, fixture) for item in _need(data, "lessons", list, where))
    if [lesson.id for lesson in lessons] != list(lesson_ids):
        raise ContentError(f"{where}: lessons 의 순서·id 가 lesson_ids 와 다릅니다.")
    if [lesson.order for lesson in lessons] != list(range(1, len(lessons) + 1)):
        raise ContentError(f"{where}: 레슨 order 는 1 부터 빠짐없이 차례대로여야 합니다.")

    status = _choice(data.get("status"), COURSE_STATUSES, where, "status")
    if status == "published":
        for lesson in lessons:
            missing = [a for a in lesson.requirements if not lesson.activity_available(a)]
            if lesson.status != "published" or missing:
                raise ContentError(f"{where}: 레슨 {lesson.id} 의 필수 자료/평가({', '.join(missing) or 'status'})가 "
                                   "승인되지 않아 강좌를 published 로 둘 수 없습니다.")

    return Course(
        id=course_id, slug=slug, title=_text(data, "title", where), title_ko=_text(data, "title_ko", where),
        description=_text(data, "description", where), objectives=_texts(data, "objectives", where),
        sdgs=sdg_numbers, sdg_student_selected=selected, review_status=str(review.get("status", "")),
        estimated_hours=hours, difficulty_levels=levels, status=status, content_version=version,
        final_assessment_status=str(final.get("status", "upcoming")), lessons=lessons, fixture=fixture,
    )


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ContentError(f"{os.path.relpath(path, CONTENT_DIR)}: 파일이 없습니다.")
    except json.JSONDecodeError as exc:
        raise ContentError(f"{os.path.relpath(path, CONTENT_DIR)}: JSON 문법 오류 ({exc.msg}, {exc.lineno}행)")


def _read_catalog_file(directory, fixture):
    index = _read_json(os.path.join(directory, "catalog.json"))
    if not isinstance(index, dict) or index.get("schema_version") != 1 or not isinstance(index.get("courses"), list):
        raise ContentError(f"{os.path.relpath(directory, CONTENT_DIR) or '.'}/catalog.json: 형식이 잘못됐습니다.")
    courses = []
    for name in index["courses"]:
        path = os.path.join(directory, name)
        courses.append(parse_course(_read_json(path), where=os.path.relpath(path, CONTENT_DIR), fixture=fixture))
    return courses


def build_catalog(courses, sdgs):
    """강좌 목록 전체를 검사한다: 강좌 id·slug·레슨 id 중복."""
    seen_courses, seen_slugs, seen_lessons = set(), set(), set()
    for c in courses:
        if c.id in seen_courses:
            raise ContentError(f"강좌 id {c.id!r} 가 중복됐습니다.")
        if c.slug in seen_slugs:
            raise ContentError(f"강좌 slug {c.slug!r} 가 중복됐습니다.")
        for lesson in c.lessons:
            if lesson.id in seen_lessons:
                raise ContentError(f"레슨 id {lesson.id!r} 가 중복됐습니다.")
            seen_lessons.add(lesson.id)
        seen_courses.add(c.id)
        seen_slugs.add(c.slug)
        for n in c.sdgs:
            if n not in sdgs:
                raise ContentError(f"{c.id}: SDG {n} 정보가 sdgs.json 에 없습니다.")
    return Catalog(courses=tuple(courses), sdgs=sdgs)


def _read_sdgs():
    data = _read_json(os.path.join(CONTENT_DIR, "sdgs.json"))
    try:
        return {int(k): (str(v[0]), str(v[1])) for k, v in data["goals"].items()}
    except (KeyError, TypeError, ValueError, IndexError):
        raise ContentError("sdgs.json: 형식이 잘못됐습니다.")


@lru_cache(maxsize=2)
def load_catalog(include_fixtures=False):
    """JSON 을 읽어 검사한 Catalog. 파일은 배포와 함께 바뀌므로 프로세스마다 한 번만 읽는다."""
    courses = _read_catalog_file(CONTENT_DIR, fixture=False)
    if include_fixtures:
        courses += _read_catalog_file(os.path.join(CONTENT_DIR, "dev_fixtures"), fixture=True)
    return build_catalog(courses, _read_sdgs())


def get_catalog():
    """현재 설정에 맞는 Catalog. 개발용 테스트 강좌는 ECONOVA_DEV_FIXTURES=1 (운영 아님) 일 때만 포함된다."""
    return load_catalog(include_fixtures=config.dev_fixtures_enabled())
