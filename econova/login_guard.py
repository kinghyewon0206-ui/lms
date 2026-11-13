"""로그인 시도 제한 (Phase 8B-1).

세 가지 카운터를 15분 구간으로 센다 (지금 구간 + 바로 전 구간 → 15~30분 창). 실패만 세고, 성공하면 그 계정+IP 카운터를 지운다.
- 계정+IP   : 같은 기기·네트워크에서 한 계정의 비밀번호를 계속 틀림 (기본 10)
- 계정      : 여러 곳에서 한 계정을 노림 (기본 50). 이전에 이 브라우저로 로그인에 성공했다는 서명 쿠키가 있으면 이 제한은
              건너뛴다 → 공격자가 일부러 실패를 쌓아 진짜 주인을 잠그기 어렵다 (계정+IP 제한은 그대로 적용)
- IP        : 한 곳에서 여러 계정을 노림 (기본 200). 학교·공공 네트워크는 많은 학생이 같은 IP 를 쓰므로 넉넉하게 둔다
              (40명이 각각 두세 번 틀려도 막히지 않음)

클라이언트 IP: 기본은 request.remote_addr (프록시 헤더를 믿지 않음). Render 처럼 앞단 프록시가 있으면 그 수를
ECONOVA_TRUSTED_PROXY_HOPS 로 지정해야만 X-Forwarded-For 의 오른쪽에서 그만큼 떨어진 값을 쓴다 (클라이언트가 왼쪽에
마음대로 넣은 값은 쓰지 않음). 키는 해시라 이메일·IP 원문을 저장하지 않는다. 만료 기록은 purge 명령이 지운다.
"""
import datetime
import hashlib
import ipaddress

from flask import current_app, request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from econova import config, storage

BUCKET_SECONDS = 15 * 60
DEVICE_COOKIE = "econova_known_login"
DEVICE_MAX_AGE = 60 * 60 * 24 * 30


def _limit(name, default, lo=1, hi=100000):
    try:
        value = int(config.env(name) or default)
    except ValueError:
        raise config.ConfigError(f"{name} must be an integer.")
    if not lo <= value <= hi:
        raise config.ConfigError(f"{name} must be between {lo} and {hi}.")
    return value


def limits():
    return {"account_ip": _limit("ECONOVA_LOGIN_MAX_PER_ACCOUNT_IP", 10),
            "account": _limit("ECONOVA_LOGIN_MAX_PER_ACCOUNT", 50),
            "ip": _limit("ECONOVA_LOGIN_MAX_PER_IP", 200)}


def trusted_proxy_hops():
    return _limit("ECONOVA_TRUSTED_PROXY_HOPS", 0, lo=0, hi=5)


def client_ip():
    """신뢰할 수 있는 클라이언트 IP. 프록시를 설정하지 않았으면 X-Forwarded-For 를 무시한다."""
    hops = trusted_proxy_hops()
    remote = request.remote_addr or "unknown"
    if hops:
        chain = [p.strip() for p in request.headers.get("X-Forwarded-For", "").split(",") if p.strip()]
        if len(chain) >= hops:
            candidate = chain[-hops]   # 신뢰하는 프록시가 덧붙인 값 (왼쪽의 위조 가능한 값은 무시)
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                return remote
    return remote


def ip_candidates(max_hops=3):
    """프록시 홉 수 확인용 (관리자 진단 화면): 홉 수 0~max_hops 일 때 각각 어떤 주소를 클라이언트로 볼지.
    추측하지 않고, 사람이 알고 있는 자기 공인 IP 와 비교해 맞는 홉 수를 고르게 한다."""
    remote = request.remote_addr or "unknown"
    chain = [p.strip() for p in request.headers.get("X-Forwarded-For", "").split(",") if p.strip()]
    out = [{"hops": 0, "ip": remote, "note": "Direct connection address (X-Forwarded-For ignored)"}]
    for hops in range(1, max_hops + 1):
        if len(chain) < hops:
            out.append({"hops": hops, "ip": remote, "note": "List too short; using the direct connection address"})
            continue
        try:
            out.append({"hops": hops, "ip": str(ipaddress.ip_address(chain[-hops])), "note": f"Entry {hops} from the right"})
        except ValueError:
            out.append({"hops": hops, "ip": remote, "note": "Not a valid IP; using the direct connection address"})
    return {"remote_addr": remote, "chain": chain, "candidates": out, "configured": trusted_proxy_hops()}


def _h(*parts):
    return hashlib.sha256(("login|" + "|".join(parts)).encode("utf-8")).hexdigest()[:40]


def _keys(kind, ident, now):
    bucket = int(now.replace(tzinfo=datetime.timezone.utc).timestamp()) // BUCKET_SECONDS
    return [f"{kind}:{_h(kind, ident)}:{bucket}", f"{kind}:{_h(kind, ident)}:{bucket - 1}"]


def _idents(email, ip):
    email = str(email or "").strip().lower()
    return {"account_ip": f"{email}|{ip}", "account": email, "ip": ip}


def known_device(email):
    """이 브라우저가 이 계정으로 최근 로그인에 성공했는가 (서명된 쿠키)."""
    raw = request.cookies.get(DEVICE_COOKIE)
    if not raw:
        return False
    try:
        data = _serializer().loads(raw, max_age=DEVICE_MAX_AGE)
    except BadSignature:
        return False
    return data == _h("device", str(email or "").strip().lower())


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="econova-known-login")


def device_cookie_value(email):
    return _serializer().dumps(_h("device", str(email or "").strip().lower()))


def blocked(email, now=None):
    """막아야 하면 이유 코드('account_ip' | 'account' | 'ip'), 아니면 None."""
    now = now or storage._utcnow()
    lim, ids = limits(), _idents(email, client_ip())
    for kind in ("account_ip", "ip", "account"):
        if kind == "account" and known_device(email):
            continue
        if storage.sum_login_counters(_keys(kind, ids[kind], now), now) >= lim[kind]:
            return kind
    return None


def record_failure(email, now=None):
    now = now or storage._utcnow()
    expires = now + datetime.timedelta(seconds=2 * BUCKET_SECONDS)
    for kind, ident in _idents(email, client_ip()).items():
        storage.incr_login_counter(_keys(kind, ident, now)[0], expires)


def record_success(email, now=None):
    """성공하면 이 계정+IP 카운터만 지운다 (계정·IP 전체 카운터는 다른 시도가 섞여 있으므로 그대로)."""
    now = now or storage._utcnow()
    storage.delete_login_counters(_keys("account_ip", _idents(email, client_ip())["account_ip"], now))
