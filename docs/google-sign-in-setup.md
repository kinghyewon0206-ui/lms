# Google 로그인 설정 (소유자용, 2026-11-21)

> 코드는 준비됨 (`econova/google_auth.py`, `app.py` 의 `/auth/google*`, `/account`). 클라이언트 ID·비밀값이 없으면 버튼이 숨겨지고 주소는 404 다.
> 이 문서의 ID·도메인은 모두 **예시 자리표시자**다. 실제 값은 소유자가 만든 뒤 환경변수에만 넣는다.

## 1. 동작 요약
- "Continue with Google" → Google 계정 선택 → `/auth/google/callback`.
- 서버 흐름: 인가 코드 + PKCE(S256) + state + nonce. 요청 범위는 `openid email profile` 뿐이다 (민감 범위 없음, 갱신 토큰 없음).
- ID 토큰 검증: 서명(Google 공개키)·aud·exp (google-auth), iss·nonce·sub·`email_verified` (직접 확인).
- 계정은 Google 의 `sub` 로 식별한다.
  - 처음 보는 `sub` 이고 그 이메일을 쓰는 계정이 없으면 **학생 계정**을 새로 만든다. 관리자 권한은 절대 주지 않는다.
  - 같은 이메일의 기존 계정이 있으면 **합치지 않는다.** 비밀번호로 로그인한 뒤 Account 페이지에서 직접 연결하라고 안내한다.
- 연결: 로그인 상태에서 Account → "Link a Google account" (POST + CSRF). Google 계정 하나 ↔ ECONOVA 계정 하나.
- 해제: 비밀번호로 만든 계정만 가능. Google 로 만든 계정은 비밀번호가 없어서 해제할 수 없다.
- 오류: 화면에는 일반 안내만 보여 준다. 이유는 서버 로그에 남기며, 토큰·비밀값은 기록하지 않는다.

## 2. Google Cloud Console 작업 (정확한 순서)
기존 Firebase 프로젝트를 그대로 쓴다 (새 프로젝트를 만들지 않는다. 운영용이면 운영 Firebase 프로젝트, 시험용이면 `econova-dev`).
1. https://console.cloud.google.com → 상단에서 해당 프로젝트 선택.
2. 메뉴 **Google Auth Platform** → 처음이면 **Get started**:
   - App name: `ECONOVA`
   - User support email: 소유자 이메일
   - Audience: **External** (심사위원은 조직 밖 계정)
   - Contact information: 소유자 이메일 → 동의 → Create
3. **Branding**: 앱 이름, 로고(선택), Application home page `https://<운영 도메인>/`, Privacy policy / Terms 링크(있으면), **Authorized domains** 에 운영 도메인(예: `<project>.vercel.app` 또는 소유 도메인).
4. **Data Access**: 범위를 추가하지 않는다. 기본 `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile` 만 쓴다.
5. **Audience**: Publishing status 를 **In production** 으로 바꾼다 (Publish app).
   - Testing 상태에서는 등록한 테스트 사용자(최대 100명)만 로그인할 수 있다. 그래서 심사위원이 막힐 수 있다.
   - 비민감 범위만 쓰는 앱은 Google 앱 검증이 필수가 아니다 (공식 페이지에서 직접 확인하지 못했고 검색 요약으로만 확인함).
   - 브랜드 검증을 받지 않으면 동의 화면에 앱 이름 대신 도메인만 보일 수 있다. 검증에는 영업일 2~3일이 걸린다는 안내가 있다. 대회 일정이 있으면 미리 신청한다.
6. **Clients → Create Client → Web application**:
   - Name: `ECONOVA web (production)`
   - Authorized JavaScript origins: 비워 둔다 (서버 흐름이라 필요 없음)
   - **Authorized redirect URIs** (정확히 일치해야 한다. 스킴·대소문자·끝 슬래시까지 같아야 하고 와일드카드는 안 된다):
     - `https://<운영 도메인>/auth/google/callback`
     - (로컬 시험용, 선택) `http://localhost:5071/auth/google/callback`
   - 커밋마다 바뀌는 Vercel 미리보기 주소는 등록할 수 없다. 미리보기에서 시험하려면 고정 별칭(브랜치 도메인)을 하나 정해서 등록한다.
   - Create → Client ID 와 Client secret 확인. **비밀값은 채팅·문서·커밋에 붙여 넣지 않는다.**
7. Vercel 환경변수(Production): `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`(Sensitive), `GOOGLE_OAUTH_REDIRECT_URI=https://<운영 도메인>/auth/google/callback` → 다시 배포.
   운영에서 둘 중 하나만 있거나 redirect 가 https 가 아니면 앱이 시작하지 않는다.

## 3. 로컬 시험 (선택)
`.env`(Git 제외)에 위 세 값을 넣고 `GOOGLE_OAUTH_REDIRECT_URI=http://localhost:5071/auth/google/callback` 으로 5071 서버를 실행한다. 5070 검토 서버에는 넣지 않는다.

## 4. 시험된 것 / 시험되지 않은 것
- 시험됨 (`tests/test_google_auth.py`, sqlite·가짜 Firestore 모두): 요청 매개변수, PKCE 검증값, 새 계정, 재로그인, sub 기준 식별, 관리자 미부여, 이메일 충돌 시 합치지 않음, 연결·중복 연결·다른 계정 연결 거부, 세션 사용자 바뀜, 해제 규칙, state 위조·만료·재사용·없음, nonce·iss·aud·exp·sub·email_verified 오류, 서명 오류, 취소, 토큰 교환 실패, 설정 없을 때 숨김·404, 운영 설정 검증, 비밀값 비노출.
- **시험되지 않음 (실제 자격 증명 필요):** Google 실제 토큰 교환, 실제 서명 검증(google-auth 의 공개키 다운로드), 동의 화면 표시, Vercel 도메인의 콜백. 클라이언트를 만든 뒤 미리보기 배포에서 한 번 직접 로그인해 확인한다.
