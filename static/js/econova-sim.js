/* ECONOVA 경제 시뮬레이션 계산 (econova/simulations.py 와 같은 공식·같은 반올림).
   브라우저에서는 window.EconovaSim, Node 테스트에서는 module.exports 로 쓴다.
   가상의 교육용 모형이며 실제 통계가 아니다. */
(function (root) {
  "use strict";
  var CALC_VERSION = "sim-1";
  // 설명 문구는 econova/simulations.py LIMITS 와 같아야 한다 (오류 문구 일치 테스트)
  var LIMITS = {
    a: [0, 1000, false, "수요 절편 a (가격이 0일 때의 수요량)"], b: [0, 100, false, "수요 기울기 b (가격이 1 오를 때 줄어드는 수요량)"],
    c: [-1000, 1000, true, "공급 절편 c (가격이 0일 때의 공급량, 음수 가능)"], d: [0, 100, false, "공급 기울기 d (가격이 1 오를 때 늘어나는 공급량)"],
    t: [0, 1000, true, "단위당 탄소세 t"], md: [0, 1000, true, "단위당 외부 피해 md (가정값)"], e: [0, 1000, true, "단위당 배출량 e (가정값)"]
  };
  var INPUTS = { "supply-demand": ["a", "b", "c", "d"], "carbon-tax": ["a", "b", "c", "d", "t", "md", "e"] };
  var NUM_RE = /^[+-]?(\d+(\.\d*)?|\.\d+)$/;

  function r6(x) {
    if (x === 0) return 0;
    var sign = x < 0 ? -1 : 1;
    var v = sign * Math.floor(Math.abs(x) * 1e6 + 0.5) / 1e6;
    return v === 0 ? 0 : v;
  }

  function parseNumber(raw) {
    if (typeof raw === "number") return isFinite(raw) ? raw : null;
    var text = String(raw == null ? "" : raw).trim().replace(/ /g, "");
    if (/^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$/.test(text)) text = text.replace(/,/g, "");
    if (!NUM_RE.test(text)) return null;
    var v = parseFloat(text);
    return isFinite(v) ? v : null;
  }

  /* 입력 검사. 반환: {ok: true, inputs} 또는 {ok: false, field, message} */
  function parseInputs(simId, raw) {
    var names = INPUTS[simId];
    if (!names) return { ok: false, field: "simulation", message: "알 수 없는 시뮬레이션입니다." };
    var out = {};
    for (var i = 0; i < names.length; i++) {
      var name = names[i], lim = LIMITS[name], value = raw[name];
      if (name === "md" && (value === undefined || value === null || String(value).trim() === "")) continue;
      var n = parseNumber(value);
      if (n === null) return { ok: false, field: name, message: lim[3] + ": 숫자를 입력해 주세요." };
      if (n > lim[1] || n < lim[0] || (n === lim[0] && !lim[2])) {
        return { ok: false, field: name, message: lim[3] + ": " + (lim[2] ? lim[0] + " 이상" : lim[0] + " 보다 크고") + " " + lim[1] + " 이하여야 합니다." };
      }
      out[name] = n;
    }
    return { ok: true, inputs: out };
  }

  function supplyDemand(a, b, c, d) {
    var p = (a - c) / (b + d), q = a - b * p, choke = a / b, start = Math.max(0, -c / d);
    var res = { model: "supply-demand", demand_choke_price: r6(choke), supply_start_price: r6(start) };
    if (a <= c) {
      res.status = "no_positive_equilibrium";
      res.reason = "가격이 0일 때도 공급량이 수요량보다 많거나 같아서, 양(+)의 균형 가격이 없어요.";
      return res;
    }
    if (q <= 1e-12 || p <= 0) {
      res.status = "no_positive_equilibrium";
      res.reason = "공급이 시작되는 가격이 수요가 0이 되는 가격보다 높아서, 거래가 일어나지 않아요.";
      return res;
    }
    var cs = 0.5 * (choke - p) * q;
    var ps = c >= 0 ? c * p + 0.5 * d * p * p : 0.5 * (p - start) * q;
    res.status = "interior"; res.reason = "";
    res.price = r6(p); res.quantity = r6(q);
    res.consumer_surplus = r6(cs); res.producer_surplus = r6(ps); res.total_surplus = r6(cs + ps);
    return res;
  }

  function carbonTax(a, b, c, d, t, md, e) {
    if (e === undefined) e = 1;
    var base = supplyDemand(a, b, c, d);
    var res = { model: "carbon-tax", baseline: base };
    if (base.status !== "interior") {
      res.status = "invalid_baseline"; res.reason = "세금이 없을 때도 양(+)의 균형이 없어 세금 효과를 계산할 수 없어요.";
      return res;
    }
    var p0 = (a - c) / (b + d), q0 = a - b * p0;
    var pc = (a - c + d * t) / (b + d), pp = pc - t, qt = a - b * pc;
    if (qt <= 1e-12) {
      res.status = "no_trade_after_tax"; res.reason = "세금이 너무 커서 거래가 사라져요 (거래량 0).";
      res.quantity = 0; res.revenue = 0;
      return res;
    }
    if (pp < 0) {
      res.status = "producer_price_negative";
      res.reason = "세금이 너무 커서 생산자가 받는 가격이 0 아래로 내려가요. 이 단순 모형으로는 해석하기 어려워요.";
      return res;
    }
    var dq = qt - q0, dwl = 0.5 * t * (q0 - qt);
    res.status = "interior"; res.reason = "";
    res.consumer_price = r6(pc); res.producer_price = r6(pp); res.quantity = r6(qt); res.revenue = r6(t * qt);
    res.consumer_burden_per_unit = r6(pc - p0); res.producer_burden_per_unit = r6(p0 - pp);
    res.consumer_share = r6(d / (b + d)); res.producer_share = r6(b / (b + d));
    res.consumer_burden_total = r6((pc - p0) * qt); res.producer_burden_total = r6((p0 - pp) * qt);
    res.quantity_change = r6(dq); res.deadweight_loss_private = r6(dwl);
    res.emissions_before = r6(e * q0); res.emissions_after = r6(e * qt); res.emissions_change = r6(e * dq);
    if (md !== undefined && md !== null) {
      var avoided = md * (q0 - qt);
      res.avoided_damage = r6(avoided); res.social_welfare_change = r6(avoided - dwl);
    }
    return res;
  }

  function interpret(base, now) {
    var notes = [];
    if (now.a > base.a) notes.push("수요 증가: 같은 가격에서 더 많이 사려 해요. 수요곡선이 오른쪽으로 이동해요.");
    else if (now.a < base.a) notes.push("수요 감소: 같은 가격에서 덜 사려 해요. 수요곡선이 왼쪽으로 이동해요.");
    if (now.b !== base.b) notes.push("수요 기울기 변화: 소비자가 가격에 " + (now.b > base.b ? "더" : "덜") + " 민감하게 반응해요.");
    if (now.c > base.c) notes.push("공급 증가: 같은 가격에서 더 많이 팔려 해요. 공급곡선이 오른쪽으로 이동해요.");
    else if (now.c < base.c) notes.push("공급 감소: 같은 가격에서 덜 팔려 해요. 공급곡선이 왼쪽으로 이동해요.");
    if (now.d !== base.d) notes.push("공급 기울기 변화: 생산자가 가격에 " + (now.d > base.d ? "더" : "덜") + " 민감하게 반응해요.");
    var r0 = supplyDemand(base.a, base.b, base.c, base.d), r1 = supplyDemand(now.a, now.b, now.c, now.d);
    if (r0.status === "interior" && r1.status === "interior" && notes.length) {
      var dp = r1.price - r0.price, dq = r1.quantity - r0.quantity;
      var word = function (v, up, down) { return v > 1e-9 ? up : (v < -1e-9 ? down : "변화 없음"); };
      notes.push("결과: 균형 가격 " + word(dp, "상승", "하락") + ", 균형 거래량 " + word(dq, "증가", "감소") + ".");
    }
    return notes;
  }

  function run(simId, raw) {
    var parsed = parseInputs(simId, raw);
    if (!parsed.ok) return parsed;
    var x = parsed.inputs;
    var results = simId === "supply-demand" ? supplyDemand(x.a, x.b, x.c, x.d) : carbonTax(x.a, x.b, x.c, x.d, x.t, x.md, x.e);
    return { ok: true, inputs: x, results: results };
  }

  function niceMax(x) {
    if (x <= 0) return 1;
    var exp = Math.pow(10, Math.floor(Math.log10(x)));
    var ms = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < ms.length; i++) if (ms[i] * exp >= x - 1e-9) return ms[i] * exp;
    return 10 * exp;
  }

  var api = { CALC_VERSION: CALC_VERSION, LIMITS: LIMITS, INPUTS: INPUTS, r6: r6, parseNumber: parseNumber,
              parseInputs: parseInputs, supplyDemand: supplyDemand, carbonTax: carbonTax, interpret: interpret,
              run: run, niceMax: niceMax };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.EconovaSim = api;
})(typeof window !== "undefined" ? window : this);
