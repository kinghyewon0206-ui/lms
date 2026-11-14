# 진단평가 재설계 (econ-diagnostic v4 초안) — 내부 문서

- 작성일: 2026-11-14 · 상태: **draft (미승인)** · 기준(thresholds): 0.4 / 0.75 그대로, `provisional: true`
- 이 문서는 공개 저장소에 있으므로 **정답·정답 위치·허용오차 값은 적지 않는다.** 정답 키는 비공개 폴더에만 있다.
- 원본: `~/econova-private/i18n/econ-diagnostic.full.json` → `assessment_tool.py import econ` 으로 공개 파일
  `content/diagnostic.json` 과 비공개 키를 다시 만들었다. 버전은 도구가 올렸다 (HEAD v3 → v4, 문항 전부 변경).

## 1. 설계 원칙

- 대상: **수업 전** 고등학생. 용어 암기 없이 일상 추론으로 풀 수 있게, 필요한 정의(예: 노동력)는 문제 안에서 준다.
- 9개 강좌(c01–c09)의 출발 개념을 한 문항씩 이상 다룬다. 태도·의견 문항 없음, 고급 수학 없음.
- 문항 수 12개 (스키마 한도 10–12). 객관식 10, 수치형 2, 그래프 1 (균형점 미표시, `ceiling_shortage` 자동 검증).
- 수치형은 단위·반올림 자리를 문제에 적고, 허용오차는 "요청 자리의 절반" 규칙(tolerance 검토 규칙 R2)을 따른다.
  흔한 오답 계산(분모를 잘못 고르기, 단리로 계산하기 등)은 허용 범위 밖임을 Python 으로 확인했다.
- 모든 정답은 Python 으로 독립 재계산·검증했다 (그래프 균형·상한가 부족량, 비율, 복리, 기회비용 비교).

## 2. 문항 구성표

| 문항 | 강좌 / 개념 | 카테고리(id) | 예상 난이도 |
|---|---|---|---|
| q01 | c01 · 기회비용 (차선의 대안 하나만 포기) | scarcity | 쉬움 |
| q02 | c02 · 수요 증가 시 균형 가격·거래량 변화 | supply_demand | 쉬움 |
| q03 | c02 · 그래프: 가격 상한(최고가격)과 부족 | supply_demand | 보통 |
| q04 | c03 · 부정적 외부효과와 과잉 생산 | market_failure | 보통 |
| q05 | c03 · 공공재와 무임승차 | market_failure | 보통 |
| q06 | c04 · 명목 vs 실질 GDP (물가 상승분 구분) | macroeconomy | 보통 |
| q07 | c05 · 실업률 (노동력 정의를 문제에서 제공, 수치형) | macroeconomy | 어려움 |
| q08 | c06 · 소득 대비 세금 비율 비교 (누진세 개념, 용어 없이) | income_money | 쉬움 |
| q09 | c07 · 복리 vs 단리 (수치형) | income_money | 보통 |
| q10 | c08 · 비교우위 (절대우위와 구분) | scarcity | 어려움 |
| q11 | c09 · SDG 문제 정의: 증상과 근본 원인 구분 | policy | 보통 |
| q12 | c09 · 정책 주장을 뒷받침하는 증거 판단 (비교 집단) | policy | 어려움 |

카테고리 6개 × 각 2문항 (스키마: 카테고리마다 1문항 이상).

| id | 표시 이름 | 강좌 |
|---|---|---|
| scarcity | Scarcity, choices, and trade | c01, c08 |
| supply_demand | Markets and prices | c02 |
| market_failure | When markets fall short | c03 |
| macroeconomy | Output, prices, and jobs | c04, c05 |
| income_money | Income, taxes, and saving | c06, c07 |
| policy | Reasoning about SDG policy | c09 |

환율 방향(c08)은 문항 수 제한 때문에 비교우위로 대체했다. 인플레이션은 q06(명목·실질)에서 간접적으로 다룬다.

## 3. 이전 버전(v3) 대비 변경

- 범위: v3 는 c01–c02 (용어, 희소성, 수요·공급, 그래프, 간단 계산, 정책) 중심 → v4 는 c01–c09 전체.
- 문항: 12개 모두 새로 작성. 용어 회상형 문항(수요 법칙 이름, "수요량" 정의) 삭제, 탄력성 계산·수요함수 대입 삭제.
- 카테고리: `terminology`, `graph`, `calculation` 삭제, `market_failure`, `macroeconomy`, `income_money` 추가.
  `scarcity`, `supply_demand`, `policy` 는 id 유지(이름만 변경).
- 그래프: 2개 → 1개 (`market_ceiling`, 새 수치). 사용하지 않는 `market` 그래프 삭제.
- description, review.note 갱신. thresholds 값·`provisional` 은 그대로.

### 영향 (코드 변경 없음, 확인만)
- 채점·추천 로직은 카테고리 id 를 하드코딩하지 않는다 (`diagnostic.score`, `recommendations.py`, `report.py`).
- **기존 응시 기록**은 옛 카테고리 id(`terminology`, `graph`, `calculation`)를 저장하고 있다. 결과·리포트·대시보드는
  `category_names.get(id, id)` 로 표시하므로 옛 기록에서는 이 세 영역이 **id 그대로(영문 소문자)** 보인다.
  필요하면 옛 id 의 표시 이름을 별도로 매핑하는 작은 수정을 제안한다 (이번 작업에서는 하지 않음).
- `recommendations.MIN_EVIDENCE = 3` 이므로 2문항짜리 카테고리의 약점 표시는 v3 와 마찬가지로 모두 "provisional" 로 나온다.
- 테스트(`tests/test_diagnostic.py`)는 합성 진단평가(`content/dev_fixtures/diagnostic.json`)만 쓰므로 영향 없음.

## 4. 중복 검사 결과

- `qa.py` (c01–c09 전 평가 + 진단평가): 0.8 이상 유사 프롬프트 **없음**. 진단평가 MCQ 위치 분포 정상 출력.
- 추가 검사(진단평가 프롬프트 ↔ 모든 퀴즈·기말 문항 + 레슨 worked example 문제): 문항별 최대 유사도 0.34–0.48.
- 수치형 문항의 숫자 조합은 레슨·평가에서 재사용되지 않음을 grep 으로 확인했다.
- 개념이 겹치는 문항(예: c09-l1 증상/원인, c06-l2 세금 분류)은 있지만 상황·숫자·질문 방식이 다르다.
- QA 의 기존 경고(c01/c02 example-copy?)는 이번 변경과 무관하다.

## 5. 정답 위치 분포 (객관식 10문항)

| 위치 | a | b | c | d |
|---|---|---|---|---|
| 개수 | 3 | 2 | 3 | 2 |

연속 반복·주기 패턴 없음. 오답 선택지에 절대어(always, never, all, only 등) 없음. 정답이 눈에 띄게 가장 긴 문항 없음
(정답 길이 ÷ 오답 평균 길이 0.91–1.03).

## 6. 기준(thresholds) 분석 — **제안이며 적용하지 않음**

### 현재 규칙을 12문항에 적용하면
| 정답 수 | 비율 | 추천 |
|---|---|---|
| 0–4 | 0–33% | beginner |
| 5–8 | 42–67% | intermediate |
| 9–12 | 75–100% | advanced |

문항 수가 v3 와 같아서 경계 점수(4/5, 8/9)는 바뀌지 않는다.

### 문제점
1. **추측 점수**: 객관식 10문항을 무작위로 찍으면 평균 2.5문항(약 21%)이 맞는다. beginner/intermediate 경계(5문항)는
   추측보다 2.5문항 높을 뿐이라, 운이 좋으면 아무것도 모르는 학생도 intermediate 로 추천될 수 있다.
2. **범위가 넓어졌다**: v4 는 c04–c08 처럼 대부분의 학생이 아직 배우지 않은 영역을 포함한다. 수업 전 학생의 평균 점수는
   v3 보다 낮을 가능성이 크고, 그러면 같은 기준에서도 beginner 추천 비율이 늘어난다. 이것이 의도(대부분 기초부터 시작)에
   맞는지는 실제 응시 데이터로 확인해야 한다.
3. **단일 총점의 한계**: 난이도 추천은 모든 강좌에 같은 값이 쓰이지만, 진단평가는 이제 강좌별 개념을 다룬다. 예를 들어
   c01–c03 영역을 모두 맞히고 c05–c07 영역을 모두 틀린 학생과 그 반대 학생이 같은 추천을 받는다.

### 권고
- **당분간 0.4 / 0.75 유지** (provisional 표시 유지). 기준을 바꿀 근거가 될 학생 데이터가 아직 없고,
  경계 점수가 v3 와 같아 기존 기록과 비교하기 쉽다.
- 파일럿(가능하면 30–50명 이상) 후 다음을 검토한다: 문항별 정답률(0.3–0.85 범위 밖이면 수정), 변별도,
  총점 분포, 그리고 추천 수준과 첫 강좌 퀴즈 성적의 일치 정도.

### 대안 (모두 제안 단계)
- **A. 추측 보정 기준**: beginner/intermediate 경계를 6/12(50%)로 올리고 advanced 는 9/12 유지.
  추측 평균보다 확실히 높은 학생만 intermediate 로 추천한다.
- **B. 카테고리 최소 조건**: advanced 는 "9문항 이상 **그리고** 0/2 인 카테고리 없음",
  intermediate 는 "5문항 이상 **그리고** 0/2 카테고리가 2개 이하". 한 영역만 강한 학생의 과대 추천을 막는다.
- **C. 강좌별 추천 (구조 변경 필요)**: 카테고리 점수를 해당 강좌에 연결해 강좌마다 다른 시작 난이도를 제안한다.
  예) `supply_demand` 2/2 → c02 intermediate 이상, 0/2 → c02 beginner. 2문항뿐이라 신뢰도가 낮으므로
  "참고" 표시가 필요하고, 코드·화면 변경이 따른다.
- **D. 점수 구간 → 시작 강좌 안내**: 0–4 "c01 부터 beginner", 5–8 "c01–c03 intermediate, 이후 강좌 beginner",
  9–12 "원하는 강좌부터 intermediate/advanced". 난이도와 학습 순서를 함께 안내한다 (화면 문구 추가 필요).

권장 순서: 지금은 유지 → 파일럿 데이터로 A 또는 B 검토 → 데이터가 충분히 쌓이면 C/D 검토.
어떤 변경이든 기존 기록은 당시 기준 그대로 보존된다 (`attempt.thresholds` 저장, 재계산 안 함).

## 7. 검증 기록
- `assessment_tool.py import econ` → `imported econ-diagnostic v 4`
- `flask --app app check-content` → 내용 OK, 모든 평가에 정답 키 있음
- `qa.py` → 0.8 이상 중복 없음
- `pytest -q tests/test_diagnostic.py tests/test_english_only.py` → 86 passed
- 승인·게시 없음. thresholds·추천 코드 변경 없음. 커밋 없음.
