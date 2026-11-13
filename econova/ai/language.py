"""AI 응답 언어 규칙. 모든 시스템 지시문(safety.system_prompt)이 이 상수를 포함해야 한다 (테스트로 확인)."""

ENGLISH_ONLY_INSTRUCTION = (
    "Language: Always respond in English, even if the student writes in another language "
    "or the material contains text in another language. Write every JSON string value in clear, natural American English."
)
