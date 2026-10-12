# LMS

하버드·스탠퍼드 등 대학 무료 강의를 모아 보고, AI 상담으로 나만의 커리큘럼을 만드는 학습 사이트.
Flask + (로컬: sqlite3 / 배포: Firebase Firestore).

## 로컬에서 실행

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py   # http://localhost:5000
```

`.env` 파일(커밋되지 않음)에 `OPENAI_API_KEY=...` 를 넣으면 AI 상담이 켜진다.

## 배포 (Render)

`render.yaml` 참고. Render 의 Environment 에 아래 값을 넣는다.

| 이름 | 설명 |
|---|---|
| `SECRET_KEY` | 세션 서명 키 (Render 가 자동 생성) |
| `OPENAI_API_KEY` | AI 커리큘럼 상담용 |
| `FIREBASE_CREDENTIALS_JSON` | Firebase 서비스 계정 키(JSON 전체). 있으면 Firestore 를 쓰고, 없으면 sqlite 를 쓴다 |

Render 무료 플랜은 재배포할 때마다 디스크가 초기화되므로, 회원 데이터는 Firestore 에 저장한다.
