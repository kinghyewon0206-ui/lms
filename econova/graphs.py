"""수요·공급 그래프의 좌표 계산 (결정적). 템플릿은 이 결과로 SVG 를 그린다.

선형 수요 Q = a − bP, 공급 Q = c + dP. 세로축 가격 P, 가로축 수량 Q (경제학 관례).
"""

WIDTH, HEIGHT, PAD = 520, 340, 46


def _x(q, q_max):
    return round(PAD + q / q_max * (WIDTH - 2 * PAD), 1)


def _y(p, p_max):
    return round(HEIGHT - PAD - p / p_max * (HEIGHT - 2 * PAD), 1)


def _segment(q_at, p_lo, p_hi, p_max, q_max):
    """가격 구간 [p_lo, p_hi] 에서 0 ≤ Q ≤ q_max 인 부분만 잘라 낸 선분. 없으면 None."""
    lo, hi = max(0.0, p_lo), min(p_max, p_hi)
    if lo >= hi:
        return None
    pts = [(q_at(lo), lo), (q_at(hi), hi)]
    if any(q < 0 or q > q_max + 1e-9 for q, _ in pts):
        return None
    return {"x1": _x(pts[0][0], q_max), "y1": _y(pts[0][1], p_max), "x2": _x(pts[1][0], q_max), "y2": _y(pts[1][1], p_max)}


def geometry(spec):
    p_max, q_max = float(spec["axis"]["p_max"]), float(spec["axis"]["q_max"])
    lines = []
    for d in spec["demand"]:
        a, b = float(d["a"]), float(d["b"])
        # Q = a − bP 가 [0, q_max] 안에 있는 가격 구간: (a − q_max)/b ≤ P ≤ a/b
        seg = _segment(lambda p: a - b * p, (a - q_max) / b, a / b, p_max, q_max)
        if seg:
            lines.append({**seg, "label": d["label"], "kind": "demand"})
    for s in spec["supply"]:
        c, d = float(s["c"]), float(s["d"])
        seg = _segment(lambda p: c + d * p, -c / d, (q_max - c) / d, p_max, q_max)
        if seg:
            lines.append({**seg, "label": s["label"], "kind": "supply", "label_side": s.get("label_side", "right")})
    points = [{"x": _x(e["quantity"], q_max), "y": _y(e["price"], p_max), "price": e["price"], "quantity": e["quantity"],
               "label": f"{e['demand']}·{e['supply']}"} for e in spec.get("expected_equilibria", [])]
    price_lines = [{"y": _y(pl["price"], p_max), "x1": PAD, "x2": WIDTH - PAD, "label": pl["label"], "price": pl["price"]}
                   for pl in spec.get("price_lines", []) if 0 <= pl["price"] <= p_max]
    ticks_p = [round(p_max * i / 4, 2) for i in range(5)]
    ticks_q = [round(q_max * i / 4, 2) for i in range(5)]
    return {
        "width": WIDTH, "height": HEIGHT, "pad": PAD, "lines": lines, "points": points, "price_lines": price_lines,
        "p_ticks": [{"v": _fmt(t), "y": _y(t, p_max)} for t in ticks_p],
        "q_ticks": [{"v": _fmt(t), "x": _x(t, q_max)} for t in ticks_q],
        "p_label": spec["axis"].get("p_label", "P"), "q_label": spec["axis"].get("q_label", "Q"),
        "origin": {"x": PAD, "y": HEIGHT - PAD}, "right": WIDTH - PAD, "top": PAD,
    }


def _fmt(v):
    return str(int(v)) if float(v).is_integer() else f"{v:g}"
