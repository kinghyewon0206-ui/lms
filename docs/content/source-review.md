# ECONOVA 출처 검토 패키지 (사람 검토용)

> 내부 문서 (운영자용, 한국어 설명 · 영어 콘텐츠 원문 유지). 작성: 2026-11-14, Claude Code (AI).
> **이 문서는 AI 가 만든 검토 자료이며 사람의 승인이 아니다.** `content/sources.json` 의 89개 출처는 모두 `verification.status = "verified"` 이지만,
> 이는 AI 가 페이지를 열어 본 기록일 뿐이고 `checked_by` 에도 "Not yet checked by a human (not an approval)" 로 적혀 있다.
> 이 문서를 만들면서 콘텐츠 JSON·sources.json·레슨·코드·테스트는 바꾸지 않았다.
> 레슨 위치·문구는 브랜치 `feature/econova-lms-renewal` 의 커밋 `bd3a872` 상태 기준이다. 작성 중 다른 작업이 `content/lessons/c03-l3.json` 을 미커밋으로 바꿨다 (P03-5 참고).

범위: 9개 강좌 · 27개 레슨 · 출처 89개. 근거 자료: `content/sources.json`, `content/lessons/c0X-lY.json`, `docs/content/c0X-review.md`, `docs/content/review-backlog.md`,
그리고 2026-11-14 에 AI 가 WebFetch 로 다시 연 페이지 (아래 각 표의 "재확인" 열). WebFetch 는 페이지를 작은 모델로 요약해 돌려주므로,
"페이지에 X 가 없다" 는 판정은 **요약 기반**이다. 사람 검토자는 링크를 직접 열어 최종 판단해야 한다.

---

## 1. 이 문서 사용법

### 1.1 AI 확인 ≠ 사람 승인
- `verified` 는 "AI 가 페이지를 열어 제목·저자·라이선스·다루는 개념을 확인했다" 는 뜻이다. 레슨의 **특정 문장**을 그 출처가 뒷받침하는지는 별개 문제이고,
  각 강좌 검토 문서가 "출처가 직접 뒷받침하지 않는 부분" 을 따로 적어 둔 이유다.
- 이 문서의 판정(직접 / 간접 / 뒷받침 없음 / 페이지 열리지 않음)도 AI 판정이다. 사람이 확인하기 전까지는 제안일 뿐이다.

| 판정 | 뜻 |
|---|---|
| **직접** | 인용한 출처 페이지가 그 주장을 사실상 그대로 말한다. |
| **간접** | 출처가 관련 개념·현상은 다루지만, 레슨의 용어·식·일반화·결론은 출처에 없다 (AI 의 표준 교과서식 확장). |
| **뒷받침 없음** | 인용한 출처(들)에 그 주장이 없다. 표준 교과 지식일 수는 있다. |
| **페이지 열리지 않음** | 이번 재확인에서 페이지를 열지 못했다 (HTTP 오류 등). |

### 1.2 관리 화면에서 출처를 "사람 확인" 으로 표시하는 방법 (현재 코드 기준)
`/admin/content` → 출처 대상(target type `source`) → `/admin/content/source/<source_id>` 페이지.

**주의할 점 (코드 확인 결과, `econova/admin_content.py`):**
1. `review_state()` 는 파일 상태가 `verified` 인 출처를 처음부터 **"Approved (from the canonical file)"** 로 보여 준다 (`base = "approved" if file_state == "verified"`).
   즉 관리 화면의 "Approved" 표시는 **AI 확인을 그대로 옮긴 것**이며 사람 승인 기록이 아니다. 화면 제목 옆에 "(from the canonical file)" 이 보이면 아직 DB 검토 기록이 없다는 뜻이다.
2. 사람 확인을 남기려면: **Reopen**(approved → in_review) → 링크를 열어 이 문서의 해당 행을 확인 → **Approve**.
   Approve 에는 5자 이상 검토 의견과 "직접 검토했다" 확인 체크가 필요하고, 검토자 이름에 AI 표지가 있으면 거부된다. 고칠 것이 있으면 **Request changes**(→ draft).
3. 그 결과는 DB 검토 기록(`review record #n`)으로만 남는다. 출처(`source`)는 `RELEASABLE` 대상이 아니므로 릴리스 계획으로 `sources.json` 에 되써지지 않는다.
   따라서 `sources.json` 의 `checked_by` 문구("Checked by Claude Code (AI)…")는 사람이 확인한 뒤에도 그대로 남는다. 사람 확인을 정본 파일에도 남기려면
   (a) 사람이 직접 `verification.checked_by`/`checked_at` 을 고치거나 (b) 앱 변경을 따로 결정해야 한다 (이번에 하지 않음).
4. 의견란에 이 문서의 항목 번호(예: `P05-4`)와 판단(유지/문구 수정/출처 교체)을 적으면 나중에 추적하기 쉽다.

### 1.3 권장 작업 방식
1. 2장(우선 검토)의 항목을 위에서부터 판단한다. 각 항목의 "제안" 은 AI 제안이며, 레슨 문구 변경은 별도 콘텐츠 수정·재검토 절차를 거친다.
2. 3장 표로 출처별 사람 확인(Reopen → Approve)을 기록한다.
3. 4장(열리지 않은 출처)과 5장(근접 의역)은 공개 전 차단 여부를 판단한다.

---

## 2. 우선 검토 (Flagged areas)

각 행: **위치**(레슨 id + JSON 경로/제목) · **주장**(영어 원문 요약) · **인용 출처** · **2026-11-14 재확인 내용**(AI 가 연 페이지에서 본 것만) · **판정** · **제안**.
"인용 출처" 가 레벨 본문(`levels.*.sections`)인 경우, 레슨 스키마상 섹션에는 출처가 없고 레슨 전체 `source_ids` 와 연결된 개념(`concept_ids`)의 출처가 적용된다.

### 2.1 c05 — 최저임금 효과와 수요독점

| # | 위치 | 주장 (요약) | 인용 출처 | 재확인 (2026-11-14) | 판정 | 제안 |
|---|---|---|---|---|---|---|
| P05-1 | c05-l3 `concepts[3]` "Employer market power (monopsony)" | A monopsony employer hires fewer workers and pays a lower wage than a competitive market. | openstax-pe3-14-2 | 14.2 가 수요독점 정의, Lm·Wm < Lc·Wc, 노동의 한계비용 > 임금 설명을 모두 담음 | 직접 | 유지 |
| P05-2 | c05-l3 `real_world_examples[1]` "One employer, few alternatives" | Classic example: town with a single large employer (mining company); laws such as minimum wages aim to balance bargaining power. | openstax-pe3-14-2 | 웨스트버지니아 마을의 유일한 석탄 회사 예, 노사 힘의 균형을 위한 법률 목록에 "Setting minimum hourly wages" 포함 | 직접 | 유지 |
| P05-3 | c05-l3 `levels.advanced.sections[1]` "Monopsony and contested evidence" ¶0 | Monopsonist faces upward-sloping supply; MCL > wage; hires where demand = MCL. | (개념) openstax-pe3-14-2 | 14.2 에 같은 논리 있음 | 직접 | 유지 |
| P05-4 | c05-l3 `levels.advanced.sections[1]` ¶1, `levels.advanced.summary`, `levels.intermediate.sections[2]` "Why the evidence is mixed" ¶1 | A minimum wage between W_m and W_c can raise both the wage and employment under monopsony. | openstax-pe3-14-2 (개념) | 14.2 는 이 분석을 **하지 않음** (최저임금은 근로자 보호 법률 목록에만 등장). 4.1 은 수요독점을 다루지 않음 | 뒷받침 없음 | 표준 교과 이론으로 유지하되 "in the standard monopsony model" 처럼 모형 결과임을 밝힘. 직접 출처 후보 CBO 보고서(`cbo.gov/publication/55410`)는 오늘도 HTTP 403 — **확인된 대체 출처 없음** |
| P05-5 | c05-l3 `levels.beginner.sections[2]` "What happens in real life is debated" ¶1 | In a one-company town, "a minimum wage can raise pay without necessarily cutting jobs." | 레슨 전체 (14.2 등) | 위와 같음. 다만 문단 끝에 "a question for evidence, not just theory" 헤지 있음 | 뒷받침 없음 | P05-4 와 함께 판단 |
| P05-6 | c05-l3 `concepts[2]` "Mixed evidence on minimum wages" | Some studies find reduced hiring of low-skill workers, others little or no effect; still debated. | openstax-pe3-4-1, openstax-pe3-21-4 | 4.1: 10% 인상 → 비숙련 고용 1~2% 감소라는 통상 추정과 "some studies have even found no effect" + 논쟁적이라고 서술. 21.4: 높은 최저임금이 저숙련 고용을 막을 수 있음 | 직접 | 유지 |
| P05-7 | c05-l3 `key_takeaways[1]`, `levels.intermediate.summary`, `objectives[1]` | Effects "depend on how high the minimum is relative to local wages and on employer market power." | 4.1, 21.4, 14.2 | "지역 임금 대비 수준" 은 4.1·21.4 에 명시 없음 (21.4 는 "high minimum wages" 만). 고용주 지배력과 최저임금 효과의 연결은 어느 출처에도 없음 | 간접 | 문구를 "economists point to factors such as…" 로 완화하거나 P05-4 결정과 맞춤 |
| P05-8 | c05-l2 `levels.advanced.sections[0]` "Measurement identities" | E/N = p(1 − u); improving prospects can draw people into the labor force and briefly raise u. | openstax-pe3-21-1 등 | 21.1 은 정의(노동력 = 취업 + 실업)만 제공. 항등식·해석은 정의에서 유도한 것 | 간접 | 유도식으로 유지 (출처 문제 아님) |
| P05-9 | c05-l3 `concepts[4]` "Job training and job-search help" | Training fixes skill mismatches; search help speeds matching; results depend on design. | openstax-pe3-21-4 | 21.4: 구직·재훈련 지원이 복귀를 앞당길 수 있다, 지원 설계가 구직 의욕을 해치지 않게 해야 한다 | 직접 | 유지 |
| P05-10 | c05-l3 `real_world_examples[0]` "Minimum wage and living wage debates" | Supporters argue full-time workers should afford essentials; living wage laws in cities. | openstax-pe3-4-1 | 4.1: 생활임금 논거, 1994 볼티모어 첫 조례, 이후 수십 개 도시 | 직접 | 유지 |

보조 확인: ILOSTAT 실업률 정의 페이지(`ilostat.ilo.org/methods/concepts-and-definitions/description-unemployment-rate/`)도 오늘 HTTP 403.

### 2.2 c06 — 재분배·불평등

| # | 위치 | 주장 (요약) | 인용 출처 | 재확인 | 판정 | 제안 |
|---|---|---|---|---|---|---|
| P06-1 | c06-l1 `concepts[4]` "Gini coefficient" (앞부분) | Area between diagonal and Lorenz curve ÷ area under diagonal; 0–1, World Bank also 0–100. | worldbank-gini-index | 정의 일치. 페이지 자체가 0~100 과 0~1 을 섞어 씀 | 직접 | 유지 (척도 혼용 안내는 이미 레슨에 있음) |
| P06-2 | c06-l1 `levels.advanced.summary` / `levels.advanced.sections[1]` | G = 1 − 2∫L(p)dp; for a listed population G = mean absolute difference ÷ (2 × mean). | worldbank-gini-index | 페이지가 "모든 쌍의 절대 차이 평균을 평균의 두 배로 나눈 값" 을 **말로** 설명. 적분식은 없음 | 간접 | 유지 (수학적 동치). 교사가 쓰는 정의와 맞출지(backlog A7) 결정 |
| P06-3 | c06-l1 `concepts[4]` 끝, `objectives[2]` | Gini from grouped (quintile) data understates inequality. | worldbank-gini-index | 페이지는 "grouped data 로 추정" 만 말하고 과소추정은 말하지 않음 | 뒷받침 없음 | 표준 결과로 유지하되 "within-group differences are ignored" 같은 이유 문장 유지 확인 |
| P06-4 | c06-l3 `concepts[0]` "Absolute and relative poverty lines" | A relative line moves with typical incomes, e.g., half of the median income. | openstax-pe3-15-1, worldbank-measuring-poverty | 15.1: "absolute/relative" 용어 없음, "Any poverty line will be somewhat arbitrary" 와 나라별 차이만. World Bank: 절대(PPP) 빈곤선만, 상대 빈곤선 언급 없음 | 뒷받침 없음 | **추가 출처 확인함:** Eurostat Glossary "At-risk-of-poverty rate" (https://ec.europa.eu/eurostat/statistics-explained/index.php?title=Glossary:At-risk-of-poverty_rate) — 기준선 = 국가 중위 등가가처분소득의 **60%**, "does not measure wealth or poverty, but low income in comparison to other residents". 레슨의 예 "half of the median" 은 OECD 기준(50%)인데 OECD 페이지는 403 → 예를 "60% (EU)" 로 바꾸거나 "for example, 50% or 60% of the median" 으로 쓰고 Eurostat 추가 |
| P06-5 | c06-l3 `concepts[1]` "Poverty rate and poverty gap" | Poverty gap = total money needed to raise everyone below the line up to it. | openstax-pe3-15-1 | 빈곤율 정의는 15.1 에 있음. 빈곤 갭은 15.1·World Bank 모두 없음 | 뒷받침 없음 (빈곤 갭 부분) | 빈곤 갭을 표준 정의로 유지할지 결정. 확인된 대체 출처 없음 |
| P06-6 | c06-l2 `concepts[1]` "Marginal vs. average tax rate" | Average rate = total tax ÷ total income; bracket logic. | openstax-pe3-30-2 | 30.2: 한계세율은 있음(괄호 설명이 다소 느슨), **평균세율 정의 없음**. 15.5 는 "effective income tax = total taxes paid divided by total income" 을 정의 | 간접 | `openstax-pe3-15-5` 를 이 개념의 source_ids 에 추가 검토 (같은 개념을 "effective" 라는 이름으로 정의) |
| P06-7 | c06-l2 `sdg_case.paragraphs[1]` (Country F) | A sales tax "takes a larger share of income from low-income households". | openstax-pe3-30-2, openstax-pe3-15-5 | 30.2 는 판매세를 주요 지방 세원으로만 언급, 역진성 분류 없음. 15.5 도 없음 | 뒷받침 없음 | 가상 상황의 전제로 명시("In this hypothetical…")하거나 표준 설명으로 유지. 확인된 대체 출처 없음 |
| P06-8 | c06-l2 `concepts[5]` "The equity-efficiency trade-off" | Redistribution may weaken incentives; size debated; some policies raise both. | openstax-pe3-15-5, openstax-pe3-15-2 | 15.5: 과도한 재분배가 근로·창업 의욕을 꺾을 수 있다 + 그 견해가 "may be too pessimistic", 함께 오르는 사례 | 직접 | 유지 (균형 서술 확인됨) |
| P06-9 | c06-l2 `concepts[2]` "Transfer payments: cash and in-kind" | Cash vs in-kind classification. | openstax-pe3-15-3, openstax-pe3-15-5 | 15.3 은 TANF·EITC·SNAP·Medicaid·주거·LIHEAP 를 설명, 15.5 는 현금/현물 구분 없음 | 간접 | 유지 (분류는 표준 용어) |
| P06-10 | c06-l3 `concepts[3]` "Poverty trap and effective marginal tax rate" | Share of an extra dollar lost = EMTR; near 100% → poverty trap. | openstax-pe3-15-2, openstax-pe3-15-3 | 15.2: $1 벌면 $1 감액 → "no net gain", 50센트 감액 대안. "effective marginal tax rate" 용어는 없음 | 간접 | 유지 |
| P06-11 | c06-l3 `concepts[4]` "Targeting vs. universality" | Targeted vs universal trade-offs (take-up, stigma, cost). | openstax-pe3-15-3, openstax-pe3-15-2 | 저자 기록상 AI 확장. 이번 재확인에서 이 구분을 따로 찾지 않음 | 간접 (저자 기록) | 사람이 균형성 확인 |
| P06-12 | c06-l2 `real_world_examples[0]` "Income, payroll, and capped taxes" | Federal income tax progressive; capped payroll tax regressive above the cap. | openstax-pe3-30-2 | 30.2 에 그대로 있음 | 직접 | 유지 |
| P06-13 | c06-l1 `real_world_examples[2]` | Wealth is more unequal than income; inheritance taxes. | openstax-pe3-15-5 | 15.5: 소득 차이가 누적되어 부가 더 불평등, 상속세(2022 기준 면제 한도) | 직접 | 유지 |
| P06-14 | c06-l3 `real_world_examples[1]` "International poverty lines" | Global lines derived from national lines of low-income countries; PPPs. | worldbank-measuring-poverty | 일치. 현재 값은 $3.00/$4.20/$8.30 (2021 PPP, 2025-06 개정) — 레슨은 수치를 쓰지 않음 | 직접 | 유지 (수치 쓰지 않는 원칙 유지) |

### 2.3 c07 — 금융 규정·미국 관할 특정 규칙

**횡단 문제:** c07 레슨 3개 전체에서 "rules differ by country / jurisdiction" 류의 문장을 찾지 못했다 (`countr`, `jurisdiction` 검색 결과는 가상 국가 이름뿐). backlog A8 은 "국가마다 다름 문장 확인" 을 전제로 하므로, 사람 검토 때 **이 문장이 실제로 없다는 점**을 먼저 확인하고 추가 여부를 결정해야 한다.

| # | 위치 | 주장 (요약) | 인용 출처 | 재확인 | 판정 | 제안 |
|---|---|---|---|---|---|---|
| P07-1 | c07-l2 `real_world_examples[0]` "Where households keep their savings" | In the U.S., FDIC insures deposits up to a limit per depositor, per bank, per ownership category; stocks/bonds/funds/crypto not covered. | fdic-deposit-insurance, openstax-pe3-17-2 | FDIC: $250,000 per depositor, per ownership category, per insured bank; 주식·채권·펀드·연금·암호자산 등 비보호 | 직접 | 유지. 미국 사례임을 명시한 점 OK. 다른 나라 예금보험도 한도가 있다는 일반 문장 추가 검토 |
| P07-2 | c07-l2 `real_world_examples[1]` ¶0 첫 문장, `levels.intermediate.sections[2]` ¶1 | U.S. rules require banks to state APY in a standard way reflecting rate and compounding. | cfpb-reg-dd-apy | Regulation DD Appendix A: 일수 기반 APY 식 | 직접 | 유지. 공개 직전 규정 재확인 (backlog A8) |
| P07-3 | c07-l2 `real_world_examples[1]` ¶0 | For mortgages, APR includes certain fees. | cfpb-mortgage-apr | 이자율 + points + 중개 수수료 + 기타 비용 | 직접 | 유지 |
| P07-4 | c07-l2 `real_world_examples[1]` ¶0 끝 | Credit card statements generally must show payoff time at minimum payment; paying more = less interest. | cfpb-minimum-payment-box | 발급사는 최소 결제 시 상환 기간과 36개월 상환 월액을 보여야 함; 더 내면 이자 감소 | 직접 | 유지 |
| P07-5 | c07-l3 `real_world_examples[1]` "How regulators describe scams" | FTC four signs: impersonation, problem/prize, pressure, unusual payment. | ftc-avoid-scam | 4가지 신호 그대로 | 직접 | 유지. 목록 구조가 같으므로 5장 표현 점검 권장 |
| P07-6 | c07-l1 `concepts[3]` "Budget and budgeting methods" | Zero-based budget; 50/30/20 guideline. | cfpb-pay-stub-tool, openstax-pe3-2-1 | pay-stub PDF 는 받았으나 본문 추출 실패(내용 미확인). 2.1 은 예산 제약·기회비용만 | 뒷받침 없음 | "examples, not rules" 표기 유지 확인. 일반 관행으로 둘지 결정 |
| P07-7 | c07-l1 `concepts[4]` "Financial goals (SMART framing)" | SMART goals. | cfpb-emergency-fund-guide | CFPB: 구체적·달성 가능한 목표 설정 권장, SMART 용어 없음 | 간접 | 유지 또는 SMART 를 "a common framing" 으로 표시 |
| P07-8 | c07-l3 `levels.intermediate.sections[1]` ¶0 | "past returns do not guarantee future returns" | openstax-pe3-17-2, 17-3 | 17.2 에 이 문구 없음. 17.3: 주가는 "random walk with a trend", 운용 펀드 절반~3분의 2 가 시장 평균 하회 | 간접 | 교육적 주의 문구로 유지 |
| P07-9 | c07-l2 `concepts[3]` "APR vs. APY", `levels.intermediate.summary` | APY = (1 + APR/n)^n − 1. | cfpb-reg-dd-apy | Reg DD 는 일수 기반 식만 (365 일 기준이면 같은 결과) | 간접 | 유지 (수학적 동치) |
| P07-10 | c07-l2 `concepts[5]` "The cost of borrowing" 등 APR 일반화 | APR may include some fees depending on loan type and rules. | cfpb-mortgage-apr, cfpb-credit-card-apr | 주택담보대출 페이지만 수수료 포함을 말함. 신용카드 APR 페이지는 수수료 포함 여부를 말하지 않음 | 간접 | 현재 헤지("depending on…") 유지 |
| P07-11 | c07-l2 `levels.intermediate.sections[0]` "Saving, liquidity, and the emergency fund" | Emergency fund size: "several months of essential expenses" as a rule of thumb. | cfpb-emergency-fund-guide | CFPB 는 개월 수를 말하지 않고 "depends on your situation" | 뒷받침 없음 | 레슨의 "rule of thumb… depends on your situation" 헤지 유지 확인 |
| P07-12 | c07-l3 `concepts[6]` "Mobile money…", `real_world_examples[2]` | Financial inclusion = access to affordable payments/savings/credit/insurance; mobile money; digital finance risks. | worldbank-financial-inclusion, worldbank-global-findex | World Bank: 공식 정의 없음(접근성 설명), SDG 언급 없음, 모바일 머니 계정 수(2020) 언급, 약탈적 대출 등 위험 명시 | 간접 (정의) / 직접 (위험·모바일 머니) | 유지. SDG 연결은 UN 페이지 근거로만 |

### 2.4 c08 — 무역 정책·관세·환율 효과

| # | 위치 | 주장 (요약) | 인용 출처 | 재확인 | 판정 | 제안 |
|---|---|---|---|---|---|---|
| P08-1 | c08-l1 `levels.advanced.sections[2]` "Tariff welfare analysis" | Small-country tariff: CS loss, PS gain, tariff revenue, two deadweight-loss triangles. | openstax-pe3-34-1 | 34.1: 소비자 손실 > 생산자 이득 → 사회적 잉여 감소 (설탕 사례). "deadweight loss"·"tariff revenue" 용어 없음 | 간접 | 표준 분석으로 유지 |
| P08-2 | c08-l1 `levels.advanced.sections[3]` "Compensation and adjustment" ¶0 | Winners could in principle compensate losers. | openstax-pe3-34-5 | 34.5 는 이득이 불균등하고 패자를 고려해야 한다고만 함. 보상 원리 없음 | 뒷받침 없음 | 표준 후생경제학 설명으로 유지 ("in principle" 헤지 있음) |
| P08-3 | c08-l1 `sdg_case.options[0].costs[0]` | "retraining does not always lead to jobs with similar pay" | (사례 출처) 34.5 등 | 34.5 는 재교육 지원을 권고만 하고 한계는 말하지 않음 | 뒷받침 없음 | 균형을 위한 일반 서술로 유지할지 결정. 확인된 출처 없음 |
| P08-4 | c08-l1 `concepts[4]` "Who gains and who loses from trade" | Trade raises total income but hurts some groups; adjustment costs; temporary support. | openstax-pe3-34-2, 34-5 | 34.5: "temporary support and assistance", 재교육 지원 | 직접 | 유지 |
| P08-5 | c08-l1 `real_world_examples[1]` "Protection as an indirect subsidy" | Consumers pay more; losers include consumers, foreign exporters, input-using industries. | openstax-pe3-34-1 | 34.1 에 세 집단 모두 있음 | 직접 | 유지 |
| P08-6 | c08-l2 `concepts[4]` "Trade balance", `levels.advanced.sections[2]` "Elasticities, timing, and the trade balance" | Depreciation tends to raise exports/lower imports; effect depends on elasticities and time. | openstax-pe3-29-3, openstax-pe3-5-1 | 29.3: 약한 통화가 수출을 촉진한다는 말은 있으나 수입·무역수지·탄력성·시차는 없음 | 간접 | 현재 "tendencies, not predictions" 헤지 유지 |
| P08-7 | c08-l2 `real_world_examples[1]` "Why sharp currency moves can be risky" | Large swings in exporter profits; banks borrowing in foreign currency. | openstax-pe3-29-3, 29-2 | 29.3: 태국 은행 사례, 수출 기업 손익 급변 | 직접 | 유지 |
| P08-8 | c08-l3 `concepts[3]` "Resilience and its costs", `objectives[1]`, `levels.intermediate.sections[1]` | Diversifying suppliers or holding inventory improves resilience but costs money in normal times. | openstax-pe3-33-3 | 33.3 은 회복력·교란·다변화·재고를 **다루지 않음** | 뒷받침 없음 | **대체 출처 확인함:** IMF F&D "The Stretch of Supply Chains" (Cerdeiro & Hansen, 2022-06-02), https://www.imf.org/en/Publications/fandd/issues/2022/06/the-stretch-of-supply-chains-B2B — 공급처 다변화·과잉 재고를 "insurance strategies that entail costs" 로 설명. 이 개념의 source_ids 에 추가하고 33.3 은 가치사슬 부분에만 남기는 안 |
| P08-9 | c08-l3 `concepts[1]` "Value added" | Value added at all stages sums to the final price. | openstax-pe3-33-3 | 33.3 에 부가가치 측정 없음 | 뒷받침 없음 (인용 출처 기준) | c04-l1 이 같은 설명(밀·밀가루·빵)을 OpenStax 19.1 에 연결해 씀. 19.1 이 부가가치 합을 말하는지는 이번에 확인하지 않았으므로 사람이 19.1 을 열어 확인 후 연결 결정 |
| P08-10 | c08-l3 `real_world_examples[0]` "Splitting up the value chain" | Production split into stages across countries; trade in components; smartphone example. | openstax-pe3-33-3, 33-4 | 33.3: 가치사슬 분할, 부품 무역, 아이폰 예 (레슨은 "a smartphone" 으로 일반화) | 직접 | 유지 |
| P08-11 | c08-l3 `real_world_examples[1]` "Debates about standards and trade" | Standards can become hidden protectionism. | openstax-pe3-34-2, 34-3 | 34.3: 반덤핑이 "a cover story" 가 될 수 있다, 국가안보 논거가 핑계가 됨, 환경 "race to the bottom". 34.3 은 노동 기준을 수입 제한 논거로 다루지 않음 | 간접 | 유지 |

### 2.5 c09 — 캡스톤 연구 방법 (이중차분 · 편익-비용 · 출처 평가)

| # | 위치 | 주장 (요약) | 인용 출처 | 재확인 | 판정 | 제안 |
|---|---|---|---|---|---|---|
| P09-1 | c09-l2 `levels.advanced.sections[1]` "Counterfactuals, selection bias, and difference-in-differences" ¶0 | Counterfactual, selection bias, random assignment removes selection bias. | jpal-intro-evaluations | J-PAL: Raskin 사례로 반사실, "selection problem", 무작위 배정, 사전-사후 비교 | 직접 | 유지 |
| P09-2 | 같은 섹션 ¶1 | DiD = (after − before) treated − (after − before) comparison; relies on parallel trends. | jpal-intro-evaluations 등 | J-PAL 소개 페이지에 이중차분·평행 추세 **없음** | 뒷받침 없음 | 대체 출처 시도: J-PAL `resource/impact-evaluation-methods` → **404**, World Bank "Impact Evaluation in Practice" OKR PDF → **403**. **확인된 대체 출처 없음.** 표준 계량 방법으로 유지하거나 사람이 열리는 출처(예: World Bank OKR 의 같은 책)를 직접 열어 연결 |
| P09-3 | c09-l2 `worked_examples[3]` "Before-and-after vs. a comparison group" | 8 − 5 = 3 percentage points. | (레슨 전체) | 산술 예. P09-2 에 종속 | 뒷받침 없음 (방법) | P09-2 와 함께 결정 |
| P09-4 | c09-l2 `levels.advanced.sections[2]` "Cost-effectiveness, benefit–cost ratios, …" ¶0 앞부분 | CE ratio = C ÷ ΔY (or ΔY per $100); multi-year costs discounted. | jpal-cea | J-PAL CEA: 비용 대비 효과 비율, US$100 당 효과로 보고, 다년 비용 10% 할인 | 직접 | 유지 |
| P09-5 | 같은 섹션 뒷부분 | Benefit–cost ratio vs net benefit ranking ("ratio if budget divisible, net benefit if mutually exclusive"); distribution weights. | jpal-cea, openstax-pe3-12-4 | J-PAL CEA: 편익-비용 분석·비율·순편익 **없음**. 12.4: 청정대기법 비용 약 $5,000억 vs 편익 중간값 $22조(약 44배), 한계편익·한계비용 분석은 있으나 "benefit-cost ratio"·"net benefits"·할인 용어 없음 | 뒷받침 없음 (순위 규칙) / 간접 (편익·비용 비교) | 대체 출처 시도: 호주 ATAP CBA 지침(시간 초과 2회), NZ Treasury CBA guide(403), UQ Pressbooks Social CBA(403), Queensland TMR PDF(읽을 수 있는 본문 없음). **확인된 대체 출처 없음.** 규칙 문장을 "a common guideline" 으로 표시 |
| P09-6 | c09-l3 `concepts[3]` "Costs over time: real values and present value" | Real value = nominal ÷ price index; PV = Σ Cₜ ÷ (1 + r)ᵗ. | openstax-pe3-19-2, 17-3, jpal-cea | 19.2: 디플레이터로 실질화(직접). 17.3: 연복리 미래가치 식만. J-PAL: 할인율 사용. PV 식 자체는 없음 | 간접 | 유지 (복리식의 역산) |
| P09-7 | c09-l2 출처 평가 체크리스트 (중급) | Authority, purpose, publication, relevance, date, documentation; "conflict of interest". | berkeley-evaluating-resources | 6가지 기준 일치, 후원·경제적 이해를 물음. "conflict of interest" 용어 없음 | 직접 (기준) / 간접 (용어) | 유지. 목록 구조가 같아 5장 표현 점검 권장 |
| P09-8 | c09-l2 1차/2차 자료 | Primary = firsthand; secondary = analysis of primary. | uw-primary-secondary | UW 가이드 정의 일치 (3차 자료 정의는 없음) | 직접 | 유지 |
| P09-9 | c09-l3 투입→활동→산출→성과 사슬, 실행 위험 q × ΔY, 산출 vs 성과 지표 | Logic-model chain. | (없음) | J-PAL 소개 페이지는 "theory of change" 만 언급, 투입-활동-산출-성과 틀은 없음 | 뒷받침 없음 | 일반 정책평가 용어로 유지하거나 J-PAL 의 theory of change 용어로 연결 |
| P09-10 | c09-l3 루브릭 자기평가 안내 ("if unsure, pick the lower level and note why") | App guidance. | (없음) | 외부 출처 대상 아님 (앱 동작 `weighted_summary` 근거) | 해당 없음 | 캡스톤 루브릭 승인(A4)과 함께 판단 |

### 2.6 c04 — 출처가 직접 뒷받침하지 않는 7가지 설명

| # | 위치 | 주장 (요약) | 인용 출처 | 재확인 | 판정 | 제안 |
|---|---|---|---|---|---|---|
| P04-1 | c04-l2 `concepts[5]` "Compound growth and the rule of 70", `levels.*` "Compounding and the accuracy of the rule of 70" | Doubling time ≈ 70 ÷ growth rate (%). | openstax-pe3-20-2 | 20.2: 복리 성장식 (GDP × (1 + g)^years) 있음, **70의 법칙·doubling time 없음** | 뒷받침 없음 (규칙) / 직접 (복리식) | 레슨이 ln 2 ÷ ln(1+g) 로 유도하므로 수학적 근사로 유지. 공신력 있는 열리는 출처는 찾지 못함(검색 결과가 상업 사이트뿐이라 제안하지 않음) |
| P04-2 | c04-l1 `concepts[3]`, `worked_examples[3]`, `key_takeaways[2]` | Percentage points vs percent change. | openstax-pe3-19-2 | 19.2 에 "percentage points" 용어 없음 (성장률 계산은 있음) | 뒷받침 없음 | 산술 정의로 유지 |
| P04-3 | c04-l1 `concepts[6]` "Correlation vs. causation", `levels.intermediate.sections[4]`, `levels.advanced.sections[3]` | Correlation ≠ causation; reverse causation or a third factor. | openstax-is2e-12-3, openstax-pe3-19-5 | 통계 12.3: "correlation does not imply causation", x→y 또는 y→x 를 보여 주지 않는다(역인과는 간접), 제3 변수 언급 없음. 19.5: 1인당 GDP 와 생활 개선이 함께 나타남, 인과 논의 없음 | 간접 | 유지 |
| P04-4 | c04-l2 `concepts[6]`, `levels.intermediate.sections[3]` ¶1, `levels.advanced.sections[3]` "Measuring decoupling" | Relative vs absolute decoupling; emissions intensity identity. | un-sdg-8 | SDG 8.4 "decoupling growth from environmental degradation" 확인. 상대/절대 구분 없음 | 간접 | 유지. UNEP 출처는 이전에 403 |
| P04-5 | c04-l2 `levels.advanced.sections[1]` "An aggregate production function" | y = A·k^α·h^(1−α). | openstax-pe3-20-3 | 20.3: 총생산함수·물적/인적 자본·기술·성장회계를 말로 설명, 식 없음 | 간접 | "A common form" 표기 유지 |
| P04-6 | c04-l3 `levels.advanced.sections[3]` "Expected vs. unexpected inflation" ¶1 끝 ("At very high rates…") | People try hard to avoid holding cash at very high inflation. | openstax-pe3-22-4, imf-fd-inflation-basics | 22.4: 재분배·가격 신호 흐림·이스라엘·독일 초인플레이션, 현금 회피 **없음**. IMF F&D: 현금 회피 없음 | 뒷받침 없음 | 문장 삭제 또는 표준 설명으로 유지 결정 |
| P04-7 | c04-l3 `sdg_case.options[2].costs[1]` | "Bringing inflation down can slow spending and hiring for a while." | un-sdg-8, openstax-pe3-22-4, ecb-monetary-policy-intro | 22.4·ECB 모두 없음 (ECB 는 "possible side effects" 만). **이미 레지스트리에 있는 IMF F&D "Inflation: Prices on the Rise"** 가 긴축(금리 인상)으로 총수요를 줄이고 인플레이션을 낮추려 경제활동을 한동안 낮게 유지할 수 있다고 설명 | 뒷받침 없음 (현재 인용) | 이 선택지의 source_ids 에 `imf-fd-inflation-basics` 추가 (오늘 열어 확인) |

### 2.7 c03 — 탄소세 프레이밍

| # | 위치 | 주장 (요약) | 인용 출처 | 재확인 | 판정 | 제안 |
|---|---|---|---|---|---|---|
| P03-1 | c03-l3 `concepts[2]` "Carbon tax" | A pollution tax on greenhouse gases; with ETS one of main forms of carbon pricing; revenue can support households or clean investment. | imf-climate-mitigation, openstax-pe3-12-3 | IMF: 탄소세와 배출권거래제를 "pricing instruments" 로 묶고 가장 효율적 수단이라 함, 세수를 저소득 가계·친환경 전환에 사용. 공식 정의 없음. 12.3: 오염세 일반, "carbon tax" 용어 없음 | 간접 (정의) / 직접 (가격 수단·세수 사용) | 유지 |
| P03-2 | c03-l3 `real_world_examples[2]` "Carbon pricing and the use of revenue" | IMF sees carbon pricing as central; revenue use for acceptability. | imf-climate-mitigation | 일치 (revenue recycling, targeted compensation) | 직접 | 유지 |
| P03-3 | c03-l3 `levels.advanced.sections[2]` "The optimal tax rate: the Pigouvian tax" | t = md maximizes welfare (Pigouvian tax). | openstax-pe3-12-1, 12-3 | 12.3 에 "Pigouvian" 용어 없음 (오염세와 같은 개념) | 간접 | 표준 용어로 유지 |
| P03-4 | c03-l3 `sdg_case.options[0].name` | "carbon dividend, the standard economics term" | un-sdg-7, un-sdg-13 | UN 페이지에 없는 용어 (레슨이 스스로 표준 용어라고 밝힘) | 간접 | 유지 |
| P03-5 | c03-l3 `worked_examples[0–2]`, `graphs[0]`, `levels.*` 시뮬레이션 안내 | $6 tax per unit; 1 kg per unit → 4 kg drop. | (가상 예) | 이 단위면 톤당 약 $6,000. IMF 페이지는 대형 배출국에 2030년까지 **톤당 $75** 로 오르는 탄소세가 필요하다고 함. 커밋된 레슨(HEAD `bd3a872`)에는 "실제 탄소 가격과 비교하지 말 것" 류 문장이 **없음**. 단, 이 문서를 쓰는 동안 작업 트리의 `c03-l3.json` 이 (다른 AI 작업으로, 미커밋) content_version 3 으로 바뀌어 B1 A안 문구("a teaching value in the model units, not a real carbon price…" 등)가 시뮬레이션 안내 3곳·그래프 캡션·SDG 사례에 추가됨 | 해당 없음 (가상 수치) — 표기 필요 | 작업 트리의 A안 문구를 사람이 검토·승인하면 해결. 승인 전까지는 미해결로 취급 |
| P03-6 | c03-l2 `levels.intermediate.sections[1]` 등 (free riding + tragedy of the commons in climate) | Climate action shows both free riding and the tragedy of the commons. | openstax-pe3-12-5, 13-3 | 13.3 에 무임승차 개념 있음. 12.5 는 이번에 다시 열지 않음 (저자 기록: 12.5 는 "free rider" 를 쓰지 않음) | 간접 | 유지 |

### 2.8 우선 검토 판정 집계

| 강좌 | 직접 | 간접 | 뒷받침 없음 | 페이지 열리지 않음 | 해당 없음 | 계 |
|---|---|---|---|---|---|---|
| c05 | 6 | 2 | 2 | 0 | 0 | 10 |
| c06 | 5 | 5 | 4 | 0 | 0 | 14 |
| c07 | 5 | 5 | 2 | 0 | 0 | 12 |
| c08 | 4 | 3 | 4 | 0 | 0 | 11 |
| c09 | 4 | 1 | 4 | 0 | 1 | 10 |
| c04 | 0 | 3 | 4 | 0 | 0 | 7 |
| c03 | 1 | 4 | 0 | 0 | 1 | 6 |
| **계** | **25** | **23** | **20** | **0** | **2** | **70** |

판정이 "직접/간접" 처럼 둘로 나뉜 행은 **주장의 핵심 부분** 기준 하나로 셌다 (P07-12 간접, P09-5 뒷받침 없음, P09-7 직접, P03-1 간접, P04-1 뒷받침 없음).
인용 출처 페이지가 오늘 열리지 않은 항목은 없다 (CFPB·IMF·FTC 는 curl 에서는 403/404 였지만 WebFetch 로는 열렸다 — 4장 참고).

---

## 3. 전체 출처 표 (발행처별)

열 설명: **레슨 (인용 수)** = `lesson_ids` 와 레슨 JSON 의 `source_ids` 등장 횟수(개념·예시·SDG 사례·레슨 전체 포함). **뒷받침 개념** = sources.json `concepts` (앞 6개).
**AI 확인** = sources.json `verification` (모두 AI, 사람 확인 아님). **재확인** = 2026-11-14 AI 재확인: "WebFetch OK" 는 페이지 본문을 열어 본 것,
"curl 200 (본문 미확인)" 은 HTTP 상태만 본 것이다. **OpenStax 는 단일 페이지 앱이라 curl 200 이 해당 절의 존재를 보장하지 않는다.**

### OpenStax — Principles of Economics 3e (55개)

라이선스·재사용: CC BY-NC-SA 4.0 + OpenStax의 LLM 학습·수집 금지 고지(사전 서면 허락 필요). 링크·출처 표기만, 본문 복사 금지.

| id | 제목 (URL) | 레슨 (인용 수) | 뒷받침 개념 | AI 확인 (checked_at · method 요지) | 2026-11-14 재확인 | 문제 |
|---|---|---|---|---|---|---|
| `openstax-pe3-3-1` | [3.1 Demand, Supply, and Equilibrium in Markets for Goods and Services](https://openstax.org/books/principles-economics-3e/pages/3-1-demand-supply-and-equilibrium-in-markets-for-goods-and-services) | c02-l1, c02-l2 (9) | demand, quantity_demanded, law_of_demand, supply, law_of_supply, equilibrium … | verified (AI) 2026-11-13 · Rechecked 2026-11-13: title, authors, CC BY-NC-SA, and the no-LLM-training notice are present; defines demand/quantity demanded, supply/quantity supplied, the laws of … | WebFetch OK | — |
| `openstax-pe3-3-2` | [3.2 Shifts in Demand and Supply for Goods and Services](https://openstax.org/books/principles-economics-3e/pages/3-2-shifts-in-demand-and-supply-for-goods-and-services) | c02-l1 (5) | demand_shifters, supply_shifters, movement_vs_shift | verified (AI) 2026-11-13 · Rechecked 2026-11-13: lists factors that shift demand (income, normal/inferior goods, tastes, population, prices of related goods, expectations) and factors that shift… | curl 200 (본문 미확인) | — |
| `openstax-pe3-3-3` | [3.3 Changes in Equilibrium Price and Quantity: The Four-Step Process](https://openstax.org/books/principles-economics-3e/pages/3-3-changes-in-equilibrium-price-and-quantity-the-four-step-process) | c02-l2 (2) | equilibrium, four_step | verified (AI) 2026-11-13 · Rechecked 2026-11-13: explains the four-step analysis and the case where demand and supply shift together (only the price or the quantity change can be determined). | curl 200 (본문 미확인) | — |
| `openstax-pe3-3-4` | [3.4 Price Ceilings and Price Floors](https://openstax.org/books/principles-economics-3e/pages/3-4-price-ceilings-and-price-floors) | c02-l2, c05-l3 (8) | price_ceiling, price_floor, shortage, surplus | verified (AI) 2026-11-13 · Rechecked 2026-11-13: explains price ceiling (rent control) → shortage and price floor (farm price supports) → surplus. Deadweight loss is not in this section → cite 3… | WebFetch OK | 근접 의역: c02-l2 price ceiling 정의가 원문과 8단어 연속 일치 |
| `openstax-pe3-5-1` | [5.1 Price Elasticity of Demand and Price Elasticity of Supply](https://openstax.org/books/principles-economics-3e/pages/5-1-price-elasticity-of-demand-and-price-elasticity-of-supply) | c02-l3, c08-l2, c09-l1 (8) | price_elasticity_demand, midpoint_method, elasticity_categories, price_elasticity_supply | verified (AI) 2026-11-13 · Rechecked 2026-11-13: defines price elasticity of demand; covers elastic, inelastic, and unit elastic demand and the midpoint method. | WebFetch OK | — |
| `openstax-pe3-5-3` | [5.3 Elasticity and Pricing](https://openstax.org/books/principles-economics-3e/pages/5-3-elasticity-and-pricing) | c02-l3, c03-l3 (7) | total_revenue, food_demand_inelastic, tax_incidence | verified (AI) 2026-11-13 · Rechecked 2026-11-13: explains elasticity and total revenue, sharp price drops when farm output surges, and that the less elastic side bears more of a tax (tax inciden… | curl 200 (본문 미확인) | — |
| `openstax-pe3-3-5` | [3.5 Demand, Supply, and Efficiency](https://openstax.org/books/principles-economics-3e/pages/3-5-demand-supply-and-efficiency) | c02-l2 (2) | consumer_surplus, producer_surplus, deadweight_loss | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it explains consumer, producer, and social (total) surplus, deadweight loss, and how price ceilings and price floors create d… | curl 200 (본문 미확인) | — |
| `openstax-pe3-1-1` | [1.1 What Is Economics, and Why Is It Important?](https://openstax.org/books/principles-economics-3e/pages/1-1-what-is-economics-and-why-is-it-important) | c01-l1, c09-l1 (8) | scarcity, economics, division_of_labor, specialization | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it explains the definition of economics (choice under scarcity), scarcity, and division of labor and specialization (Adam Smi… | WebFetch OK | — |
| `openstax-pe3-1-4` | [1.4 How To Organize Economies: An Overview of Economic Systems](https://openstax.org/books/principles-economics-3e/pages/1-4-how-to-organize-economies-an-overview-of-economic-systems) | c01-l1 (4) | traditional_economy, command_economy, market_economy, mixed_economy | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it explains traditional, command, market, and mixed economies (this section does not go into detail on how prices coordinate … | curl 200 (본문 미확인) | — |
| `openstax-pe3-2-1` | [2.1 How Individuals Make Choices Based on Their Budget Constraint](https://openstax.org/books/principles-economics-3e/pages/2-1-how-individuals-make-choices-based-on-their-budget-constraint) | c01-l1, c01-l2, c01-l3, c07-l1, c09-l1, c09-l3 (19) | budget_constraint, opportunity_cost, sunk_cost, marginal_analysis, utility | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it explains the budget constraint, opportunity cost, sunk cost, marginal analysis, and utility. c07 (2026-11-13, AI): reopene… | WebFetch OK | — |
| `openstax-pe3-2-2` | [2.2 The Production Possibilities Frontier and Social Choices](https://openstax.org/books/principles-economics-3e/pages/2-2-the-production-possibilities-frontier-and-social-choices) | c01-l2, c08-l1 (7) | production_possibilities_frontier, increasing_opportunity_cost, productive_efficiency, allocative_efficiency | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it explains the production possibilities frontier, slope = opportunity cost, increasing opportunity cost (the bowed-out shape… | curl 200 (본문 미확인) | — |
| `openstax-pe3-2-3` | [2.3 Confronting Objections to the Economic Approach](https://openstax.org/books/principles-economics-3e/pages/2-3-confronting-objections-to-the-economic-approach) | c01-l3 (4) | rationality, self_interest_and_values | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it covers the objection that people are not always rational, and explains that people are both self-interested and altruistic… | curl 200 (본문 미확인) | — |
| `openstax-pe3-12-1` | [12.1 The Economics of Pollution](https://openstax.org/books/principles-economics-3e/pages/12-1-the-economics-of-pollution) | c01-l3, c03-l1, c03-l3, c08-l3, c09-l1, c09-l2 (21) | externality, private_cost, social_cost | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it explains externalities (effects on third parties), private cost and social cost, and why goods that create pollution are o… | WebFetch OK | 근접 의역 경계: c03-l1 externality 정의 6단어 일치 |
| `openstax-pe3-12-2` | [12.2 Command-and-Control Regulation](https://openstax.org/books/principles-economics-3e/pages/12-2-command-and-control-regulation) | c03-l3 (3) | command_and_control | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it explains command-and-control regulation that sets allowable emissions or technology, the lack of incentive to cut beyond t… | curl 200 (본문 미확인) | — |
| `openstax-pe3-12-3` | [12.3 Market-Oriented Environmental Tools](https://openstax.org/books/principles-economics-3e/pages/12-3-market-oriented-environmental-tools) | c03-l3, c09-l1, c09-l2, c09-l3 (14) | pollution_charge, marketable_permits, cap_and_trade, property_rights | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it explains pollution taxes (firms cut emissions until cutting costs more than the tax), emissions trading (cap-and-trade; su… | WebFetch OK | carbon tax·Pigouvian 용어 없음 |
| `openstax-pe3-12-5` | [12.5 International Environmental Issues](https://openstax.org/books/principles-economics-3e/pages/12-5-international-environmental-issues) | c03-l2 (2) | international_externality, climate_change | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it treats global warming and biodiversity as international externalities, explains why negotiation between countries with dif… | curl 200 (본문 미확인) | — |
| `openstax-pe3-13-1` | [13.1 Investments in Innovation](https://openstax.org/books/principles-economics-3e/pages/13-1-investments-in-innovation) | c03-l1 (5) | positive_externality, social_benefit | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it defines positive externalities (benefits to third parties), explains that social benefit exceeds private benefit so the ma… | curl 200 (본문 미확인) | — |
| `openstax-pe3-13-3` | [13.3 Public Goods](https://openstax.org/books/principles-economics-3e/pages/13-3-public-goods) | c03-l2, c09-l1 (13) | public_good, nonexcludable, nonrival, free_rider, common_resources, tragedy_of_the_commons | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it covers public goods (non-excludable, non-rival), the free-rider problem (a prisoner's dilemma example), provision through … | WebFetch OK | — |
| `openstax-pe3-4-1` | [4.1 Demand and Supply at Work in Labor Markets](https://openstax.org/books/principles-economics-3e/pages/4-1-demand-and-supply-at-work-in-labor-markets) | c05-l1, c05-l3 (15) | labor_market, derived_demand, labor_supply, labor_equilibrium, labor_shifts, minimum_wage … | verified (AI) 2026-11-13 · Opened 2026-11-13: title, authors, CC BY-NC-SA, and the no-LLM-training notice are present. Covers labor demand as derived from demand for the product, upward-sloping … | WebFetch OK | 수요독점·고용주 시장지배력 언급 없음 |
| `openstax-pe3-14-1` | [14.1 The Theory of Labor Markets](https://openstax.org/books/principles-economics-3e/pages/14-1-the-theory-of-labor-markets) | c05-l1 (4) | derived_demand, marginal_product, labor_equilibrium | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Uses the term 'derived demand'; defines marginal product of labor (declining with fixed capital) and the value of t… | curl 200 (본문 미확인) | — |
| `openstax-pe3-14-2` | [14.2 Wages and Employment in an Imperfectly Competitive Labor Market](https://openstax.org/books/principles-economics-3e/pages/14-2-wages-and-employment-in-an-imperfectly-competitive-labor-market) | c05-l3 (3) | monopsony | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Defines monopsony (one employer with market power, e.g. a single coal company in a town); the monopsonist hires whe… | WebFetch OK | 수요독점 하 최저임금 고용 증가 분석 없음 (c05-l3) |
| `openstax-pe3-15-3` | [15.3 The Safety Net](https://openstax.org/books/principles-economics-3e/pages/15-3-the-safety-net) | c05-l3, c06-l2, c06-l3 (12) | earned_income_support, transfer_payments, social_protection, poverty_trap, targeting_universality | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Describes the Earned Income Tax Credit (delivered through the tax system, rises with earnings, levels off, then pha… | WebFetch OK | — |
| `openstax-pe3-20-2` | [20.2 Labor Productivity and Economic Growth](https://openstax.org/books/principles-economics-3e/pages/20-2-labor-productivity-and-economic-growth) | c05-l2, c04-l2 (8) | productivity_human_capital | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Defines labor productivity as the value produced per unit of labor input (e.g., per hour worked); states that over … | WebFetch OK | 70의 법칙 없음 |
| `openstax-pe3-20-3` | [20.3 Components of Economic Growth](https://openstax.org/books/principles-economics-3e/pages/20-3-components-of-economic-growth) | c05-l2, c04-l2 (8) | productivity_human_capital | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Defines human capital as the skills and knowledge that make workers productive, built through education and trainin… | WebFetch OK | Cobb-Douglas 식 없음 |
| `openstax-pe3-21-1` | [21.1 How Economists Define and Compute Unemployment Rate](https://openstax.org/books/principles-economics-3e/pages/21-1-how-economists-define-and-compute-unemployment-rate) | c05-l2, c09-l1 (9) | labor_force, unemployed, not_in_labor_force, participation_rate, unemployment_rate | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Defines unemployed (no job, available, actively searched in the previous four weeks), employed, labor force, out of… | WebFetch OK | c05-l2 구조가 원문 순서와 거의 같음(6단어 일치는 없음) |
| `openstax-pe3-21-3` | [21.3 What Causes Changes in Unemployment over the Short Run](https://openstax.org/books/principles-economics-3e/pages/21-3-what-causes-changes-in-unemployment-over-the-short-run) | c05-l2 (3) | unemployment_types | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Defines cyclical unemployment (labor demand falls when firms expect a slowdown) and explains wages that are sticky … | curl 200 (본문 미확인) | — |
| `openstax-pe3-21-4` | [21.4 What Causes Changes in Unemployment over the Long Run](https://openstax.org/books/principles-economics-3e/pages/21-4-what-causes-changes-in-unemployment-over-the-long-run) | c05-l2, c05-l3 (6) | unemployment_types, active_labor_policy, minimum_wage_evidence | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Defines frictional and structural unemployment and the natural rate (rate when the economy is neither booming nor i… | WebFetch OK | — |
| `openstax-pe3-19-1` | [19.1 Measuring the Size of the Economy: Gross Domestic Product](https://openstax.org/books/principles-economics-3e/pages/19-1-measuring-the-size-of-the-economy-gross-domestic-product) | c04-l1 (4) | gdp, final_vs_intermediate | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it defines GDP as the value of all final goods and services produced within a country in a given year and explains that inter… | WebFetch OK | 근접 의역: c04-l1 GDP 정의 11단어 연속 일치 |
| `openstax-pe3-19-2` | [19.2 Adjusting Nominal Values to Real Values](https://openstax.org/books/principles-economics-3e/pages/19-2-adjusting-nominal-values-to-real-values) | c04-l1, c09-l1, c09-l3 (8) | nominal_vs_real_gdp, gdp_deflator, growth_rate | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it distinguishes nominal from real GDP, defines the GDP deflator as a price index for all final goods and services, converts … | WebFetch OK | percentage points 용어 없음 |
| `openstax-pe3-19-4` | [19.4 Comparing GDP among Countries](https://openstax.org/books/principles-economics-3e/pages/19-4-comparing-gdp-among-countries) | c04-l1 (3) | gdp_per_capita | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it defines GDP per capita as GDP divided by population and says it gives only a rough idea of differences in living standards. | curl 200 (본문 미확인) | — |
| `openstax-pe3-19-5` | [19.5 How Well GDP Measures the Well-Being of Society](https://openstax.org/books/principles-economics-3e/pages/19-5-how-well-gdp-measures-the-well-being-of-society) | c04-l1 (5) | gdp_limits, gdp_per_capita | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it lists what GDP leaves out (leisure, household production, environmental quality, health and literacy outcomes, inequality,… | WebFetch OK | — |
| `openstax-pe3-22-1` | [22.1 Tracking Inflation](https://openstax.org/books/principles-economics-3e/pages/22-1-tracking-inflation) | c04-l3 (4) | price_index, inflation_rate, price_level | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it explains pricing a basket of goods, a price index with a base year set to 100, and the inflation rate as the percentage ch… | curl 200 (본문 미확인) | — |
| `openstax-pe3-22-2` | [22.2 How to Measure Changes in the Cost of Living](https://openstax.org/books/principles-economics-3e/pages/22-2-how-to-measure-changes-in-the-cost-of-living) | c04-l3 (3) | consumer_price_index, substitution_bias, quality_bias | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it covers the CPI as a fixed-basket measure and its substitution bias and quality/new-goods bias, and efforts to reduce them. | curl 200 (본문 미확인) | — |
| `openstax-pe3-22-4` | [22.4 The Confusion Over Inflation](https://openstax.org/books/principles-economics-3e/pages/22-4-the-confusion-over-inflation) | c04-l3, c07-l2, c07-l3 (12) | real_income, inflation_redistribution, price_stability | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it explains real vs. nominal values, how unexpected inflation helps fixed-rate borrowers and hurts lenders, losses for people… | WebFetch OK | 현금 보유 회피·디스인플레이션 비용 없음 |
| `openstax-pe3-28-1` | [28.1 The Federal Reserve Banking System and Central Banks](https://openstax.org/books/principles-economics-3e/pages/28-1-the-federal-reserve-banking-system-and-central-banks) | c04-l3 (3) | central_bank, monetary_policy | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it describes conducting monetary policy as a core central bank role, with goals of low unemployment and low inflation (the pa… | curl 200 (본문 미확인) | — |
| `openstax-pe3-15-1` | [15.1 Drawing the Poverty Line](https://openstax.org/books/principles-economics-3e/pages/15-1-drawing-the-poverty-line) | c06-l1, c06-l3 (6) | poverty_line, poverty_rate_gap, inequality_vs_poverty | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Defines poverty by a poverty line (income needed for a basic standard of living) and separates it from inequality (… | WebFetch OK | 절대/상대 빈곤, 빈곤 갭 없음 (c06-l3) |
| `openstax-pe3-15-2` | [15.2 The Poverty Trap](https://openstax.org/books/principles-economics-3e/pages/15-2-the-poverty-trap) | c06-l2, c06-l3 (7) | poverty_trap, equity_efficiency_tradeoff | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Explains that benefits reduced as earnings rise act like a tax on work and can leave little or no gain from working… | WebFetch OK | — |
| `openstax-pe3-15-4` | [15.4 Income Inequality: Measurement and Causes](https://openstax.org/books/principles-economics-3e/pages/15-4-income-inequality-measurement-and-causes) | c06-l1, c09-l1, c09-l2 (11) | quintile_distribution, lorenz_curve, inequality_vs_poverty, causes_of_inequality | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Describes income shares by quintile; the Lorenz curve (cumulative population share vs. cumulative income share, 45-… | WebFetch OK | — |
| `openstax-pe3-15-5` | [15.5 Government Policies to Reduce Income Inequality](https://openstax.org/books/principles-economics-3e/pages/15-5-government-policies-to-reduce-income-inequality) | c06-l1, c06-l2, c06-l3 (14) | redistribution, tax_progressivity, equality_vs_equity, equity_efficiency_tradeoff, economic_mobility, income_vs_wealth … | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Covers redistribution through transfer programs and progressive taxation; effective vs. statutory tax rates; the la… | WebFetch OK | 현금/현물 구분 없음 |
| `openstax-pe3-30-2` | [30.2 Taxation](https://openstax.org/books/principles-economics-3e/pages/30-2-taxation) | c06-l2, c06-l3, c09-l2, c09-l3 (13) | tax_progressivity, marginal_average_rate, public_finance | verified (AI) 2026-11-13 · Opened 2026-11-13: title and book metadata present. Defines progressive (rates rise with income; federal income tax example), proportional/flat (one fixed percentage; … | WebFetch OK | 평균세율 정의·판매세 역진성 없음 (c06-l2) |
| `openstax-pe3-17-1` | [17.1 How Businesses Raise Financial Capital](https://openstax.org/books/principles-economics-3e/pages/17-1-how-businesses-raise-financial-capital) | c07-l2, c07-l3 (4) | borrowing_cost, financial_risk_types | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): opened the page and confirmed it describes bank loans repaid with principal plus interest, bonds as contracts to repay with interest (example of … | curl 200 (본문 미확인) | — |
| `openstax-pe3-17-2` | [17.2 How Households Supply Financial Capital](https://openstax.org/books/principles-economics-3e/pages/17-2-how-households-supply-financial-capital) | c07-l2, c07-l3 (9) | saving_emergency_fund, risk_return, diversification, financial_risk_types, long_term_planning | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): opened the page and confirmed checking/savings accounts and CDs (early-withdrawal penalty), bank accounts as low risk, low return, high liquidity… | WebFetch OK | "과거 수익률≠미래" 문구 없음 |
| `openstax-pe3-17-3` | [17.3 How to Accumulate Personal Wealth](https://openstax.org/books/principles-economics-3e/pages/17-3-how-to-accumulate-personal-wealth) | c07-l2, c07-l3, c09-l1, c09-l3 (13) | simple_interest, compound_interest, real_return, risk_return, diversification, long_term_planning | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): opened the page and confirmed compound interest (interest on principal plus accumulated interest), the future value formula principal × (1 + rate… | WebFetch OK | n회 복리식 없음(연복리만) |
| `openstax-pe3-33-1` | [33.1 Absolute and Comparative Advantage](https://openstax.org/books/principles-economics-3e/pages/33-1-absolute-and-comparative-advantage) | c08-l1 (6) | absolute_advantage, comparative_advantage, gains_from_trade, terms_of_trade | verified (AI) 2026-11-13 · c08 (2026-11-13, AI): opened the page and confirmed definitions of absolute advantage (more output with the same resources) and comparative advantage (lower opportunit… | WebFetch OK | c08-l1 comparative advantage 정의 6단어 일치(표준 용어) |
| `openstax-pe3-33-2` | [33.2 What Happens When a Country Has an Absolute Advantage in All Goods](https://openstax.org/books/principles-economics-3e/pages/33-2-what-happens-when-a-country-has-an-absolute-advantage-in-all-goods) | c08-l1 (6) | absolute_advantage, comparative_advantage, terms_of_trade, gains_from_trade | verified (AI) 2026-11-13 · c08 (2026-11-13, AI): opened the page and confirmed that a country with an absolute advantage in all goods still gains by specializing in its comparative advantage, th… | curl 200 (본문 미확인) | — |
| `openstax-pe3-33-3` | [33.3 Intra-industry Trade between Similar Economies](https://openstax.org/books/principles-economics-3e/pages/33-3-intra-industry-trade-between-similar-economies) | c08-l3 (6) | global_value_chain, value_added, economies_of_scale, dynamic_comparative_advantage | verified (AI) 2026-11-13 · c08 (2026-11-13, AI): opened the page and confirmed intra-industry trade, splitting up the value chain into stages across firms and countries (trade in components, mad… | WebFetch OK | 회복력·재고·부가가치 측정 없음 → c08-l3 resilience 개념의 유일한 출처로 부적합 |
| `openstax-pe3-33-4` | [33.4 The Benefits of Reducing Barriers to International Trade](https://openstax.org/books/principles-economics-3e/pages/33-4-the-benefits-of-reducing-barriers-to-international-trade) | c08-l1, c08-l3 (6) | tariff, global_value_chain, gains_from_trade | verified (AI) 2026-11-13 · c08 (2026-11-13, AI): opened the page and confirmed that tariffs are taxes on imported goods, the WTO's role in negotiating lower barriers, unmeasured gains (variety, … | curl 200 (본문 미확인) | — |
| `openstax-pe3-34-1` | [34.1 Protectionism: An Indirect Subsidy from Consumers to Producers](https://openstax.org/books/principles-economics-3e/pages/34-1-protectionism-an-indirect-subsidy-from-consumers-to-producers) | c08-l1 (3) | tariff, import_quota, nontariff_barriers, protectionism | verified (AI) 2026-11-13 · c08 (2026-11-13, AI): opened the page and confirmed definitions of protectionism, tariffs, import quotas and nontariff barriers; a demand and supply analysis in which … | WebFetch OK | DWL·관세 수입 용어 없음 |
| `openstax-pe3-34-2` | [34.2 International Trade and Its Effects on Jobs, Wages, and Working Conditions](https://openstax.org/books/principles-economics-3e/pages/34-2-international-trade-and-its-effects-on-jobs-wages-and-working-conditions) | c08-l1, c08-l3 (6) | distribution_of_gains, jobs_and_trade, labor_standards | verified (AI) 2026-11-13 · c08 (2026-11-13, AI): opened the page and confirmed that protection reshuffles jobs between industries rather than creating them, that trade helps some workers and hur… | curl 200 (본문 미확인) | — |
| `openstax-pe3-34-3` | [34.3 Arguments in Support of Restricting Imports](https://openstax.org/books/principles-economics-3e/pages/34-3-arguments-in-support-of-restricting-imports) | c08-l3 (4) | infant_industry, anti_dumping, environment_and_trade, race_to_the_bottom | verified (AI) 2026-11-13 · c08 (2026-11-13, AI): opened the page and confirmed the textbook's assessment of arguments for restricting imports, including its view that the environmental race-to-t… | WebFetch OK | — |
| `openstax-pe3-34-5` | [34.5 The Tradeoffs of Trade Policy](https://openstax.org/books/principles-economics-3e/pages/34-5-the-tradeoffs-of-trade-policy) | c08-l1 (4) | distribution_of_gains, adjustment_assistance | verified (AI) 2026-11-13 · c08 (2026-11-13, AI): opened the page and confirmed that some workers and firms lose from trade, that gains are not shared equally and policy should consider those who… | WebFetch OK | 보상 원리·재교육 한계 없음 |
| `openstax-pe3-29-1` | [29.1 How the Foreign Exchange Market Works](https://openstax.org/books/principles-economics-3e/pages/29-1-how-the-foreign-exchange-market-works) | c08-l2 (7) | exchange_rate, appreciation_depreciation, export_import_prices, currency_winners_losers, forex_market | verified (AI) 2026-11-13 · c08 (2026-11-13, AI): opened the page and confirmed that exchange rates can be quoted in either direction (reciprocals), that a currency appreciates/strengthens when i… | curl 200 (본문 미확인) | — |
| `openstax-pe3-29-2` | [29.2 Demand and Supply Shifts in Foreign Exchange Markets](https://openstax.org/books/principles-economics-3e/pages/29-2-demand-and-supply-shifts-in-foreign-exchange-markets) | c08-l2 (3) | forex_market, purchasing_power_parity | verified (AI) 2026-11-13 · c08 (2026-11-13, AI): opened the page and confirmed that the exchange rate is set by demand and supply for a currency, that expectations (which can shift both curves a… | curl 200 (본문 미확인) | — |
| `openstax-pe3-29-3` | [29.3 Macroeconomic Effects of Exchange Rates](https://openstax.org/books/principles-economics-3e/pages/29-3-macroeconomic-effects-of-exchange-rates) | c08-l2 (6) | export_import_prices, currency_winners_losers, trade_balance | verified (AI) 2026-11-13 · c08 (2026-11-13, AI): opened the page and confirmed that exchange rates affect incentives to export and import, that sharp movements cause large swings in profits for … | WebFetch OK | 시차·탄력성(J-curve) 없음 |
| `openstax-pe3-12-4` | [12.4 The Benefits and Costs of U.S. Environmental Laws](https://openstax.org/books/principles-economics-3e/pages/12-4-the-benefits-and-costs-of-u-s-environmental-laws) | c09-l2, c09-l3 (6) | cost_effectiveness, uncertainty_justification, tradeoffs_implementation | verified (AI) 2026-11-14 · c09 (2026-11-14, AI): opened the page and confirmed: an EPA study estimated Clean Air Act benefits for 1970-1990 far above costs, but overall benefits exceeding costs … | WebFetch OK | 편익-비용 비율·순편익·현재가치 용어 없음 |

### OpenStax — Introductory Statistics 2e (2개)

라이선스·재사용: 위와 같음 (CC BY-NC-SA 4.0 + LLM 고지).

| id | 제목 (URL) | 레슨 (인용 수) | 뒷받침 개념 | AI 확인 (checked_at · method 요지) | 2026-11-14 재확인 | 문제 |
|---|---|---|---|---|---|---|
| `openstax-is2e-12-3` | [12.3 The Regression Equation](https://openstax.org/books/introductory-statistics-2e/pages/12-3-the-regression-equation) | c04-l1, c09-l2 (5) | correlation_coefficient, correlation_causation | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed that, in its discussion of the correlation coefficient, it states that correlation does not imply causation (a strong correla… | WebFetch OK | — |
| `openstax-is2e-1-4` | [1.4 Experimental Design and Ethics](https://openstax.org/books/introductory-statistics-2e/pages/1-4-experimental-design-and-ethics) | c09-l2 (4) | correlation_causation, counterfactual | verified (AI) 2026-11-14 · c09 (2026-11-14, AI): opened the page and confirmed it explains explanatory and response variables, lurking variables (vitamin E example: users also exercise, eat well… | curl 200 (본문 미확인) | — |

### United Nations (UN DESA SDGs, UN Statistics Division) (11개)

라이선스·재사용: UN 웹사이트 이용 약관. 목표·세부목표 문구는 짧게 인용/요약 + 링크.

| id | 제목 (URL) | 레슨 (인용 수) | 뒷받침 개념 | AI 확인 (checked_at · method 요지) | 2026-11-14 재확인 | 문제 |
|---|---|---|---|---|---|---|
| `un-sdg-2` | [Goal 2: End hunger, achieve food security and improved nutrition and promote sustainable agriculture](https://sdgs.un.org/goals/goal2) | c02-l1, c02-l2, c02-l3, c09-l2 (8) | food_security, food_price_volatility, food_reserves | verified (AI) 2026-11-13 · Rechecked 2026-11-13: confirmed the Goal 2 title and the wording of targets 2.1 (end hunger, access to safe food) and 2.c (functioning food markets, limiting price vol… | WebFetch OK | — |
| `un-sdg-12` | [Goal 12: Ensure sustainable consumption and production patterns](https://sdgs.un.org/goals/goal12) | c01-l1, c01-l2, c01-l3, c02-l2, c02-l3, c08-l3 (16) | food_waste, sustainable_consumption | verified (AI) 2026-11-13 · Rechecked 2026-11-13: confirmed the Goal 12 title and targets 12.2 (efficient use of natural resources), 12.3 (halve food waste, reduce food losses), 12.5 (reduce wast… | WebFetch OK | — |
| `un-sdg-7` | [Goal 7: Ensure access to affordable, reliable, sustainable and modern energy for all](https://sdgs.un.org/goals/goal7) | c03-l1, c03-l2, c03-l3 (6) | energy_access, renewable_energy, energy_efficiency | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed the Goal 7 title and targets 7.1 (access to modern energy), 7.2 (increase the share of renewable energy), and 7.3 (double the… | curl 200 (본문 미확인) | — |
| `un-sdg-13` | [Goal 13: Take urgent action to combat climate change and its impacts](https://sdgs.un.org/goals/goal13) | c03-l1, c03-l2, c03-l3 (6) | climate_action, climate_policy_integration | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed the Goal 13 title and targets 13.1 (resilience to climate-related hazards), 13.2 (integrate climate measures into national po… | curl 200 (본문 미확인) | — |
| `un-sdg-8` | [Goal 8: Promote sustained, inclusive and sustainable economic growth, full and productive employment and decent work for all](https://sdgs.un.org/goals/goal8) | c05-l1, c05-l2, c05-l3, c04-l1, c04-l2, c04-l3, c07-l1, c07-l2, c07-l3, c08-l1, c08-l2, c08-l3 (28) | decent_work, productive_employment, youth_neet, labour_rights, financial_inclusion | verified (AI) 2026-11-13 · Opened 2026-11-13: goal title and targets 8.2 (productivity through diversification, technological upgrading and innovation), 8.5 (full and productive employment and d… | WebFetch OK | — |
| `un-sdg-1` | [Goal 1: End poverty in all its forms everywhere](https://sdgs.un.org/goals/goal1) | c06-l1, c06-l3, c07-l1, c07-l2, c07-l3, c09-l2 (15) | social_protection, poverty_line, public_finance, financial_inclusion | verified (AI) 2026-11-13 · Opened 2026-11-13: goal title and targets 1.1 (eradicate extreme poverty), 1.2 (reduce at least by half the proportion living in poverty in all its dimensions accordin… | WebFetch OK | — |
| `un-sdg-10` | [Goal 10: Reduce inequality within and among countries](https://sdgs.un.org/goals/goal10) | c06-l1, c06-l2, c06-l3 (6) | redistribution, inequality_vs_poverty, tax_progressivity | verified (AI) 2026-11-13 · Opened 2026-11-13: goal title and targets 10.1 (income growth of the bottom 40 per cent above the national average), 10.2 (inclusion of all), 10.3 (equal opportunity, … | curl 200 (본문 미확인) | — |
| `un-sdg-17` | [Goal 17: Strengthen the means of implementation and revitalize the Global Partnership for Sustainable Development](https://sdgs.un.org/goals/goal17) | c08-l1, c08-l2, c08-l3 (7) | global_partnership, multilateral_trading_system, developing_country_exports, market_access | verified (AI) 2026-11-13 · c08 (2026-11-13, AI): opened the page and confirmed the Goal 17 title and the trade targets 17.10 (universal, rules-based, open, non-discriminatory and equitable multi… | curl 200 (본문 미확인) | — |
| `un-sdg-4` | [Goal 4: Ensure inclusive and equitable quality education and promote lifelong learning opportunities for all](https://sdgs.un.org/goals/goal4) | c09-l1, c09-l2, c09-l3 (8) | sdg_targets, measurable_indicators | verified (AI) 2026-11-14 · c09 (2026-11-14, AI): opened the page and confirmed the goal title, target 4.1 (all girls and boys complete free, equitable and quality primary and secondary education… | WebFetch OK | — |
| `un-sdg-6` | [Goal 6: Ensure availability and sustainable management of water and sanitation for all](https://sdgs.un.org/goals/goal6) | c09-l1, c09-l3 (7) | sdg_targets, measurable_indicators | verified (AI) 2026-11-14 · c09 (2026-11-14, AI): opened the page and confirmed the goal title, target 6.1 (universal and equitable access to safe and affordable drinking water for all by 2030) w… | curl 200 (본문 미확인) | — |
| `unstats-sdg-indicators` | [SDG Indicators: Global indicator framework for the Sustainable Development Goals and targets of the 2030 Agenda](https://unstats.un.org/sdgs/indicators/indicators-list/) | c09-l1, c09-l3 (6) | sdg_targets, measurable_indicators, problem_statement | verified (AI) 2026-11-14 · c09 (2026-11-14, AI): opened the page and confirmed that the global indicator framework was developed by the Inter-Agency and Expert Group on SDG Indicators (IAEG-SDGs… | curl 200 (본문 미확인) | — |

### World Bank (5개)

라이선스·재사용: World Bank 이용 약관 (Gini 메타데이터는 CC BY 4.0 으로 기록). 수치는 인용하지 않고 요약·링크.

| id | 제목 (URL) | 레슨 (인용 수) | 뒷받침 개념 | AI 확인 (checked_at · method 요지) | 2026-11-14 재확인 | 문제 |
|---|---|---|---|---|---|---|
| `worldbank-food-security-update` | [Food Security Update](https://www.worldbank.org/en/topic/agriculture/brief/food-security-update) | c02-l3 (2) | food_price_inflation, food_security | verified (AI) 2026-11-13 · Rechecked 2026-11-13: a regularly published Food Security Update that tracks domestic food price inflation by country (figures change with each edition, so none are qu… | curl 200 (본문 미확인) | — |
| `worldbank-gini-index` | [Gini index (SI.POV.GINI) — Metadata glossary, World Development Indicators](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/SI.POV.GINI) | c06-l1 (5) | gini_coefficient, lorenz_curve | verified (AI) 2026-11-13 · Opened 2026-11-13: defines the Gini index via the area between the Lorenz curve and a line of absolute equality, with 0 = perfect equality and 100 = perfect inequality… | WebFetch OK | 0~100/0~1 혼용, 그룹 자료 과소추정 언급 없음; 평균 절대 차이 정의는 말로 있음 |
| `worldbank-measuring-poverty` | [Measuring Poverty](https://www.worldbank.org/en/topic/measuringpoverty) | c06-l3 (3) | poverty_line | verified (AI) 2026-11-13 · Opened 2026-11-13: describes global poverty lines for extreme poverty derived from national poverty lines (median of lines in each income group), higher lines for lowe… | WebFetch OK | 상대 빈곤선·빈곤 갭 없음; 현재 값 $3.00/일(2025-06 개정) |
| `worldbank-financial-inclusion` | [Financial Inclusion (topic overview)](https://www.worldbank.org/en/topic/financialinclusion/overview) | c07-l3 (5) | financial_inclusion, digital_finance | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): opened the page and confirmed access to affordable financial services such as payments, credit, savings products and insurance is described as cr… | WebFetch OK | — |
| `worldbank-global-findex` | [The Global Findex Database 2025](https://www.worldbank.org/en/publication/globalfindex) | c07-l3 (3) | digital_finance, financial_inclusion | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): opened the page and confirmed the database tracks account ownership including mobile money and digitally enabled accounts, saving, borrowing, dig… | curl 200 (본문 미확인) | — |

### FAO (1개)

라이선스·재사용: FAO 이용 약관. 지수 정의만 요약 (수치는 매월 갱신).

| id | 제목 (URL) | 레슨 (인용 수) | 뒷받침 개념 | AI 확인 (checked_at · method 요지) | 2026-11-14 재확인 | 문제 |
|---|---|---|---|---|---|---|
| `fao-food-price-index` | [FAO Food Price Index](https://www.fao.org/worldfoodsituation/foodpricesindex/en/) | c02-l3 (2) | food_price_volatility, price_index | verified (AI) 2026-11-13 · Rechecked 2026-11-13: an index of monthly changes in international prices of five commodity groups (cereals, vegetable oils, dairy, meat, sugar), weighted by 2014–2016… | curl 200 (본문 미확인) | — |

### IMF (2개)

라이선스·재사용: IMF 이용 약관. 요약·링크, 수치 미인용.

| id | 제목 (URL) | 레슨 (인용 수) | 뒷받침 개념 | AI 확인 (checked_at · method 요지) | 2026-11-14 재확인 | 문제 |
|---|---|---|---|---|---|---|
| `imf-climate-mitigation` | [Climate mitigation](https://www.imf.org/en/Topics/climate-change/climate-mitigation) | c03-l3 (4) | carbon_tax, emissions_trading, carbon_pricing, revenue_recycling | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it presents carbon taxes and emissions trading systems as the key pricing tools for climate mitigation, and describes using t… | WebFetch OK (curl 403 = bot block) | 탄소세 공식 정의 없음; 2030년까지 톤당 $75 언급 (c03 시뮬레이션 단위 ≈ 톤당 $6,000과 대비) |
| `imf-fd-inflation-basics` | [Inflation: Prices on the Rise](https://www.imf.org/en/Publications/fandd/issues/Series/Back-to-Basics/Inflation) | c04-l3 (6) | inflation_rate, consumer_price_index, purchasing_power, inflation_redistribution | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it defines inflation as the rate at which prices rise over a period, describes the CPI basket, calls the erosion of purchasin… | WebFetch OK (curl 403 = bot block) | 현금 회피 없음; 긴축으로 경기 둔화는 있음 |

### ECB (1개)

라이선스·재사용: ECB 이용 약관. 요약·링크.

| id | 제목 (URL) | 레슨 (인용 수) | 뒷받침 개념 | AI 확인 (checked_at · method 요지) | 2026-11-14 재확인 | 문제 |
|---|---|---|---|---|---|---|
| `ecb-monetary-policy-intro` | [Monetary policy: Introduction](https://www.ecb.europa.eu/mopo/intro/html/index.en.html) | c04-l3 (4) | price_stability, central_bank | verified (AI) 2026-11-13 · 2026-11-13: opened the page and confirmed it states the primary objective of price stability, keeping inflation low, stable and predictable (with a medium-term numeric… | WebFetch OK | 인플레이션 비용·긴축의 단기 영향 언급 없음 |

### U.S. government (CFPB · FDIC · FTC) (8개)

라이선스·재사용: 미국 연방정부 저작물(일반적으로 미국 내 저작권 없음). 요약·링크. 미국 법·규정이므로 다른 나라 학습자에게는 적용되지 않음.

| id | 제목 (URL) | 레슨 (인용 수) | 뒷받침 개념 | AI 확인 (checked_at · method 요지) | 2026-11-14 재확인 | 문제 |
|---|---|---|---|---|---|---|
| `cfpb-pay-stub-tool` | [Understanding your pay stub (Your Money, Your Goals tool)](https://files.consumerfinance.gov/f/documents/cfpb_understanding-your-pay-stub_tool_2021-08.pdf) | c07-l1 (5) | gross_net_income, budget | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): downloaded and read the PDF text. Confirmed gross wages = pay before deductions, net pay = gross pay minus all deductions ('take-home' pay), dedu… | PDF 받음(220.8KB, 2021-07-30 수정), 본문 추출 실패 → 내용 미확인 | — |
| `cfpb-emergency-fund-guide` | [An essential guide to building an emergency fund](https://www.consumerfinance.gov/an-essential-guide-to-building-an-emergency-fund/) | c07-l1, c07-l2 (7) | saving_emergency_fund, financial_goals, fixed_variable_expenses | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): opened the page and confirmed an emergency fund is money for unexpected expenses (repairs, medical bills, loss of income) outside regular monthly… | WebFetch OK (curl 403 = bot block) | 개월 수 경험칙 없음; SMART 용어 없음 |
| `cfpb-reg-dd-apy` | [Appendix A to Part 1030 (Regulation DD) - Annual Percentage Yield Calculation](https://www.consumerfinance.gov/rules-policy/regulations/1030/a/) | c07-l2 (3) | apr_apy | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): opened the page and confirmed the APY measures the total interest paid on an account based on the interest rate and the frequency of compounding,… | WebFetch OK (curl 403 = bot block) | 일수 기반 식만; 미국 규정(국가별 차이 주의) |
| `cfpb-mortgage-apr` | [What is the difference between a mortgage interest rate and an APR?](https://www.consumerfinance.gov/ask-cfpb/what-is-the-difference-between-a-mortgage-interest-rate-and-an-apr-en-135/) | c07-l2 (4) | apr_apy, borrowing_cost | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): opened the page and confirmed the interest rate is the cost of borrowing without fees, and the APR is a broader measure that also includes points… | WebFetch OK (curl 403 = bot block) | 주택담보대출 한정 |
| `cfpb-credit-card-apr` | [What is a credit card interest rate? What does APR mean?](https://www.consumerfinance.gov/ask-cfpb/what-is-a-credit-card-interest-rate-what-does-apr-mean-en-44/) | c07-l2 (3) | apr_apy, borrowing_cost | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): opened the page and confirmed a card's interest rate is the price of borrowing, stated as a yearly rate (APR), and that on most cards interest on… | WebFetch OK (curl 403 = bot block) | APR 의 수수료 포함 여부 언급 없음 |
| `cfpb-minimum-payment-box` | [A box on my credit card bill says that I will pay off the balance in three years if I pay a certain amount. What does that mean?](https://www.consumerfinance.gov/ask-cfpb/a-box-on-my-credit-card-bill-says-that-i-will-pay-off-the-balance-in-three-years-if-i-pay-a-certain-amount-what-does-that-mean-do-i-have-to-pay-that-much-if-i-pay-that-much-and-make-new-purchases-will-i-still-owe-nothing-after-three-years-en-36/) | c07-l2 (3) | borrowing_cost | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): opened the page and confirmed statements must show how long payoff takes paying only the minimum, the amount needed to pay off the balance in 36 … | WebFetch OK (curl 403 = bot block) | — |
| `fdic-deposit-insurance` | [Understanding Deposit Insurance](https://www.fdic.gov/resources/deposit-insurance/understanding-deposit-insurance) | c07-l2, c07-l3 (4) | saving_emergency_fund, risk_return | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): opened the page and confirmed FDIC insurance covers deposits (checking, savings, money market deposit accounts, CDs) at insured banks up to a lim… | WebFetch OK | 미국 제도 |
| `ftc-avoid-scam` | [How To Avoid a Scam](https://consumer.ftc.gov/articles/how-avoid-scam) | c07-l3 (3) | fraud_scams | verified (AI) 2026-11-13 · c07 (2026-11-13, AI): opened the page and confirmed four signs of a scam (impersonating a known organization, a problem or prize, pressure to act immediately, payment … | WebFetch OK (curl 404 — 봇 차단 추정) | 미국 기관; 4대 신호 목록 구조가 레슨과 같음 |

### J-PAL (2개)

라이선스·재사용: J-PAL 이용 약관. 요약·링크.

| id | 제목 (URL) | 레슨 (인용 수) | 뒷받침 개념 | AI 확인 (checked_at · method 요지) | 2026-11-14 재확인 | 문제 |
|---|---|---|---|---|---|---|
| `jpal-intro-evaluations` | [Introduction to randomized evaluations](https://www.povertyactionlab.org/resource/introduction-evaluations) | c09-l2, c09-l3 (7) | counterfactual, self_assessment_reflection | verified (AI) 2026-11-14 · c09 (2026-11-14, AI): opened the page (last updated April 2023) and confirmed: impact evaluation compares participants with a comparison group; the counterfactual is w… | WebFetch OK | 이중차분·평행 추세 없음 |
| `jpal-cea` | [Conducting cost-effectiveness analysis (CEA)](https://www.povertyactionlab.org/resource/conducting-cost-effectiveness-analysis-cea) | c09-l2, c09-l3 (10) | cost_effectiveness, uncertainty_justification, costs_over_time, proposal_structure | verified (AI) 2026-11-14 · c09 (2026-11-14, AI): opened the page (last updated July 2020) and confirmed: CEA reduces a program to a ratio of cost to impact (example: dollars per additional day o… | WebFetch OK | 편익-비용 분석 없음; 할인율 10% 언급 |

### Universities (library guides) (2개)

라이선스·재사용: 각 대학 도서관 웹사이트 약관. 요약·링크 (Berkeley 6개 기준은 목록 구조가 같으므로 표현 확인 필요).

| id | 제목 (URL) | 레슨 (인용 수) | 뒷받침 개념 | AI 확인 (checked_at · method 요지) | 2026-11-14 재확인 | 문제 |
|---|---|---|---|---|---|---|
| `berkeley-evaluating-resources` | [Evaluating Resources](https://guides.lib.berkeley.edu/evaluating-resources) | c09-l2, c09-l3 (4) | source_reliability, self_assessment_reflection | verified (AI) 2026-11-14 · c09 (2026-11-14, AI): opened the page (last updated Nov 7, 2025) and confirmed its six questions for evaluating a source: authority (author's expertise, institutional … | WebFetch OK | "conflict of interest" 용어 없음; 1차/2차 정의 없음(별도 가이드 링크) |
| `uw-primary-secondary` | [Integrated Social Sciences Program: Primary and Secondary Sources](https://guides.lib.uw.edu/research/iss/sourcetypes) | c09-l2 (2) | primary_secondary | verified (AI) 2026-11-14 · c09 (2026-11-14, AI): opened the page and confirmed it describes a primary source as an original document containing firsthand information and a secondary source as an… | WebFetch OK | — |

---

## 4. 빠졌거나 열리지 않았거나 의심스러운 참고 자료

### 4.1 저자가 열지 못해 쓰지 않은 페이지 (강좌 검토 문서 기록)
검토 문서에는 이 페이지들의 **URL 이 기록되어 있지 않다.** 아래 "오늘 재시도" 는 AI 가 추정한 대표 URL 로 다시 열어 본 결과이며, 원래 시도한 URL 과 같다는 보장은 없다.

| 출처 (기록) | 기록된 상태 | 강좌 | 오늘 재시도 (2026-11-14) | 영향 |
|---|---|---|---|---|
| UNEP (디커플링 등) | HTTP 403, 레지스트리에서 삭제 | c02 (c04 디커플링 관련) | 재시도 안 함 (URL 미기록) | P04-4 간접 판정 유지 |
| ILOSTAT 개념 정의 | HTTP 403 | c05 | `ilostat.ilo.org/methods/concepts-and-definitions/description-unemployment-rate/` → **403** | 실업 정의는 OpenStax 21.1 로 충분 |
| ILO 최저임금 페이지 | HTTP 404 | c05 | 재시도 안 함 (URL 미기록) | P05-4 대체 출처 없음 |
| CBO 최저임금 보고서 | HTTP 403 | c05 | `cbo.gov/publication/55410` → **403** | P05-4 대체 출처 없음 |
| investor.gov 복리 계산기·용어·위험 | HTTP 403 | c07 | 재시도 안 함 | OpenStax 17.3·CFPB 로 대체됨 |
| CFPB "APR vs APY" 질문 | HTTP 404 | c07 | 재시도 안 함 (URL 미기록) | APY 는 Reg DD 로 대체 |
| OECD global value/supply chains | HTTP 403 | c08 | (다른 OECD 페이지) `oecd.org/en/data/indicators/poverty-rate.html` → **403** | P08-8 은 IMF F&D 로 대체 가능 |
| World Bank 탄소 가격 대시보드 | HTTP 403 | c03 | `carbonpricingdashboard.worldbank.org` → **403** | IMF 페이지로 충분 |
| (c09) Library of Congress 1차 자료, Berkeley·Cornell 추측 URL | 403 / 404 | c09 | 재시도 안 함 | UW 가이드로 대체 |

### 4.2 현재 레지스트리 89개 URL 상태 (2026-11-14)
- **curl (일반 브라우저 UA, 리다이렉트 추적):** 200 = 80개, 403 = 8개, 404 = 1개.
  - 403: `imf-climate-mitigation`, `imf-fd-inflation-basics`, `cfpb-pay-stub-tool`, `cfpb-emergency-fund-guide`, `cfpb-reg-dd-apy`, `cfpb-mortgage-apr`, `cfpb-credit-card-apr`, `cfpb-minimum-payment-box`
  - 404: `ftc-avoid-scam`
- **WebFetch 재확인:** 위 9개 중 8개(IMF 2, CFPB 5, FTC 1)는 WebFetch 로 **정상 열림** → curl 의 403/404 는 자동화 접근 차단으로 보이며, 페이지가 옮겨지거나 삭제된 증거는 없다.
  단 FTC 처럼 일반 도구에 404 를 주는 페이지는 학생 브라우저에서는 열리겠지만, 링크 점검 자동화를 만들 경우 오탐이 난다.
- **`cfpb-pay-stub-tool` (PDF):** WebFetch 로 파일(220.8 KB, 2021-07-30 수정, 1쪽 양식)은 받았으나 본문 텍스트를 추출하지 못해 **내용을 확인하지 못함**. 사람이 직접 열어 확인 필요.
- **가장 많이 인용된 20개 출처** (인용 수: un-sdg-8 28, openstax 12.1 21, 2.1 19, un-sdg-12 16, 4.1 15, un-sdg-1 15, 12.3 14, 15.5 14, 13.3 13, 30.2 13, 17.3 13, 15.3 12, 22.4 12, 15.4 11, jpal-cea 10, 3.1 9, 21.1 9, 17.2 9, 그리고 8회 동률 8개 중 3.4·5.1·un-sdg-2·1.1·20.2·20.3·19.2·un-sdg-4) **전부 WebFetch 로 열어 제목·내용을 확인**했고, 이동·404 는 없었다.
  그 밖에 이번에 본문까지 연 출처: OpenStax 14.2·21.4·15.1·15.2·19.1·19.5·29.3·33.1·33.3·34.1·34.3·34.5·12.4, 통계 12.3, World Bank Gini·Measuring Poverty·Financial Inclusion, ECB, FDIC, J-PAL 소개, Berkeley, UW.
  나머지(예: FAO, Findex, UN 통계국 지표 목록, SDG 6·7·10·13·17, OpenStax 3.2·3.3·3.5·1.4·2.2·2.3·12.2·12.5·13.1·14.1·17.1·19.4·21.3·22.1·22.2·28.1·29.1·29.2·33.2·33.4·34.2, 통계 1.4)는 curl 상태만 확인했다.

### 4.3 내용상 의심스러운 연결 (출처는 열리지만 인용 위치가 맞지 않음)
- `openstax-pe3-33-3` 가 c08-l3 "Resilience and its costs" 의 **유일한** 출처 → P08-8.
- `openstax-pe3-30-2` 가 "average tax rate" 의 유일한 출처 → P06-6 (15.5 가 더 적합).
- `openstax-pe3-14-2` 가 수요독점 하 최저임금 고용 증가 주장에 쓰임 → P05-4.
- `worldbank-measuring-poverty` 가 상대 빈곤선 정의에 쓰임 → P06-4 (Eurostat 가 직접 근거).
- c04-l3 SDG 사례 선택지 3 의 둔화 비용 → P04-7 (IMF F&D 가 적합, 이미 레지스트리에 있음).
- 수치가 바뀐 출처: World Bank 국제 빈곤선이 2025-06 에 $3.00/일(2021 PPP)로 개정됨. 레슨은 수치를 쓰지 않으므로 영향 없음.

---

## 5. 근접 의역·저작권 점검

방법: OpenStax 에 가장 많이 기대는 레슨 문장 14개를 골라, AI 가 WebFetch 로 해당 OpenStax 페이지를 열어 그 개념의 원문 문장과 비교했다
(6단어 이상 연속 일치, 문장 구조 일치 여부). 비교는 WebFetch 의 요약 모델이 한 것이므로 **사람이 원문과 나란히 놓고 최종 확인**해야 한다.
이 문서에는 OpenStax 원문을 길게 옮기지 않았다.

| # | 레슨 위치 | OpenStax 페이지 | 6단어+ 연속 일치 | 판정 | 제안 |
|---|---|---|---|---|---|
| 1 | c02-l1 `concepts[0]` Demand | 3.1 | "consumers are willing and able to" (표준 경제학 구) | 독립 표현 | 유지 |
| 2 | c02-l2 `concepts[3]` Price ceiling and price floor | 3.4 | **"A price ceiling is a legal maximum price" (8단어)** — 원문 정의의 첫머리와 같음 | 근접 의역 (짧은 정의) | "A price ceiling sets the highest price that may legally be charged…" 처럼 재작성 권장 |
| 3 | c01-l1 `concepts[0]` Scarcity | 1.1 | 없음 | 독립 표현 | 유지 |
| 4 | c01-l2 `concepts[0]` Opportunity cost | 2.1 | 없음 | 독립 표현 | 유지 |
| 5 | c03-l1 `concepts[1]` Externality | 12.1 | "on a third party who is" (6단어) | 근접 의역 경계 (구조 유사) | 표준 정의라 위험은 낮지만 한 구절 재작성 고려 |
| 6 | c03-l1 `concepts[0]` Market failure | 12.1 | 없음 | 독립 표현 | 유지 |
| 7 | c03-l2 `concepts[2]` Public good | 13.3 | 없음 | 독립 표현 | 유지 |
| 8 | c04-l1 `concepts[0]` GDP (및 `levels.intermediate.sections[0]` ¶0, `key_takeaways[0]`) | 19.1 | **"value of all final goods and services produced within a country" (11단어)** | 근접 의역 (표준 정의 문구와 거의 같음) | 국제 통용 정의 문구이기도 하지만, 세 곳 중 최소 한 곳은 재작성하거나 정의임을 밝힘 |
| 9 | c05-l2 `levels.intermediate.sections[0]` ¶0 (labor force, unemployed test, hidden unemployment) | 21.1 | 없음 (최장 5단어 "not in the labor force") | 구조가 원문 순서와 같은 근접 의역 | 개념 순서 자체는 표준이므로 유지 가능. 사람 확인 |
| 10 | c06-l1 `levels.intermediate.sections[1]` (Lorenz 곡선 성질), `concepts[5]` (불평등 원인) | 15.4 | 없음 | 독립 표현 | 유지 |
| 11 | c06-l2 `real_world_examples[1]` (safety net phase-outs) | 15.3 | 없음 (최장 4단어 "programs reduce benefits as") | 독립 표현 | 유지 |
| 12 | c07-l3 `levels.intermediate.sections[1]` (risk–return, diversification) | 17.2 | 없음 | 독립 표현 | 유지 |
| 13 | c07-l2 `concepts[2]` Compound interest | 17.3 | 없음 | 독립 표현 (개념 동일) | 유지 |
| 14 | c08-l1 `concepts[1]` Comparative advantage | 33.1 | "a country has a comparative advantage" (6단어, 용어 자체) | 첫 문장은 근접 의역 경계 | 표준 용어라 위험 낮음. 사람 확인 |

추가 관찰:
- **예시는 새로 쓴 것으로 확인됨:** 33.1 의 예는 사우디아라비아·미국의 석유·옥수수, 레슨은 가상 Northland·Southland 의 자전거·쌀. 17.3 의 예 수치와 레슨 수치($500·4%·3년 등)가 다름(저자 기록). c05 의 최저임금 그래프·예제, c03 의 탄소세 예제, c09 의 학교 급식 이중차분 예는 모두 "Hypothetical example" 로 표시된 새 예다. 33.2 와 2국 모형 **구조**(한 나라가 두 재화 모두 절대우위)는 같으므로 저자 권고대로 나란히 확인할 것.
- **번역 흔적:** 이번 표본에서 한국어 원문을 영어로 옮긴 듯한 어색한 문장은 보지 못했다 (콘텐츠는 9d1cd7b 에서 영어로 전환됨). 표본 밖 문장은 확인하지 않았다.
- **목록 구조가 같은 곳:** FTC 4대 신호(c07-l3), Berkeley 6개 기준(c09-l2). 사실·기준 목록이라 저작권 위험은 낮지만 표현을 원문과 나란히 확인 권장.

### 5.1 라이선스·이용 조건 메모
- **OpenStax (57개):** CC BY-NC-SA 4.0. 페이지에 "사전 서면 허락 없이 LLM 학습·수집·생성형 AI 제공물에 이용 금지" 고지가 있음(오늘 4.1 에서 확인).
  ECONOVA 는 원문을 저장·전송하지 않고 링크·출처만 쓴다고 기록되어 있다. 다만 (a) 근접 의역 항목(#2·#8)은 "각색(adaptation)" 으로 볼 여지가 있어 BY(출처 표기)·NC(비상업)·SA(동일 조건) 의무가 문제될 수 있고,
  (b) 이 콘텐츠의 작성·검증과 이번 재확인 과정에서 AI 도구(Claude Code 의 WebFetch)가 OpenStax 페이지를 읽었다. 이것이 OpenStax 고지의 "ingest" 에 해당하는지는 **사람(필요하면 법률 검토)이 판단할 문제**이며 이 문서는 결론을 내리지 않는다.
  ECONOVA 의 상업성 여부(NC 조건)도 운영자가 확인해야 한다.
- **미국 정부(CFPB·FDIC·FTC, 8개):** 연방정부 저작물로 기록. 미국 법·규정 내용이므로 다른 나라 학습자에게 적용되지 않는다는 안내가 c07 에 없다(2.3 참고).
- **UN·World Bank·IMF·ECB·FAO·J-PAL·대학 도서관:** 각 사이트 이용 약관에 따라 요약·링크만. World Bank Gini 메타데이터는 CC BY 4.0 으로 기록.

---

## 6. 요약 집계와 권장 사람 검토 순서

### 6.1 집계
- 출처 89개: 모두 `verified` (AI), 사람 확인 0개. 발행처별: OpenStax 경제학 55 · OpenStax 통계 2 · UN 11 · World Bank 5 · 미국 정부 8 · IMF 2 · J-PAL 2 · 대학 2 · ECB 1 · FAO 1.
- 우선 검토 70개 주장 (2.8): **직접 25 · 간접 23 · 뒷받침 없음 20 · 페이지 열리지 않음 0 · 해당 없음 2**.
- URL 상태: 89개 중 WebFetch 로 본문 확인 56개, 그중 열리지 않은 것 0개. 본문 미확인 1개(cfpb-pay-stub-tool PDF). 나머지 32개는 curl 200 만 확인.
- 근접 의역 표본 14개: 독립 표현 9 · 근접 의역/경계 5 (그중 명확히 재작성 권장 2: price ceiling 정의, GDP 정의).
- 이번에 **열어서 확인한 추가·대체 출처 2개** (레지스트리에 없음): Eurostat "At-risk-of-poverty rate" 용어집(P06-4), IMF F&D "The Stretch of Supply Chains"(P08-8). 레지스트리 안에서 재배치 제안 2개: `openstax-pe3-15-5` → c06-l2 평균세율(P06-6), `imf-fd-inflation-basics` → c04-l3 SDG 선택지 3(P04-7).
- 대체 출처를 찾지 못한 항목: 이중차분(P09-2), 편익-비용 순위 규칙(P09-5), 수요독점 하 최저임금(P05-4), 빈곤 갭(P06-5), 판매세 역진성(P06-7), 70의 법칙(P04-1).

### 6.2 권장 순서
1. **c07 국가별 안내 누락 (2.3 횡단 문제)** — 공개 범위(국제 학습자)와 직결. backlog A8 결정과 함께.
2. **c05 P05-4·P05-5·P05-7** — 논쟁적 정책 주장, 출처 없음. backlog A6.
3. **c08 P08-8 (회복력 출처 교체)** — 개념 정의의 유일한 출처가 맞지 않음. IMF F&D 추가 여부.
4. **c06 P06-4~P06-7** — 정의 출처 보완(Eurostat, 15.5), 판매세 문장 처리. backlog A7.
5. **c09 P09-2·P09-5·P09-9** — 캡스톤 방법론. 캡스톤 승인(A4) 전에 결정.
6. **c03 P03-5 (탄소세 수치 표기)** — 작업 트리에 추가된 B1 A안 문구(미커밋) 검토.
7. **c04 P04-6·P04-7** 와 나머지 B2 항목.
8. **5장 근접 의역 #2·#8** 재작성, #5·#9·#14 사람 확인, OpenStax 라이선스·LLM 고지 판단(5.1).
9. **3장 출처별 사람 확인 기록** (관리 화면 Reopen → Approve, 1.2 절차). `cfpb-pay-stub-tool` PDF 는 사람이 직접 열어 확인.
10. 모든 결정 후 레슨 수정이 있으면 해당 레슨 재검토 → 승인 (`final-review-plan.md` 순서).

## 부록: 이 검토 뒤 바로 반영한 것 (2026-11-14, AI · 사람 검토 전)
- **관리 화면 표시 수정:** sources.json 의 "verified" 출처가 관리 화면에서 "Approved" 로 보이던 문제를 고쳤다. 이제 "AI-checked (not human-approved)"
  로 표시되고, 사람 검토를 위해 Draft 상태에서 시작한다 (사람 승인은 DB 검토 기록으로만 남음). 레슨 인용 가능 여부(파일의 verified)는 그대로다.
- **근접 의역 2건 재작성:** c02-l2 가격 상한·하한 정의, c04-l1 GDP 정의(개념·중급 설명·학습목표·핵심 정리 4곳)를 원문과 다른 표현으로 바꿨다.
  c03-l1 외부효과 정의("on a third party who is", 6단어)는 표준 표현이라 그대로 두었다 — 사람 판단.
- **c07 국가별 제도 안내:** c07 레슨 3개에서 미국 제도를 처음 언급하는 문단에 "미국 예시이며 금융 규칙·보호 제도·기관은 나라마다 다르다"는 문장을 넣었다.
  (해당 문단이 있는 레벨에만 들어감 — 모든 레벨에 넣을지는 사람 결정)
- 나머지 지적(출처가 직접 뒷받침하지 않는 주장 20건, 간접 지지 23건, 새 출처 후보)은 `review-backlog.md` A2·B2·B3 로 사람 결정을 기다린다.

