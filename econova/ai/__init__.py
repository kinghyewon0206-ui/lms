"""ECONOVA AI 계층 (Phase 6).

- client.py          : 공급자(실제 OpenAI / 테스트·개발용 모의), 설정, 구조화 응답 검증, 시간 제한·오류 처리
- safety.py          : 서버 고정 지시문, 신뢰할 수 없는 입력 감싸기, 입력·출력 검사, 가명 처리
- usage.py           : 사용 한도(학생별·전체 일일 요청, 동시 요청, 반복 요청)와 토큰 사용량 기록 — 저장소 공유
- context.py         : 승인된 학습자료·확인된 출처로만 만든 근거 맥락
- tutor.py / feedback.py / debate.py / recommendations.py : 기능별 흐름

원칙: AI 는 점수·진도·수료·수강 정보를 바꾸지 않는다. AI 가 실패해도 학습은 계속된다.
"""
