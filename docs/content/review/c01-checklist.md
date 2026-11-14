# c01 Economics & Choices — 사람 검토 체크리스트 (c02~c09 템플릿)

> 내부 문서 (운영자용). 정답은 이 파일에 쓰지 않는다 (정답·해설은 관리 화면이나 비공개 `~/econova-private/review/c01-review-package.md`).
> 검토 방법·서버 켜기: `docs/content/human-review-guide.md`. **아래 승인 칸은 사람이 직접 채운다. AI 는 채우지 않는다.**
> 다른 강좌는 이 파일을 복사해 `c0N-checklist.md` 로 만들고 링크의 강좌 번호만 바꾼다.

- 검토자: ______  · 검토 날짜: ______  · 검토 서버: http://127.0.0.1:5070
- 이 강좌의 AI 검토 기록: `docs/content/c01-review.md`, 출처 검토: `docs/content/source-review.md`, 허용 오차 제안: `docs/content/tolerance-policy-proposal.md`

## 0. 검토 순서 (권장 약 2~3시간)
1. 강좌 정보 → 2. 레슨 1~3 (하·중·상 모두) → 3. 형성 퀴즈 3개 → 4. 최종 평가·합격 기준 → 5. 출처 → 6. 학생 화면 → 7. 종합 판정

## 1. 강좌 정보 — `/admin/content` 의 c01 "Course description and learning objectives"
- [ ] 제목 "Economics & Choices", 설명, 학습목표 3개가 레슨 내용과 맞다
- [ ] SDG 12 연결이 적절하다
- 메모: ______

## 2. 레슨 (각 레슨을 beginner / intermediate / advanced 로 모두 연다)
| 레슨 | 미리보기 | 확인 |
|---|---|---|
| L1 Scarcity and Economic Choices | `/preview/c01/c01-l1?level=beginner` · `?level=intermediate` · `?level=advanced` | ☐ |
| L2 Opportunity Cost and Rational Decisions | `/preview/c01/c01-l2?level=beginner` · `?level=intermediate` · `?level=advanced` | ☐ |
| L3 Sustainable Consumption and Resource Allocation | `/preview/c01/c01-l3?level=beginner` · `?level=intermediate` · `?level=advanced` | ☐ |

레슨마다 확인할 것:
- [ ] **교육적 정확성:** 정의(희소성, 기회비용, 매몰비용, 한계적 사고, PPF, 기회비용 체증, 외부효과·사회적 비용)가 정확하다
- [ ] **명확성·가독성:** 고등학생이 혼자 읽고 이해할 수 있는 영어다. 어색한 번역투가 없다
- [ ] **난이도 차이:** 하(생활 예시) → 중(개념·관계) → 상(계산·형식)이 실제로 다르다
- [ ] **예제:** 풀이 예제(L1 3개, L2 4개, L3 3개)의 숫자·단계가 맞고 "Hypothetical example" 로 표시돼 있다
- [ ] **SDG 사례:** L1 학교 예산, L2 학교 축제 일회용품, L3 급식 음식물 쓰레기 — 선택지 3개의 편익·비용·가정이 공정하다
- [ ] **출처:** 하단 "Sources" 의 링크가 열리고 주장과 맞는다 (OpenStax 1.1·1.4·2.1·2.2·2.3·12.1, UN SDG 12)
- [ ] **기술 동작:** 화면이 깨지지 않는다, 레벨 전환이 된다, 출처 링크가 열린다

## 3. 형성 퀴즈 (각 5문항, 정답·해설 보임)
| 퀴즈 | 관리 화면 | 확인 |
|---|---|---|
| L1 | `/admin/content/assessment/c01-l1-quiz` | ☐ |
| L2 | `/admin/content/assessment/c01-l2-quiz` | ☐ |
| L3 | `/admin/content/assessment/c01-l3-quiz` | ☐ |
- [ ] **평가 공정성:** 정답이 하나뿐이고, 오답이 그럴듯한 오개념이며, 문장 길이·문법으로 정답이 드러나지 않는다
- [ ] 레슨에서 배운 내용 안에서 출제됐다 (학습목표 번호와 맞음)
- [ ] 수치형 문항에 단위·반올림 안내가 있고 허용 오차가 적절하다 (c01-l1-q5: 허용 오차 정책 제안 참고)
- [ ] 해설이 왜 맞고 왜 틀렸는지 설명한다

## 4. 최종 평가와 합격 기준
- [ ] 최종 평가 10문항 — `/admin/content/assessment/c01-final` (세 레슨을 고르게 다룸, 퀴즈와 중복 없음)
- [ ] 합격 기준 70% (10문항 중 7개)·재응시 3회 — `/admin/content/passing/c01-final` (최종 평가 승인 **뒤에** 판단)
- [ ] 제목 일관성: 최종 평가 제목이 "Economics and Choice: Final Assessment" 로 강좌 제목 "Economics & Choices" 와 다르다 → 통일할지 결정 (AI 가 발견, 아직 안 고침)

## 5. 학생 화면 (실제 강좌는 공개 전이라 개발용 테스트 강좌로 흐름만 확인)
- [ ] `/courses` 에서 c01 이 "Coming soon" 으로 보이고 학생이 레슨을 열 수 없다
- [ ] 개발용 테스트 강좌로 수강 → 레슨 → 퀴즈 → 최종 평가 → 수료 → `/report` 흐름의 영어 문구·버튼이 자연스럽다

## 6. AI 가 미리 표시한 c01 확인 사항
| 항목 | 내용 | 판단 |
|---|---|---|
| 예제 복사 경고 (오탐 추정) | c01-l2-q4 와 L2 예제 4 가 0·10·20·30·40 같은 흔한 수를 공유. 표와 답은 다름 | ☐ 유지 ☐ 수정 |
| 달러 변환 | 원화 예시를 달러로 바꿈 (통화 점검 124항목 이상 없음) | ☐ |
| 분업 사례 | OpenStax 의 핀 공장 대신 축제 샌드위치 예시 사용 (근접 의역 아님) | ☐ |
| 경제 체제 4분류 | 교과서 공통 틀 — OpenStax 1.4 와 나란히 보고 근접 의역 여부 확인 | ☐ |

## 7. 수정 요청 (AI 가 반영할 목록)
| # | 위치 (레슨/문항 id, 레벨) | 문제 | 원하는 수정 |
|---|---|---|---|
| 1 | | | |
| 2 | | | |

## 8. 종합 판정 (사람만 기입)
| 항목 | 상태 (미검토 / 수정 요청 / 승인 가능) | 관리 화면 결정 기록 여부 |
|---|---|---|
| 강좌 정보 | 미검토 | ☐ |
| L1 자료 / L1 퀴즈 | 미검토 | ☐ |
| L2 자료 / L2 퀴즈 | 미검토 | ☐ |
| L3 자료 / L3 퀴즈 | 미검토 | ☐ |
| 최종 평가 | 미검토 | ☐ |
| 합격 기준 | 미검토 | ☐ |
| 출처 (c01 인용분) | 미검토 | ☐ |

관리 화면에서 "Approve" 를 눌러도 공개되지 않는다. 공개는 릴리스 계획·커밋·배포라는 별도 단계다 (`docs/content/final-review-plan.md`).
