"""ECONOVA — SDG 로 배우는 고등학생 경제 자기주도 학습 플랫폼 (Flask 앱 시작점).

여기에는 앱 설정·시작 전 안전 검사·회원가입/로그인·대시보드·오류 화면·관리 CLI 만 둔다.
학습 화면은 econova/web.py (Blueprint 'econova'), 학생 화면은 student_web.py, AI 는 ai_web.py, 관리 화면은 admin_web.py.
"""
import datetime
import json
import os
import re
import secrets
import time

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from econova import config, content, google_auth, learning, login_guard, quotas, roles, storage
from econova.auth import login_required
from econova import web as econova_web
from econova.storage import DuplicateEmailError, create_user, get_user_by_email, get_user_by_id, init_db, using_firestore

# 정적 파일은 public/static 에 둔다: Vercel 은 public/** 를 CDN 으로 바로 제공하고 Flask 의 static_folder 는 쓰지 않는다.
# 로컬·테스트에서는 Flask 가 같은 폴더를 /static/... 으로 제공하므로 주소(url_for('static', ...))는 그대로다.
app = Flask(__name__, static_folder="public/static", static_url_path="/static")
# 실서비스에서는 반드시 환경변수로 안전한 값을 설정하세요.
app.config["SECRET_KEY"] = config.secret_key()   # 운영에서 없거나 약하면 시작하지 않는다
# 세션 쿠키: 자바스크립트에서 읽지 못하게, 다른 사이트 요청에 실리지 않게, 운영(HTTPS)에서는 Secure
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=config.is_production(),
                  MAX_CONTENT_LENGTH=1024 * 1024)   # 요청 본문 1MB 상한 (가장 긴 캡스톤 제출도 수십 KB)
app.config["DATABASE"] = config.sqlite_path()
storage.init_app(app)
app.register_blueprint(econova_web.bp)
from econova import prototype_web  # noqa: E402
app.register_blueprint(prototype_web.bp)   # 디자인 시안: ECONOVA_DESIGN_PROTOTYPES=1 이고 운영이 아닐 때만 (그 외에는 404)
# 위험한 설정이면 요청을 받기 전에 기동을 멈춘다: 운영 환경인데 DB_BACKEND 가 없거나,
# 운영 환경에서 개발용 테스트 강좌(ECONOVA_DEV_FIXTURES=1)를 켜려는 경우.
# (강좌 JSON 형식 오류는 여기서 멈추지 않는다. 로그인은 계속 쓸 수 있고 ECONOVA 화면만 안내 페이지를 보여준다.
#  배포 전에는 flask --app app check-content 로 검사한다.)
config.db_backend()
config.dev_fixtures_enabled()
config.content_preview_enabled()
config.design_prototypes_enabled()   # 운영에서 디자인 시안을 켜면 멈춘다
config.private_content_dir()      # 비공개 정답 키 폴더가 저장소 안을 가리키면 멈춘다
login_guard.limits()              # 로그인 제한·신뢰 프록시 설정 값이 잘못되면 멈춘다
quotas.validate_all()             # 저장 한도 설정 값이 잘못되면 멈춘다
login_guard.trusted_proxy_hops()
from econova.ai import client as _ai_client  # noqa: E402
_ai_client.settings()             # 운영에서 모의 AI, 키 없는 openai 공급자, 잘못된 한도 값이면 멈춘다
_ai_client.feedback_enabled()     # ECONOVA_AI_FEEDBACK 값이 on/off 가 아니면 멈춘다
google_auth.settings()            # Google 로그인 설정이 반쪽이거나 운영에서 콜백 주소가 없으면 멈춘다
app.jinja_env.globals["google_enabled"] = google_auth.enabled
from econova import ui_charts  # noqa: E402
app.jinja_env.globals["diagnostic_radar"] = ui_charts.diagnostic_radar

app.jinja_env.globals["is_admin_user"] = lambda: roles.is_admin(g.user)   # 메뉴 표시용 (권한 검사는 서버에서 따로)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


_BOOT_AT = time.time()          # 서버리스 인스턴스가 시작된 시각 (콜드 스타트 측정용)
_SERVED = {"count": 0}


@app.before_request
def _start_timer():
    g._t0 = time.perf_counter()


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
    if config.env("ECONOVA_TIMING_HEADERS") == "1":   # 콜드 스타트 측정 (끝나면 끈다). 비밀값·사용자 정보는 넣지 않는다.
        _SERVED["count"] += 1
        dur = (time.perf_counter() - g.get("_t0", time.perf_counter())) * 1000
        resp.headers["Server-Timing"] = f"app;dur={dur:.1f}"
        resp.headers["X-Econova-Instance"] = (f"{'cold' if _SERVED['count'] == 1 else 'warm'}; "
                                              f"age={time.time() - _BOOT_AT:.0f}s; served={_SERVED['count']}")
    return resp


# --------------------------------------------------------------- routes
@app.route("/")
def index():
    if g.user:
        return redirect(url_for("dashboard"))
    # 랜딩 페이지에는 실제 강좌(c01~c09)의 제목·SDG·공개 여부만 보여 준다. 개발용 테스트 강좌는 제외한다.
    # 강좌 JSON 을 읽지 못해도 공개 첫 화면은 열려야 하므로, 그때는 강좌 목록 없이 보여 준다.
    try:
        cat = learning.catalog()
        real, sdgs = [c for c in cat.visible() if not getattr(c, "fixture", False)], cat.sdgs
    except content.ContentError as exc:
        app.logger.error("Landing page: course content unavailable: %s", exc)
        real, sdgs = [], {}
    return render_template("index.html", landing_courses=real, sdg_info=sdgs)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = None
        if not name:
            error = "Please enter your name."
        elif len(name) > 50:
            error = "Your name must be 50 characters or fewer."
        elif len(email) > 254 or not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Your password must be at least 8 characters."
        elif len(password) > 256:
            error = "Your password is too long (256 characters max)."
        elif password != confirm:
            error = "The passwords don't match."

        if error is None:
            try:
                create_user(email, name, generate_password_hash(password, method="pbkdf2:sha256"))
            except DuplicateEmailError:
                error = "An account with this email already exists."
            else:
                flash("Your account has been created. Please log in.", "success")
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
            flash("Too many login attempts. Please wait about 15 minutes and try again.", "error")
            return render_template("login.html", email=email), 429
        user = get_user_by_email(email)
        if user is None or not check_password_hash(user["password_hash"], password):
            login_guard.record_failure(email)
            flash("Incorrect email or password.", "error")
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


# --------------------------------------------------------------- Google 로그인
def _google_redirect_uri():
    return google_auth.settings()["redirect_uri"] or url_for("google_callback", _external=True)


def _start_session(user):
    session.clear()                 # 로그인할 때 세션을 새로 만든다 (세션 고정 공격 방지)
    session["user_id"] = user["id"]


@app.route("/auth/google")
def google_login():
    """Google 로그인·가입 시작 (로그인하지 않은 상태)."""
    if not google_auth.enabled():
        abort(404)
    if g.user:
        return redirect(url_for("dashboard"))
    return redirect(google_auth.begin(session, "login", _google_redirect_uri()))


@app.route("/account/google/link", methods=["POST"])
@login_required
def google_link_start():
    """로그인한 계정에 Google 계정을 연결하기 시작한다 (POST + CSRF 토큰: 다른 사이트가 몰래 연결을 시작하지 못하게)."""
    if not google_auth.enabled():
        abort(404)
    if storage.get_identity_for_user(google_auth.PROVIDER, g.user["id"]):
        flash("A Google account is already linked to your ECONOVA account.", "error")
        return redirect(url_for("account"))
    return redirect(google_auth.begin(session, "link", _google_redirect_uri(), user_id=g.user["id"]))


@app.route("/auth/google/callback")
def google_callback():
    if not google_auth.enabled():
        abort(404)
    try:
        pending = google_auth.take_pending(session, request.args.get("state", ""))
    except google_auth.GoogleAuthError as exc:
        app.logger.warning("Google sign-in rejected: %s", exc)
        flash("Google sign-in could not be completed. Please try again.", "error")
        return redirect(url_for("login"))
    if request.args.get("error") or not request.args.get("code"):
        flash("Google sign-in was cancelled.", "error")
        return redirect(url_for("account") if pending["intent"] == "link" else url_for("login"))
    try:
        token = google_auth.exchange_code(request.args["code"], pending["verifier"], pending["redirect_uri"])
        claims = google_auth.verify_id_token(token, pending["nonce"])
    except google_auth.GoogleAuthError as exc:
        app.logger.warning("Google sign-in rejected: %s", exc)
        flash("Google sign-in could not be completed. Please try again.", "error")
        return redirect(url_for("account") if pending["intent"] == "link" else url_for("login"))
    sub, email = str(claims["sub"]), str(claims.get("email", "")).strip().lower()
    identity = storage.get_identity(google_auth.PROVIDER, sub)

    if pending["intent"] == "link":
        if g.user is None or g.user["id"] != pending.get("user_id"):
            flash("Please log in again before linking a Google account.", "error")
            return redirect(url_for("login"))
        if identity is not None:
            same = identity["user_id"] == g.user["id"]
            flash("This Google account is already linked to your ECONOVA account." if same else
                  "This Google account is already linked to a different ECONOVA account.", "success" if same else "error")
            return redirect(url_for("account"))
        try:
            storage.create_identity(google_auth.PROVIDER, sub, g.user["id"], email_at_link=email, created_account=False)
        except storage.IdentityConflict:
            flash("A Google account is already linked to your ECONOVA account.", "error")
            return redirect(url_for("account"))
        flash("Your Google account is now linked. You can use \"Continue with Google\" to log in.", "success")
        return redirect(url_for("account"))

    # intent == "login": 연결된 계정이 있으면 그 계정으로, 없으면 새 계정을 만든다 (이메일이 같아도 자동 병합하지 않음)
    if identity is not None:
        user = get_user_by_id(identity["user_id"])
        if user is None:
            flash("The ECONOVA account linked to this Google account no longer exists.", "error")
            return redirect(url_for("login"))
        _start_session(user)
        return redirect(url_for("dashboard"))
    if len(email) > 254 or not EMAIL_RE.match(email):
        flash("Your Google account did not share a valid email address.", "error")
        return redirect(url_for("login"))
    if get_user_by_email(email) is not None:
        flash("An ECONOVA account already uses this email. Log in with your email and password, "
              "then link Google from your Account page.", "error")
        return redirect(url_for("login"))
    name = (str(claims.get("name") or "").strip() or email.split("@")[0])[:50]
    try:
        # Google 로 만든 계정에는 아무도 모르는 무작위 비밀번호를 둔다 (비밀번호 로그인은 쓸 수 없음)
        create_user(email, name, generate_password_hash(secrets.token_urlsafe(32), method="pbkdf2:sha256"))
    except DuplicateEmailError:
        flash("An ECONOVA account already uses this email. Log in with your email and password, "
              "then link Google from your Account page.", "error")
        return redirect(url_for("login"))
    user = get_user_by_email(email)
    try:
        storage.create_identity(google_auth.PROVIDER, sub, user["id"], email_at_link=email, created_account=True)
    except storage.IdentityConflict:      # 동시에 두 번 눌러 다른 요청이 먼저 연결한 경우
        identity = storage.get_identity(google_auth.PROVIDER, sub)
        user = get_user_by_id(identity["user_id"]) if identity else None
        if user is None:
            flash("Google sign-in could not be completed. Please try again.", "error")
            return redirect(url_for("login"))
    _start_session(user)
    flash("Welcome to ECONOVA! Your account was created with Google.", "success")
    return redirect(url_for("dashboard"))


@app.route("/account")
@login_required
def account():
    identity = storage.get_identity_for_user(google_auth.PROVIDER, g.user["id"])
    return render_template("account.html", identity=identity)


@app.route("/account/google/unlink", methods=["POST"])
@login_required
def google_unlink():
    identity = storage.get_identity_for_user(google_auth.PROVIDER, g.user["id"])
    if identity is None:
        return redirect(url_for("account"))
    if identity["created_account"]:
        # Google 로 만든 계정은 비밀번호가 없어서, 연결을 끊으면 다시 로그인할 방법이 없다
        flash("This account was created with Google, so Google is its only way to log in. It can't be unlinked.", "error")
        return redirect(url_for("account"))
    storage.delete_identity(google_auth.PROVIDER, g.user["id"])
    flash("Your Google account was unlinked. Log in with your email and password from now on.", "success")
    return redirect(url_for("account"))


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


@app.errorhandler(405)
def method_not_allowed(_exc):
    return render_template("errors/error.html", code=405, title="This action isn't available here",
                           message="Use the buttons on the page instead of opening this address directly."), 405


@app.errorhandler(500)
def server_error(_exc):
    # 어떤 경우에도 내부 정보(예외 내용)는 보여 주지 않는다
    try:
        return render_template("errors/error.html", code=500, title="Something went wrong",
                               message="The problem was recorded. Please try again in a moment."), 500
    except Exception:  # noqa: BLE001 — 템플릿까지 실패하면 가장 단순한 응답
        return "Something went wrong. Please try again in a moment.", 500


@app.cli.command("init-db")
def init_db_command():
    """로컬 sqlite 테이블을 만든다(마이그레이션): flask --app app init-db
    Firestore 는 스키마가 없어 할 일이 없다 (문서를 처음 쓸 때 만들어진다). 앱 import 때는 실행되지 않는다."""
    if using_firestore():
        click.echo("DB_BACKEND=firestore: there are no tables to create. Nothing was changed.")
        return
    init_db()
    click.echo(f"Initialized the {config.db_backend()} storage.")


@app.cli.command("check-content")
def check_content_command():
    """강좌 JSON(content/)을 검사한다. 실제 강좌와 개발용 테스트 강좌 파일을 모두 읽는다.
    배포 전에 실행: flask --app app check-content  (문제가 있으면 종료 코드 1)"""
    try:
        real = content.load_catalog(include_fixtures=False)
        with_fixtures = content.load_catalog(include_fixtures=True)
    except content.ContentError as exc:
        raise click.ClickException(f"Course content error: {exc}")
    fixtures = [c for c in with_fixtures.courses if c.fixture]
    click.echo(f"Course content OK: {len(real.courses)} real course(s) ({sum(len(c.lessons) for c in real.courses)} lesson(s), "
               f"{len(real.published())} published), {len(fixtures)} dev test course(s)")
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
        closed.append(f"Diagnostic assessment: {test['keys_problem']}")
    for line in closed:
        click.echo(f"  [No answer key -> cannot be taken] {line}")
    click.echo(f"Answer key check: {len(closed)} assessment(s) cannot be opened" if closed else "Answer key check: every assessment has an answer key.")
    if blocking:
        raise click.ClickException(f"Approved assessments are missing answer keys: {', '.join(blocking)}")


# ---------------------------------------------------------------- 플랫폼 관리자 (Phase 7)
# 관리자 권한은 웹에서 바꿀 수 없다. 서버 셸에 접근할 수 있는 운영자가 본인 확인을 거친 뒤 CLI 로만 부여한다.
# 가입 이메일은 소유 확인을 하지 않으므로 "이 이메일이면 관리자" 같은 자동 부여는 하지 않는다.
@app.cli.command("admin-grant")
@click.argument("email")
@click.option("--operator", required=True, help="Name of the operator granting access (recorded in the audit log)")
@click.option("--verification", required=True,
              help="How you confirmed the account owner's identity (e.g., 'Verified in person 2026-11-05; saw the account's logged-in screen')")
@click.option("--note", default="", help="Note")
def admin_grant_command(email, operator, verification, note):
    """이미 가입한 계정에 플랫폼 관리자 권한을 준다. 확인 문구를 직접 입력해야 한다."""
    email = email.strip().lower()
    if len(verification.strip()) < 10 or len(operator.strip()) < 2:
        raise click.ClickException("Give a specific operator name and identity-verification method (at least 10 characters).")
    if config.is_production() and config.env("ECONOVA_ALLOW_ADMIN_BOOTSTRAP").strip() != "1":
        raise click.ClickException("In production, ECONOVA_ALLOW_ADMIN_BOOTSTRAP=1 must be set temporarily for this command only.")
    user = get_user_by_email(email)
    if user is None:
        raise click.ClickException("No account is registered with that email. The user must sign up first.")
    typed = click.prompt(f"Re-enter the email of the account to make an admin ({email})", default="", show_default=False)
    if typed.strip().lower() != email:
        raise click.ClickException("The confirmation email does not match. Nothing was changed.")
    storage.grant_admin(user["id"], operator.strip(), verification.strip(), note.strip())
    click.echo(f"Granted admin access: {email} (granted by {operator.strip()})")


@app.cli.command("admin-revoke")
@click.argument("email")
def admin_revoke_command(email):
    """관리자 권한을 취소한다 (계정은 학생으로 돌아간다. 부여 기록은 취소 시각과 함께 남는다)."""
    user = get_user_by_email(email.strip().lower())
    if user is None:
        raise click.ClickException("No account is registered with that email.")
    storage.revoke_admin(user["id"])
    click.echo(f"Revoked admin access: {email}")


@app.cli.command("admin-list")
def admin_list_command():
    """현재 관리자 계정 목록 (운영자 확인용)."""
    ids = storage.list_admin_user_ids()
    for uid in ids:
        user = get_user_by_id(uid)
        grant = storage.get_admin_grant(uid)
        click.echo(f"- {user['email'] if user else uid} · granted {grant['granted_at']} by {grant['granted_by']}")
    click.echo(f"{len(ids)} admin(s)")


@app.cli.command("content-release-apply")
@click.argument("plan_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, help="Check only; do not change any files")
@click.option("--trust-plan", is_flag=True,
              help="When this DB has no review records (a plan exported from production): apply only plans whose signature verifies with ECONOVA_RELEASE_SIGNING_KEY")
def content_release_apply_command(plan_file, dry_run, trust_plan):
    """관리 화면에서 내려받은 릴리스 계획을 정본 JSON 의 review 블록에 반영한다 (개발 환경 전용, 웹에서는 불가).
    항목마다 지금 파일의 내용 지문이 승인 때와 같은지 다시 확인하고, 다르면 건너뛴다. 반영 뒤에는 check-content 와
    테스트를 돌리고, 사람이 diff 를 확인한 뒤 커밋한다."""
    import json as _json
    from econova import admin_content
    if config.is_production():
        raise click.ClickException("Canonical content files are never changed in production. Apply the plan in development and deploy with Git.")
    with open(plan_file, encoding="utf-8") as f:
        plan = _json.load(f)
    signed_ok = admin_content.plan_signature_ok(plan, config.env("ECONOVA_RELEASE_SIGNING_KEY"))

    def verify(item):
        """(문제, DB 가 정한 값). DB 에 기록이 있으면 검토자·날짜·번호를 DB 에서 가져온다 (계획의 값은 믿지 않는다).
        DB 에 없으면 --trust-plan 과 유효한 서명이 둘 다 있어야 한다 (서명 없는·고친 계획으로 승인을 만들 수 없게)."""
        record = storage.get_content_review(item["review_id"])
        if record is None:
            if not trust_plan:
                return "No review record in this DB (use --trust-plan for a signed plan exported from production)", None
            if not signed_ok:
                return "Plan signature missing or invalid (check ECONOVA_RELEASE_SIGNING_KEY) — not applied", None
            return None, None
        if (record["decision"], record["content_digest"], record["target_type"], record["target_id"]) != \
                ("approve", item["content_digest"], item["target_type"], item["target_id"]):
            return "Plan does not match the review record", None
        if storage.get_admin_grant(record["reviewer_user_id"]) is None:
            return "The approving admin's access was revoked — needs a new review", None
        later = admin_content.superseded_by(record, storage.list_content_reviews(item["target_type"], item["target_id"]))
        if later is not None:   # 승인 뒤에 '다시 검토'·'수정 요청' 이 기록됐다면 이 승인은 반영하지 않는다
            return f"'{admin_content.DECISION_KO.get(later['decision'], later['decision'])}' (#{later['id']}) was recorded after the approval", None
        return None, {"review_id": record["id"], "reviewer_name": record["reviewer_name"],
                      "approved_at": record["created_at"].strftime("%Y-%m-%d") if record["created_at"] else ""}
    try:
        results = admin_content.apply_release(plan, verify_record=verify, dry_run=dry_run)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    for item, result in results:
        click.echo(f"- {item['target_type']}:{item['target_id']} → {result}")
    content.load_catalog.cache_clear()
    click.echo("After applying, run flask --app app check-content and the tests, then review the diff.")


@app.cli.command("content-verify-approvals")
@click.option("--include-fixtures", is_flag=True, help="Also check dev fixtures")
def content_verify_approvals_command(include_fixtures):
    """정본 JSON 의 관리자 승인(합격 기준 포함)이 모두 DB 의 검토 기록으로 뒷받침되는지 확인한다 (읽기만 함).
    배포 직후 운영 환경에서 실행한다. 기록이 없거나 지문이 다르면 종료 코드 1."""
    from econova import admin_content
    approvals = admin_content.canonical_admin_approvals(include_fixtures)
    problems = admin_content.verify_canonical_approvals(
        storage.get_content_review, include_fixtures, list_reviews=storage.list_content_reviews,
        reviewer_active=lambda uid: storage.get_admin_grant(uid) is not None)
    for t, why in problems:
        click.echo(f"  [Verification failed] {t.type}:{t.id} — {why}")
    if problems:
        raise click.ClickException(f"{len(problems)} canonical approval(s) could not be verified")
    click.echo(f"All {len(approvals)} canonical admin approval(s) match the DB review records.")


@app.cli.command("ai-purge")
def ai_purge_command():
    """보존 기간(ECONOVA_AI_RETENTION_DAYS, 기본 30일)이 지난 AI 대화 메시지와 오래된 사용량 기록을 지운다.
    점수·진도·수강 기록은 건드리지 않는다. 운영에서는 Render Cron Job 등으로 매일 실행한다."""
    r = _daily_cleanup()
    click.echo(f"AI data cleanup: deleted {r['messages']} message(s) older than {r['days']} days and {r['conversations']} empty conversation(s).")
    click.echo(f"Login failure cleanup: deleted {r['login_counters']} expired record(s).")


def _daily_cleanup():
    """ai-purge 와 Vercel Cron 이 같이 쓰는 정리 작업. 여러 번 실행해도 결과가 같다 (Vercel Cron 은 중복 실행될 수 있다)."""
    from econova.ai import client as ai_client
    days = ai_client.settings().retention_days
    before = storage._utcnow() - datetime.timedelta(days=days)
    msgs, convs = storage.purge_ai_data(before, usage_before=storage._utcnow() - datetime.timedelta(days=max(days, 90)))
    n = storage.purge_login_counters(storage._utcnow())
    return {"days": days, "messages": msgs, "conversations": convs, "login_counters": n}


@app.route("/internal/cron/daily-cleanup")
def cron_daily_cleanup():
    """Vercel Cron 전용 (vercel.json). CRON_SECRET 이 없으면 404, Authorization: Bearer 값이 다르면 401.
    학생 기록(점수·진도·수강)은 건드리지 않는다."""
    expected = config.env("CRON_SECRET").strip()
    if not expected:
        abort(404)
    sent = request.headers.get("Authorization", "")
    if not secrets.compare_digest(sent.encode(), f"Bearer {expected}".encode()):
        abort(401)
    result = _daily_cleanup()
    app.logger.info("Daily cleanup: %s", result)
    return {"ok": True, **result}


@app.cli.command("private-keys-bundle")
@click.option("--output", required=True, type=click.Path(dir_okay=False),
              help="File to write (must be outside the repository; never commit it)")
def private_keys_bundle_command(output):
    """비공개 폴더의 정답 키를 서버리스 배포용 묶음(gzip+base64) 한 개로 만든다 (Vercel 의 Sensitive 환경변수
    ECONOVA_PRIVATE_KEYS_BUNDLE 또는 Secret Manager 비밀 값으로 쓴다). 화면에는 개수·크기·지문만 출력한다.
    공개 평가 파일과 맞지 않는 키가 하나라도 있으면 만들지 않는다."""
    import glob as _glob
    import hashlib as _hashlib
    from econova import private_content
    out = os.path.realpath(os.path.expanduser(output))
    if out == os.path.realpath(config.BASE_DIR) or out.startswith(os.path.realpath(config.BASE_DIR) + os.sep):
        raise click.ClickException("Write the bundle outside the repository so answer keys are never committed.")
    keys, problems = {}, []
    publics = sorted(_glob.glob(os.path.join(content.CONTENT_DIR, "assessments", "*.json"))) + [os.path.join(content.CONTENT_DIR, "diagnostic.json")]
    for path in publics:
        with open(path, encoding="utf-8") as f:
            public = json.load(f)
        try:
            data = private_content.read_keys(public["id"])
            private_content.merge(public, data, os.path.relpath(path, content.CONTENT_DIR))
            keys[public["id"]] = data
        except private_content.KeysUnavailable as exc:
            problems.append(str(exc))
    if problems:
        raise click.ClickException("Not written; keys missing or out of date:\n  " + "\n  ".join(problems))
    text = private_content.encode_bundle(keys)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        f.write(text)
    os.chmod(out, 0o600)
    click.echo(f"Wrote {len(keys)} answer keys: {len(text):,} characters (Vercel limits the total size of all environment variables), "
               f"sha256 {_hashlib.sha256(text.encode()).hexdigest()[:16]} -> {out}")


@app.cli.command("check-public-files")
@click.option("--staged", is_flag=True, help="Check only staged files (same as the pre-commit hook)")
def check_public_files_command(staged):
    """공개 저장소에 올리면 안 되는 내용(정답 키·교사용 검토 문서·API 키)이 커밋 대상에 있는지 검사한다."""
    from econova import public_safety
    if public_safety.main(["--staged"] if staged else []):
        raise click.ClickException("Found content that must not be committed.")


@app.cli.command("review-package")
@click.argument("course_id")
@click.option("--output", "-o", default=None, type=click.Path(dir_okay=False),
              help="Path of the Markdown file to create. Default: <private folder>/review/<course>-review-package.md")
def review_package_command(course_id, output):
    """교사용 교육 검토 문서(정답 포함)를 만든다. 학생 화면으로는 제공하지 않는다. 어떤 자료도 승인하지 않는다.
    정답이 들어 있으므로 저장소 밖(비공개 폴더)이나, 저장소 안이라면 git 이 무시하는 곳에만 쓴다."""
    import datetime
    from econova import public_safety, review_package
    if output is None:
        private_dir = config.private_content_dir()
        if not private_dir:
            raise click.ClickException("No private folder (ECONOVA_PRIVATE_CONTENT_DIR) is set, so there is no default location. Use -o to choose one.")
        output = os.path.join(private_dir, "review", f"{course_id}-review-package.md")
    inside, ignored = public_safety.is_ignored_inside_repo(output)
    if inside and not ignored:
        raise click.ClickException(f"{output} is inside the repository where it could be committed. Not writing it, because the answers could become public. "
                                   "Choose the private folder or a folder git ignores (docs/review/).")
    catalog = content.load_catalog(include_fixtures=False)
    course = catalog.course(course_id)
    if course is None:
        raise click.ClickException(f"Course {course_id!r} does not exist.")
    try:
        text = review_package.build(course, catalog.sources, datetime.date.today().isoformat())
    except review_package.KeysMissing as exc:
        raise click.ClickException(str(exc))
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    click.echo(f"Created the review document: {output}")


if __name__ == "__main__":
    if not using_firestore():  # 로컬 sqlite 는 편의상 실행할 때 준비한다 (import 할 때는 하지 않는다)
        with app.app_context():
            init_db()
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
