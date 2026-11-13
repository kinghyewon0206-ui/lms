"""로그인 확인 데코레이터. app.py 와 econova/web.py 가 같이 쓴다."""
from functools import wraps

from flask import flash, g, redirect, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped
