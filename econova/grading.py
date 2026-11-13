"""결정적 채점 (진단평가·레슨 퀴즈·최종 평가가 같이 쓴다). AI 는 점수에 관여하지 않는다.

- 객관식: 제출한 값이 그 문항의 선택지 id 중 하나이고, 정답 id 와 같으면 정답. 선택지에 없는 값은 오답.
- 수치형: 앞뒤 공백을 지우고, 천 단위 쉼표(1,000)만 없앤 뒤 소수점(.)으로 읽는다. |입력 − 정답| ≤ 허용오차 이면 정답.
  지수 표기(1e3), 소수점 쉼표(12,5), 분수(1/2), %, 무한대·NaN 처럼 모호하거나 유한하지 않은 값은 읽지 않고 오답으로 둔다.
- 빈 답은 오답. 문항마다 배점(points)이 있고 점수는 맞힌 문항 배점의 합이다.
"""
import math
import re

_NUM_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
_THOUSANDS_RE = re.compile(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?")
MAX_ANSWER_LENGTH = 50


def is_plain_number(text):
    return bool(_NUM_RE.match(text))


def parse_number(raw):
    """수치 답 읽기. 읽을 수 없으면 None."""
    text = str(raw or "").strip().replace(" ", "")
    if _THOUSANDS_RE.fullmatch(text):
        text = text.replace(",", "")
    if not is_plain_number(text):
        return None
    value = float(text)
    return value if math.isfinite(value) else None


def is_correct(q, raw):
    """q: {type, answer, choices?, tolerance?}. raw: 학생 입력 문자열."""
    if q["type"] == "mcq":
        raw = str(raw or "")
        return raw in {c["id"] for c in q["choices"]} and raw == q["answer"]
    value = parse_number(raw)
    return value is not None and abs(value - q["answer"]) <= q["tolerance"] + 1e-9


def grade(questions, answers):
    """questions: 정답이 들어 있는 문항 목록(서버 전용). answers: {문항 id: 입력}.
    반환: score, max_score, ratio, results[{id, answer, correct, points}]. 모르는 문항 id 는 무시한다."""
    answers = {str(k): str(v)[:MAX_ANSWER_LENGTH] for k, v in (answers or {}).items()}
    results, score, max_score = [], 0.0, 0.0
    for q in questions:
        raw = answers.get(q["id"], "")
        points = float(q.get("points", 1))
        ok = is_correct(q, raw)
        results.append({"id": q["id"], "answer": raw, "correct": ok, "points": points})
        max_score += points
        score += points if ok else 0.0
    return {"score": score, "max_score": max_score, "ratio": score / max_score if max_score else 0.0, "results": results}
