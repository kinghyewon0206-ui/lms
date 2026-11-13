# Render 확인용(staging) 서비스로 프록시 홉 수 확인하기

> 목적: Render 앞단 프록시 뒤에서 실제 클라이언트 IP 가 어떻게 들어오는지 **측정**해 `ECONOVA_TRUSTED_PROXY_HOPS` 를 정한다.
> 추측하지 않는다. 운영 서비스(`lms`)와 그 환경변수는 건드리지 않는다. 확인이 끝나면 확인용 서비스를 지운다.

## 1. 구조 (운영에는 붙지 않음)
| 서비스 | 시작 명령 | 진단 경로 |
|---|---|---|
| 운영 `lms` (main 브랜치) | `gunicorn app:app` | **없음** — 이 시작점은 `staging_wsgi.py` 를 불러오지 않는다 |
| 확인용 `econova-proxy-staging` | `gunicorn staging_wsgi:app` | `/_staging/proxy-diagnostics` (조건을 모두 만족할 때만) |

`econova/proxy_diagnostics.py` 의 조건:
- `ECONOVA_PROXY_DIAGNOSTICS=1` 이 아니면 항상 404 (기본값: 꺼짐)
- `ECONOVA_PROXY_DIAGNOSTICS_TOKEN`: 32자 이상, 영문·숫자·`-`·`_`, 서로 다른 문자 16개 이상. 아니면 **시작 거부**
- Render 가 넣어 주는 `RENDER_SERVICE_NAME` 이 정확히 `econova-proxy-staging` 이 아니면 **시작 거부** (부분 일치 아님)
- 요청 헤더 `X-Econova-Diagnostics: <토큰>` 만 받는다 (`hmac.compare_digest`). 주소에 쿼리가 하나라도 있으면 404. 틀리면 404
- 응답(JSON, `Cache-Control: no-store`): 직접 연결 주소, `X-Forwarded-For` 목록(최대 10개), 홉 수별 후보,
  지금 설정으로 판정한 클라이언트 IP(로그인 제한이 쓰는 값), `X-Real-IP`·`True-Client-IP`·`CF-Connecting-IP`(IP 형식일 때만)
- 쿠키·Authorization·세션·사용자 정보·토큰은 응답에 넣지 않는다. 앱은 이 요청을 기록(log)하지 않는다
- 토큰이 있어도 관리자·학생 화면 권한은 생기지 않는다 (기존 관리자 규칙 그대로)

## 2. 확인용 서비스 설정 (Render 대시보드에서 직접)
- **New → Web Service** (Blueprint·`render.yaml` 동기화 쓰지 않음 → 운영 `lms` 설정과 무관)
- Repository `kinghyewon0206-ui/lms`, Branch **`feature/econova-lms-renewal`**, Root Directory 비움
- Name **`econova-proxy-staging`** (정확히. 다르면 진단을 켠 상태로는 시작하지 않는다)
- Region: 운영 `lms` 와 같은 리전 (같은 프록시 경로를 재기 위해)
- Instance Type **Free** (기본값이 유료일 수 있으니 직접 선택)
- **Auto-Deploy: Off** (수동 배포만)
- Runtime Python
- Build Command: `pip install -r requirements.txt && flask --app app init-db`
- Start Command: `gunicorn staging_wsgi:app --bind 0.0.0.0:$PORT`
- Health Check Path: `/login`

환경변수
| 이름 | 값 |
|---|---|
| `PYTHON_VERSION` | `3.12.4` |
| `DB_BACKEND` | `sqlite` (서비스 안의 임시 파일. 실제 사용자 데이터 없음) |
| `SECRET_KEY` | Render "Generate" (운영과 다른 값) |
| `ECONOVA_AI_PROVIDER` | `off` |
| `ECONOVA_TRUSTED_PROXY_HOPS` | `0` (시작값) |
| `ECONOVA_LOGIN_MAX_PER_ACCOUNT_IP` / `_PER_ACCOUNT` / `_PER_IP` | `3` / `6` / `8` (빠른 시험용) |
| `ECONOVA_PROXY_DIAGNOSTICS` | `1` (시험 중에만) |
| `ECONOVA_PROXY_DIAGNOSTICS_TOKEN` | 아래 3장에서 만든 값 (시험 중에만) |

**넣지 않는다**: `OPENAI_API_KEY`, `OPENAI_MODEL`, `FIREBASE_CREDENTIALS_JSON`, `ECONOVA_DEV_FIXTURES`(운영 모드라 넣으면 시작 거부),
`ECONOVA_PRIVATE_CONTENT_DIR`, `ECONOVA_ALLOW_ADMIN_BOOTSTRAP`.

주소: `https://econova-proxy-staging.onrender.com` (이름이 이미 쓰였으면 Render 가 뒤에 글자를 붙인다 — 대시보드의 주소를 쓴다).

## 3. 진단 토큰 (채팅·문서에 붙여 넣지 않음)

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > ~/econova-dev-secrets/staging-diag.token && chmod 600 ~/econova-dev-secrets/staging-diag.token
```

```bash
pbcopy < ~/econova-dev-secrets/staging-diag.token
```

Render 의 `ECONOVA_PROXY_DIAGNOSTICS_TOKEN` 칸에 붙여 넣은 뒤 `pbcopy < /dev/null` 로 클립보드를 비운다.

## 4. 측정 절차
> 무료 인스턴스는 15분 동안 요청이 없으면 잠들고, 잠들거나 재배포하면 sqlite 가 초기화된다. 한 번에 이어서 한다.
> 환경변수를 바꾸면 재배포되므로 시험 계정은 다시 만든다. IP 값은 채팅에 쓰지 말고 "몇 번째 홉이 내 IP 와 같았다" 만 기록한다.

```bash
export STG=https://econova-proxy-staging.onrender.com
```

```bash
curl -s -H "X-Econova-Diagnostics: $(cat ~/econova-dev-secrets/staging-diag.token)" "$STG/_staging/proxy-diagnostics"
```

1. 네트워크 1(학교·집 Wi-Fi)에서 자기 공인 IP 를 따로 확인하고, 위 명령의 `candidates` 중 그 IP 가 나오는 `hops` 를 기록한다.
2. **위조**: 같은 명령에 `-H "X-Forwarded-For: 203.0.113.250"` 를 더한다. 1에서 고른 홉 수의 IP 가 그대로 내 IP 이고
   203.0.113.250 이 아니어야 한다 (`x_forwarded_for` 목록의 왼쪽에 위조값이 붙는 것은 정상).
3. 네트워크 2(휴대폰 테더링)에서 1~2 반복. **두 네트워크에서 같은 홉 수**일 때만 채택한다. 다르거나 불분명하면 0 을 유지한다.
4. 홉 수 0 상태 기록: 시험 계정으로 네트워크 1에서 서로 다른 계정 로그인 실패 8번 → 9번째 429. 이때 네트워크 2에서도 429 가
   나오면 "홉 수 0 이면 모든 사용자가 프록시 IP 하나로 보인다" 는 증거다.
5. `ECONOVA_TRUSTED_PROXY_HOPS=<측정값>` 으로 바꿔 재배포 → 진단의 `resolved_client_ip` 가 내 IP, 위조값을 넣어도 그대로인지.
6. 로그인 제한 (시험 계정 `it-stg-a/b/c@econova-it.invalid`, 화면에서 가입):
   - a: 네트워크 1에서 3번 틀림 → 4번째(맞는 비밀번호도) 429 / 네트워크 2에서 a 의 주인은 로그인 성공
   - a: `X-Forwarded-For` 값을 바꿔 가며 틀려도 같은 곳으로 센다 (curl 로 `/login` POST 는 CSRF 때문에 브라우저로 하는 편이 쉽다)
   - b, c: 같은 네트워크에서 각각 2번 틀린 뒤 로그인 성공 (공유 네트워크에서 서로 잠그지 않음)
   - 네트워크 1에서 계정을 바꿔 가며 8번 틀림 → 9번째 429, 네트워크 2는 정상
   - a 로 한 번 로그인에 성공한 브라우저는 계정 전체 제한(6)을 다른 곳의 실패가 채워도 로그인 가능
7. 세션 쿠키: 브라우저 개발자 도구에서 `session`·`econova_known_login` 이 `Secure`·`HttpOnly`·`SameSite=Lax` 인지.
8. 끝: `ECONOVA_PROXY_DIAGNOSTICS`·`ECONOVA_PROXY_DIAGNOSTICS_TOKEN` 삭제 → 재배포 → 같은 curl 이 404 인지 → Settings → Suspend →
   **Delete Web Service** (이름 입력). 로컬 토큰 파일도 지운다.

## 5. 비용과 한도 (계정마다 다를 수 있음 — 대시보드에서 확인)
- Free 웹 서비스는 워크스페이스당 월 750시간을 운영 `lms` 와 **함께** 쓴다. 다 쓰면 Free 서비스가 그 달 동안 멈춘다.
- 대역폭·빌드 시간에도 무료 한도가 있고, 결제 수단이 등록된 워크스페이스는 한도를 넘으면 요금이 나올 수 있다 (없으면 서비스가 멈춤).
  이번 시험은 빌드 1~3번, 요청 수십 개라 한도에 비해 아주 작지만 **0원이 보장되는 것은 아니다.**
- Free 에는 셸·SSH·영구 디스크가 없다 (그래서 관리자 화면 대신 이 토큰 진단을 쓴다).

## 6. 운영과의 관계
- 확인용 서비스는 별도 서비스라 운영 `lms` 의 설정·환경변수·배포에 영향이 없다. `render.yaml` 도 바꾸지 않는다.
- 운영 `lms` 는 `main` 을 배포한다. 기능 브랜치 푸시나 확인용 서비스 배포는 운영을 배포하지 않는다.
- 측정한 홉 수를 운영에 넣는 것은 **별도 승인**. 운영도 같은 값인지 운영에서 다시 확인한다 (운영은 Firestore·관리자 계정이 있어
  기존 관리자 진단 화면 `/admin/diagnostics/request` 를 쓸 수 있다).
