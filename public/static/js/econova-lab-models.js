/* ECONOVA Economics Lab models 3-9: same formulas and rounding as econova/lab_models.py.
   Exposed as window.EconovaLab in the browser and module.exports in Node tests.
   Hypothetical teaching models; the numbers are not real statistics or forecasts. */
(function (root) {
  "use strict";
  var CALC_VERSION = "lab-1";
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
  function g(v) { return String(v); }   // same text as lab_models._fmt

  /* spec = econova.lab_models.SPECS[simId] (sent by the server). Returns {ok, inputs} or {ok:false, field, message}. */
  function parseInputs(spec, raw) {
    var out = {};
    for (var i = 0; i < spec.inputs.length; i++) {
      var s = spec.inputs[i], value = raw[s.name];
      if (s.kind === "select") {
        var found = false;
        for (var k = 0; k < s.options.length; k++) {
          if (String(s.options[k][0]) === String(value == null ? "" : value).trim()) { out[s.name] = s.options[k][0]; found = true; break; }
        }
        if (!found) return { ok: false, field: s.name, message: s.label + ": choose one of the listed options." };
        continue;
      }
      var n = typeof value === "boolean" ? null : parseNumber(value);
      if (n === null) return { ok: false, field: s.name, message: s.label + ": enter a number." };
      if (s.integer && n !== Math.floor(n)) return { ok: false, field: s.name, message: s.label + ": enter a whole number." };
      if (n < s.min || n > s.max) return { ok: false, field: s.name, message: s.label + ": must be between " + g(s.min) + " and " + g(s.max) + "." };
      out[s.name] = n;
    }
    return { ok: true, inputs: out };
  }

  // ---------------------------------------------------------------- LAB 01
  function opportunityCost(x) {
    var spending = x.px * x.x + x.py * x.y, leftover = x.budget - spending, tol = 1e-9 * Math.max(1, x.budget);
    var status = leftover < -tol ? "infeasible" : (Math.abs(leftover) <= tol ? "on_line" : "inside");
    return { model: "opportunity-cost", status: status, spending: r6(spending), leftover: r6(Math.max(0, leftover)),
             over_budget: r6(Math.max(0, -leftover)), max_x: r6(x.budget / x.px), max_y: r6(x.budget / x.py),
             oc_x_in_y: r6(x.px / x.py), oc_y_in_x: r6(x.py / x.px), forgone_y: r6(x.x * x.px / x.py),
             max_y_given_x: r6(Math.max(0, (x.budget - x.px * x.x) / x.py)), x: r6(x.x), y: r6(x.y) };
  }

  // ---------------------------------------------------------------- LAB 04
  function inflation(x) {
    var pi = x.inflation / 100, gr = x.wage_growth / 100, n = Math.trunc(x.years), series = [];
    for (var t = 0; t <= n; t++) {
      var pIndex = 100 * Math.pow(1 + pi, t), nominal = x.income0 * Math.pow(1 + gr, t);
      series.push({ t: t, nominal: r6(nominal), real: r6(nominal / (pIndex / 100)), price_index: r6(pIndex), basket: r6(x.basket0 * pIndex / 100) });
    }
    var end = series[series.length - 1];
    var nominalEnd = x.income0 * Math.pow(1 + gr, n), realEnd = x.income0 * Math.pow(1 + gr, n) / Math.pow(1 + pi, n);
    var realGrowth = (1 + gr) / (1 + pi) - 1;
    return { model: "inflation", status: realGrowth > 1e-12 ? "real_gain" : (realGrowth < -1e-12 ? "real_loss" : "real_flat"), series: series,
             nominal_end: end.nominal, real_end: end.real, price_index_end: end.price_index, basket_end: end.basket,
             baskets_start: r6(x.income0 / x.basket0), baskets_end: r6(nominalEnd / (x.basket0 * Math.pow(1 + pi, n))),
             nominal_change: r6((nominalEnd / x.income0 - 1) * 100), real_change: r6((realEnd / x.income0 - 1) * 100),
             real_growth: r6(realGrowth * 100), real_growth_approx: r6(x.wage_growth - x.inflation), value_of_100: r6(100 / Math.pow(1 + pi, n)) };
  }

  // ---------------------------------------------------------------- LAB 05
  function minimumWage(x) {
    var a = x.a, b = x.b, c = x.c, d = x.d, wmin = x.wmin;
    var base = { model: "minimum-wage", wmin: r6(wmin), demand_choke_wage: r6(a / b) };
    if (a <= c) return Object.assign(base, { status: "no_equilibrium", reason: "Even at a wage of $0, more people want to work than employers want to hire, so there is no positive equilibrium wage." });
    var wEq = (a - c) / (b + d), lEq = a - b * wEq;
    if (lEq <= 1e-12) return Object.assign(base, { status: "no_equilibrium", reason: "Nobody would be employed at the equilibrium wage in this market." });
    Object.assign(base, { eq_wage: r6(wEq), eq_employment: r6(lEq), wage_bill_before: r6(wEq * lEq) });
    if (wmin <= wEq + 1e-12) {
      return Object.assign(base, { status: "nonbinding", wage: r6(wEq), employment: r6(lEq), employment_change: 0, labor_supplied: r6(lEq),
                                   excess_supply: 0, wage_bill: r6(wEq * lEq) });
    }
    var emp = Math.max(0, a - b * wmin), sup = c + d * wmin;
    return Object.assign(base, { status: emp > 0 ? "binding" : "binding_no_jobs", wage: r6(wmin), employment: r6(emp), employment_change: r6(emp - lEq),
                                 labor_supplied: r6(sup), excess_supply: r6(sup - emp), wage_bill: r6(wmin * emp) });
  }

  // ---------------------------------------------------------------- LAB 06
  function sum(a) { var s = 0; for (var i = 0; i < a.length; i++) s += a[i]; return s; }
  function gini(values) {
    var n = values.length, total = sum(values);
    if (total <= 0) return null;
    var diff = 0;
    for (var i = 0; i < n; i++) for (var j = 0; j < n; j++) diff += Math.abs(values[i] - values[j]);
    return diff / (2 * n * total);
  }
  function lorenz(values) {
    var total = sum(values), cum = 0, pts = [{ p: 0, s: 0 }], sorted = values.slice().sort(function (p, q) { return p - q; });
    for (var i = 0; i < sorted.length; i++) { cum += sorted[i]; pts.push({ p: r6((i + 1) / sorted.length), s: r6(cum / total) }); }
    return pts;
  }
  function inequality(x) {
    var pre = [x.h1, x.h2, x.h3, x.h4, x.h5], total = sum(pre);
    if (total <= 0) return { model: "inequality", status: "no_income", reason: "Total income is 0, so income shares and the Gini coefficient are undefined." };
    var tau = x.tax_rate / 100;
    var taxes = pre.map(function (h) { return tau * Math.max(0, h - x.exemption); }), revenue = sum(taxes);
    var rank = [0, 1, 2, 3, 4].sort(function (i, j) { return pre[i] - pre[j] || i - j; });
    var tr = [0, 0, 0, 0, 0];
    if (x.mode === "equal") tr = [1, 2, 3, 4, 5].map(function () { return revenue / 5; });
    else if (x.mode === "bottom_two") { tr[rank[0]] = revenue / 2; tr[rank[1]] = revenue / 2; }
    else if (x.mode === "top_two") { tr[rank[3]] = revenue / 2; tr[rank[4]] = revenue / 2; }
    else tr = pre.map(function (h) { return revenue * h / total; });
    var post = pre.map(function (h, i) { return h - taxes[i] + tr[i]; });
    var g0 = gini(pre), g1 = gini(post), change = g1 - g0;
    var lo0 = Math.min.apply(null, pre), hi0 = Math.max.apply(null, pre), lo1 = Math.min.apply(null, post), hi1 = Math.max.apply(null, post);
    return { model: "inequality", status: change > 1e-9 ? "less_equal" : (change < -1e-9 ? "more_equal" : "unchanged"),
             pre: pre.map(r6), post: post.map(r6), taxes: taxes.map(r6), transfers: tr.map(r6), revenue: r6(revenue),
             gini_before: r6(g0), gini_after: r6(g1), gini_change: r6(change), lorenz_before: lorenz(pre), lorenz_after: lorenz(post),
             bottom_share_before: r6(lo0 / total * 100), bottom_share_after: r6(lo1 / total * 100),
             top_share_before: r6(hi0 / total * 100), top_share_after: r6(hi1 / total * 100),
             ratio_before: lo0 > 0 ? r6(hi0 / lo0) : null, ratio_after: lo1 > 0 ? r6(hi1 / lo1) : null };
  }

  // ---------------------------------------------------------------- LAB 07
  var MAX_LOAN_MONTHS = 600;
  function compoundInterest(x) {
    var r = x.rate / 100, n = Math.trunc(x.compounding), pi = x.inflation / 100, T = Math.trunc(x.years);
    var i = Math.pow(1 + r / n, n / 12) - 1, bal = x.principal, series = [];
    for (var t = 0; t <= T; t++) {
      if (t > 0) for (var m = 0; m < 12; m++) bal = bal * (1 + i) + x.monthly;
      var contrib = x.principal + 12 * x.monthly * t;
      series.push({ t: t, balance: r6(bal), contributions: r6(contrib), interest: r6(bal - contrib), real: r6(bal / Math.pow(1 + pi, t)) });
    }
    var apy = Math.pow(1 + r / n, n) - 1, end = series[series.length - 1];
    var out = { model: "compound-interest", series: series, balance_end: end.balance, contributions_end: end.contributions, interest_end: end.interest,
                real_balance_end: end.real, apy: r6(apy * 100), real_return: r6(((1 + apy) / (1 + pi) - 1) * 100), monthly_rate: r6(i * 100) };
    var j = x.loan_apr / 100 / 12, loanSeries = [{ t: 0, balance: r6(x.loan) }];
    out.loan_ear = r6((Math.pow(1 + j, 12) - 1) * 100); out.loan_first_interest = r6(x.loan * j);
    if (x.loan <= 0) { out.loan_status = "no_loan"; out.loan_series = loanSeries; out.status = "ok"; return out; }
    if (x.payment <= x.loan * j + 1e-12) { out.loan_status = "never_repaid"; out.loan_series = loanSeries; out.status = "ok"; return out; }
    var lb = x.loan, paid = 0, ip = 0, months = 0;
    while (lb > 1e-9 && months < MAX_LOAN_MONTHS) {
      var interest = lb * j, pay = Math.min(x.payment, lb + interest);
      lb = lb + interest - pay; paid += pay; ip += interest; months += 1;
      if (months % 12 === 0 || lb <= 1e-9) loanSeries.push({ t: r6(months / 12), balance: r6(Math.max(0, lb)) });
    }
    out.loan_series = loanSeries; out.loan_total_paid = r6(paid); out.loan_total_interest = r6(ip);
    if (lb > 1e-9) { out.loan_status = "not_repaid_in_50_years"; out.loan_remaining = r6(lb); }
    else { out.loan_status = "repaid"; out.loan_months = months; }
    out.status = "ok";
    return out;
  }

  // ---------------------------------------------------------------- LAB 08
  function isClose(p, q, tol) { return Math.abs(p - q) <= Math.max(1e-12 * Math.max(Math.abs(p), Math.abs(q)), tol); }
  function comparativeAdvantage(x) {
    var sa = x.share_a / 100, sb = x.share_b / 100;
    var maxFa = x.labor_a / x.a_food, maxCa = x.labor_a / x.a_cloth, maxFb = x.labor_b / x.b_food, maxCb = x.labor_b / x.b_cloth;
    var ocA = x.a_food / x.a_cloth, ocB = x.b_food / x.b_cloth;
    var af = sa * maxFa, ac = (1 - sa) * maxCa, bf = sb * maxFb, bc = (1 - sb) * maxCb;
    var out = { model: "comparative-advantage", oc_a: r6(ocA), oc_b: r6(ocB), max_food_a: r6(maxFa), max_cloth_a: r6(maxCa),
                max_food_b: r6(maxFb), max_cloth_b: r6(maxCb), autarky_food_a: r6(af), autarky_cloth_a: r6(ac), autarky_food_b: r6(bf),
                autarky_cloth_b: r6(bc), world_food_before: r6(af + bf), world_cloth_before: r6(ac + bc),
                abs_food: x.a_food < x.b_food ? "A" : (x.b_food < x.a_food ? "B" : "none"),
                abs_cloth: x.a_cloth < x.b_cloth ? "A" : (x.b_cloth < x.a_cloth ? "B" : "none") };
    if (isClose(ocA, ocB, 1e-12)) {
      out.status = "no_comparative_advantage"; out.food_exporter = "none";
      out.reason = "Both countries give up the same amount of cloth for one unit of food, so neither has a comparative advantage. Specializing would not raise world output, so there are no gains from trade in this model.";
      return out;
    }
    var exporter = ocA < ocB ? "A" : "B", food, cloth, ocExp, ocImp;
    if (exporter === "A") { food = maxFa; cloth = maxCb; ocExp = ocA; ocImp = ocB; } else { food = maxFb; cloth = maxCa; ocExp = ocB; ocImp = ocA; }
    out.food_exporter = exporter; out.world_food_after = r6(food); out.world_cloth_after = r6(cloth);
    out.gain_range_low = r6(ocExp); out.gain_range_high = r6(ocImp);
    if (x.exported > food + 1e-9 || x.price * x.exported > cloth + 1e-9) {
      out.status = "infeasible_trade";
      out.reason = "The trade is impossible: the exporter can't sell more food than it makes, and the other country can't pay with more cloth than it makes.";
      return out;
    }
    var expB = [food - x.exported, x.price * x.exported], impB = [x.exported, cloth - x.price * x.exported];
    var consA = exporter === "A" ? expB : impB, consB = exporter === "A" ? impB : expB;
    out.cons_food_a = r6(consA[0]); out.cons_cloth_a = r6(consA[1]); out.cons_food_b = r6(consB[0]); out.cons_cloth_b = r6(consB[1]);
    out.reach_a = r6(consA[0] / maxFa + consA[1] / maxCa); out.reach_b = r6(consB[0] / maxFb + consB[1] / maxCb);
    var p = x.price;
    if (x.exported <= 1e-12) out.status = "no_trade";
    else if (ocExp + 1e-12 < p && p < ocImp - 1e-12) out.status = "mutual_gain";
    else if (isClose(p, ocExp, 1e-12) || isClose(p, ocImp, 1e-12)) out.status = "one_side_no_gain";
    else out.status = "one_side_loses";
    return out;
  }

  // ---------------------------------------------------------------- LAB 09
  function projectNpv(inv, op, ben, years, r, extra) {
    var npv = -inv;
    for (var t = 1; t <= years; t++) npv += (ben - op + (extra || 0)) / Math.pow(1 + r, t);
    return npv;
  }
  function payback(flows) {
    var cum = flows[0];
    if (cum >= 0) return 0;
    for (var t = 1; t < flows.length; t++) {
      if (cum + flows[t] >= 0 && flows[t] > 0) return (t - 1) + (-cum) / flows[t];
      cum += flows[t];
    }
    return null;
  }
  function sdgProject(x, projects) {
    var r = x.discount / 100, n = Math.trunc(x.years), net = x.benefit - x.op_cost;
    var flows = [-x.investment], dflows = [-x.investment], cum = -x.investment, dcum = -x.investment;
    var series = [{ t: 0, cf: r6(-x.investment), dcf: r6(-x.investment), cum: r6(cum), dcum: r6(dcum) }];
    var pvB = 0, pvC = x.investment;
    for (var t = 1; t <= n; t++) {
      var df = 1 / Math.pow(1 + r, t);
      flows.push(net); dflows.push(net * df); cum += net; dcum += net * df; pvB += x.benefit * df; pvC += x.op_cost * df;
      series.push({ t: t, cf: r6(net), dcf: r6(net * df), cum: r6(cum), dcum: r6(dcum) });
    }
    var pb = payback(flows), dpb = payback(dflows);
    var out = { model: "sdg-project", series: series, npv: r6(dcum), pv_benefits: r6(pvB), pv_costs: r6(pvC), bcr: pvC > 0 ? r6(pvB / pvC) : null,
                payback: pb === null ? null : r6(pb), discounted_payback: dpb === null ? null : r6(dpb), undiscounted_net: r6(cum),
                env_total: r6(x.env_units * n), env_unit: projects[x.project].env_unit,
                status: dcum > 1e-6 ? "npv_positive" : (dcum < -1e-6 ? "npv_negative" : "npv_zero") };
    if (x.env_value > 0) out.npv_with_env = r6(projectNpv(x.investment, x.op_cost, x.benefit, n, r, x.env_units * x.env_value));
    out.alternatives = Object.keys(projects).map(function (k) {
      var v = projects[k].values;
      return { project: k, label: projects[k].label, npv: r6(projectNpv(v.investment, v.op_cost, v.benefit, v.years, r)) };
    });
    return out;
  }

  var FUNCS = { "opportunity-cost": opportunityCost, "inflation": inflation, "minimum-wage": minimumWage, "inequality": inequality,
                "compound-interest": compoundInterest, "comparative-advantage": comparativeAdvantage, "sdg-project": sdgProject };

  /* run(simId, spec, raw, projects) -> {ok, inputs, results} or {ok:false, field, message} */
  function run(simId, spec, raw, projects) {
    var parsed = parseInputs(spec, raw);
    if (!parsed.ok) return parsed;
    return { ok: true, inputs: parsed.inputs, results: FUNCS[simId](parsed.inputs, projects) };
  }

  function niceMax(x) {
    if (!(x > 0)) return 1;
    var exp = Math.pow(10, Math.floor(Math.log10(x))), ms = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < ms.length; i++) if (ms[i] * exp >= x - 1e-9) return ms[i] * exp;
    return 10 * exp;
  }

  var api = { CALC_VERSION: CALC_VERSION, r6: r6, parseNumber: parseNumber, parseInputs: parseInputs, run: run, gini: gini,
              lorenz: lorenz, niceMax: niceMax, FUNCS: FUNCS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.EconovaLab = api;
})(typeof window !== "undefined" ? window : this);
