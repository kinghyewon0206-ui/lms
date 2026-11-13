"""Firestore 연동 시험 15개 영역 (Phase 8B-2). fake 는 외부 접속 없이, live 는 승인된 개발 프로젝트에서 같은 시험을 한다.

모든 데이터는 시험 계정(@econova-it.invalid)과 개발용 합성 강좌(dev-f1/f2/f3)·합성 진단평가·합성 정답 키로만 만든다.
실행이 끝나면 이번 실행에서 생긴 문서를 모두 지운다 (conftest.backend).
"""
import datetime
import threading

import pytest

from econova import admin_content as ac
from econova import content, login_guard, simulations, storage
from econova.ai import usage
from integration_tests import guards
from integration_tests.conftest import CSRF, FS_LIVE, login, post, set_csrf, signup, take

DRAFT_TOPIC = "dev-f1/draft-topic-hidden"
SIM_INPUTS = {"a": "100", "b": "2", "c": "10", "d": "1"}


def _final_record(course_id="dev-f2"):
    return {"course_id": course_id, "lesson_id": None, "assessment_id": f"{course_id}-final", "assessment_version": 1,
            "course_content_version": 1, "kind": "final", "score": 0, "max_score": 1, "ratio": 0.0, "passed": False,
            "answers": {}, "results": [], "passing": {}}


def _parallel(app, n, fn):
    """n 개 스레드에서 fn(i) 를 동시에 실행. 각 결과 또는 예외를 돌려준다."""
    out = [None] * n
    barrier = threading.Barrier(n)

    def worker(i):
        with app.app_context():
            barrier.wait()
            try:
                out[i] = fn(i)
            except Exception as exc:   # noqa: BLE001 — 예외 종류까지 결과로 확인한다
                out[i] = exc
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join(timeout=120) for t in threads]
    return out


# 1 ---------------------------------------------------------------- 인증·사용자 저장
def test_01_auth_and_user_persistence(app, new_user):
    u = new_user("가입시험")
    with app.app_context():
        rec = storage.get_user_by_email(u.email)
        assert rec["name"] == "가입시험" and rec["role"] == "student"
        assert "it-password-123" not in str(rec)                  # 비밀번호 원문은 저장하지 않는다
    c = app.test_client()
    assert signup(c, u.email).status_code != 302 or "이미" in c.get("/signup").get_data(as_text=True)
    with app.app_context():
        assert storage.get_user_by_email(u.email)["name"] == "가입시험"   # 같은 이메일 재가입이 덮어쓰지 않음
    assert u.client.get("/dashboard").status_code == 200
    post(u.client, "/logout")
    assert u.client.get("/dashboard").status_code in (302, 401)
    assert login(u.client, u.email).status_code == 302


def test_01b_concurrent_signup_same_email_creates_one_user(app, backend):
    email = f"it-{backend.run_id}-race@{guards.IT_EMAIL_DOMAIN}"
    out = _parallel(app, 5, lambda i: storage.create_user(email, f"동시{i}", "hash"))
    assert sum(1 for r in out if not isinstance(r, Exception)) == 1
    assert all(isinstance(r, storage.DuplicateEmailError) for r in out if isinstance(r, Exception))


# 2 ---------------------------------------------------------------- 수강 신청
def test_02_enrollment(app, new_user):
    u = new_user()
    assert post(u.client, "/courses/dev-f1/enroll", difficulty="intermediate").status_code in (302, 303)
    assert post(u.client, "/courses/dev-f1/enroll", difficulty="advanced").status_code in (302, 303)   # 두 번째는 변화 없음
    with app.app_context():
        e = storage.get_enrollment(u.id, "dev-f1")
        assert e["selected_difficulty"] == "intermediate" and e["status"] != "completed"
        out = _parallel(app, 6, lambda i: storage.enroll_course(u.id, "dev-f3", "beginner", 1))
        assert [r for r in out if r is True] == [True] and all(r is False for r in out if r is not True)


# 3 ---------------------------------------------------------------- 레슨 진도
def test_03_lesson_progress(app, new_user):
    u = new_user()
    post(u.client, "/courses/dev-f1/enroll")
    assert post(u.client, "/learn/dev-f1/dev-f1-l1/material-reviewed").status_code in (302, 303)
    lesson = content.get_catalog().course("dev-f1").lesson("dev-f1-l1")
    take(u.client, "/learn/dev-f1/dev-f1-l1/quiz", lesson.quiz_assessment)
    with app.app_context():
        p = storage.list_lesson_progress(u.id, "dev-f1")["dev-f1-l1"]
        assert p["material_reviewed"] and p["status"] == "completed"
        assert "dev-f1-l2" not in storage.list_lesson_progress(u.id, "dev-f1") or \
            storage.list_lesson_progress(u.id, "dev-f1")["dev-f1-l2"]["status"] != "completed"


# 4·5 ------------------------------------------------------------- 평가 응시·중복·동시 제출
def test_04_assessment_attempt_is_persisted(app, new_user):
    u = new_user()
    post(u.client, "/courses/dev-f1/enroll")
    lesson = content.get_catalog().course("dev-f1").lesson("dev-f1-l1")
    url, _, _ = take(u.client, "/learn/dev-f1/dev-f1-l1/quiz", lesson.quiz_assessment, correct=False)
    assert u.client.get(url).status_code == 200
    with app.app_context():
        attempts = storage.list_assessment_attempts(u.id, assessment_id=lesson.quiz_assessment.id)
        assert len(attempts) == 1 and not attempts[0]["passed"] and attempts[0]["ratio"] == 0   # 형성 퀴즈는 합격 기준 없음(None)


def test_05_duplicate_and_concurrent_submissions(app, new_user):
    u = new_user()
    post(u.client, "/courses/dev-f2/enroll")
    course = content.get_catalog().course("dev-f2")
    for lesson in course.lessons:
        post(u.client, f"/learn/dev-f2/{lesson.id}/material-reviewed")
        if lesson.quiz_assessment:
            take(u.client, f"/learn/dev-f2/{lesson.id}/quiz", lesson.quiz_assessment)
    url, token, answers = take(u.client, "/courses/dev-f2/final", course.final, correct=False)
    again = u.client.post("/courses/dev-f2/final", data={"csrf_token": CSRF, "submission_token": token, **answers})
    assert again.status_code in (302, 303, 409)           # 같은 토큰 재전송 → 새 응시를 만들지 않음
    with app.app_context():
        assert len(storage.list_assessment_attempts(u.id, assessment_id="dev-f2-final")) == 1
        rec = _final_record()
        with pytest.raises(storage.DuplicateSubmission):
            storage.save_assessment_attempt(u.id, rec, token, max_attempts=3)
    # 다른 토큰으로 동시에 6번 → 최대 3번 (이미 1번 사용 → 2개만 더 저장)
    out = _parallel(app, 6, lambda i: storage.save_assessment_attempt(u.id, rec, f"it-concurrent-{i:04d}-tok", max_attempts=3))
    saved = [r for r in out if not isinstance(r, Exception)]
    errors = [r for r in out if isinstance(r, Exception)]
    assert len(saved) == 2 and all(isinstance(e, storage.AttemptLimitReached) for e in errors), [type(e).__name__ for e in errors]
    with app.app_context():
        assert len(storage.list_assessment_attempts(u.id, assessment_id="dev-f2-final")) == 3


# 6 ---------------------------------------------------------------- 최종 평가 수료
def test_06_final_assessment_completion(app, new_user):
    u = new_user()
    post(u.client, "/courses/dev-f2/enroll")
    course = content.get_catalog().course("dev-f2")
    for lesson in course.lessons:
        post(u.client, f"/learn/dev-f2/{lesson.id}/material-reviewed")
        if lesson.quiz_assessment:
            take(u.client, f"/learn/dev-f2/{lesson.id}/quiz", lesson.quiz_assessment)
    take(u.client, "/courses/dev-f2/final", course.final, correct=False)
    with app.app_context():
        assert storage.get_enrollment(u.id, "dev-f2")["status"] != "completed"
    take(u.client, "/courses/dev-f2/final", course.final, correct=True)
    with app.app_context():
        e = storage.get_enrollment(u.id, "dev-f2")
        assert e["status"] == "completed" and e.get("completed_at")
        first = e["completed_at"]
    assert u.client.get("/courses/dev-f2/completion").status_code == 200
    with app.app_context():
        assert storage.get_enrollment(u.id, "dev-f2")["completed_at"] == first   # 한 번만 기록


# 7 ---------------------------------------------------------------- 진단평가
def test_07_diagnostic_results(app, new_user):
    u = new_user()
    assert post(u.client, "/diagnostic/take").status_code in (302, 303)
    with app.app_context():
        attempts = storage.list_diagnostic_attempts(u.id)
        assert len(attempts) == 1 and attempts[0]["diagnostic_id"] == "dev-diagnostic"   # 합성 진단평가
    assert u.client.get(f"/diagnostic/attempts/{attempts[0]['id']}").status_code == 200


# 8 ---------------------------------------------------------------- 시뮬레이션 기록
def test_08_simulation_records_are_recomputed(app, new_user):
    u = new_user()
    res = u.client.post("/lab/supply-demand/save", data={"csrf_token": CSRF, **SIM_INPUTS, "equilibrium_price": "999"})
    assert res.status_code in (302, 303) and "/lab/saved/" in res.headers["Location"]
    with app.app_context():
        runs = storage.list_simulation_runs(u.id)
        assert len(runs) == 1
        _inputs, expected = simulations.run("supply-demand", SIM_INPUTS)
        assert runs[0]["results"] == expected                    # 화면이 보낸 값이 아니라 서버 재계산값
    assert u.client.get(res.headers["Location"]).status_code == 200


# 9 ---------------------------------------------------------------- AI 사용량 카운터
def test_09_ai_usage_counters(app, new_user, monkeypatch):
    monkeypatch.setenv("ECONOVA_AI_DAILY_REQUESTS", "2")
    u = new_user()
    post(u.client, "/courses/dev-f1/enroll")
    codes = [u.client.post("/api/tutor", data={"csrf_token": CSRF, "course_id": "dev-f1", "lesson_id": "dev-f1-l1",
                                                "message": f"수요가 뭐예요 {i}"}).status_code for i in range(3)]
    assert codes == [200, 200, 429]
    with app.app_context():
        used = storage.get_ai_usage(u.id, usage.today())["user"]
        assert used["requests"] == 2 and used["input_tokens"] > 0
        v = new_user()
        now = storage._utcnow()
        out = _parallel(app, 8, lambda i: storage.reserve_ai_request(v.id, usage.today(), 3, 100000, f"h{i}", now, 0))
        assert sum(1 for r in out if not isinstance(r, Exception)) == 3
        assert all(isinstance(r, storage.AILimitExceeded) for r in out if isinstance(r, Exception))
        assert storage.get_ai_usage(v.id, usage.today())["user"]["requests"] == 3


# 10 --------------------------------------------------------------- 로그인 시도 제한
def test_10_login_rate_limits(app, backend, new_user):
    u = new_user()
    c = app.test_client()
    ip = "198.19.7.7"
    codes = []
    for _ in range(11):
        set_csrf(c)
        codes.append(login(c, u.email, "wrong-password", environ_base={"REMOTE_ADDR": ip}).status_code)
    assert codes[:10] == [401] * 10 and codes[10] == 429
    assert login(c, u.email, environ_base={"REMOTE_ADDR": ip}).status_code == 429          # 맞는 비밀번호도 잠시 막힘
    assert login(c, u.email, environ_base={"REMOTE_ADDR": "198.19.7.8"}).status_code == 302  # 다른 곳의 주인은 가능
    with app.app_context():
        ids = backend.ids("econ_login_counters")
        assert ids and not any(u.email in i or ip in i for i in ids)                      # 키는 해시
        docs = [backend.db.collection("econ_login_counters").document(i).get().to_dict() for i in ids]
        assert not any(u.email in str(d) or ip in str(d) for d in docs)
    later = storage._utcnow() + datetime.timedelta(minutes=31)
    with app.test_request_context(environ_base={"REMOTE_ADDR": ip}):
        assert login_guard.blocked(u.email) is not None and login_guard.blocked(u.email, now=later) is None
    with app.app_context():
        storage.purge_login_counters(later + datetime.timedelta(minutes=31))   # 만료 기록 정리 (전체 읽기 쿼리)


# 11 --------------------------------------------------------------- 관리자 권한·검토 기록
def test_11_admin_grants_and_review_records(app, new_user):
    a = new_user("가상관리자")
    assert a.client.get("/admin/content").status_code == 404                  # 부여 전에는 관리 화면 없음
    with app.app_context():
        storage.grant_admin(a.id, "연동 시험", "가상 시험 계정 (실제 사람 아님)")
    login(a.client, a.email)
    set_csrf(a.client)
    assert a.client.get("/admin/content").status_code == 200
    digest = ac.find_target("debate", DRAFT_TOPIC, include_fixtures=True).digest
    for decision in ("start_review", "approve", "reopen"):
        data = {"csrf_token": CSRF, "decision": decision, "comment": "연동 시험에서 확인했습니다.", "content_digest": digest,
                "confirm_reviewed": "1"}
        assert a.client.post(f"/admin/content/debate/{DRAFT_TOPIC}/review", data=data).status_code == 303
    with app.app_context():
        mine = [r for r in storage.list_content_reviews("debate", DRAFT_TOPIC) if r["reviewer_user_id"] == str(a.id)]
        assert [r["decision"] for r in mine] == ["start_review", "approve", "reopen"]   # 오래된 것부터
        assert [r["to_state"] for r in mine] == ["in_review", "approved", "in_review"]
        storage.revoke_admin(a.id)
    assert a.client.get("/admin/content").status_code == 404                  # 취소 즉시 막힘
    s = new_user()
    assert s.client.get("/admin/content").status_code == 404


# 12 --------------------------------------------------------------- 캡스톤·버전 기록
def test_12_capstone_and_versions(app, new_user):
    u = new_user()
    post(u.client, "/courses/dev-f3/enroll")
    for text in ("첫 번째 문제 정의", "두 번째 문제 정의"):
        assert post(u.client, "/capstone/dev-f3/edit", sdg="7", problem=text).status_code in (302, 303)
    with app.app_context():
        versions = storage.list_capstone_versions(u.id, "dev-f3")
        assert sorted(v["version"] for v in versions) == [1, 2]
    assert u.client.get("/capstone/dev-f3/versions/1").status_code == 200
    with app.app_context():
        out = _parallel(app, 5, lambda i: storage.save_capstone_version(u.id, "dev-f3", {"problem": f"동시 {i}"}, 1))
        assert not [r for r in out if isinstance(r, Exception)]
        nums = sorted(v["version"] for v in storage.list_capstone_versions(u.id, "dev-f3"))
        assert nums == list(range(1, 8))                               # 빠지거나 겹치는 번호 없음


# 13 --------------------------------------------------------------- 학생 데이터 분리
def test_13_student_data_isolation(app, new_user):
    a, b = new_user(), new_user()
    post(a.client, "/courses/dev-f1/enroll")
    lesson = content.get_catalog().course("dev-f1").lesson("dev-f1-l1")
    attempt_url, _, _ = take(a.client, "/learn/dev-f1/dev-f1-l1/quiz", lesson.quiz_assessment)
    sim_url = a.client.post("/lab/supply-demand/save", data={"csrf_token": CSRF, **SIM_INPUTS}).headers["Location"]
    post(a.client, "/diagnostic/take")
    with app.app_context():
        diag_id = storage.list_diagnostic_attempts(a.id)[0]["id"]
    for url in (attempt_url, sim_url, f"/diagnostic/attempts/{diag_id}"):
        assert a.client.get(url).status_code == 200
        assert b.client.get(url).status_code == 404, url
    assert b.client.post(attempt_url + "/explain", data={"csrf_token": CSRF}).status_code == 404
    with app.app_context():
        assert storage.list_simulation_runs(b.id) == [] and storage.list_diagnostic_attempts(b.id) == []
        assert storage.list_assessment_attempts(b.id) == []


# 14 --------------------------------------------------------------- 트랜잭션 재시도
@pytest.mark.skipif(FS_LIVE is not None, reason="충돌 주입은 fake 전용. live 는 위 동시 실행 시험(1b·2·5·9·12)이 실제 재시도를 거친다")
def test_14_transactions_are_safe_to_retry(app, backend, new_user):
    u = new_user()
    db = backend.db
    with app.app_context():
        db.inject_conflicts = 2
        assert storage.enroll_course(u.id, "dev-f2", "beginner", 1) is True
        db.inject_conflicts = 2
        storage.save_assessment_attempt(u.id, _final_record(), "it-retry-token-000001", max_attempts=3)
        db.inject_conflicts = 1
        storage.reserve_ai_request(u.id, usage.today(), 5, 100000, "retry-hash", storage._utcnow(), 0)
        db.inject_conflicts = 1
        storage.save_capstone_version(u.id, "dev-f3", {"problem": "재시도"}, 1)
        assert db.retries >= 6
        assert len(storage.list_assessment_attempts(u.id, assessment_id="dev-f2-final")) == 1
        counter = db.collection("users").document(u.id).collection("econ_assessment_counters").document("dev-f2-final").get()
        assert counter.to_dict()["count"] == 1                          # 다시 실행해도 한 번만 셈
        assert storage.get_ai_usage(u.id, usage.today())["user"]["requests"] == 1
        assert [v["version"] for v in storage.list_capstone_versions(u.id, "dev-f3")] == [1]


# 15 --------------------------------------------------------------- 쿼리·색인
def test_15_queries_and_indexes(app, new_user):
    """ECONOVA 의 Firestore 읽기는 문서 직접 읽기와 (하위)컬렉션 전체 읽기뿐이고 where/order_by 쿼리가 없다 (이전 LMS 의
    쿼리는 없앴다) → 색인을 만들 필요가 없다. live 에서 'index required'(FailedPrecondition)가 나면 이 시험이 실패한다."""
    u = new_user()
    post(u.client, "/courses/dev-f1/enroll")
    with app.app_context():
        assert [e["course_id"] for e in storage.list_enrollments(u.id)] == ["dev-f1"]   # 하위 컬렉션 전체 읽기
        storage.list_content_reviews()                                                    # 최상위 컬렉션 전체 읽기
        storage.purge_ai_data(storage._utcnow() - datetime.timedelta(days=3650))          # 전체 읽기 정리
