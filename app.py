"""ECONOVA — SDG 로 배우는 고등학생 경제 자기주도 학습 플랫폼 (Flask 앱 시작점).

여기에는 앱 설정·시작 전 안전 검사·회원가입/로그인·대시보드·오류 화면·관리 CLI 만 둔다.
학습 화면은 econova/web.py (Blueprint 'econova'), 학생 화면은 student_web.py, AI 는 ai_web.py, 관리 화면은 admin_web.py.
"""
import datetime
import json
import os
import re
import secrets

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from econova import config, content, learning, login_guard, quotas, roles, storage
from econova.auth import login_required
from econova import web as econova_web
from econova.storage import DuplicateEmailError, create_user, get_user_by_email, get_user_by_id, init_db, using_firestore

app = Flask(__name__)
# 실서비스에서는 반드시 환경변수로 안전한 값을 설정하세요.
app.config["SECRET_KEY"] = config.secret_key()   # 운영에서 없거나 약하면 시작하지 않는다
# 세션 쿠키: 자바스크립트에서 읽지 못하게, 다른 사이트 요청에 실리지 않게, 운영(HTTPS)에서는 Secure
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=config.is_production(),
                  MAX_CONTENT_LENGTH=1024 * 1024)   # 요청 본문 1MB 상한 (가장 긴 캡스톤 제출도 수십 KB)
app.config["DATABASE"] = config.sqlite_path()
storage.init_app(app)
app.register_blueprint(econova_web.bp)
# 위험한 설정이면 요청을 받기 전에 기동을 멈춘다: 운영 환경인데 DB_BACKEND 가 없거나,
# 운영 환경에서 개발용 테스트 강좌(ECONOVA_DEV_FIXTURES=1)를 켜려는 경우.
# (강좌 JSON 형식 오류는 여기서 멈추지 않는다. 로그인은 계속 쓸 수 있고 ECONOVA 화면만 안내 페이지를 보여준다.
#  배포 전에는 flask --app app check-content 로 검사한다.)
config.db_backend()
config.dev_fixtures_enabled()
config.content_preview_enabled()
config.private_content_dir()      # 비공개 정답 키 폴더가 저장소 안을 가리키면 멈춘다
login_guard.limits()              # 로그인 제한·신뢰 프록시 설정 값이 잘못되면 멈춘다
quotas.validate_all()             # 저장 한도 설정 값이 잘못되면 멈춘다
login_guard.trusted_proxy_hops()
from econova.ai import client as _ai_client  # noqa: E402
_ai_client.settings()             # 운영에서 모의 AI, 키 없는 openai 공급자, 잘못된 한도 값이면 멈춘다
_ai_client.feedback_enabled()     # ECONOVA_AI_FEEDBACK 값이 on/off 가 아니면 멈춘다

app.jinja_env.globals["is_admin_user"] = lambda: roles.is_admin(g.user)   # 메뉴 표시용 (권한 검사는 서버에서 따로)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def load_user():
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf_token", "")
    # 세션에 토큰이 없을 때 "-" 를 보내면 통과하던 문제가 있어서, 토큰이 없으면 무조건 거절한다
    if request.method == "POST" and not (expected and secrets.compare_digest(sent, expected)):
        abort(400)  # 다른 사이트에서 몰래 보낸 요청 차단
    user_id = session.get("user_id")
    g.user = get_user_by_id(user_id) if user_id is not None else None


@app.after_request
def security_headers(resp):
    """다른 사이트가 화면을 몰래 감싸(iframe) 관리자 버튼을 누르게 하는 공격(clickjacking), 형식 추측, 주소 유출을 막는다."""
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


# --------------------------------------------------------------- routes
@app.route("/")
def index():
    if g.user:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = None
        if not name:
            error = "이름을 입력해주세요."
        elif len(name) > 50:
            error = "이름은 50자 이하로 입력해주세요."
        elif len(email) > 254 or not EMAIL_RE.match(email):
            error = "올바른 이메일을 입력해주세요."
        elif len(password) < 8:
            error = "비밀번호는 8자 이상이어야 합니다."
        elif len(password) > 256:
            error = "비밀번호가 너무 길어요 (256자 이하)."
        elif password != confirm:
            error = "비밀번호가 일치하지 않습니다."

        if error is None:
            try:
                create_user(email, name, generate_password_hash(password, method="pbkdf2:sha256"))
            except DuplicateEmailError:
                error = "이미 가입된 이메일입니다."
            else:
                flash("회원가입이 완료되었습니다. 로그인해주세요.", "success")
                return redirect(url_for("login"))

        flash(error, "error")
        return render_template("signup.html", name=name, email=email), 400

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()[:254]
        password = request.form.get("password", "")

        # 로그인 시도 제한 (econova/login_guard.py): 계정+IP·계정·IP 별 실패 수. 저장소 기록이라 워커 사이에 공유된다.
        if login_guard.blocked(email):
            # 어느 제한에 걸렸는지는 알리지 않는다 (계정 존재 여부 등을 추측할 수 없게)
            flash("로그인 시도가 많아 잠시 막았어요. 15분쯤 뒤에 다시 시도해 주세요.", "error")
            return render_template("login.html", email=email), 429
        user = get_user_by_email(email)
        if user is None or not check_password_hash(user["password_hash"], password):
            login_guard.record_failure(email)
            flash("이메일 또는 비밀번호가 올바르지 않습니다.", "error")
            return render_template("login.html", email=email), 401

        login_guard.record_success(email)
        session.clear()
        session["user_id"] = user["id"]
        resp = redirect(url_for("dashboard"))
        # 이 브라우저는 이 계정으로 로그인에 성공했다는 서명 쿠키 (계정 전체 제한을 건너뛰어 주인이 잠기지 않게)
        resp.set_cookie(login_guard.DEVICE_COOKIE, login_guard.device_cookie_value(email), max_age=login_guard.DEVICE_MAX_AGE,
                        httponly=True, samesite="Lax", secure=config.is_production())
        return resp

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    """ECONOVA 학생 대시보드: 수강 중인 강좌별 진도, 진단평가, 학습 추천."""
    from econova import ai_web, diagnostic as diag
    test = diag.load()
    return econova_web.render_econova("econova/dashboard.html",
                                      diagnostic=learning.latest_diagnostic(g.user["id"]),
                                      recs=ai_web.dashboard_recommendations(g.user["id"]), ai_enabled=ai_web.ai_enabled(),
                                      area_names=test["category_names"], **learning.dashboard(g.user["id"]))


# ---------------------------------------------------------------- 오류 화면
# 기본 영어 오류 페이지 대신 ECONOVA 화면. 강좌 JSON 을 읽지 않으므로 콘텐츠가 깨져 있어도 보인다.
@app.errorhandler(403)
def forbidden(_exc):
    return render_template("errors/403.html", course_id=(request.view_args or {}).get("course_id")), 403


@app.errorhandler(404)
def not_found(_exc):
    return render_template("errors/404.html"), 404


@app.cli.command("init-db")
def init_db_command():
    """로컬 sqlite 테이블을 만든다(마이그레이션): flask --app app init-db
    Firestore 는 스키마가 없어 할 일이 없다 (문서를 처음 쓸 때 만들어진다). 앱 import 때는 실행되지 않는다."""
    if using_firestore():
        click.echo("DB_BACKEND=firestore: 미리 만들 테이블이 없습니다. 아무것도 바꾸지 않았습니다.")
        return
    init_db()
    click.echo(f"{config.db_backend()} 저장소를 초기화했습니다.")


@app.cli.command("check-content")
def check_content_command():
    """강좌 JSON(content/)을 검사한다. 실제 강좌와 개발용 테스트 강좌 파일을 모두 읽는다.
    배포 전에 실행: flask --app app check-content  (문제가 있으면 종료 코드 1)"""
    try:
        real = content.load_catalog(include_fixtures=False)
        with_fixtures = content.load_catalog(include_fixtures=True)
    except content.ContentError as exc:
        raise click.ClickException(f"강좌 콘텐츠 오류: {exc}")
    fixtures = [c for c in with_fixtures.courses if c.fixture]
    click.echo(f"강좌 콘텐츠 정상: 실제 강좌 {len(real.courses)}개 (레슨 {sum(len(c.lessons) for c in real.courses)}개, "
               f"공개 {len(real.published())}개), 개발용 테스트 강좌 {len(fixtures)}개")
    # 정답 키 확인: 키가 없거나 맞지 않는 평가는 열리지 않는다(fail closed). 공개(승인)된 평가에 키가 없으면 오류.
    from econova import diagnostic
    closed, blocking = [], []
    for c in with_fixtures.courses:
        for a in [lesson.quiz_assessment for lesson in c.lessons] + [c.final]:
            if a is not None and not a.answer_keys:
                closed.append(f"{a.id}: {a.keys_problem}")
                if a.approved:
                    blocking.append(a.id)
    test = diagnostic.load()
    if not test["answer_keys"]:
        closed.append(f"진단평가: {test['keys_problem']}")
    for line in closed:
        click.echo(f"  [정답 키 없음 → 응시 불가] {line}")
    click.echo(f"정답 키 확인: 열 수 없는 평가 {len(closed)}개" if closed else "정답 키 확인: 모든 평가에 정답 키가 있습니다.")
    if blocking:
        raise click.ClickException(f"승인된 평가에 정답 키가 없습니다: {', '.join(blocking)}")


# ---------------------------------------------------------------- 플랫폼 관리자 (Phase 7)
# 관리자 권한은 웹에서 바꿀 수 없다. 서버 셸에 접근할 수 있는 운영자가 본인 확인을 거친 뒤 CLI 로만 부여한다.
# 가입 이메일은 소유 확인을 하지 않으므로 "이 이메일이면 관리자" 같은 자동 부여는 하지 않는다.
@app.cli.command("admin-grant")
@click.argument("email")
@click.option("--operator", required=True, help="권한을 부여하는 운영자 이름 (감사 기록에 남음)")
@click.option("--verification", required=True,
              help="이 계정 주인이 맞는지 확인한 방법 (예: '대면 확인 2026-11-05, 계정 로그인 화면 확인')")
@click.option("--note", default="", help="메모")
def admin_grant_command(email, operator, verification, note):
    """이미 가입한 계정에 플랫폼 관리자 권한을 준다. 확인 문구를 직접 입력해야 한다."""
    email = email.strip().lower()
    if len(verification.strip()) < 10 or len(operator.strip()) < 2:
        raise click.ClickException("운영자 이름과 본인 확인 방법(10자 이상)을 구체적으로 적어야 합니다.")
    if config.is_production() and config.env("ECONOVA_ALLOW_ADMIN_BOOTSTRAP").strip() != "1":
        raise click.ClickException("운영 환경에서는 ECONOVA_ALLOW_ADMIN_BOOTSTRAP=1 을 이 명령에만 잠시 설정해야 합니다.")
    user = get_user_by_email(email)
    if user is None:
        raise click.ClickException("그 이메일로 가입한 계정이 없습니다. 본인이 먼저 가입해야 합니다.")
    typed = click.prompt(f"관리자 권한을 줄 계정의 이메일을 다시 입력하세요 ({email})", default="", show_default=False)
    if typed.strip().lower() != email:
        raise click.ClickException("확인 이메일이 다릅니다. 아무것도 바꾸지 않았습니다.")
    storage.grant_admin(user["id"], operator.strip(), verification.strip(), note.strip())
    click.echo(f"관리자 권한을 부여했습니다: {email} (부여자 {operator.strip()})")


@app.cli.command("admin-revoke")
@click.argument("email")
def admin_revoke_command(email):
    """관리자 권한을 취소한다 (계정은 학생으로 돌아간다. 부여 기록은 취소 시각과 함께 남는다)."""
    user = get_user_by_email(email.strip().lower())
    if user is None:
        raise click.ClickException("그 이메일로 가입한 계정이 없습니다.")
    storage.revoke_admin(user["id"])
    click.echo(f"관리자 권한을 취소했습니다: {email}")


@app.cli.command("admin-list")
def admin_list_command():
    """현재 관리자 계정 목록 (운영자 확인용)."""
    ids = storage.list_admin_user_ids()
    for uid in ids:
        user = get_user_by_id(uid)
        grant = storage.get_admin_grant(uid)
        click.echo(f"- {user['email'] if user else uid} · 부여 {grant['granted_at']} by {grant['granted_by']}")
    click.echo(f"관리자 {len(ids)}명")


@app.cli.command("content-release-apply")
@click.argument("plan_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, help="파일을 바꾸지 않고 확인만")
@click.option("--trust-plan", is_flag=True,
              help="이 DB 에 검토 기록이 없을 때(운영에서 내보낸 계획): ECONOVA_RELEASE_SIGNING_KEY 로 서명이 확인된 계획만 반영")
def content_release_apply_command(plan_file, dry_run, trust_plan):
    """관리 화면에서 내려받은 릴리스 계획을 정본 JSON 의 review 블록에 반영한다 (개발 환경 전용, 웹에서는 불가).
    항목마다 지금 파일의 내용 지문이 승인 때와 같은지 다시 확인하고, 다르면 건너뛴다. 반영 뒤에는 check-content 와
    테스트를 돌리고, 사람이 diff 를 확인한 뒤 커밋한다."""
    import json as _json
    from econova import admin_content
    if config.is_production():
        raise click.ClickException("운영 환경에서는 정본 콘텐츠 파일을 바꾸지 않습니다. 개발 환경에서 반영하고 Git 으로 배포하세요.")
    with open(plan_file, encoding="utf-8") as f:
        plan = _json.load(f)
    signed_ok = admin_content.plan_signature_ok(plan, config.env("ECONOVA_RELEASE_SIGNING_KEY"))

    def verify(item):
        """(문제, DB 가 정한 값). DB 에 기록이 있으면 검토자·날짜·번호를 DB 에서 가져온다 (계획의 값은 믿지 않는다).
        DB 에 없으면 --trust-plan 과 유효한 서명이 둘 다 있어야 한다 (서명 없는·고친 계획으로 승인을 만들 수 없게)."""
        record = storage.get_content_review(item["review_id"])
        if record is None:
            if not trust_plan:
                return "이 DB 에 검토 기록이 없음 (운영에서 내보낸 서명된 계획이면 --trust-plan)", None
            if not signed_ok:
                return "계획 서명이 없거나 맞지 않음 (ECONOVA_RELEASE_SIGNING_KEY 확인) — 반영하지 않음", None
            return None, None
        if (record["decision"], record["content_digest"], record["target_type"], record["target_id"]) != \
                ("approve", item["content_digest"], item["target_type"], item["target_id"]):
            return "검토 기록과 계획 내용이 다름", None
        if storage.get_admin_grant(record["reviewer_user_id"]) is None:
            return "승인한 관리자의 권한이 취소됨 — 다시 검토 필요", None
        later = admin_content.superseded_by(record, storage.list_content_reviews(item["target_type"], item["target_id"]))
        if later is not None:   # 승인 뒤에 '다시 검토'·'수정 요청' 이 기록됐다면 이 승인은 반영하지 않는다
            return f"승인 뒤에 '{admin_content.DECISION_KO.get(later['decision'], later['decision'])}'(#{later['id']}) 이 기록됨", None
        return None, {"review_id": record["id"], "reviewer_name": record["reviewer_name"],
                      "approved_at": record["created_at"].strftime("%Y-%m-%d") if record["created_at"] else ""}
    try:
        results = admin_content.apply_release(plan, verify_record=verify, dry_run=dry_run)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    for item, result in results:
        click.echo(f"- {item['target_type']}:{item['target_id']} → {result}")
    content.load_catalog.cache_clear()
    click.echo("반영 뒤에는 flask --app app check-content 와 테스트를 실행하고 diff 를 확인하세요.")


@app.cli.command("content-verify-approvals")
@click.option("--include-fixtures", is_flag=True, help="개발용 fixture 도 검사")
def content_verify_approvals_command(include_fixtures):
    """정본 JSON 의 관리자 승인(합격 기준 포함)이 모두 DB 의 검토 기록으로 뒷받침되는지 확인한다 (읽기만 함).
    배포 직후 운영 환경에서 실행한다. 기록이 없거나 지문이 다르면 종료 코드 1."""
    from econova import admin_content
    approvals = admin_content.canonical_admin_approvals(include_fixtures)
    problems = admin_content.verify_canonical_approvals(
        storage.get_content_review, include_fixtures, list_reviews=storage.list_content_reviews,
        reviewer_active=lambda uid: storage.get_admin_grant(uid) is not None)
    for t, why in problems:
        click.echo(f"  [검증 실패] {t.type}:{t.id} — {why}")
    if problems:
        raise click.ClickException(f"검증되지 않은 정본 승인 {len(problems)}개")
    click.echo(f"정본 관리자 승인 {len(approvals)}개 모두 DB 검토 기록과 일치합니다.")


@app.cli.command("ai-purge")
def ai_purge_command():
    """보존 기간(ECONOVA_AI_RETENTION_DAYS, 기본 30일)이 지난 AI 대화 메시지와 오래된 사용량 기록을 지운다.
    점수·진도·수강 기록은 건드리지 않는다. 운영에서는 Render Cron Job 등으로 매일 실행한다."""
    import datetime
    from econova.ai import client as ai_client
    days = ai_client.settings().retention_days
    before = storage._utcnow() - datetime.timedelta(days=days)
    msgs, convs = storage.purge_ai_data(before, usage_before=storage._utcnow() - datetime.timedelta(days=max(days, 90)))
    click.echo(f"AI 기록 정리: {days}일 지난 메시지 {msgs}개, 빈 대화 {convs}개를 지웠습니다.")
    n = storage.purge_login_counters(storage._utcnow())
    click.echo(f"로그인 실패 기록 정리: 만료된 기록 {n}개를 지웠습니다.")


@app.cli.command("check-public-files")
@click.option("--staged", is_flag=True, help="이미 스테이지한 파일만 검사 (pre-commit 훅과 같음)")
def check_public_files_command(staged):
    """공개 저장소에 올리면 안 되는 내용(정답 키·교사용 검토 문서·API 키)이 커밋 대상에 있는지 검사한다."""
    from econova import public_safety
    if public_safety.main(["--staged"] if staged else []):
        raise click.ClickException("커밋하면 안 되는 내용이 있습니다.")


@app.cli.command("review-package")
@click.argument("course_id")
@click.option("--output", "-o", default=None, type=click.Path(dir_okay=False),
              help="만들 Markdown 파일 경로. 기본: <비공개 폴더>/review/<강좌>-review-package.md")
def review_package_command(course_id, output):
    """교사용 교육 검토 문서(정답 포함)를 만든다. 학생 화면으로는 제공하지 않는다. 어떤 자료도 승인하지 않는다.
    정답이 들어 있으므로 저장소 밖(비공개 폴더)이나, 저장소 안이라면 git 이 무시하는 곳에만 쓴다."""
    import datetime
    from econova import public_safety, review_package
    if output is None:
        private_dir = config.private_content_dir()
        if not private_dir:
            raise click.ClickException("비공개 폴더(ECONOVA_PRIVATE_CONTENT_DIR)가 없어 기본 위치를 정할 수 없습니다. -o 로 지정하세요.")
        output = os.path.join(private_dir, "review", f"{course_id}-review-package.md")
    inside, ignored = public_safety.is_ignored_inside_repo(output)
    if inside and not ignored:
        raise click.ClickException(f"{output} 는 저장소 안의 커밋될 수 있는 위치입니다. 정답이 공개될 수 있어 쓰지 않습니다. "
                                   "비공개 폴더나 git 이 무시하는 폴더(docs/review/)를 지정하세요.")
    catalog = content.load_catalog(include_fixtures=False)
    course = catalog.course(course_id)
    if course is None:
        raise click.ClickException(f"강좌 {course_id!r} 가 없습니다.")
    try:
        text = review_package.build(course, catalog.sources, datetime.date.today().isoformat())
    except review_package.KeysMissing as exc:
        raise click.ClickException(str(exc))
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    click.echo(f"검토 문서를 만들었습니다: {output}")


if __name__ == "__main__":
    if not using_firestore():  # 로컬 sqlite 는 편의상 실행할 때 준비한다 (import 할 때는 하지 않는다)
        with app.app_context():
            init_db()
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
