# ECONOVA 최종 커리큘럼 검토·공개 계획

> 내부 문서 (운영자용, 한국어). 2026-11-14 작성, 9개 강좌·27개 레슨 초안 완료 시점. 아직 아무것도 승인·공개하지 않았다.
> 학생 화면·콘텐츠는 영어 전용. 사람 결정 항목 목록은 `docs/content/review-backlog.md`.

## 0. 원칙
- **초안 완성 ≠ 승인.** AI 작성·AI 출처 확인·AI 정확성 검토는 모두 사람 승인이 아니다 (로더가 AI 승인 기록을 거부한다).
- 승인은 관리 화면(`/admin/content`)에서 플랫폼 관리자가 한다. 승인 기록은 내용 지문에 묶여 있어, 승인 뒤 내용이 바뀌면 다시 검토해야 한다.
- 공개는 승인된 내용만 릴리스 계획(`flask content-release-apply`)으로 반영하고 커밋한다. 웹 화면은 정본 JSON 을 고치지 않는다.

## 1. 검토 순서 (권장)
| 단계 | 할 일 | 산출물 / 기준 |
|---|---|---|
| 1 | **출처 사람 확인** (89개) | 각 강좌 `docs/content/cNN-review.md` 출처 표를 보며 링크를 열어 확인. "출처가 직접 뒷받침하지 않는 설명"은 교과 일반 지식으로 인정하거나 출처 보완 (backlog A2, B2, B3) |
| 2 | **레슨 자료 검토·승인** (27개) | 강좌 순서 c01 → c09. 하·중·상 차이, 경제학 정확성, 공정한 정책 서술, 영어 가독성. 강좌 사이 용어 일관성 (backlog B7) |
| 3 | **형성 퀴즈·최종 평가·정답 키 승인** | 비공개 검토 문서 `~/econova-private/review/cNN-content-review-en-*.md` 로 정답·해설 확인. 허용 오차 정책 결정(backlog A5) 후 필요한 문항만 version 올려 재생성 |
| 4 | **합격 기준 승인** (c01~c08: 70%, 재응시 3회) | 최종 평가 승인 **뒤에** 별도 승인 (backlog A3) |
| 5 | **c09 캡스톤 정의 → 루브릭 승인** | 수료 조건은 레슨 3 완료 + 제출 + 루브릭 자기평가 + 성찰, 최종 평가 없음 (backlog A4) |
| 6 | **진단평가 전 범위 재작성·승인** | 9개 강좌 범위로 영역 확대, 추천 기준 재설정 (backlog B4) |
| 7 | **과정 흐름·난이도 점검** | 강좌 순서(c01 기초 → c02 시장 → c03 실패 → c04·c05 거시·노동 → c06·c07 분배·금융 → c08 무역 → c09 캡스톤), 레슨당 학습 시간, 진단 추천 결과가 강좌 난이도와 맞는지 |
| 8 | **학생 화면·학습 흐름 점검** | 로컬 미리보기(격리 DB, 모의 AI)로 가입 → 진단 → 수강 → 레슨(하·중·상) → 퀴즈 → 최종 평가/캡스톤 → 수료 → 리포트. 모바일 폭, 접근성, 영어 문구 |
| 9 | **콘텐츠 릴리스 준비** | 승인된 항목만 릴리스 계획 → 서명 → `content-release-apply` → `content-verify-approvals` → 공개 커밋. 정답 키는 Render Secret Files 로 |
| 10 | **Render `lms` 서비스 교체** | `docs/deployment-econova.md` 순서: 자동 배포 끔 → main 병합(사람 승인) → 환경변수(Firebase `econova-dev`, 학원 OpenAI 키, AI 한도 20/300, 오답 설명 off) → 배포 → 확인. 최소 권한 Firebase 자격 증명은 공개 배포 전에 준비 |

## 2. 강좌별 검토 문서
| 강좌 | 공개 검토 문서 | 비공개(정답 포함) |
|---|---|---|
| c01 Economics & Choices | `docs/content/c01-review.md` | `~/econova-private/review/c01-content-review-en-2026-11-13.md` |
| c02 Markets & Prices | `docs/content/c02-review.md` | `~/econova-private/review/c02-content-review-en-2026-11-13.md` |
| c03 Market Failure | `docs/content/c03-review.md` | `~/econova-private/review/c03-content-review-en-2026-11-13.md` |
| c04 Growth & Stability | `docs/content/c04-review.md` | `~/econova-private/review/c04-content-review-en-2026-11-13.md` |
| c05 Labor & Employment | `docs/content/c05-review.md` | `~/econova-private/review/c05-content-review-en-2026-11-13.md` |
| c06 Inequality & Policy | `docs/content/c06-review.md` | `~/econova-private/review/c06-content-review-en-2026-11-13.md` |
| c07 Personal Finance | `docs/content/c07-review.md` | `~/econova-private/review/c07-content-review-en-2026-11-13.md` |
| c08 Global Economics | `docs/content/c08-review.md` | `~/econova-private/review/c08-content-review-en-2026-11-13.md` |
| c09 SDG Economic Challenge | `docs/content/c09-review.md` | `~/econova-private/review/c09-content-review-en-2026-11-14.md` |

## 3. 예상 작업량 (사람)
- 강좌당 2~3시간 (레슨 3 + 문항 25~ + 출처 확인) × 9 ≈ 20~27시간, 진단평가·캡스톤 루브릭·학습 흐름 점검 별도.
- 한 번에 한 강좌씩 승인하면 그 강좌부터 공개할 수 있다 (강좌 공개는 그 강좌의 승인 항목만 필요).
