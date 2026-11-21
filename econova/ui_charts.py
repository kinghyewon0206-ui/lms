"""Small, deterministic chart geometry for templates (no client-side charting library).

radar(): points for a radar chart from real per-area results. Values are fractions 0..1; labels come from the caller.
"""
import math


def radar(values, cx=150, cy=132, r=92):
    """values: [(label, fraction)] -> geometry dict for an SVG radar (axes, rings, polygon, labels)."""
    n = len(values)
    if n < 3:
        return None
    pts, axes, labels, rings = [], [], [], []
    for i, (label, v) in enumerate(values):
        a = -math.pi / 2 + 2 * math.pi * i / n
        ca, sa = math.cos(a), math.sin(a)
        axes.append((round(cx + r * ca, 1), round(cy + r * sa, 1)))
        rv = max(min(float(v), 1.0), .06)
        pts.append((round(cx + r * rv * ca, 1), round(cy + r * rv * sa, 1)))
        labels.append({"x": round(cx + (r + 18) * ca, 1), "y": round(cy + (r + 18) * sa + 4, 1), "text": label, "lines": _two_lines(label),
                       "pct": int(round(float(v) * 100)), "anchor": "middle" if abs(ca) < .3 else ("start" if ca > 0 else "end")})
    for f in (.25, .5, .75, 1):
        rings.append(" ".join(f"{cx + r * f * math.cos(-math.pi / 2 + 2 * math.pi * i / n):.1f},"
                              f"{cy + r * f * math.sin(-math.pi / 2 + 2 * math.pi * i / n):.1f}" for i in range(n)))
    return {"cx": cx, "cy": cy, "points": pts, "poly": " ".join(f"{x},{y}" for x, y in pts), "axes": axes,
            "labels": labels, "rings": rings}


def _two_lines(label, width=14):
    """Short labels stay on one line; longer ones are split near the middle at a word boundary."""
    if len(label) <= width or " " not in label:
        return [label]
    words, best = label.split(), None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = max(len(a), len(b))
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1]


def diagnostic_radar(attempt, names):
    """Radar from a diagnostic attempt's by_category results (real data only). None when there is no attempt."""
    if not attempt or not attempt.get("by_category"):
        return None
    vals = [(names.get(cid, cid), (v["correct"] / v["total"]) if v.get("total") else 0.0)
            for cid, v in attempt["by_category"].items()]
    return radar(vals)
