# 다음 승인 단계 점검표 (Phase 8B-2 이후)

> 각 줄은 사람이 직접 확인하고 체크한다. 이 문서의 명령은 그대로 복사해 실행하지 말고, 한 줄씩 읽고 확인한 뒤 실행한다.
> 세부 절차: 연동 `docs/phase-8b2-integration.md`, 커밋 `docs/release/commit-plan.md`, 콘텐츠 `docs/content-readiness.md`.

## 1. 학생 검토와 Git 체크포인트
- [ ] 학생이 `docs/release/student-summary.md` 의 체크리스트를 직접 끝냈다 (앱 실행, 주요 파일 읽기, `pytest` 실행)
- [ ] 커밋 메시지의 "reviewed by the student" 문장이 사실이다 — 아니면 문장을 빼거나 커밋하지 않는다
- [ ] pre-commit 훅이 켜져 있다 (`git config --get core.hooksPath` → `tools/git-hooks`). `--no-verify` 는 쓰지 않는다
- [ ] 스테이지 목록이 `commit-plan.md` 의 파일 표와 같고, 정답 키·`.env`·DB·`.claude/`·`docs/review/` 가 없다
- [ ] 커밋 뒤 저장소 안에서 전체 테스트 통과. 푸시는 따로 승인

## 2. 개발 Firebase 자격 증명 (승인 지점 A)
- [ ] 개발 전용 프로젝트 id (dev/test 등 구간 포함), Firestore Native 모드, 운영과 결제·IAM 분리
- [ ] 서비스 계정 역할은 Cloud Datastore User 만, 키는 저장소 밖 600 권한
- [ ] `firestore_marker check` → `create` 순서로 표식 문서, 그다음 연동 시험
- [ ] 시험 뒤 남은 문서 0, 키 폐기 계획

## 3. 개발 OpenAI 자격 증명과 예산 (승인 지점 B)
- [ ] 운영과 분리된 OpenAI 프로젝트·키, 콘솔 월 예산·알림 먼저
- [ ] 모델 이름 결정, 요청 예산(권장 8) 승인
- [ ] 오답 설명에 틀린 문항의 정답·해설을 보내는 정책 결정 (승인 전에는 live 에서 건너뜀)
- [ ] 결과의 실제 토큰·비용으로 운영 한도(`ECONOVA_AI_DAILY_REQUESTS`, `..._GLOBAL_DAILY_REQUESTS`) 결정

## 4. 관리자 본인 확인
- [ ] 플랫폼 관리자 후보와 본인 확인 방법 결정 (웹 부여 불가, 서버 CLI `admin-grant` + 확인 기록만)
- [ ] 부여·취소 절차와 기록 보관자 결정, 퇴임 시 `admin-revoke`

## 5. 비공개 평가 콘텐츠 배치
- [ ] 승인된 평가의 정답 키만 Render Secret Files(`ECONOVA_PRIVATE_CONTENT_DIR=/etc/secrets`)에 배치
- [ ] 키 버전·`public_sha256` 이 공개 JSON 과 맞는지 `check-content` 로 확인 (불일치면 응시 불가로 안전하게 멈춤)
- [ ] 키 백업 위치와 접근 권한 결정 (현재 로컬 `~/econova-private` + 외부 백업 폴더)

## 6. c02 교육 콘텐츠 검토
- [ ] 레슨 3개 학습자료를 관리 화면에서 검토·결정 (`content-readiness.md` 체크리스트)
- [ ] 출처 라이선스 확인 (요약·링크만, 출처 본문을 옮기거나 AI 에 보내지 않음)

## 7. 평가·합격 기준 승인
- [ ] 퀴즈 3개·최종 평가·진단평가 문항과 정답·해설을 비공개 검토 문서로 확인 후 승인
- [ ] 최종 평가 승인 **뒤에** 합격 기준(제안 70%) 따로 결정
- [ ] 최종 평가 재응시 횟수(3)·정답 공개 시점(합격 또는 기회 소진 뒤) 확인

## 8. 콘텐츠 릴리스 리허설
- [ ] `ECONOVA_RELEASE_SIGNING_KEY`(32자 이상)와 릴리스 담당자 결정
- [ ] 서명된 계획 → 개발 환경 `content-release-apply --dry-run` → 반영 → `content-verify-approvals` → 테스트 → diff 검토
- [ ] 개발 Firebase 위에서 c02 를 published 로 바꾼 브랜치로 학생 흐름 전체 리허설 (운영 공개는 별도 승인)

## 9. 운영 롤백 계획
- [ ] Render 이전 배포로 되돌리기(대시보드 Rollback) 담당자·절차 확인
- [ ] Firestore 내보내기(백업) 일정과 복원 리허설 1회 (개발 프로젝트에서)
- [ ] 콘텐츠 롤백: 공개를 되돌리는 커밋(`published` → `coming_soon`)과 정답 키 파일 되돌리기 순서
- [ ] `ECONOVA_AI_PROVIDER=off` 로 AI 를 즉시 끄는 절차 (재배포 없이 환경변수 변경 + 재시작)
- [ ] `ECONOVA_TRUSTED_PROXY_HOPS` 를 측정값으로 바꾼 뒤 문제가 생기면 0 으로 되돌리기
