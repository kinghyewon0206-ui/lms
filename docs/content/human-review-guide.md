# ECONOVA 사람 검토 안내 (로컬 미리보기·관리 화면으로 검토하기)

> 내부 문서 (운영자용, 한국어). JSON 파일을 직접 열지 않고, 실제 ECONOVA 화면에서 커리큘럼을 검토하는 방법이다.
> 검토 서버는 **이 컴퓨터 안에서만** 돈다. 실제 Firestore·OpenAI·학생 데이터에 연결하지 않는다.

## 1. 검토 서버 켜기
두 방법 중 하나를 쓴다.
- **Claude 앱:** 미리보기 서버 목록에서 `econova-review` 실행 (`.claude/launch.json` 에 등록됨).
- **터미널:** 저장소 폴더에서 아래 명령을 실행한다.

```bash
tools/review-server.sh
```

브라우저에서 http://127.0.0.1:5070 을 연다.

이 서버의 설정 (`tools/review-server.sh`):
| 항목 | 값 |
|---|---|
| 데이터베이스 | `~/econova-private/review-server/review.db` (전용 SQLite, 저장소 밖. 운영 DB 와 무관) |
| AI | `mock` (가짜 응답, OpenAI 요청 없음), AI 오답 설명 off |
| 초안 미리보기 | 켜짐 (`/preview/...`) |
| 개발용 테스트 강좌 | 켜짐 (학생 흐름을 끝까지 시험하는 "Dev Test Course" 들. 실제 강좌가 아님) |
| 정답 키 | `~/econova-private` (관리자 검토 화면에서만 보임) |

## 2. 처음 한 번: 검토용 관리자 계정
1. http://127.0.0.1:5070/signup 에서 본인 계정을 만든다 (이 로컬 DB 에만 저장).
2. 터미널에서 관리자 권한을 준다 (확인 질문에 같은 이메일이 자동 입력됨):

```bash
tools/review-server.sh make-admin 본인이메일@example.com
```

3. 로그인하면 상단에 "Content admin" 메뉴가 보인다.

## 3. 무엇을 어디서 검토하나
| 검토 대상 | 화면 |
|---|---|
| 강좌 제목·설명·학습목표 | `/admin/content` → 강좌의 "Course description and learning objectives" 행 |
| 레슨 (하·중·상 설명, 개념, 예제, 그래프, 실제 사례, SDG 사례, 시뮬레이션, 출처) | `/preview/<강좌>/<레슨>?level=beginner` (또는 `intermediate`, `advanced`). 예: `/preview/c01/c01-l1?level=advanced` |
| 형성 퀴즈 (문항·선택지·정답·해설) | `/admin/content/assessment/<강좌>-l<번호>-quiz` (예: `c01-l1-quiz`) |
| 최종 평가와 정답 해설 | `/admin/content/assessment/<강좌>-final` |
| 합격 기준 (70%·3회 제안) | `/admin/content/passing/<강좌>-final` |
| 진단평가와 추천 기준 | `/admin/content/diagnostic/econ-diagnostic` (학생 화면은 `/diagnostic`) |
| c09 캡스톤 안내·루브릭 | `/admin/content/capstone/c09` |
| 학생 화면·흐름·영어 문구 | 개발용 테스트 강좌로 직접 수강: `/courses` → "Dev Test Course" 수강 → 레슨 → 퀴즈 → 최종 평가 → 수료 → `/report`. 캡스톤은 `/capstone/dev-f3` |
| 정답이 담긴 강좌 전체 문서 (인쇄·오프라인용) | `tools/review-server.sh review-package c01` → `~/econova-private/review/c01-review-package.md` |
| 출처 | 각 레슨 미리보기 하단 "Sources" + `docs/content/source-review.md`. 관리 화면의 Source 항목은 "AI-checked (not human-approved)" 로 표시되며, 사람이 확인한 뒤 거기서 승인 기록을 남긴다 |

실제 강좌(c01~c09)는 아직 공개 전이라, 학생 화면(`/learn/...`)에서는 보이지 않는 것이 정상이다. 실제 강좌 내용은 미리보기와 관리 화면으로만 본다.

## 4. 검토 결정 기록 (공개되지 않게)
- **검토 메모:** 강좌마다 체크리스트(`docs/content/review/c01-checklist.md` 를 복사해 `c02-checklist.md` …)에 적는다.
  고칠 점은 체크리스트의 "수정 요청" 표에 적어 주면 AI 가 반영한다.
- **관리 화면의 결정 버튼:** "Start review" → "Approve" / "Request changes" / "Reopen review".
  - 결정은 **이 로컬 DB 에 감사 기록으로만** 남는다. 정본 JSON 은 바뀌지 않는다.
  - **"Approve" 를 눌러도 공개되지 않는다.** 공개하려면 릴리스 계획 다운로드 → 서명 → `flask content-release-apply` → 커밋 → 배포가
    따로 필요하고, 모두 사람이 직접 하는 단계다.
  - Approve 는 의견 5자 이상과 확인란이 필요하고, AI 이름으로는 승인할 수 없다. 내용이 바뀌면 이전 승인은 자동으로 무효가 된다.
- AI(Claude Code)는 어떤 항목도 승인하지 않는다. 사람이 "검토 완료"라고 말하기 전에는 체크리스트의 승인 칸을 채우지 않는다.

## 5. 정리
- 서버 끄기: 터미널에서 Ctrl+C (또는 앱의 미리보기 중지).
- 검토 DB 초기화 (로컬에 기록한 검토 결정도 지워짐):

```bash
tools/review-server.sh reset
```
