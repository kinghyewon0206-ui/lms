# Phase 8B-2 연동 시험 하네스와 승인 절차

> 지금까지 한 것: 하네스·거부 조건·가짜 백엔드를 만들고 **fake 모드로만** 실행했다. 실제 Firebase 접속, OpenAI 요청, 클라우드 자원 생성,
> Render 설정 변경은 **하지 않았다**. live 모드는 아래 승인 지점(A·B·C)을 사람이 하나씩 승인한 뒤에만 실행한다.

## 1. 구성
| 파일 | 역할 |
|---|---|
| `integration_tests/guards.py` | live 시작 조건 검사 (접속 **전**). 하나라도 어긋나면 종료 코드 4 로 멈춘다 |
| `integration_tests/conftest.py` | `.env` 를 읽지 않고 셸의 운영 변수를 지운 뒤 시작. fake/live 백엔드, 시험 계정, 정리(teardown) |
| `integration_tests/fake_backends.py` | 가짜 Firestore(트랜잭션 직렬화·충돌 주입 재시도·쓰기 뒤 읽기 금지)·가짜 Chat Completions |
| `integration_tests/transport.py` | OpenAI 로 보내기 **전** 검사: 주소 1개, 요청 예산, 본문 24KB·출력 700토큰 상한, 가명 형식, 금지 문자열 |
| `integration_tests/test_firestore_integration.py` | Firestore 15개 영역 (16개 시험) |
| `integration_tests/test_openai_integration.py` | OpenAI 모델 형식·근거·지어낸 출처·토큰 기록·실패 처리 (11개 시험) |
| `integration_tests/firestore_marker.py` | 개발 프로젝트 표식 문서 확인·생성 (사람이 승인 뒤 직접 실행) |
| `tests/test_phase8b2.py` | 위 안전장치 자체의 시험 + fake 모드 전체 실행 + 승인 없는 live 요청 거부 (기본 `pytest` 에 포함) |

`integration_tests/` 는 기본 `pytest`(testpaths=tests)에 들어가지 않는다. `tests/conftest.py` 가 Firebase SDK 를 아예 막기 때문에 따로 둔다.

```bash
.venv/bin/python -m pytest integration_tests      # fake (기본): 외부 접속 0
```

## 2. Firestore 시험 범위 (fake 에서 16개 통과)
| # | 영역 | 확인 내용 |
|---|---|---|
| 1 | 인증·사용자 저장 | 가입·로그인·로그아웃, 비밀번호 원문 미저장, 같은 이메일 재가입이 덮어쓰지 않음, **동시 가입 5건 → 1명만** |
| 2 | 수강 신청 | 두 번째 신청은 변화 없음, **동시 신청 6건 → True 1건** |
| 3 | 레슨 진도 | 자료 확인 + 퀴즈 → 레슨 완료, 다른 레슨은 그대로 |
| 4 | 평가 응시 | 응시 기록 저장·결과 화면 |
| 5 | 중복·동시 제출 | 같은 토큰 재전송 → 새 응시 없음, **다른 토큰 동시 6건 → 최대 3회까지만**, 나머지는 AttemptLimitReached |
| 6 | 최종 평가 수료 | 불합격 → 미수료, 합격 → 수료 한 번만 기록 |
| 7 | 진단평가 | 합성 진단평가 응시 기록·결과 화면 |
| 8 | 시뮬레이션 | 화면이 보낸 값이 아니라 서버 재계산값 저장 |
| 9 | AI 사용량 | 하루 한도 2 → 세 번째 429, 토큰 기록, **동시 예약 8건 → 한도 3건만** |
| 10 | 로그인 제한 | 같은 곳 11번째 429, 다른 곳의 주인은 로그인, 카운터 키·값에 이메일·IP 원문 없음, 30분 뒤 해제, 만료 정리 |
| 11 | 관리자·검토 기록 | 부여 전 404 → CLI 부여 → 검토 시작·승인·다시 검토 기록 3건(순서·상태) → 권한 취소 즉시 404 |
| 12 | 캡스톤 | 버전 1·2, 버전 화면, **동시 저장 5건 → 번호 3~7 빠짐·겹침 없음** |
| 13 | 학생 데이터 분리 | 다른 학생의 응시·시뮬레이션·진단 결과 주소 404, AI 설명 요청 404, 목록에 섞이지 않음 |
| 14 | 트랜잭션 재시도 | (fake) 충돌을 주입해 함수를 다시 실행해도 수강·응시 횟수·AI 사용량·캡스톤 버전이 한 번만 반영 |
| 15 | 쿼리·색인 | (하위)컬렉션 전체 읽기·전체 읽기 정리 쿼리 (이전 LMS 의 where 쿼리는 없앰). 복합 색인이 필요하면 live 에서 실패 |

실행이 끝나면 이번 실행에서 생긴 최상위 문서를 하위 컬렉션까지 지우고, 남은 문서가 0개인지 확인한다 (표식 문서·이전 문서는 그대로).

**하네스가 실제 결함을 잡는지 (변이 시험, 저장소 복사본에서)**: 응시 횟수 검사 제거 → 5번 실패 · 지어낸 출처 통과 → 튜터 시험 실패 ·
공급자에 가명 대신 이메일 → 6개 실패 · 토큰 기록 누락 → 2개 실패 · 트랜잭션 밖에서 미리 쓰기 → 14번 실패. 모두 잡혔다.

## 3. OpenAI 시험 범위 (fake 에서 11개 통과)
| 시험 | 확인 내용 | live 요청 |
|---|---|---|
| 모델 형식 | `json_schema` strict + `max_completion_tokens` + `temperature` 를 모델이 받는지 (안 받으면 공급자 오류 내용 `param` 을 보여 줌) | 1 |
| 튜터 근거 | 합성 출처 1개만 허용 → 응답에 **지어낸 출처 id 를 덧붙여도** 화면에서 지워지고 grounded 로 표시되지 않음. 앱이 기록한 토큰 = 공급자 `usage` | 1 |
| 토론·추천·캡스톤 | 각 기능의 구조화 응답 검사 통과, 오류 안내 없음 | 3 |
| 오답 설명 | 맞힌 문항은 정답·해설 모두 보내지 않음 (틀린 문항만) — **정책 승인 전 live 건너뜀** | (0, 승인 시 1) |
| 실패 처리 | 시간 초과 504·서버 오류 502·거절·잘림·JSON 아님·스키마 위반 → 학생 안내만, 대화 미저장, 실패도 사용량에 셈 | fake 만 |
| 잘못된 키 | 401 → 502 일반 안내, 키가 응답에 없음 | 1 (토큰 비용 없음) |

모든 요청은 보내기 전에 검사한다: 시험 계정 이메일·이름·비밀번호, 합성 정답 키 해설, 출처 레지스트리의 확인 메모, 승인 전 실제 c02 학습자료
문장이 있으면 **보내지 않고** 실패한다. `ECONOVA_IT_REAL_KEYS_DIR` 를 주면 실제 정답 키 해설도 로컬에서 대조한다 (값은 출력하지 않음).
학습자료는 개발용 합성 강좌(dev-f1/dev-f3)만 쓰고, 근거 확인용 출처는 "ECONOVA 연동 시험용 합성 출처"(실제 문헌 아님) 하나다.

## 4. 프록시·세션 확인 절차 (ECONOVA 로 교체한 Render `lms` 에서)
> 2026-11 결정: 별도 확인용(staging) 서비스는 만들지 않는다. ECONOVA 로 교체한 운영 서비스 `lms` 에서 기존 관리자 진단 화면으로 잰다.
홉 수는 **추측하지 않고 잰다**. 관리자 진단 화면 `/admin/diagnostics/request` 를 쓴다
(`ECONOVA_PROXY_DIAGNOSTICS=1` 일 때만 열리고, 관리자 본인 요청의 헤더만 보여 주며 저장·기록하지 않는다).

1. 교체 배포 뒤 `lms` 에 `ECONOVA_PROXY_DIAGNOSTICS=1`, `ECONOVA_TRUSTED_PROXY_HOPS=0` 을 둔다. 관리자는 Render 셸이 없으므로
   이 컴퓨터에서 Firestore 로 직접 부여한다 (`docs/deployment-econova.md` 5장).
2. 내 공인 IP 를 따로 확인한다 (다른 서비스·공유기 관리 화면).
3. 진단 화면을 연다 → `X-Forwarded-For` 항목 수와, 홉 수별 주소 표에서 **내 공인 IP 가 나오는 홉 수**를 기록한다.
4. 위조 확인: `curl -H "X-Forwarded-For: 203.0.113.250" -b <관리자 세션 쿠키> https://<서비스 주소>/admin/diagnostics/request`
   → 3에서 고른 홉 수의 주소가 **여전히 내 IP** 이고 203.0.113.250 이 아니어야 한다. 다른 네트워크(휴대폰 테더링)에서도 반복.
5. 같은 결과가 두 네트워크에서 나오면 그 값을 기록하고 운영 설정 변경을 따로 승인받는다. 다르면 설정하지 않는다 (0 유지 + IP 제한 상향).
6. 측정이 끝나면 `ECONOVA_PROXY_DIAGNOSTICS` 를 지운다.

함께 확인할 것:
| 항목 | 기대 |
|---|---|
| 세션 쿠키 | `Secure`·`HttpOnly`·`SameSite=Lax` (진단 화면에 Secure 표시), `econova_known_login` 도 같음 |
| scheme | 진단 화면 `scheme` 이 https 가 아니어도 쿠키는 Secure (운영 설정으로 고정). 외부 링크 생성이 http 로 나오면 기록 |
| SECRET_KEY | 32자 이상이 아니면 앱이 시작하지 않음 (로그 확인) |
| 로그인 제한 | 같은 기기에서 11번째 실패 429, 다른 네트워크의 같은 계정은 로그인 가능, 홉 수 설정 전에는 IP 제한이 모든 사용자에게 공유됨을 기록 |
| 로그아웃 | 세션을 비우지만 서명 쿠키라 서버에서 무효화하지 못함 (알려진 위험, 9장) |

## 5. 승인 지점 — 여기서 멈춘다
### A. 개발 Firebase (사람이 만들고 알려 줄 것)
- 새 Firebase 프로젝트 1개 (예: `econova-dev-20261110` — id 에 dev/test/it/qa/sandbox/staging 구간 필요), Firestore **Native 모드**,
  운영과 결제 계정·IAM 공유 없음. 무료(Spark) 등급으로 충분 (아래 7장).
- 서비스 계정 1개, 역할 **Cloud Datastore User** 만. JSON 키 1개 → 저장소 밖 `~/econova-dev-secrets/`, `chmod 600`.
- (2026-11-13 결정) 예전 LMS 데이터는 버려도 되므로 **예전 운영 프로젝트 id 는 받지 않는다.** 사람이 지정한 ECONOVA 프로젝트
  (`econova-dev`) 한 곳만 쓰고, 다른 프로젝트는 키의 `project_id`·서비스 계정 소속·접속한 프로젝트·표식 문서 확인에서 거부된다.
  예전 데이터 이전·호환 확인은 시험 범위에 없다. 이 코드는 `.env` 를 읽지 않는다.
- 실행 (승인 뒤, 셸에 `FIREBASE_CREDENTIALS_JSON` 이 없어야 함):

```bash
export ECONOVA_IT_FIRESTORE=live ECONOVA_IT_FIREBASE_PROJECT_ID=<개발 id>
```

```bash
export ECONOVA_IT_FIREBASE_CREDENTIALS_FILE=$HOME/econova-dev-secrets/<키>.json ECONOVA_IT_FIRESTORE_APPROVAL=<개발 id>
```

```bash
.venv/bin/python -m integration_tests.firestore_marker check
```

```bash
.venv/bin/python -m integration_tests.firestore_marker create
```

```bash
.venv/bin/python -m pytest integration_tests/test_firestore_integration.py -v
```

### B. 개발 OpenAI
- 운영과 분리된 OpenAI 프로젝트의 키 1개 → 저장소 밖 파일(`chmod 600`, 한 줄). 콘솔에서 **프로젝트 월 예산·알림을 먼저** 설정.
- 모델 이름 (structured outputs 지원 여부는 하네스의 첫 시험이 확인). 앱 기본값 `gpt-4o-mini` 는 예시일 뿐이다.
- 요청 예산: 기본 시험 6회 → **`ECONOVA_IT_OPENAI_MAX_REQUESTS=8` 권장** (상한 30). 오답 설명 정책 승인 시 +1.
- 실행 (승인 뒤, 셸에 `OPENAI_API_KEY` 가 없어야 함):

```bash
export ECONOVA_IT_OPENAI=live ECONOVA_IT_OPENAI_KEY_FILE=$HOME/econova-dev-secrets/openai-dev.key
```

```bash
export ECONOVA_IT_OPENAI_MODEL=<모델> ECONOVA_IT_OPENAI_MAX_REQUESTS=8 ECONOVA_IT_OPENAI_APPROVAL=<모델>:8
```

```bash
.venv/bin/python -m pytest integration_tests/test_openai_integration.py -v
```

끝에 "보낸 요청 n/8, 공급자 기록 토큰 입력·출력, HTTP 오류" 한 줄이 출력된다. 키와 요청 본문은 출력·저장하지 않는다.

### C. 프록시 측정 (4장)
- 별도 서비스 없이, ECONOVA 로 교체한 `lms` 에서 측정하는 동안만 `ECONOVA_PROXY_DIAGNOSTICS=1`.

## 6. 정리
- Firestore: 실행이 끝나면 이번 실행이 만든 문서만 자동 정리 (남은 문서 0 확인, 표식·기존 문서는 그대로). `econova-dev` 는 나중에
  운영에도 쓸 수 있으므로 **프로젝트·데이터베이스를 지우지 않는다.** 운영 전환 전에 시험용 로컬 키를 폐기하고, 운영용은 최소 권한 키를 새로 만든다.
- OpenAI: 키 폐기, 사용량 화면에서 실제 비용 확인 → 운영 한도(`ECONOVA_AI_*`) 결정에 반영.
- Render: 측정 뒤 `ECONOVA_PROXY_DIAGNOSTICS` 삭제.

## 7. 예상 비용과 요청 상한
| 자원 | 1회 실행 | 상한 장치 | 예상 비용 |
|---|---|---|---|
| Firestore | 읽기 약 400~1,000 · 쓰기 약 300 · 삭제 약 270 (fake 계측 근사) | 개발 프로젝트 무료 등급 일일 한도 | 무료 등급 일일 한도의 몇 % 이내 — 0원 예상 (한도는 콘솔에서 확인) |
| OpenAI | 6회 (오답 설명 승인 시 7회), 요청당 입력 약 0.5~4천 자, 출력 ≤ 500 토큰 | 하네스 예산(기본 8, 최대 30) · 본문 24KB · 출력 700토큰 · 콘솔 예산 | 최악: 8회 × (입력 6천 + 출력 500 토큰) = 입력 4.8만·출력 4천 토큰. 소형 모델 단가 기준 **수 센트 이하** (실제 단가는 공급자 가격표로 확인) |
| Render | 기존 `lms` 서비스 그대로 (새 서비스 없음) | — | 추가 서비스 비용 없음 |

## 8. 지금 확인한 것과 못 한 것
- 확인: fake 모드 27개 통과, 안전장치 시험 20개(+진단 화면 4개) 통과, 승인 없는 live 요청은 접속 전에 종료 코드 4, 변이 5종 모두 검출.
- 못 한 것: 실제 Firestore 트랜잭션 충돌·재시도, 실제 색인 요구, 실제 모델의 structured outputs·토큰 수·지연, Render 실제 헤더 구조.

## 9. 남은 위험
- 서명 세션은 로그아웃·권한 취소 뒤에도 쿠키가 남아 있으면 유효 (관리자 권한은 요청마다 DB 로 확인하므로 관리 화면은 즉시 막힘).
- 홉 수 확인 전에는 IP 제한이 사이트 전체에 공유될 수 있다.
- 오답 설명을 실제 AI 로 켜면 그 학생이 틀린 문항의 정답·해설이 공급자에게 간다 (정책 결정 필요).
- (해결) 이전 LMS 링크 확인의 DNS 재바인딩 가능성 — 이전 LMS 를 없애 해당 코드가 없다. 관리 화면·Firestore 전체 읽기 성능.
