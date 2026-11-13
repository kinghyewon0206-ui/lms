"""경제 시뮬레이션 계산 엔진 (결정적 순수 함수). 외부 API·AI 를 쓰지 않는다.
static/js/econova-sim.js 가 같은 공식·같은 반올림을 구현하고, tests 가 두 구현이 같은 값을 내는지 확인한다.

단위 (모두 가상의 교육용 모형이며 실제 통계가 아니다)
- 가격 P, 세금 t, 외부 피해 md: 원 / 개 (가상의 화폐 단위)
- 수량 Q: 개
- 배출량: 배출 계수 e (kg / 개) × 수량

모형
- 수요 Qd = a − bP, 공급 Qs = c + dP  (a > 0, b > 0, d > 0)
- 균형 P* = (a − c)/(b + d), Q* = a − bP*
- 생산자에게 단위당 세금 t: Qs = c + d(P − t)
  소비자 가격 Pc = (a − c + d·t)/(b + d), 생산자 가격 Pp = Pc − t, 거래량 Qt = a − b·Pc, 세수 = t·Qt
- 시장 내부 손실(사중손실, 외부효과가 없다고 가정) = ½ · t · (Q* − Qt)
- 외부 피해(단위당 md, 일정하다고 가정)를 넣으면 사회적 후생 변화 = md·(Q* − Qt) − 사중손실
  → 세금이 외부 피해를 반영하면 사회 전체로는 이득일 수 있다. 세금이 항상 후생을 줄인다는 뜻이 아니다.

반올림: 모든 출력은 소수 6자리 (반올림, 0.5 는 0 에서 먼 쪽). -0 은 0 으로.
"""
import math

from econova import grading

CALC_VERSION = "sim-1"
SIMULATIONS = {
    "supply-demand": {"title": "Supply and Demand Equilibrium", "inputs": ("a", "b", "c", "d")},
    "carbon-tax": {"title": "Carbon Tax and the Market", "inputs": ("a", "b", "c", "d", "t", "md", "e")},
}

# (최솟값, 최댓값, 최솟값 포함?, 설명, 단위)
LIMITS = {
    "a": (0, 1000, False, "Demand intercept a (quantity demanded when the price is 0)", "units"),
    "b": (0, 100, False, "Demand slope b (drop in quantity demanded when the price rises by 1)", "units per $1"),
    "c": (-1000, 1000, True, "Supply intercept c (quantity supplied when the price is 0; may be negative)", "units"),
    "d": (0, 100, False, "Supply slope d (rise in quantity supplied when the price rises by 1)", "units per $1"),
    "t": (0, 1000, True, "Carbon tax per unit t", "$ per unit"),
    "md": (0, 1000, True, "External damage per unit md (assumed)", "$ per unit"),
    "e": (0, 1000, True, "Emissions per unit e (assumed)", "kg per unit"),
}
DEFAULTS = {
    "supply-demand": {"a": 100, "b": 2, "c": 10, "d": 1},
    "carbon-tax": {"a": 100, "b": 2, "c": 10, "d": 1, "t": 6, "md": 6, "e": 1},
}


class SimError(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field, self.message = field, message


def r6(x):
    """소수 6자리 반올림 (JS 와 같은 규칙)."""
    if x == 0:
        return 0.0
    sign = -1.0 if x < 0 else 1.0
    v = sign * math.floor(abs(x) * 1e6 + 0.5) / 1e6
    return 0.0 if v == 0 else v


def parse_inputs(sim_id, raw):
    """폼·JSON 입력을 검사해 숫자 dict 로. 문제가 있으면 SimError(field, 이유)."""
    if sim_id not in SIMULATIONS:
        raise SimError("simulation", "Unknown simulation.")
    out = {}
    for name in SIMULATIONS[sim_id]["inputs"]:
        value = raw.get(name, "")
        if value is None:
            value = ""
        if isinstance(value, bool):
            raise SimError(name, f"{LIMITS[name][3]}: enter a number.")
        if isinstance(value, (int, float)):
            number = float(value)
        else:
            text = str(value).strip()
            if not text and name == "md":
                continue   # 외부 피해는 비워 둘 수 있다 (모를 때)
            number = grading.parse_number(text)   # 채점과 같은 숫자 규칙 (지수 표기·inf·nan 거절)
            if number is None:
                raise SimError(name, f"{LIMITS[name][3]}: enter a number.")
        if not math.isfinite(number):
            raise SimError(name, f"{LIMITS[name][3]}: must be a finite number.")
        lo, hi, inclusive, label, _ = LIMITS[name]
        if number > hi or number < lo or (number == lo and not inclusive):
            rule = f"at least {lo}" if inclusive else f"greater than {lo}"
            raise SimError(name, f"{label}: must be {rule} and at most {hi}.")
        out[name] = number
    return out


def supply_demand(a, b, c, d):
    """선형 수요·공급의 균형. 양(+)의 가격·수량 균형이 없으면 status 로 알린다."""
    p = (a - c) / (b + d)
    q = a - b * p
    choke = a / b                      # 수요량이 0 이 되는 가격
    start = max(0.0, -c / d)           # 공급이 시작되는 가격
    result = {"model": "supply-demand", "inputs": {"a": a, "b": b, "c": c, "d": d},
              "demand_choke_price": r6(choke), "supply_start_price": r6(start)}
    if a <= c:
        return {**result, "status": "no_positive_equilibrium",
                "reason": "Even at a price of 0, quantity supplied is at least as large as quantity demanded, so there is no positive equilibrium price."}
    if q <= 1e-12 or p <= 0:
        return {**result, "status": "no_positive_equilibrium",
                "reason": "Supply only starts at a price above the price where quantity demanded drops to 0, so no trade takes place."}
    cs = 0.5 * (choke - p) * q
    ps = c * p + 0.5 * d * p * p if c >= 0 else 0.5 * (p - start) * q
    return {**result, "status": "interior", "reason": "",
            "price": r6(p), "quantity": r6(q), "consumer_surplus": r6(cs), "producer_surplus": r6(ps),
            "total_surplus": r6(cs + ps)}


def interpret(base, new):
    """두 입력(dict)의 차이를 경제적 의미로 설명하는 문장들 (결정적 규칙)."""
    notes = []
    if new["a"] > base["a"]:
        notes.append("Demand increases: buyers want to buy more at every price. The demand curve shifts right.")
    elif new["a"] < base["a"]:
        notes.append("Demand decreases: buyers want to buy less at every price. The demand curve shifts left.")
    if new["b"] != base["b"]:
        notes.append("Demand slope changes: consumers react " + ("more" if new["b"] > base["b"] else "less") + " strongly to price.")
    if new["c"] > base["c"]:
        notes.append("Supply increases: sellers want to sell more at every price. The supply curve shifts right.")
    elif new["c"] < base["c"]:
        notes.append("Supply decreases: sellers want to sell less at every price. The supply curve shifts left.")
    if new["d"] != base["d"]:
        notes.append("Supply slope changes: producers react " + ("more" if new["d"] > base["d"] else "less") + " strongly to price.")
    r0, r1 = supply_demand(**{k: base[k] for k in "abcd"}), supply_demand(**{k: new[k] for k in "abcd"})
    if r0["status"] == r1["status"] == "interior" and notes:
        dp, dq = r1["price"] - r0["price"], r1["quantity"] - r0["quantity"]
        word = lambda v, up, down: up if v > 1e-9 else down if v < -1e-9 else "does not change"
        notes.append(f"Result: the equilibrium price {word(dp, 'rises', 'falls')} and the equilibrium quantity {word(dq, 'increases', 'decreases')}.")
    return notes


def carbon_tax(a, b, c, d, t, md=None, e=1.0):
    """생산자에게 부과하는 단위당 탄소세의 효과. 세금이 없을 때의 균형과 비교한다."""
    base = supply_demand(a, b, c, d)
    result = {"model": "carbon-tax", "inputs": {"a": a, "b": b, "c": c, "d": d, "t": t, "md": md, "e": e},
              "baseline": base}
    if base["status"] != "interior":
        return {**result, "status": "invalid_baseline", "reason": "There is no positive equilibrium even without the tax, so the effect of the tax cannot be calculated."}
    p0, q0 = (a - c) / (b + d), a - b * (a - c) / (b + d)
    pc = (a - c + d * t) / (b + d)
    pp = pc - t
    qt = a - b * pc
    if qt <= 1e-12:
        return {**result, "status": "no_trade_after_tax", "reason": "The tax is so large that trade disappears (quantity 0).",
                "quantity": 0.0, "revenue": 0.0}
    if pp < 0:
        return {**result, "status": "producer_price_negative",
                "reason": "The tax is so large that the price producers receive falls below 0. This simple model cannot interpret that case."}
    dq = qt - q0
    dwl = 0.5 * t * (q0 - qt)
    out = {**result, "status": "interior", "reason": "",
           "consumer_price": r6(pc), "producer_price": r6(pp), "quantity": r6(qt), "revenue": r6(t * qt),
           "consumer_burden_per_unit": r6(pc - p0), "producer_burden_per_unit": r6(p0 - pp),
           "consumer_share": r6(d / (b + d)), "producer_share": r6(b / (b + d)),
           "consumer_burden_total": r6((pc - p0) * qt), "producer_burden_total": r6((p0 - pp) * qt),
           "quantity_change": r6(dq), "deadweight_loss_private": r6(dwl),
           "emissions_before": r6(e * q0), "emissions_after": r6(e * qt), "emissions_change": r6(e * dq)}
    if md is not None:
        avoided = md * (q0 - qt)
        out.update(avoided_damage=r6(avoided), social_welfare_change=r6(avoided - dwl))
    return out


def run(sim_id, raw):
    """시뮬레이션 실행: 입력 검사 → 계산. (sim_id, 입력 dict) → (정리된 입력, 결과)."""
    inputs = parse_inputs(sim_id, raw)
    if sim_id == "supply-demand":
        return inputs, supply_demand(**inputs)
    return inputs, carbon_tax(**{k: inputs[k] for k in ("a", "b", "c", "d", "t")}, md=inputs.get("md"), e=inputs["e"])


def graph_spec(sim_id, inputs, results):
    """econova.graphs.geometry 가 그릴 수 있는 그래프 명세 (서버 첫 화면용. 이후에는 JS 가 같은 방식으로 그린다)."""
    a, b, c, d = (inputs[k] for k in "abcd")
    demand = [{"label": "D", "a": a, "b": b}]
    supply = [{"label": "S", "c": c, "d": d}]
    eq, lines = [], []
    if sim_id == "supply-demand":
        if results["status"] == "interior":
            eq.append({"demand": "D", "supply": "S", "price": results["price"], "quantity": results["quantity"]})
    else:
        supply.append({"label": "S+t", "c": c - d * inputs["t"], "d": d, "label_side": "left"})
        base = results["baseline"]
        if base["status"] == "interior":
            eq.append({"demand": "D", "supply": "S", "price": base["price"], "quantity": base["quantity"]})
        if results["status"] == "interior":
            eq.append({"demand": "D", "supply": "S+t", "price": results["consumer_price"], "quantity": results["quantity"]})
            lines = [{"label": "Consumer price", "price": results["consumer_price"]},
                     {"label": "Producer price", "price": results["producer_price"]}]
    p_top = max(a / b, 1.0)
    return {"id": f"sim-{sim_id}", "title": SIMULATIONS[sim_id]["title"], "caption": "Hypothetical model results. These are not real statistics.",
            "axis": {"p_max": nice_max(p_top * 1.1), "q_max": nice_max(max(a, c + d * p_top, 1.0) * 1.1),
                     "p_label": "Price P ($)", "q_label": "Quantity Q (units)"},
            "demand": demand, "supply": supply, "price_lines": lines, "expected_equilibria": eq}


def nice_max(x):
    """축 최댓값을 보기 좋은 수(1·2·2.5·5·10 × 10^n)로 올린다."""
    if x <= 0:
        return 1.0
    exp = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 2.5, 5, 10):
        if m * exp >= x - 1e-9:
            return float(m * exp)
    return float(10 * exp)


ROW_LABELS = {
    "supply-demand": (("price", "Equilibrium price", "$"), ("quantity", "Equilibrium quantity", "units"), ("consumer_surplus", "Consumer surplus", "$"),
                      ("producer_surplus", "Producer surplus", "$"), ("total_surplus", "Total surplus", "$")),
    "carbon-tax": (("consumer_price", "Price paid by consumers", "$ per unit"), ("producer_price", "Price received by producers", "$ per unit"),
                   ("quantity", "Quantity after tax", "units"), ("quantity_change", "Change in quantity", "units"), ("revenue", "Tax revenue", "$"),
                   ("consumer_burden_per_unit", "Consumer burden (per unit)", "$ per unit"), ("producer_burden_per_unit", "Producer burden (per unit)", "$ per unit"),
                   ("consumer_share", "Consumer share of the tax", ""), ("deadweight_loss_private", "Deadweight loss (assuming no external damage)", "$"),
                   ("emissions_before", "Emissions (before tax)", "kg"), ("emissions_after", "Emissions (after tax)", "kg"),
                   ("avoided_damage", "Avoided external damage (assumed)", "$"), ("social_welfare_change", "Change in social welfare (assumed)", "$")),
}


def result_rows(sim_id, results):
    """표에 보여줄 (이름, 값, 단위). 계산되지 않은 값(균형 없음, md 미입력 등)은 뺀다."""
    return [(label, results[key], unit) for key, label, unit in ROW_LABELS[sim_id] if isinstance(results.get(key), (int, float))]
