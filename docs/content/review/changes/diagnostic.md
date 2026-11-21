# 변경 기록 — econ-diagnostic (진단평가) 종합 점검, 2026-11-21

- 작성: Claude Code (AI). 사람(교사·관리자)의 검토나 승인이 아니다. 상태는 그대로 draft.
- 공개 문서이므로 정답·정답 위치·허용오차 값·정답 해설은 적지 않는다.
- 공개 파일 `content/diagnostic.json` 은 `assessment_tool.py import econ` 으로 다시 만들었다 (assessment version 5 → 6).
- thresholds(0.4 / 0.75, provisional), 카테고리 id·이름, 문항 수(12), 문항 id, 그래프 정의, review.status 는 바꾸지 않았다.

| # | location | problem (category) | decision and reasoning | change | source/evidence |
|---|---|---|---|---|---|
| 1 | q11 prompt | 용어 불일치 (terminology) | 지문은 "root cause" 를 쓰지만 c09-l1 레슨은 "symptom vs. underlying cause" 로 가르친다. 같은 개념을 같은 말로 묻도록 맞춤 | "root cause" → "underlying cause" | c09-l1 concepts ("Symptoms vs. underlying causes") |
| 2 | q11 choice (하나) | 정답 근거가 약함 (one defensible answer) | 선택지 하나가 c09-l1 의 "keep asking why" 기준으로 보면 증상인지 원인인지 모호하게 쓰여 있어, 정답이 하나뿐인지 다툼 여지가 있었다. 지문에서 바로 추론되는 내용으로 표현을 정확히 해 증상·결과·원인 구분이 분명해지도록 함 | 선택지 문구 수정 (선택지 id·정답 위치 불변) | c09-l1 concepts 정의 |
| 3 | q11 explanation | 해설-선택지 일치 (explanation) | 수정한 선택지와 c09 용어(증상·결과·underlying cause)에 맞게 해설을 다시 씀 | 해설 수정 (비공개 키) | — |
| 4 | q07 prompt | 수치 입력 안내 형식 (numeric policy) | 퍼센트 답의 표준 안내 문장("Enter a number only; for example, enter N for N%.")과 다르게 쓰여 있었다. 반올림 자리(nearest whole percent)는 유지하므로 R2 허용오차 규칙은 그대로 | 입력 안내를 표준 형식으로 교체 | 브리프 수치 정책 R1–R5 |
| 5 | q04 explanation | 용어 정합성 (terminology) | 해설이 "full social cost" 만 말하고 사회적 비용 = 사적 비용 + 외부 비용 관계와 "추가 단위의 사회적 비용 > 구매자 가치" 논리를 빠뜨림. 공통 용어 결정에 맞춤 (수업 전 학생 수준은 유지) | 해설 수정 (비공개 키) | 브리프 공통 용어(외부효과) |
| 6 | 비공개 오답 계산 목록 | 수치 문항 오답 검사 범위 (numeric policy) | q07 에는 흔한 잘못된 분모 계산 항목이 없었고, q09 에는 1년치만 계산한 값이 없었다 | wrong_methods.json 에 q07 항목 추가, q09 항목에 값 1개 추가 (비공개) | Python 재계산 |
| 7 | review.history | 기록 | 브리프 규칙대로 이력 1건 추가 (정답 정보 없음, 아래 8–9 반영해 같은 항목의 note 갱신) | history 항목 추가 | — |
| 8 | q01 choices (두 개) | 정의 짜맞추기 단서 (no clues) | 독립 검토자 지적: 한 선택지가 정의 문구("next-best use")를 그대로 담아 개념 이해 없이 정의와 짝지어 풀 수 있었다. 두 선택지를 지문의 순위 정보로만 표현해, 학생이 기회비용 정의를 스스로 적용해야 풀리게 함. 정답 위치 불변 | 선택지 문구 2개 수정, 해설 수정 (비공개 키) | 독립 재풀이 검토 (2026-11-21) |
| 9 | description | 범위 설명 불일치 (accuracy) | 설명은 "income, taxes and money" 를 다룬다고 했지만 화폐를 묻는 문항은 없다. 실제 범위와 카테고리 이름("Income, taxes, and saving")에 맞춤. 목록이 쉼표로 모호해져 세미콜론으로 구분 | 설명 문구 수정 | 문항 구성표 |

## 점검했으나 문제 없음 (12문항 전부)

- 모든 정답을 직접 다시 계산·추론했다: q01 기회비용(차선 하나), q02 수요 증가, q03 그래프(수요·공급 매개변수로 균형과 상한가에서의 수요량·공급량을 계산, 상한가가 균형 아래라 부족 발생, `ceiling_shortage` 자동 검증 통과), q04 부정적 외부효과, q05 공공재·무임승차, q06 명목 vs 실질, q07 실업률(노동력 기준), q08 소득 대비 세금 비율, q09 복리, q10 비교우위(기회비용 비교), q11 증상 vs 원인, q12 비교 집단 증거.
- 객관식은 문항마다 정답이 하나이고, 오답은 그럴듯하지만 근거가 틀렸다 (흔한 오개념: 두 대안 합산, 곡선 이동 혼동, 절대우위, 상관 vs 인과 등).
- 단서 점검: 정답이 유일하게 가장 길거나 유일하게 단서어(hedge)를 가진 문항 없음. 정답 위치 분포는 설계 문서와 같고, 이번 수정으로 정답 위치는 바뀌지 않았다.
- 수치 정책: q07·q09 모두 반올림 자리 명시 → R2. q09 는 여러 단계 복리 → "Round only at the final step." 있음 (R5). 사용자는 숫자만 입력.
- 그래프: 매개변수에서 그려지고 `expected_equilibria` 가 비어 있어 응시 화면에 균형점·균형표가 나오지 않는다 (`templates/econova/_graph.html` 은 균형점이 있을 때만 표를 그림).
- 카테고리 적합성: 각 문항이 표시된 카테고리와 강좌(c01–c09) 영역에 맞다. 카테고리 6개 × 2문항 유지.
- 공통 용어(실질값, 실업률·노동력, 외부효과, 비교우위, 누진세)와 c01–c09 레슨의 정의와 충돌 없음.

## Unresolved / uncertain

- 난이도 기준(0.4 / 0.75)과 문항별 실제 난이도는 학생 데이터가 없어 검증할 수 없다. 기준은 지시대로 바꾸지 않았다 (`docs/content/diagnostic-redesign.md` 6절의 제안 참고).
- q10 은 "필요한 셔츠 수가 Ana 혼자 만들 수 있는 범위" 라는 암묵적 가정이 있다. 진단평가 수준에서는 표준적인 단순화라 그대로 두었다.
- 2문항짜리 카테고리라 영역별 약점 표시는 계속 provisional 로만 나온다 (코드 동작, 이번 범위 밖).
- 새 출처는 추가하지 않았다 (모든 문항이 가상 예시이고 사실 주장이 없음).

## Not changed on purpose

- thresholds, 카테고리 id·이름, 문항 수·id, draft 상태, 그래프 수치.
- q02, q03, q05, q06, q08–q10, q12 의 공개 문구 (정확하고 정답이 하나뿐이라 수정할 이유 없음).
- q07 의 반올림 자리 안내 (정답은 정확한 정수지만 잘못된 분모 계산값을 정수로 반올림해도 오답이 되도록 R2 를 유지).
- review.note 의 "v3 redesign" 표기 (설계 문서의 v4 와 번호가 다르지만 사실 오류가 아닌 내부 명칭이라 그대로 둠).
