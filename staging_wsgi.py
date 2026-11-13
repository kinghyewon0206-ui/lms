"""Render 확인용(staging) 서비스의 시작점: `gunicorn staging_wsgi:app`.

운영 서비스는 `gunicorn app:app` 으로 시작하므로 이 파일을 쓰지 않는다. 여기서는 같은 ECONOVA 앱에 프록시 진단 경로
(econova/proxy_diagnostics.py) 하나만 더한다. 켜는 조건과 절차는 docs/render-proxy-staging.md.
"""
from app import app
from econova import proxy_diagnostics

proxy_diagnostics.install(app)
