# Phase 8B 릴리스 점검표 (우선순위 순)

표시: **[사람 승인]** = 사람이 명시적으로 결정·승인해야 진행할 수 있는 단계. 나머지는 승인 뒤 기술 작업.

## P0 — 먼저 해야 할 것
1. **[사람 승인] 안전한 Git 체크포인트**: 학생이 Phase 3~7(+8A) 변경을 검토하고 커밋을 승인. 커밋 작성자는 학생 계정,
   본문에 AI 도움 기록. 커밋 직전 `flask --app app check-public-files --staged` 통과, 정리된 현재 파일만 사용
   (정답이 든 Phase 3·4 스냅샷은 절대 쓰지 않음). 푸시는 별도 승인.
2. **[사람 승인] pre-commit 훅 켜기** (각자 컴퓨터): `git config core.hooksPath tools/git-hooks`.
3. **[사람 승인] 정답 키 운영 배치 방법 확정**: Render Secret Files + `ECONOVA_PRIVATE_CONTENT_DIR=/etc/secrets`.
   백업 2곳(암호화), 접근 가능한 사람 목록, 키 갱신 절차(공개 문항 수정 → 키 재생성 → Secret File 교체).

## P1 — 실제 연동 검증
4. **[사람 승인] 개발용 Firebase 검증** (`docs/integration-test-plans.md` A).
5. **[사람 승인] 개발용 OpenAI 검증** (같은 문서 B) — 예산 하드 리밋 먼저.
6. 결과 기록 → 문제 수정 → 전체 테스트 재실행.

## P2 — 콘텐츠
7. **[사람 승인] c02 사람 검토** (`docs/content-readiness.md` 체크리스트, 비공개 검토 문서 사용).
8. **[사람 승인] 합격 기준 70%·진단 기준(40/75%) 결정**.
9. **[사람 승인] c09 캡스톤 안내·루브릭·가중치 검토** (공개할 때만).
10. 관리 화면 검토 결정 → 서명된 릴리스 계획 → 개발 환경 반영 → `check-content`·테스트 → 커밋.

## P3 — 운영 준비
11. **[사람 승인] 관리자 부여**: 대상자 본인 확인 방법을 정하고 `admin-grant` (운영에서는 `ECONOVA_ALLOW_ADMIN_BOOTSTRAP=1`
    을 그 명령에만, 끝나면 삭제). `admin-list` 로 확인.
12. Render 환경변수: `DB_BACKEND=firestore`, `FIREBASE_CREDENTIALS_JSON`(운영), `SECRET_KEY`(32자 이상, generateValue),
    `ECONOVA_PRIVATE_CONTENT_DIR=/etc/secrets`, `ECONOVA_AI_PROVIDER`(**off 로 시작 권장**), `ECONOVA_RELEASE_SIGNING_KEY`
    (32자 이상, 릴리스 담당자만 사본 보관). `ECONOVA_DEV_FIXTURES`·`ECONOVA_CONTENT_PREVIEW` 는 비움 (켜면 시작 거부).
13. **[사람 승인] AI 사용·보존**: 공급자 사용 여부, 한도 값, 보존 기간(기본 30일), `ai-purge` Render Cron(매일) 설정.
14. 백업·롤백: 배포 전 Firestore 내보내기, 이전 커밋 재배포 절차 리허설, 정답 키 백업 복구 리허설.

## P4 — 공개 리허설과 배포
15. **[사람 승인] 공개 리허설**: 스테이징(또는 개발 Firebase)에서 c02 를 published 로 바꾼 브랜치로 학생 흐름 전체 시험.
16. **[사람 승인] 운영 배포**.
17. 배포 직후 스모크 테스트: 로그인·회원가입, `/courses`, c02 레슨·퀴즈(실제 키로 열리는지), 결과 화면 해설,
    `flask --app app check-content` (정답 키 확인), `flask --app app content-verify-approvals` (정본 승인 = DB 기록),
    관리 화면 접근(관리자만), 보안 헤더·Secure 쿠키, AI off 상태 안내, 이전 LMS 보관함.
18. 첫 주 모니터링: 503(평가 닫힘), 429(한도), `ai fail` 비율, 로그인 제한 발생, 오류 로그.
