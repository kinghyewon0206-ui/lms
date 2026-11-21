/* ECONOVA economics simulation math (same formulas and rounding as econova/simulations.py).
   Exposed as window.EconovaSim in the browser and module.exports in Node tests.
   A hypothetical teaching model, not real statistics. */
(function (root) {
  "use strict";
  var CALC_VERSION = "sim-1";
  // Labels must match econova/simulations.py LIMITS (a test compares the error messages)
  var LIMITS = {
    a: [0, 1000, false, "Demand intercept a (quantity demanded when the price is 0)"], b: [0, 100, false, "Demand slope b (drop in quantity demanded when the price rises by 1)"],
    c: [-1000, 1000, true, "Supply intercept c (quantity supplied when the price is 0; may be negative)"], d: [0, 100, false, "Supply slope d (rise in quantity supplied when the price rises by 1)"],
    t: [0, 1000, true, "Carbon tax per unit t"], md: [0, 1000, true, "External damage per unit md (assumed)"], e: [0, 1000, true, "Emissions per unit e (assumed)"]
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

  /* Input validation. Returns {ok: true, inputs} or {ok: false, field, message} */
  function parseInputs(simId, raw) {
    var names = INPUTS[simId];
    if (!names) return { ok: false, field: "simulation", message: "Unknown simulation." };
    var out = {};
    for (var i = 0; i < names.length; i++) {
      var name = names[i], lim = LIMITS[name], value = raw[name];
      if (name === "md" && (value === undefined || value === null || String(value).trim() === "")) continue;
      var n = parseNumber(value);
      if (n === null) return { ok: false, field: name, message: lim[3] + ": enter a number." };
      if (n > lim[1] || n < lim[0] || (n === lim[0] && !lim[2])) {
        return { ok: false, field: name, message: lim[3] + ": must be " + (lim[2] ? "at least " + lim[0] : "greater than " + lim[0]) + " and at most " + lim[1] + "." };
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
      res.reason = "Even at a price of 0, quantity supplied is at least as large as quantity demanded, so there is no positive equilibrium price.";
      return res;
    }
    if (q <= 1e-12 || p <= 0) {
      res.status = "no_positive_equilibrium";
      res.reason = "Supply only starts at a price above the price where quantity demanded drops to 0, so no trade takes place.";
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
      res.status = "invalid_baseline"; res.reason = "There is no positive equilibrium even without the tax, so the effect of the tax cannot be calculated.";
      return res;
    }
    var p0 = (a - c) / (b + d), q0 = a - b * p0;
    var pc = (a - c + d * t) / (b + d), pp = pc - t, qt = a - b * pc;
    if (qt <= 1e-12) {
      res.status = "no_trade_after_tax"; res.reason = "The tax is so large that trade disappears (quantity 0).";
      res.quantity = 0; res.revenue = 0;
      return res;
    }
    if (pp < 0) {
      res.status = "producer_price_negative";
      res.reason = "The tax is so large that the price producers receive falls below 0. This simple model cannot interpret that case.";
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
      res.efficient_quantity = r6(Math.max(0, a - b * (a - c + d * md) / (b + d))); res.pigouvian_tax = r6(md);
    }
    return res;
  }

  function interpret(base, now) {
    var notes = [];
    if (now.a > base.a) notes.push("Demand increases: buyers want to buy more at every price. The demand curve shifts right.");
    else if (now.a < base.a) notes.push("Demand decreases: buyers want to buy less at every price. The demand curve shifts left.");
    if (now.b !== base.b) notes.push("Demand slope changes: consumers react " + (now.b > base.b ? "more" : "less") + " strongly to price.");
    if (now.c > base.c) notes.push("Supply increases: sellers want to sell more at every price. The supply curve shifts right.");
    else if (now.c < base.c) notes.push("Supply decreases: sellers want to sell less at every price. The supply curve shifts left.");
    if (now.d !== base.d) notes.push("Supply slope changes: producers react " + (now.d > base.d ? "more" : "less") + " strongly to price.");
    var r0 = supplyDemand(base.a, base.b, base.c, base.d), r1 = supplyDemand(now.a, now.b, now.c, now.d);
    if (r0.status === "interior" && r1.status === "interior" && notes.length) {
      var dp = r1.price - r0.price, dq = r1.quantity - r0.quantity;
      var word = function (v, up, down) { return v > 1e-9 ? up : (v < -1e-9 ? down : "does not change"); };
      notes.push("Result: the equilibrium price " + word(dp, "rises", "falls") + " and the equilibrium quantity " + word(dq, "increases", "decreases") + ".");
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
