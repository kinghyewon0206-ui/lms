"""개발 Firebase 프로젝트 표식 문서(econova_it/marker) 확인·생성. 사람이 직접, 승인한 뒤에만 실행한다.

    python -m integration_tests.firestore_marker check    # 읽기만: 프로젝트·표식·사용자 문서 확인
    python -m integration_tests.firestore_marker create   # 표식이 없으면 만든다 (쓰기 1회)

guards.firestore_live() 의 조건(개발 프로젝트 id, 운영 id 와 다름, 저장소 밖 600 권한 키, 키의 project_id 일치, 승인 확인값)을
모두 만족해야 접속한다. 표식이 없는 프로젝트에서는 연동 시험(live)이 시작되지 않는다. 키 내용은 출력하지 않는다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from integration_tests import guards  # noqa: E402


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    action = argv[0] if argv else ""
    if action not in ("check", "create"):
        print("사용: python -m integration_tests.firestore_marker check|create")
        return 2
    try:
        live = guards.firestore_live()
    except guards.IntegrationRefused as exc:
        print(f"[거부] {exc}")
        return 4
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = credentials.Certificate(live.credentials_path)
    if cred.project_id != live.project_id:
        print("[거부] 키의 프로젝트가 승인한 개발 프로젝트와 다릅니다.")
        return 4
    app = firebase_admin.initialize_app(cred, name="econova-it-marker")
    db = firestore.client(app)
    if db.project != live.project_id:
        print("[거부] 접속한 프로젝트가 승인한 개발 프로젝트가 아닙니다.")
        return 4
    users = [d.id for d in db.collection("users").select([]).stream()]
    others = [u for u in users if not u.endswith("@" + guards.IT_EMAIL_DOMAIN)]
    if others:
        print(f"[거부] 시험 계정이 아닌 사용자 문서가 {len(others)}개 있습니다. 이 프로젝트는 시험에 쓰지 않습니다.")
        return 4
    ref = db.collection(guards.MARKER[0]).document(guards.MARKER[1])
    snap = ref.get()
    if snap.exists:
        ok = (snap.to_dict() or {}).get("project_id") == live.project_id
        print(f"표식 문서: {'있음 (일치)' if ok else '있음 (프로젝트 불일치 — 확인 필요)'} · 시험 계정 문서 {len(users)}개")
        return 0 if ok else 4
    if action == "check":
        print(f"표식 문서: 없음 · 시험 계정 문서 {len(users)}개. 만들려면 create")
        return 1
    ref.set({"purpose": guards.MARKER_PURPOSE, "project_id": live.project_id, "created_at": firestore.SERVER_TIMESTAMP})
    print(f"표식 문서를 만들었습니다: {guards.MARKER[0]}/{guards.MARKER[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
