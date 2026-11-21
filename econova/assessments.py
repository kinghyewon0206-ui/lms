"""레슨 형성 퀴즈와 강좌 최종 평가 (content/assessments/<id>.json) 로더·검사기.

검사 규칙 (어기면 ContentError):
- 평가 id·문항 id 는 고정 문자열이고 겹치지 않는다. 문항마다 version 이 있다.
- 문항은 강좌의 레슨·학습목표(번호)·핵심 개념을 가리키고, 그 참조가 실제로 있어야 한다.
- 객관식 정답은 선택지 id 중 하나, 수치형은 숫자 정답과 0 이상의 허용오차가 있어야 한다.
  check 가 있으면 정답을 코드로 다시 계산해 확인한다.
- 검토 상태·승인 정보 규칙은 학습자료와 같다(AI 승인 불가). 승인된 평가에는 승인된 문항만 들어갈 수 있다.
- 최종 평가의 합격 기준(passing)은 proposed(제안, 미승인) / approved(교사 승인) / dev_provisional(개발용 fixture 전용) 중 하나.

정답·허용오차·해설·검증식은 공개 파일이 아니라 비공개 정답 키에 있다 (econova/private_content.py).
키를 구하지 못하면 공개 정의만 검사하고 answer_keys=False 인 평가를 만든다. 그 평가는 응시·채점할 수 없다 (fail closed).
"""
from dataclasses import dataclass

from econova import lesson_content
from econova.lesson_content import APPROVED_STATUSES, LEVELS, ContentError

KINDS = ("lesson_quiz", "final")
QUESTION_TYPES = ("mcq", "numeric")
QUESTION_STATUSES = ("draft", "approved")
PASSING_STATUSES = ("proposed", "approved", "dev_provisional")
PUBLIC_QUESTION_KEYS = ("id", "version", "type", "prompt", "lesson_id", "objective", "difficulty", "points")


@dataclass(frozen=True)
class Assessment:
    id: str
    kind: str
    course_id: str
    lesson_id: str            # 레슨 퀴즈만. 최종 평가는 ""
    version: int
    title: str
    description: str
    review: dict
    retakes_allowed: bool
    max_attempts: int         # 0 = 제한 없음
    passing: dict             # {score_ratio, status, note} 또는 {} (퀴즈)
    questions: tuple          # 정답·해설이 들어 있다(키가 있을 때). 서버에서만 쓴다
    fixture: bool = False
    answer_keys: bool = True  # False: 정답 키가 없거나 맞지 않아 응시·채점할 수 없음
    keys_problem: str = ""    # 운영자용 이유 (학생 화면에는 보내지 않는다)

    @property
    def review_status(self):
        return self.review["status"]

    @property
    def approved(self):
        return self.review_status in APPROVED_STATUSES

    @property
    def is_final(self):
        return self.kind == "final"

    def passing_usable(self, fixture_course):
        """이 기준으로 수료를 인정해도 되는가. 실제 강좌는 교사가 승인한 기준만, 개발용 fixture 는 개발용 임시 기준도."""
        status = self.passing.get("status")
        return status in ("approved", "proposed") or (fixture_course and status == "dev_provisional")

    def question(self, qid):
        return next((q for q in self.questions if q["id"] == qid), None)

    def public_questions(self):
        """학생 화면용: 정답·허용오차·해설·검증 정보·개념 외 정보는 뺀다."""
        out = []
        for q in self.questions:
            pq = {k: q[k] for k in PUBLIC_QUESTION_KEYS}
            if q["type"] == "mcq":
                pq["choices"] = [{"id": c["id"], "text": c["text"]} for c in q["choices"]]
            else:
                pq["unit"] = q.get("unit", "")
            out.append(pq)
        return out


def _need(data, key, kind, where):
    return lesson_content._need(data, key, kind, where)


def _text(data, key, where):
    return lesson_content._text(data, key, where)


def parse_assessment(data, expected_id, course, lessons, fixture=False, where=None, keys_problem=None):
    """data: 평가 JSON(정답 키를 합친 서버 전용 데이터). course: 강좌 id. lessons: {lesson_id: (objectives, concept_ids)}.
    keys_problem 이 있으면 data 는 공개 정의뿐이다: 정답 관련 검사는 건너뛰고 응시할 수 없는 평가로 만든다."""
    has_keys = keys_problem is None
    where = where or f"assessments/{expected_id}.json"
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ContentError(f"{where}: unsupported schema_version.")
    if data.get("id") != expected_id:
        raise ContentError(f"{where}: id does not match {expected_id!r} referenced by the course JSON.")
    kind = data.get("kind")
    if kind not in KINDS:
        raise ContentError(f"{where}: kind must be lesson_quiz or final.")
    if data.get("course_id") != course:
        raise ContentError(f"{where}: course_id does not match {course!r}.")
    lesson_id = str(data.get("lesson_id") or "")
    if kind == "lesson_quiz" and lesson_id not in lessons:
        raise ContentError(f"{where}: the lesson quiz's lesson_id is not a lesson in this course.")
    if kind == "final" and lesson_id:
        raise ContentError(f"{where}: a final assessment must not have a lesson_id.")
    version = _need(data, "version", int, where)
    if version < 1:
        raise ContentError(f"{where}: version must be 1 or greater.")
    # 승인 지문은 정답 키를 합친 내용 기준이다 (정답·해설이 바뀌어도 승인이 무효가 되게). 키가 없으면 검사할 수 없고 평가도 닫힌다.
    review = lesson_content._parse_review(_need(data, "review", dict, where), where, fixture,
                                          digest=lesson_content.assessment_digest(data) if has_keys else None)

    retakes = _need(data, "retakes", dict, where)
    allowed = retakes.get("allowed")
    max_attempts = retakes.get("max_attempts") or 0
    if not isinstance(allowed, bool) or not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 0:
        raise ContentError(f"{where}: retakes must include allowed (true/false) and max_attempts (0 = unlimited).")
    if not allowed:
        max_attempts = 1

    passing = data.get("passing") or {}
    if kind == "final":
        try:
            ratio = float(passing["score_ratio"])
        except (KeyError, TypeError, ValueError):
            raise ContentError(f"{where}: a final assessment must have passing.score_ratio.")
        if not 0 < ratio <= 1:
            raise ContentError(f"{where}: passing.score_ratio must be greater than 0 and at most 1.")
        status = passing.get("status")
        if status not in PASSING_STATUSES:
            raise ContentError(f"{where}: passing.status must be one of {', '.join(PASSING_STATUSES)}.")
        if status == "dev_provisional" and not fixture:
            raise ContentError(f"{where}: the development-only provisional passing standard (dev_provisional) cannot be used in a real course.")
        if status == "approved" and review["status"] not in APPROVED_STATUSES:
            raise ContentError(f"{where}: the assessment itself must be teacher-approved before its passing standard can be approved.")
        if status == "approved" and not fixture and not str(passing.get("review_id") or "").strip():
            raise ContentError(f"{where}: an approved passing standard must include an admin review record ID (passing.review_id).")
        review_ref = str(passing.get("review_id") or "")
        passing = {"score_ratio": ratio, "status": status, "note": str(passing.get("note") or "")}
        if review_ref:
            passing["review_id"] = review_ref
    elif passing:
        raise ContentError(f"{where}: lesson quizzes do not have a passing standard (submitting completes the quiz; the score is recorded separately).")

    questions, seen = [], set()
    for q in _need(data, "questions", list, where):
        qid = _text(q, "id", where)
        w = f"{where} question {qid}"
        if qid in seen:
            raise ContentError(f"{w}: duplicate question id.")
        seen.add(qid)
        qv = _need(q, "version", int, w)
        if qv < 1:
            raise ContentError(f"{w}: version must be 1 or greater.")
        qtype = q.get("type")
        if qtype not in QUESTION_TYPES:
            raise ContentError(f"{w}: type must be mcq or numeric.")
        qlesson = str(q.get("lesson_id") or "")
        if qlesson not in lessons or (kind == "lesson_quiz" and qlesson != lesson_id):
            raise ContentError(f"{w}: lesson_id is not a lesson covered by this assessment.")
        objectives, concept_ids = lessons[qlesson]
        objective = q.get("objective")
        if not isinstance(objective, int) or isinstance(objective, bool) or not 1 <= objective <= len(objectives):
            raise ContentError(f"{w}: objective must be a lesson learning objective number (1-{len(objectives)}).")
        concepts = tuple(q.get("concept_ids") or ())
        if not concepts or set(concepts) - set(concept_ids):
            raise ContentError(f"{w}: concept_ids must refer to the lesson's key concepts.")
        if q.get("difficulty") not in LEVELS:
            raise ContentError(f"{w}: difficulty must be beginner, intermediate, or advanced.")
        status = q.get("review_status")
        if status not in QUESTION_STATUSES:
            raise ContentError(f"{w}: review_status must be draft or approved.")
        if review["status"] in APPROVED_STATUSES and status != "approved":
            raise ContentError(f"{w}: an approved assessment cannot contain unapproved questions.")
        if review["status"] not in APPROVED_STATUSES and status == "approved":
            raise ContentError(f"{w}: questions cannot be approved on their own before the assessment is approved.")
        points = q.get("points", 1)
        if not isinstance(points, (int, float)) or isinstance(points, bool) or points <= 0:
            raise ContentError(f"{w}: points must be greater than 0.")
        item = {"id": qid, "version": qv, "type": qtype, "prompt": _text(q, "prompt", w), "lesson_id": qlesson,
                "objective": objective, "objective_text": objectives[objective - 1], "concept_ids": concepts,
                "difficulty": q["difficulty"], "points": points,
                "explanation": _text(q, "explanation", w) if has_keys else "",
                "review_status": status, "source_ids": tuple(q.get("source_ids") or ())}
        if qtype == "mcq":
            choices = q.get("choices") or []
            ids = [c.get("id") for c in choices]
            if len(ids) < 2 or len(set(ids)) != len(ids) or not all(str(c.get("text") or "").strip() for c in choices):
                raise ContentError(f"{w}: there must be at least 2 choices, each with a unique id and non-empty text.")
            item["choices"] = tuple({"id": c["id"], "text": c["text"]} for c in choices)
            if not has_keys:
                questions.append(item)
                continue
            if q.get("answer") not in ids:
                raise ContentError(f"{w}: the answer is not one of the choices.")
            item["answer"] = q["answer"]
        elif not has_keys:
            item["unit"] = str(q.get("unit") or "")
            questions.append(item)
            continue
        else:
            answer, tol = q.get("answer"), q.get("tolerance")
            if not isinstance(answer, (int, float)) or isinstance(answer, bool):
                raise ContentError(f"{w}: the answer to a numeric question must be a number.")
            if not isinstance(tol, (int, float)) or isinstance(tol, bool) or tol < 0:
                raise ContentError(f"{w}: tolerance must be a number of 0 or greater.")
            item.update(answer=float(answer), tolerance=float(tol), unit=str(q.get("unit") or ""))
        check = q.get("check")
        if check:
            lesson_content.check_example(check, w)
            field = check.get("answer_field")
            if qtype == "numeric" and field and abs(float(check[field]) - item["answer"]) > 1e-9:
                raise ContentError(f"{w}: the answer does not match the calculated result ({field}).")
        questions.append(item)
    if not questions:
        raise ContentError(f"{where}: there must be at least one question.")
    if kind == "final":
        missing = [lid for lid in lessons if not any(q["lesson_id"] == lid for q in questions)]
        if missing:
            raise ContentError(f"{where}: the final assessment does not cover lessons {missing}.")

    return Assessment(
        id=expected_id, kind=kind, course_id=course, lesson_id=lesson_id, version=version,
        title=_text(data, "title", where), description=_text(data, "description", where), review=review,
        retakes_allowed=allowed, max_attempts=max_attempts, passing=passing, questions=tuple(questions), fixture=fixture,
        answer_keys=has_keys, keys_problem=keys_problem or "",
    )
