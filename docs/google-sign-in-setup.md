# Google 로그인 설정 (소유자용, 2026-11-21 개정)

> 코드는 준비됨 (`econova/google_auth.py`, `app.py` 의 `/auth/google*`, `/account`). 클라이언트 ID·비밀값이 없으면 버튼이 숨겨지고 주소는 404.
> 이 문서의 도메인은 **자리표시자**다. 실제 값은 소유자가 만든 뒤 Vercel 환경변수에만 넣는다 (채팅·문서·커밋에 붙여 넣지 않는다).
> **아직 실제 Google 로그인은 한 번도 해 보지 않았다.** 아래 "시험되지 않음" 참고.

## 1. 동작
- 서버 흐름: 인가 코드 + PKCE(S256) + state + nonce, `prompt=select_account`. 범위는 `openid email profile` 뿐 (갱신 토큰·다른 Google API 없음).
- ID 토큰: 서명·aud·exp 는 google-auth, iss·aud(정확히 일치)·exp·nonce·sub·`email_verified` 는 직접 다시 확인.
- 계정 식별은 Google `sub`. 같은 이메일의 기존 계정과 **자동으로 합치지 않는다** — 비밀번호로 로그인 → Account → "Link a Google account".
- 새 Google 사용자 = 학생 계정. 관리자 권한은 절대 자동 부여 안 함. 관리자가 직접 연결하면 그 계정 그대로(관리자 권한·학습 기록 유지).
- Google 로 만든 계정은 비밀번호가 없어 연결 해제 불가. 로그인 때 세션을 새로 만든다(세션 고정 방지). 로그아웃은 POST + CSRF.

## 2. 게시(Publish)·브랜드 검증이 필요한가 — 필요 없다
Google 공식 안내(Manage App Audience): Testing 상태는 보통 등록한 테스트 사용자 100명까지, 7일마다 재동의, 경고 화면이 붙지만,
**앱이 이름·이메일·프로필(openid/email/profile)만 요청하면 예외**다 — 테스트 사용자 목록에 없어도 되고, 경고 화면이 없고, 7일 만료도 없다. Sign in with Google 도 이 예외에 해당한다.
- 따라서 **Testing 상태 그대로 심사위원이 로그인할 수 있다.** "In production" 으로 게시해도 되지만 필수는 아니다.
- 브랜드 검증(동의 화면에 앱 이름·로고 표시)은 선택이다. 없으면 동의 화면에 앱 도메인만 보인다. 검증에는 소유한 도메인의 홈페이지·개인정보처리방침·Search Console 소유 확인이 필요해서, `*.vercel.app` 주소로는 받을 수 없다 (소유 도메인이 있을 때만 고려).
- 다른 범위를 하나라도 추가하면 위 예외가 사라진다 → 범위를 추가하지 않는다.

## 3. Google Cloud Console 작업 순서
기존 Firebase 프로젝트(`econova-dev`)를 쓴다. 새 프로젝트를 만들지 않는다.
1. https://console.cloud.google.com → 상단 프로젝트 선택: `econova-dev`.
2. 메뉴 **Google Auth Platform** → (처음이면) **Get started**
   - App name: `ECONOVA`
   - User support email: 소유자 이메일
   - Audience: **External**
   - Contact information: 소유자 이메일 → 동의 → **Create**
3. **Branding**
   - Application home page: `https://<운영 도메인>/`
   - **Authorized domains**: 운영 도메인의 최상위 개인 도메인 (예: `vercel.app` 하위 주소라면 Google 이 받아 주는지 화면에서 확인. 거부되면 소유 도메인 필요). 리디렉션 주소보다 먼저 등록한다.
4. **Data Access**: 범위를 추가하지 않는다 (기본 openid·email·profile).
5. **Audience**: Testing 그대로 둔다 (2장). 테스트 사용자를 추가할 필요 없음.
6. **Clients → CREATE CLIENT → Application type: Web application**
   - Name: `ECONOVA web`
   - Authorized JavaScript origins: 비워 둔다 (서버 흐름).
   - **Authorized redirect URIs** (스킴·대소문자·끝 슬래시까지 정확히 일치. 와일드카드 불가):
     - 운영: `https://<운영 도메인>/auth/google/callback` — 운영 도메인이 정해진 뒤 추가
     - 로컬 시험: `http://localhost:5071/auth/google/callback` (localhost 는 http 허용)
   - 커밋마다 바뀌는 Vercel 미리보기 주소는 등록할 수 없다.
   - **CREATE** → Client ID 와 Client secret 확인. **비밀값은 이 화면에서 한 번만 보이므로** 바로 Vercel 환경변수(Sensitive)에 넣는다. 반영까지 5분~몇 시간 걸릴 수 있다.
7. Vercel → Settings → Environment Variables (Production):
   - `GOOGLE_OAUTH_CLIENT_ID`
   - `GOOGLE_OAUTH_CLIENT_SECRET` (Sensitive)
   - `GOOGLE_OAUTH_REDIRECT_URI=https://<운영 도메인>/auth/google/callback`
   → 재배포. 운영에서 하나만 있거나 redirect 가 https 가 아니면 앱이 시작을 거부한다.

## 4. 로컬에서 먼저 시험하기 (권장, 비밀값을 채팅에 쓰지 않는 방법)
1. 위 6단계에서 `http://localhost:5071/auth/google/callback` 등록.
2. `~/econova-private/google-oauth.env` 파일(권한 600)에 소유자가 직접 아래 세 줄을 적는다:
   `GOOGLE_OAUTH_CLIENT_ID=...` / `GOOGLE_OAUTH_CLIENT_SECRET=...` / `GOOGLE_OAUTH_REDIRECT_URI=http://localhost:5071/auth/google/callback`
3. 알려 주면 Claude Code 가 값을 출력하지 않고 5071 시험 서버(임시 DB, 5070 검토 서버와 분리)에 읽어 들여 아래 5장 항목을 실제 로그인으로 확인한다.

## 5. 시험 상태
- **자동 테스트 (통과, Google 접속 없이 모의):** `tests/test_google_auth.py` 81개 (sqlite·가짜 Firestore 각각)
  - 요청 매개변수·PKCE 검증값 일치·고정 redirect
  - 새 계정(학생, 관리자 아님, 비밀번호 로그인 불가)·재로그인·sub 기준 식별(이메일 바뀌어도 같은 계정)
  - 기존 이메일과 충돌 시 합치지 않음·관리자 이메일 탈취 시도 거부
  - 로그인 중 연결·POST+CSRF 필수·다른 계정에 연결된 Google 거부·두 번째 Google 거부·세션 사용자 바뀜 거부
  - 해제 규칙·저장소 유일성
  - state 위조·없음·만료·재사용, nonce·iss·aud(부분 일치 포함)·exp·sub·email_verified 오류, 서명 오류, 취소, 토큰 교환 실패(내용 비노출)
  - 설정 없을 때 버튼 숨김·404, 운영 설정 검증, 비밀값 비노출
  - 관리자가 연결 → Google 로그인해도 관리자·수강 기록 유지, 중복 계정 없음 / 로그아웃 후 같은 기록으로 복귀 / 로그인 때 세션 교체
- **시험되지 않음 (실제 자격 증명 필요):** 실제 토큰 교환, Google 공개키로 서명 검증, 동의 화면 표시, Testing 상태 예외의 실제 동작, Vercel 도메인 콜백, 실제 Firestore 에서의 연결 기록.

## 6. 버튼 디자인
Google 브랜딩 가이드의 Light 테마를 그대로 쓴다: 흰 배경 `#FFFFFF`, 1px `#747775` 테두리, 글자 `#1F1F1F` Google Sans Medium 14/20, 표준 4색 "G", 왼쪽 12px · G · 10px · 글자 · 오른쪽 12px, 알약 모양, 문구 "Continue with Google".
유리(반투명) 배경은 가이드가 허용하는 밝은/어두운/중립 배경이 아니므로 버튼 자체는 유리로 만들지 않았다 — 유리 패널 위에 흰 버튼으로 놓는다.
