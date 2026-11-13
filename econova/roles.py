"""사용자 역할 (Phase 7). ECONOVA 는 자기주도 학습 플랫폼이라 역할은 두 가지뿐이다.

- student (기본): 회원가입하면 누구나. 자기 학습 기록만 본다. 콘텐츠 승인·정답 키에 접근할 수 없다.
- admin (플랫폼 관리자): 교육 콘텐츠의 품질을 관리한다. 학생을 감독하지 않으며, 개별 학생의 학습 기록·대화를
  보는 화면은 없다 (집계 숫자만).

기존 기록 호환: users.role 에 'teacher' 등 예전 값이 있어도 지우거나 바꾸지 않는다. 그런 계정은 학생과 같은 권한이다
(교사 계정을 관리자로 자동 전환하지 않는다).

관리자 판정은 매 요청마다 저장소에서 다시 읽는다: role='admin' 이고, 취소되지 않은 관리자 부여 기록(econ_admin_grants)이
있어야 한다. 부여는 서버 셸의 CLI(flask admin-grant)로만 하며, 이메일만으로 자동 부여하지 않는다 (가입 이메일은 소유 확인을
하지 않으므로). 브라우저가 보낸 역할 값은 어디에서도 읽지 않는다.
"""
from functools import wraps

from flask import abort, g

from econova import storage
from econova.auth import login_required

STUDENT, ADMIN = "student", "admin"
LEGACY_ROLES = ("teacher",)   # 예전 값: 보존하되 특별한 권한 없음


def role_of(user):
    return (user["role"] if user is not None and "role" in user.keys() else None) or STUDENT


def is_admin(user):
    if user is None or role_of(user) != ADMIN:
        return False
    return storage.get_admin_grant(user["id"]) is not None


def admin_required(view):
    """관리자만. 다른 사용자에게는 관리 화면이 있는지도 알리지 않는다 (404)."""
    @login_required
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin(g.user):
            abort(404)
        return view(*args, **kwargs)

    return wrapped
