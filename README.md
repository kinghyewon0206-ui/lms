# LMS → ECONOVA

하버드·스탠퍼드 등 대학 무료 강의를 모아 보고, AI 상담으로 나만의 커리큘럼을 만드는 학습 사이트.
경제 교육 플랫폼 ECONOVA 로 바꾸는 중이다 (전환 전 상태는 `legacy-lms-v1` 태그).
Flask + (로컬: sqlite3 / 배포: Firebase Firestore).

## 로컬에서 실행

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # 처음 한 번. 필요한 값만 채운다
.venv/bin/python app.py       # http://localhost:5000 (PORT 로 바꿀 수 있다). 실행할 때 로컬 sqlite 를 준비한다
```

`flask` 명령으로 실행할 때는 DB 를 먼저 준비한다. 앱을 import 하기만 해서는 DB 를 만들거나 바꾸지 않는다.

```bash
.venv/bin/flask --app app init-db   # 테이블 생성·마이그레이션 + 강의 목록 채우기 (여러 번 실행해도 같다)
.venv/bin/flask --app app run
```

`.env`(커밋되지 않음)에 `OPENAI_API_KEY=...` 를 넣으면 AI 상담이 켜진다.

## 개발 환경과 운영 환경

어느 저장소를 쓸지는 **`DB_BACKEND`** 로만 정한다. Firebase 키가 있다는 이유만으로 Firestore 를 쓰지 않는다.

| | 로컬 개발·테스트 | 운영 (Render) |
|---|---|---|
| `DB_BACKEND` | `sqlite` (안 적으면 sqlite) | `firestore` (안 적으면 **기동 거부**) |
| 데이터 | `lms.db` 또는 `SQLITE_PATH` | Firebase Firestore |
| `FIREBASE_CREDENTIALS_JSON` | 넣지 않는다 (넣어도 sqlite 모드면 접속 안 함) | 운영 서비스 계정 키 |

- 운영 환경 판단: Render 가 넣어 주는 `RENDER` 환경변수, 또는 `APP_ENV=production`.
- 운영 Firestore 는 개발·테스트 중에 절대 바꾸지 않는다. `DB_BACKEND=firestore` 에서 `init-db` 를 실행하려면
  `--firestore` 를 따로 붙여야 한다.
- 개발용 Firebase 프로젝트는 아직 없다. 생기면 그 키만 로컬에서 쓴다.

## 테스트

```bash
.venv/bin/python -m pytest
```

- 실제 `.env` 를 읽지 않고, Firebase 와 외부 네트워크(OpenAI 등)를 부르면 실패하도록 막아 둔 상태로 실행된다.
- 회원가입·로그인·세션·CSRF·커리큘럼 테스트는 sqlite 와 **가짜 Firestore**(`tests/fake_firestore.py`) 양쪽에서 돈다.
  실제 Firestore 와 완전히 같다는 보장은 아니므로, 배포 전에는 개발용 Firebase 프로젝트에서 따로 확인해야 한다.

## 코드 구조

| 위치 | 역할 |
|---|---|
| `app.py` | Flask 앱, 라우트, AI 커리큘럼 기능 (`gunicorn app:app`) |
| `econova/config.py` | 환경 설정, `DB_BACKEND` 선택 규칙 |
| `econova/storage.py` | 저장소 계층 (sqlite / Firestore), sqlite 마이그레이션 |
| `econova/legacy_catalog.py` | 기존 LMS 의 대학 강의 목록 |
| `tests/` | pytest 테스트 |

sqlite 스키마를 바꿀 때는 `econova/storage.py` 의 `SQLITE_MIGRATIONS` 에 새 번호를 추가한다.
이미 있는 번호는 고치지 않고, 사용자 데이터가 있는 테이블은 DROP 하지 않는다.

## 배포 (Render)

`render.yaml` 참고. Render 의 Environment 에 아래 값을 넣는다.

| 이름 | 설명 |
|---|---|
| `DB_BACKEND` | `firestore` (필수. 없으면 앱이 시작되지 않는다) |
| `SECRET_KEY` | 세션 서명 키 (Render 가 자동 생성) |
| `OPENAI_API_KEY` | AI 커리큘럼 상담용 |
| `FIREBASE_CREDENTIALS_JSON` | Firebase 서비스 계정 키(JSON 전체) |

Render 무료 플랜은 재배포할 때마다 디스크가 초기화되므로, 회원 데이터는 Firestore 에 저장한다.
예전에는 서버가 시작될 때마다 Firestore 의 강의 목록을 다시 썼지만, 이제는 하지 않는다.
강의 목록(`SEED_COURSES`)을 바꿨을 때만 운영자가 직접 `flask --app app init-db --firestore` 를 실행한다.
