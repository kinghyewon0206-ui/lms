# Phase 8B-2 준비 사항 — 통제된 실제 연동 시험

> Phase 8B-1 에서는 **문서만** 준비했다. 외부 프로젝트 생성, 실제 DB 접속, OpenAI 요청은 하지 않았다.
> 세부 시험 절차는 `docs/integration-test-plans.md`, 릴리스 점검표는 `docs/release-checklist-8b.md` 에 있다.
> 아래 각 항목은 **사람의 명시적 승인** 뒤에만 시작한다.
> Phase 8B-2 에서 시험 도구(`integration_tests/`)와 승인 절차를 만들었다: `docs/phase-8b2-integration.md`. 아래 표의 수동 절차보다 그 문서가 우선한다.

## 0. 시작 조건 (모두 충족해야 함)
- [ ] 학생이 Phase 3~8B-1 변경을 검토하고 체크포인트 커밋을 승인·실행 (`docs/release/commit-plan.md`)
- [ ] 로컬 전체 테스트 통과 (커밋 뒤 저장소 안에서 다시 실행)
- [ ] 시험용 자원은 모두 운영과 분리된 **개발 전용** 자원

## 1. 개발용 Firebase
| 요구 사항 | 내용 |
|---|---|
| 프로젝트 | 새 Firebase 프로젝트 (예: `econova-dev-YYYYMMDD`). 운영과 결제·IAM 공유 금지 |
| 자격 증명 | 서비스 계정 키(JSON) 1개, 역할 `Cloud Datastore User` 만. 저장소 밖(`~/econova-dev-secrets/`, 권한 600), `.env` 금지, 실행할 때만 `FIREBASE_CREDENTIALS_JSON` 환경변수로 |
| 실행 환경 | `DB_BACKEND=firestore`, `ECONOVA_DEV_FIXTURES=1`, `ECONOVA_AI_PROVIDER=mock`, 빈 `ECONOVA_PRIVATE_CONTENT_DIR` (실제 c02 키 사용 안 함) |
| 시작 전 확인 | 키의 `project_id` 가 개발 프로젝트인지 눈으로 확인 (운영 id 면 즉시 중단) |
| 트랜잭션 | 같은 제출 토큰 동시 2회 → 응시 1개, 다른 토큰 동시 제출로 최종 평가 횟수(3) 초과 시도 → 3개까지만 (`econ_assessment_counters` 문서), AI 하루 한도·잠금, 캡스톤 버전 번호 |
| 색인 | 현재 쿼리는 하위 컬렉션 전체 읽기와 단일 필드 `==` 뿐 → 복합 색인 불필요 예상. 콘솔의 "index required" 오류를 모두 기록 |
| 동시 제출 | 두 브라우저(또는 스크립트 2개)로 최종 평가를 동시에 제출. 기대: 응시 수 ≤ 최대 횟수, 진도·수료 한 번 |
| 학생 소유권 | 계정 A 의 응시·시뮬레이션·AI 대화·캡스톤 버전 주소를 계정 B 로 열기 → 모두 404 |
| 관리자 검토 기록 | 가상 관리자(CLI 부여) → fixture 초안 토론 주제 검토 시작·승인·다시 검토 → `econ_content_reviews` 문서 3개, 다시 검토 뒤 릴리스 계획에서 빠짐 |
| 로그인 카운터 | 같은 계정 11회 실패 → 429, `econ_login_counters` 키가 해시인지, 30분 뒤 해제 |
| 정리 | 시험 뒤 데이터 내보내기(필요 시) → 프로젝트 삭제 또는 키 폐기 |

## 2. 개발용 OpenAI
| 요구 사항 | 내용 |
|---|---|
| 키 | 개발 전용 프로젝트의 키. 운영 키와 분리. 실행할 때만 `OPENAI_API_KEY` 환경변수 |
| 모델 | 공급자 문서에서 현재 제공되고 JSON 스키마(structured outputs)를 지원하는 모델을 골라 `ECONOVA_AI_MODEL` 로 지정 (코드 기본값 `gpt-4o-mini` 는 예시) |
| 지출 통제 | 공급자 콘솔에 월 하드 리밋·알림 먼저. 앱 한도: `ECONOVA_AI_DAILY_REQUESTS=5`, `ECONOVA_AI_GLOBAL_DAILY_REQUESTS=20`, `ECONOVA_LEGACY_MAX_CALLS_PER_REQUEST=2`, `ECONOVA_AI_TIMEOUT_SECONDS=20` |
| 구조화 응답 | 튜터·오답 설명·토론·추천·캡스톤 코치 각 1~2회. 스키마 통과, 형식이 틀리면 표시 안 됨 (로그 `invalid_response`) |
| 근거 설명 | 튜터 답의 출처 id 가 서버 목록 안에 있는지, 근거 수준·한계 표시. 범위 밖 질문은 `insufficient` |
| 시간 제한·오류 | 시간 제한 3초로 줄여 504 안내, 잘못된 키로 502 안내, 기록 변화 없음 |
| 전송 내용 점검 | 개발 서버에 요청 본문 로깅을 **잠시** 켜거나 프록시로 확인: 이메일·이름 없음(가명 `u_…`), 학습자료는 승인된 것만, 진단·퀴즈 정답 없음(오답 설명은 그 학생의 틀린 문항 정답·해설만 — 정책 결정 필요), 출처 본문 없음 |
| 실제 c02 | 승인 전이라 튜터에 쓰이지 않음 (개발용 강좌로만 시험) |
| 정리 | 키 폐기, 실제 비용 확인 → 운영 한도 결정에 반영 |

## 3. 콘텐츠 릴리스
| 단계 | 요구 사항 |
|---|---|
| c02 학습자료 검토 | 플랫폼 관리자가 `docs/content-readiness.md` 체크리스트로 레슨 3개 검토 → 관리 화면에서 결정 기록 |
| 평가 문항 승인 | 퀴즈 3개·최종 평가·진단평가. 정답·해설은 비공개 검토 문서(`~/econova-private/review/`)로 확인 |
| 합격 기준 승인 | 최종 평가 승인 **뒤에** '합격 기준' 대상으로 따로 결정 (70% 제안값 유지·수정 여부) |
| 출처 라이선스 | OpenStax(CC BY-NC-SA, LLM 학습 이용 금지 고지), UN·FAO·World Bank 약관 — 요약·링크만 쓰는지 사람이 확인 |
| 서명된 릴리스 계획 | 운영(또는 리허설 서버)에 `ECONOVA_RELEASE_SIGNING_KEY`(32자 이상) → 관리 화면에서 계획 내려받기 → 개발 환경 `content-release-apply --dry-run` → 반영 → `check-content`·테스트 → diff 검토 → 커밋 |
| 정답 키 | 승인된 평가의 키를 Render Secret Files 에 배치 (`ECONOVA_PRIVATE_CONTENT_DIR=/etc/secrets`) |
| 공개 리허설 | 개발 Firebase 위에서 c02 를 published 로 바꾼 브랜치로 학생 흐름 전체 → `content-verify-approvals` 통과 확인 → 운영 공개는 별도 승인 |

## 4. 운영 배포 전 남은 차단 요소
1. 학생 검토·커밋 승인 (지금 커밋 0)
2. 실제 Firestore·OpenAI 연동 미검증 (모의만)
3. c02 콘텐츠·평가·합격 기준 사람 승인 0건, 정답 키 운영 배치 전
4. `ECONOVA_TRUSTED_PROXY_HOPS` 값 확인 전 (Render 프록시 구조)
5. 관리자 계정 부여 절차·대상자 미정, `ai-purge` 예약 실행 미설정, 백업·롤백 리허설 전
