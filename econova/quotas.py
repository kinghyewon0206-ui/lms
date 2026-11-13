"""학생별 저장 한도 (Phase 8B-1). 서버에서 확인하고, 한도에 닿으면 한국어 안내와 함께 새 기록만 막는다.

원칙
- 기존 기록은 자동으로 지우지 않는다 (보존 기간이 있는 AI 메시지는 ai-purge 의 보존 정책만 따른다).
- 학생 글을 몰래 자르지 않는다 (길이 제한은 입력 단계에서 오류로 알린다).
- 평가 응시 기록·진도는 지우지 않는다. 형성 퀴즈는 원래 재응시 무제한이라 아주 넉넉한 상한만 둔다.
- sqlite·Firestore 모두 같은 규칙: 저장소의 개수 조회 결과로 판단한다.

기본값과 이유 (모두 ECONOVA_QUOTA_<이름> 으로 바꿀 수 있다)
| 이름 | 기본 | 이유 |
| SIMULATION_RUNS | 200 | 실험 저장은 비교용. 레슨 27개 × 7회 정도면 충분 |
| TUTOR_MESSAGES | 200 | 레슨 하나의 튜터 대화(질문+답 = 2개) 100번 주고받기. 보존 기간(30일)이 지나면 정리됨 |
| FEEDBACK_REQUESTS | 10 | 응시 기록 하나에 대한 AI 오답 설명 요청 수 |
| DEBATES_PER_TOPIC | 20 | 같은 토론 주제를 새로 시작하는 횟수 |
| DEBATES_TOTAL | 100 | 학생 한 명의 토론 대화 전체 |
| CAPSTONE_VERSIONS | 100 | 캡스톤 저장 버전 (저장할 때마다 새 버전이 생김) |
| CAPSTONE_FEEDBACK | 50 | 캡스톤 AI 코치 기록 |
| DIAGNOSTIC_ATTEMPTS | 50 | 진단평가 재응시 |
| QUIZ_ATTEMPTS | 100 | 재응시 제한이 없는 형성 퀴즈 하나의 응시 수 |
"""
from econova import config

DEFAULTS = {"SIMULATION_RUNS": 200, "TUTOR_MESSAGES": 200, "FEEDBACK_REQUESTS": 10, "DEBATES_PER_TOPIC": 20,
            "DEBATES_TOTAL": 100, "CAPSTONE_VERSIONS": 100, "CAPSTONE_FEEDBACK": 50, "DIAGNOSTIC_ATTEMPTS": 50,
            "QUIZ_ATTEMPTS": 100}
LABELS = {"SIMULATION_RUNS": "saved simulations", "TUTOR_MESSAGES": "AI Tutor messages for this lesson",
          "FEEDBACK_REQUESTS": "AI explanations of mistakes for this result", "DEBATES_PER_TOPIC": "debates on this topic",
          "DEBATES_TOTAL": "debate conversations", "CAPSTONE_VERSIONS": "saved Capstone project versions", "CAPSTONE_FEEDBACK": "Capstone AI coach records",
          "DIAGNOSTIC_ATTEMPTS": "diagnostic assessment attempts", "QUIZ_ATTEMPTS": "attempts on this quiz"}


class QuotaExceeded(Exception):
    def __init__(self, name, limit):
        super().__init__(name)
        self.name, self.limit = name, limit

    @property
    def message(self):
        return (f"You've reached the limit for {LABELS[self.name]} ({self.limit}). Everything you've saved so far is still kept. "
                "If you need a higher limit, please contact the site administrator.")


def limit(name):
    try:
        value = int(config.env(f"ECONOVA_QUOTA_{name}") or DEFAULTS[name])
    except ValueError:
        raise config.ConfigError(f"ECONOVA_QUOTA_{name} must be an integer.")
    if not 1 <= value <= 100000:
        raise config.ConfigError(f"ECONOVA_QUOTA_{name} must be between 1 and 100000.")
    return value


def check(name, current, adding=1):
    """current 개가 이미 있을 때 adding 개를 더 저장해도 되는지. 안 되면 QuotaExceeded."""
    lim = limit(name)
    if current + adding > lim:
        raise QuotaExceeded(name, lim)


def validate_all():
    """앱 시작 때 설정 값 검사."""
    return {name: limit(name) for name in DEFAULTS}
