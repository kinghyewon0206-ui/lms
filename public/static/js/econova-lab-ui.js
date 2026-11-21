/* ECONOVA Economics Lab UI for experiments 3-9: controls, presets, live SVG charts, baseline comparison, interpretation.
   The math lives in econova-lab-models.js (EconovaLab); the server computes the same results for the first render.
   View functions are pure (no DOM) so tests can check that chart coordinates match the calculated values. */
(function (root) {
  "use strict";
  var M = typeof module !== "undefined" && module.exports ? require("./econova-lab-models.js") : root.EconovaLab;
  var niceMax = M.niceMax;

  // ------------------------------------------------------------------ number formatting (same rules as web.lab_number)
  function fmtNum(v) {
    if (v === null || v === undefined || !isFinite(v)) return "–";
    var a = Math.abs(v), r = a >= 1 ? Math.round(a * 100) / 100 : Math.round(a * 1e4) / 1e4;
    return r.toLocaleString("en-US", { maximumFractionDigits: 4 });
  }
  function fmtUnit(v, unit) {
    if (v === null || v === undefined || !isFinite(v)) return "–";
    var t = fmtNum(v), neg = v < 0 && t !== "0";
    unit = unit || "";
    if (unit.charAt(0) === "$") return (neg ? "-$" : "$") + t + unit.slice(1);
    if (unit.charAt(0) === "%") return (neg ? "-" : "") + t + "%" + unit.slice(1);
    return (neg ? "-" : "") + t + (unit ? " " + unit : "");
  }
  function signed(v, unit) { return (v > 0 ? "+" : "") + fmtUnit(v, unit); }
  function money(v) { return fmtUnit(v, "$"); }
  function pct(v) { return fmtUnit(v, "%"); }
  function plural(v, one, many) { return Math.abs(v) === 1 ? one : many; }
  function niceRange(lo, hi) {   // y range that includes 0 and both extremes
    var top = hi > 0 ? niceMax(hi * 1.08) : 1, bottom = lo < 0 ? -niceMax(-lo * 1.08) : 0;
    return [bottom, top];
  }
  function niceCeil(v) {   // round up to a multiple of a half power of ten (108 → 120), tighter than niceMax
    if (!(v > 0)) return 1;
    var step = Math.pow(10, Math.floor(Math.log10(v))) / 2;
    return Math.ceil(v / step - 1e-9) * step;
  }
  function maxOf(list, key) { return list.reduce(function (m, p) { return Math.max(m, key ? p[key] : p); }, -Infinity); }
  function minOf(list, key) { return list.reduce(function (m, p) { return Math.min(m, key ? p[key] : p); }, Infinity); }

  // ------------------------------------------------------------------ views (pure): {summary, charts, notes, extra}
  var V = {};

  V["opportunity-cost"] = function (x, r, b) {
    var bx = b ? b.results : null;
    var xMax = niceMax(Math.max(r.max_x, x.x, bx ? bx.max_x : 0) * 1.12), yMax = niceMax(Math.max(r.max_y, x.y, bx ? bx.max_y : 0) * 1.12);
    var s = [{ type: "poly", pts: [[0, 0], [r.max_x, 0], [0, r.max_y]], cls: "fill-ok" }];
    if (bx && (bx.max_x !== r.max_x || bx.max_y !== r.max_y)) s.push({ type: "line", pts: [[0, bx.max_y], [bx.max_x, 0]], cls: "lc-muted dashed", label: "Baseline budget line" });
    s.push({ type: "line", pts: [[0, r.max_y], [r.max_x, 0]], cls: "lc-1", label: "Budget line" });
    s.push({ type: "line", pts: [[x.x, 0], [x.x, x.y], [0, x.y]], cls: "guide" });
    if (b && (b.inputs.x !== x.x || b.inputs.y !== x.y)) s.push({ type: "dot", x: b.inputs.x, y: b.inputs.y, cls: "dot-base", label: "Baseline" });
    s.push({ type: "dot", x: x.x, y: x.y, cls: r.status === "infeasible" ? "dot-bad" : "dot-ok", label: "Your choice" });
    var summary = r.status === "infeasible"
      ? "Not affordable: " + x.x + " " + plural(x.x, "book", "books") + " and " + x.y + " " + plural(x.y, "ticket", "tickets") + " cost " + money(r.spending) + ", which is " + money(r.over_budget) + " more than the " + money(x.budget) + " budget."
      : "Affordable: you spend " + money(r.spending) + " of " + money(x.budget) + (r.status === "on_line" ? " and use the whole budget." : " and have " + money(r.leftover) + " left over.");
    var notes = [
      "One book costs " + money(x.px) + ", the same money as " + fmtNum(r.oc_x_in_y) + " movie tickets. So the opportunity cost of one book is " + fmtNum(r.oc_x_in_y) + " tickets, and one ticket costs " + fmtNum(r.oc_y_in_x) + " of a book.",
      "Monetary cost of your books: " + money(x.px * x.x) + ". Opportunity cost: the " + fmtNum(r.forgone_y) + " tickets that money could have bought instead."
    ];
    if (r.status === "inside") notes.push("Your choice is inside the budget line. You could still add up to " + fmtNum(Math.floor(r.leftover / x.py + 1e-9)) + " more tickets or " + fmtNum(Math.floor(r.leftover / x.px + 1e-9)) + " more books without giving anything up.");
    if (r.status === "on_line") notes.push("Your choice is on the budget line: the only way to get one more book is to give up " + fmtNum(r.oc_x_in_y) + " tickets.");
    if (r.status === "infeasible") notes.push("Points beyond the budget line can't be bought with this budget. With " + x.x + " books, the most tickets you can afford is " + fmtNum(Math.floor(r.max_y_given_x + 1e-9)) + ".");
    if (b) {
      var bi = b.inputs;
      if (bi.px !== x.px || bi.py !== x.py) notes.push("A price change rotates the budget line: the line now meets the books axis at " + fmtNum(r.max_x) + " instead of " + fmtNum(bx.max_x) + " and the tickets axis at " + fmtNum(r.max_y) + " instead of " + fmtNum(bx.max_y) + ". The trade-off between the goods changes.");
      if (bi.budget !== x.budget && bi.px === x.px && bi.py === x.py) notes.push("A different budget shifts the budget line parallel " + (x.budget > bi.budget ? "outward" : "inward") + ": you can buy " + (x.budget > bi.budget ? "more" : "less") + " of both goods, but the opportunity cost of a book stays " + fmtNum(r.oc_x_in_y) + " tickets.");
    }
    return { summary: summary, notes: notes, charts: [{
      title: "Budget constraint", desc: summary, xLabel: "Books (good X)", yLabel: "Movie tickets (good Y)", x: [0, xMax], y: [0, yMax], series: s,
      legend: [["fill-ok", "Affordable choices"], ["lc-1", "Budget line"], [r.status === "infeasible" ? "dot-bad" : "dot-ok", "Your choice"]] }] };
  };

  V.inflation = function (x, r, b) {
    var ser = r.series, T = x.years, bs = b ? b.results.series : null;
    var top = Math.max(maxOf(ser, "nominal"), maxOf(ser, "real"), bs ? maxOf(bs, "real") : 0);
    var xMax = Math.max(T, b ? b.inputs.years : 0);
    var s1 = [];
    if (bs && b.inputs !== x && JSON.stringify(b.inputs) !== JSON.stringify(x)) s1.push({ type: "line", pts: bs.map(function (p) { return [p.t, p.real]; }), cls: "lc-muted dashed", label: "Baseline real" });
    s1.push({ type: "line", pts: ser.map(function (p) { return [p.t, p.nominal]; }), cls: "lc-1", label: "Nominal" });
    s1.push({ type: "line", pts: ser.map(function (p) { return [p.t, p.real]; }), cls: "lc-3", label: "Real" });
    var idxTop = Math.max(maxOf(ser, "price_index"), 100);
    var s2 = [{ type: "hline", y: 100, cls: "lc-muted dashed", label: "Year 0 = 100" },
              { type: "line", pts: ser.map(function (p) { return [p.t, p.price_index]; }), cls: "lc-2", label: "Price index" }];
    var summary = "After " + T + " " + plural(T, "year", "years") + ", nominal income is " + money(r.nominal_end) + " (" + signed(r.nominal_change, "%") + "), but in year-0 prices it is worth " + money(r.real_end) + " (" + signed(r.real_change, "%") + ").";
    var notes = [];
    if (r.status === "real_loss") notes.push("Prices rise faster than income (" + pct(x.inflation) + " vs " + pct(x.wage_growth) + " a year), so each year's income buys less. Purchasing power falls even though the paycheck gets bigger.");
    else if (r.status === "real_gain") notes.push("Income grows faster than prices (" + pct(x.wage_growth) + " vs " + pct(x.inflation) + " a year), so purchasing power rises.");
    else notes.push("Income grows at the same rate as prices, so real income stays the same: the bigger paycheck buys exactly the same amount.");
    notes.push("Exact real growth: (1 + " + pct(x.wage_growth) + ") ÷ (1 + " + pct(x.inflation) + ") − 1 = " + pct(r.real_growth) + " a year. The shortcut “income growth − inflation” gives " + fmtNum(r.real_growth_approx) + " percentage points, which is close only for small rates.");
    if (x.inflation === 0) notes.push("With zero inflation the price index stays at 100, so nominal and real income are the same.");
    if (x.inflation < 0) notes.push("Prices are falling (deflation), so the same nominal income buys more every year. Deflation can still be a problem for an economy, for example by making debts harder to repay.");
    notes.push("A grocery basket that costs " + money(x.basket0) + " today costs " + money(r.basket_end) + " in year " + T + ". One year's income buys " + fmtNum(r.baskets_start) + " baskets now and " + fmtNum(r.baskets_end) + " then.");
    if (b && JSON.stringify(b.inputs) !== JSON.stringify(x)) notes.push("Compared with the baseline, real income in the final year is " + signed(r.real_end - b.results.real_end, "$") + ".");
    return { summary: summary, notes: notes, charts: [
      { title: "Nominal and real income", desc: summary, xInteger: true, xLabel: "Year", yLabel: "Income ($ per year)", yPrefix: "$", x: [0, xMax], y: [0, niceMax(top * 1.08)], series: s1,
        legend: [["lc-1", "Nominal income"], ["lc-3", "Real income (year-0 dollars)"]].concat(s1[0].cls.indexOf("muted") >= 0 ? [["lc-muted dashed", "Baseline real income"]] : []) },
      { title: "Price level", desc: "Price index rises from 100 to " + fmtNum(r.price_index_end) + ".", xInteger: true, xLabel: "Year", yLabel: "Price index (year 0 = 100)", x: [0, xMax], y: [0, niceMax(idxTop * 1.08)], series: s2,
        legend: [["lc-2", "Price index"]] }] };
  };

  V["minimum-wage"] = function (x, r) {
    if (r.status === "no_equilibrium") return { summary: r.reason, notes: [r.reason + " Change the demand or supply values."], charts: [] };
    var wTop = niceMax(Math.max(r.demand_choke_wage, x.wmin, r.eq_wage) * 1.15);
    var lMax = niceMax(Math.max(x.a, x.c + x.d * wTop) * 1.05);
    var wStart = Math.max(0, -x.c / x.d);
    var s = [{ type: "line", pts: [[x.a, 0], [0, x.a / x.b]], cls: "lc-2", label: "Labor demand" },
             { type: "line", pts: [[x.c + x.d * wStart, wStart], [x.c + x.d * wTop, wTop]], cls: "lc-3", label: "Labor supply" }];
    if (x.wmin > 0) s.push({ type: "hline", y: x.wmin, cls: r.status === "nonbinding" ? "lc-muted dashed" : "lc-4", label: "Minimum wage " + money(x.wmin) });
    if (r.status !== "nonbinding") s.push({ type: "seg", x1: r.employment, y1: x.wmin, x2: r.labor_supplied, y2: x.wmin, cls: "gap" });
    s.push({ type: "dot", x: r.eq_employment, y: r.eq_wage, cls: r.status === "nonbinding" ? "dot-ok" : "dot-base", label: "Equilibrium", below: r.status !== "nonbinding" });
    if (r.status !== "nonbinding") {
      s.push({ type: "dot", x: r.employment, y: x.wmin, cls: "dot-ok", label: "Jobs", anchor: "end" });
      s.push({ type: "dot", x: r.labor_supplied, y: x.wmin, cls: "dot-bad", label: "Job seekers" });
    }
    var summary, notes = [];
    if (r.status === "nonbinding") {
      summary = "The minimum wage (" + money(x.wmin) + ") is not above the equilibrium wage (" + money(r.eq_wage) + "), so it doesn't bind: " + fmtNum(r.employment) + " thousand people work at " + money(r.wage) + " an hour.";
      notes.push("A minimum wage at or below the market wage changes nothing in this model: employers already pay more than the floor.");
    } else {
      summary = "The minimum wage binds: employers hire " + fmtNum(r.employment) + " thousand workers (" + signed(r.employment_change, "") + " thousand), while " + fmtNum(r.labor_supplied) + " thousand want to work at " + money(x.wmin) + " an hour.";
      notes.push("The floor (" + money(x.wmin) + ") is above the equilibrium wage (" + money(r.eq_wage) + "). In the competitive model, employers move up their demand curve and hire fewer workers, while more people want to work. The gap, " + fmtNum(r.excess_supply) + " thousand people, is excess labor supply.");
      notes.push("Workers who keep their jobs earn more per hour. Total hourly pay " + (r.wage_bill > r.wage_bill_before ? "rises" : (r.wage_bill < r.wage_bill_before ? "falls" : "stays the same")) + " from " + money(r.wage_bill_before) + " thousand to " + money(r.wage_bill) + " thousand, depending on how strongly employers react to the wage.");
      if (r.status === "binding_no_jobs") notes.push("The floor is at or above the wage at which employers would hire nobody (" + money(r.demand_choke_wage) + "), so employment falls to 0 in this model.");
      notes.push("When labor demand is less sensitive to wages (smaller b), the same floor costs fewer jobs. Try the scenario “Employers react little to wages”.");
    }
    notes.push("This is the competitive model only. If employers have wage-setting power (monopsony), a moderate minimum wage can raise both pay and employment, and empirical studies of real minimum wage increases find a range of effects.");
    return { summary: summary, notes: notes, charts: [{
      title: "Labor market", desc: summary, xLabel: "Workers (thousands)", yLabel: "Wage ($ per hour)", yPrefix: "$", x: [0, lMax], y: [0, wTop], series: s,
      legend: [["lc-2", "Labor demand"], ["lc-3", "Labor supply"], [r.status === "nonbinding" ? "lc-muted dashed" : "lc-4", "Minimum wage"]].concat(r.status === "nonbinding" ? [] : [["gap", "Excess labor supply"]]) }] };
  };

  V.inequality = function (x, r, b) {
    if (r.status === "no_income") return { summary: r.reason, notes: [r.reason], charts: [] };
    var lb = r.lorenz_before.map(function (p) { return [p.p * 100, p.s * 100]; });
    var la = r.lorenz_after.map(function (p) { return [p.p * 100, p.s * 100]; });
    var s1 = [{ type: "poly", pts: la.concat([[0, 0]]), cls: "fill-1" },
              { type: "line", pts: [[0, 0], [100, 100]], cls: "lc-muted", label: "Perfect equality" },
              { type: "line", pts: lb, cls: "lc-2 dashed", label: "Before" },
              { type: "line", pts: la, cls: "lc-1", label: "After" }];
    var top = Math.max(maxOf(r.pre), maxOf(r.post));
    var bars = [];
    for (var i = 0; i < 5; i++) { bars.push({ x: i + 1 - 0.19, y: r.pre[i], cls: "bar-muted" }); bars.push({ x: i + 1 + 0.19, y: r.post[i], cls: "bar-1" }); }
    var summary = "Gini coefficient: " + fmtNum(r.gini_before) + " before and " + fmtNum(r.gini_after) + " after taxes and transfers (" + (r.status === "more_equal" ? "more equal" : r.status === "less_equal" ? "less equal" : "no change") + "). 0 means everyone has the same income.";
    var payers = [];
    r.taxes.forEach(function (t, k) { if (t > 0) payers.push("household " + (k + 1) + " pays " + money(t) + "k"); });
    var notes = [payers.length ? "The tax takes " + pct(x.tax_rate) + " of income above " + money(x.exemption) + "k: " + payers.join(", ") + ". Total revenue is " + money(r.revenue) + "k." : "Nobody pays tax with these settings, so incomes don't change."];
    var modeNote = {
      equal: "Every household receives the same payment (" + money(r.revenue / 5) + "k). That is a bigger share of a low income than of a high one, so the payout itself is equalizing.",
      bottom_two: "All revenue goes to the two lowest-income households (" + money(r.revenue / 2) + "k each). Targeting concentrates support where incomes are lowest.",
      proportional: "Payments follow each household's pre-tax income, so high earners get the most back. With no exemption, everyone pays and receives the same share and the Gini coefficient does not move.",
      top_two: "Here the revenue goes to the two highest-income households. Even with a tax, this design moves money upward and can increase inequality: redistribution only reduces inequality if it is designed to."
    }[x.mode];
    if (r.revenue > 0) notes.push(modeNote);
    notes.push("The Lorenz curve shows the share of total income held by the poorest p% of households. The further it bows below the equality line, the higher the Gini coefficient.");
    if (r.gini_before === 0) notes.push("All incomes are equal, so the Lorenz curve is the equality line and the Gini coefficient is 0.");
    if (r.ratio_before !== null && r.ratio_after !== null) notes.push("The highest income is " + fmtNum(r.ratio_before) + " times the lowest before, and " + fmtNum(r.ratio_after) + " times after.");
    if (b && JSON.stringify(b.inputs) !== JSON.stringify(x) && b.results.gini_after !== undefined) notes.push("Compared with the baseline, the after-policy Gini coefficient changes by " + signed(r.gini_after - b.results.gini_after, "") + ".");
    return { summary: summary, notes: notes, charts: [
      { title: "Lorenz curve", desc: summary, xLabel: "Share of households, poorest first (%)", yLabel: "Share of total income (%)", ySuffix: "%", xSuffix: "%", x: [0, 100], y: [0, 100], series: s1, square: true,
        legend: [["lc-muted", "Perfect equality"], ["lc-2 dashed", "Before"], ["lc-1", "After taxes and transfers"]] },
      { title: "Income by household", desc: "Incomes before and after for households 1 to 5.", xLabel: "Household (fictional)", yLabel: "Income ($ thousand)", yPrefix: "$", x: [0.4, 5.6], y: [0, niceMax(top * 1.1)],
        xTicks: [1, 2, 3, 4, 5].map(function (k) { return { v: k, label: "H" + k }; }), series: [{ type: "bars", bars: bars, width: 0.34 }],
        legend: [["bar-muted", "Before"], ["bar-1", "After"]] }] };
  };

  V["compound-interest"] = function (x, r) {
    var ser = r.series, top = Math.max(maxOf(ser, "balance"), 1);
    var s1 = [{ type: "area", pts: ser.map(function (p) { return [p.t, p.contributions]; }), cls: "fill-3" },
              { type: "band", upper: ser.map(function (p) { return [p.t, p.balance]; }), lower: ser.map(function (p) { return [p.t, p.contributions]; }), cls: "fill-1" },
              { type: "line", pts: ser.map(function (p) { return [p.t, p.balance]; }), cls: "lc-1", label: "Balance" },
              { type: "line", pts: ser.map(function (p) { return [p.t, p.real]; }), cls: "lc-2 dashed", label: "In today's prices" }];
    var charts = [{ title: "Savings over time", desc: "Balance grows to " + money(r.balance_end) + ".", xInteger: true, xLabel: "Year", yLabel: "Balance ($)", yPrefix: "$", x: [0, x.years], y: [0, niceMax(top * 1.08)], series: s1,
                    legend: [["fill-3", "Your deposits"], ["fill-1", "Interest earned"], ["lc-1", "Balance"], ["lc-2 dashed", "Balance in today's prices"]] }];
    var notes = [], extra = "";
    var summary = "After " + x.years + " " + plural(x.years, "year", "years") + " you would have " + money(r.balance_end) + ": " + money(r.contributions_end) + " you deposited plus " + money(r.interest_end) + " of interest. In today's prices that is about " + money(r.real_balance_end) + ".";
    if (x.rate === 0) notes.push("With 0% interest the balance is exactly what you deposited; nothing compounds.");
    else notes.push("Compounding means interest also earns interest. An APR of " + pct(x.rate) + " credited " + ({ 1: "once a year", 4: "quarterly", 12: "monthly", 365: "daily" })[x.compounding] + " is an APY of " + pct(r.apy) + ". More frequent compounding raises the APY a little, not the APR.");
    notes.push(r.real_return < 0 ? "The interest rate is below inflation, so the real return is " + pct(r.real_return) + " a year: the balance grows in dollars but buys less over time."
      : "After inflation of " + pct(x.inflation) + ", the real return is about " + pct(r.real_return) + " a year.");
    var ls = r.loan_series;
    if (r.loan_status === "repaid" || r.loan_status === "not_repaid_in_50_years") {
      var lt = maxOf(ls, "t");
      charts.push({ title: "Loan balance", desc: "Loan balance falls from " + money(x.loan) + ".", xLabel: "Years from now", yLabel: "Amount owed ($)", yPrefix: "$", x: [0, Math.max(1, Math.ceil(lt))], y: [0, niceMax(x.loan * 1.08)],
                    series: [{ type: "line", pts: ls.map(function (p) { return [p.t, p.balance]; }), cls: "lc-4", label: "Owed" }], legend: [["lc-4", "Amount still owed"]] });
      if (r.loan_status === "repaid") notes.push("Borrowing scenario: a " + money(x.loan) + " loan at " + pct(x.loan_apr) + " APR (" + pct(r.loan_ear) + " as an effective annual rate) with " + money(x.payment) + " monthly payments takes " + r.loan_months + " months and costs " + money(r.loan_total_interest) + " in interest.");
      else notes.push("Borrowing scenario: the payment covers the interest only barely, so after 50 years " + money(r.loan_remaining) + " would still be owed.");
      notes.push("Interest on a loan compounds against you: in the first month " + money(r.loan_first_interest) + " of the payment goes to interest, and only the rest reduces the debt.");
    } else if (r.loan_status === "never_repaid") {
      extra = "<p class='lab-warn'>The " + money(x.payment) + " monthly payment doesn't cover the first month's interest (" + money(r.loan_first_interest) + "), so this loan would never be repaid. Raise the payment to see a repayment schedule.</p>";
      notes.push("When a payment is smaller than the interest charged, the debt grows instead of shrinking.");
    }
    return { summary: summary, notes: notes, charts: charts, extra: extra };
  };

  V["comparative-advantage"] = function (x, r) {
    var foods = [r.max_food_a, r.max_food_b], cloths = [r.max_cloth_a, r.max_cloth_b];
    if (r.cons_food_a !== undefined) { foods.push(r.cons_food_a, r.cons_food_b); cloths.push(r.cons_cloth_a, r.cons_cloth_b); }
    var xMax = niceCeil(maxOf(foods) * 1.1), yMax = niceCeil(maxOf(cloths) * 1.1);
    var s = [{ type: "line", pts: [[r.max_food_a, 0], [0, r.max_cloth_a]], cls: "lc-1", label: "Alba" },
             { type: "line", pts: [[r.max_food_b, 0], [0, r.max_cloth_b]], cls: "lc-2", label: "Boren" }];
    var traded = r.cons_food_a !== undefined;
    if (traded) {
      var F = r.world_food_after, C = r.world_cloth_after, expA = r.food_exporter === "A";
      s.push({ type: "line", pts: [[F, 0], [F - C / x.price, C]], cls: (expA ? "lc-1" : "lc-2") + " dashed" });
      s.push({ type: "line", pts: [[0, C], [C / x.price, 0]], cls: (expA ? "lc-2" : "lc-1") + " dashed" });
    }
    s.push({ type: "dot", x: r.autarky_food_a, y: r.autarky_cloth_a, cls: "dot-hollow-1", label: "Alba before", below: true });
    s.push({ type: "dot", x: r.autarky_food_b, y: r.autarky_cloth_b, cls: "dot-hollow-2", label: "Boren before", below: true, anchor: "end" });
    if (traded) {
      s.push({ type: "dot", x: r.cons_food_a, y: r.cons_cloth_a, cls: "dot-1", label: "Alba with trade" });
      s.push({ type: "dot", x: r.cons_food_b, y: r.cons_cloth_b, cls: "dot-2", label: "Boren with trade" });
    }
    var who = { A: "Alba", B: "Boren" }, other = { A: "Boren", B: "Alba" };
    var notes = ["Opportunity cost of 1 food: " + fmtNum(r.oc_a) + " cloth in Alba, " + fmtNum(r.oc_b) + " cloth in Boren."];
    var abs = function (k, good) { return k === "none" ? "Both countries need the same hours for " + good + "." : who[k] + " has the absolute advantage in " + good + " (fewer hours per unit)."; };
    notes.push(abs(r.abs_food, "food") + " " + abs(r.abs_cloth, "cloth"));
    var summary;
    if (r.status === "no_comparative_advantage") {
      summary = r.reason;
    } else {
      var e = r.food_exporter;
      notes.push(who[e] + " has the comparative advantage in food (lower opportunity cost) and " + other[e] + " in cloth. Comparative advantage, not absolute advantage, decides who should specialize in what.");
      notes.push("Specializing raises world output from " + fmtNum(r.world_food_before) + " to " + fmtNum(r.world_food_after) + " food and from " + fmtNum(r.world_cloth_before) + " to " + fmtNum(r.world_cloth_after) + " cloth (compared with the production you chose before trade).");
      notes.push("Both countries gain only if 1 food trades for more than " + fmtNum(r.gain_range_low) + " and less than " + fmtNum(r.gain_range_high) + " cloth. Your terms: " + fmtNum(x.price) + ".");
      if (r.status === "infeasible_trade") summary = r.reason;
      else if (r.status === "no_trade") summary = "No food is traded, so each country can only consume what it produces itself after specializing.";
      else {
        var dA = [r.cons_food_a - r.autarky_food_a, r.cons_cloth_a - r.autarky_cloth_a], dB = [r.cons_food_b - r.autarky_food_b, r.cons_cloth_b - r.autarky_cloth_b];
        notes.push("Compared with before trade: Alba " + signed(dA[0], "food") + ", " + signed(dA[1], "cloth") + "; Boren " + signed(dB[0], "food") + ", " + signed(dB[1], "cloth") + ". Whether a country gets more of both goods also depends on how much it trades.");
        summary = {
          mutual_gain: "Both countries gain: each consumes a combination beyond its own production possibility frontier, which it could not reach without trade.",
          one_side_no_gain: "The terms of trade equal one country's own opportunity cost, so that country gains nothing from trading. The other country takes all the gains.",
          one_side_loses: "These terms of trade lie outside the range between the two opportunity costs, so one country would be worse off than producing for itself. It would not agree to this deal."
        }[r.status];
      }
    }
    return { summary: summary, notes: notes, charts: [{
      title: "Production possibility frontiers", desc: summary, xLabel: "Food (units)", yLabel: "Cloth (units)", x: [0, xMax], y: [0, yMax], series: s,
      legend: [["lc-1", "Alba's frontier"], ["lc-2", "Boren's frontier"]].concat(traded ? [["lc-muted dashed", "Trading possibilities"], ["dot-1", "Consumption with trade"]] : []).concat([["dot-hollow-1", "Before trade"]]) }] };
  };

  V["sdg-project"] = function (x, r, b, projects) {
    var ser = r.series;
    var lo = Math.min(minOf(ser, "dcf"), minOf(ser, "cum"), minOf(ser, "dcum")), hi = Math.max(maxOf(ser, "dcf"), maxOf(ser, "cum"), maxOf(ser, "dcum"), 0);
    var bars = ser.map(function (p) { return { x: p.t, y: p.dcf, cls: p.dcf < 0 ? "bar-4" : "bar-3" }; });
    var s = [{ type: "bars", bars: bars, width: Math.min(0.7, 0.7 * 15 / Math.max(15, x.years)) },
             { type: "hline", y: 0, cls: "lc-axis" },
             { type: "line", pts: ser.map(function (p) { return [p.t, p.cum]; }), cls: "lc-muted dashed", label: "Not discounted" },
             { type: "line", pts: ser.map(function (p) { return [p.t, p.dcum]; }), cls: "lc-1", label: "Discounted" }];
    var unit = r.env_unit;
    var summary = "Net present value: " + money(r.npv) + ". " + (r.status === "npv_positive" ? "At a " + pct(x.discount) + " discount rate the benefits are worth more than the costs in today's money."
      : r.status === "npv_negative" ? "At a " + pct(x.discount) + " discount rate the costs are worth more than the money benefits in today's money." : "Benefits and costs are worth the same today.");
    var notes = ["Discounting: $1 received in year t is worth 1 ÷ (1 + " + pct(x.discount) + ")^t today, so late benefits count for less. The discounted cumulative line ends at the NPV."];
    if (x.discount === 0) notes.push("With a 0% discount rate, future money counts the same as money today, so the NPV equals the simple total.");
    notes.push(r.payback === null ? "The project never earns back its upfront cost, even without discounting." :
      "The money pays back after about " + fmtNum(r.payback) + " years without discounting" + (r.discounted_payback === null ? ", but never once future money is discounted." : " and " + fmtNum(r.discounted_payback) + " years with discounting."));
    if (r.bcr !== null) notes.push("Benefit-cost ratio: " + fmtNum(r.bcr) + ". Above 1 means the discounted money benefits exceed the discounted costs.");
    notes.push("Environmental benefit: " + fmtNum(r.env_total) + " " + unit.replace(" per year", "") + " over " + x.years + " " + plural(x.years, "year", "years") + ". " +
      (r.npv_with_env !== undefined ? "Valuing each unit at " + money(x.env_value) + " (an assumption) changes the NPV to " + money(r.npv_with_env) + "." : "It isn't counted in the money NPV. Enter an assumed value per unit to see how much it would change the result."));
    notes.push("Opportunity cost: the " + money(x.investment) + " could fund something else. Compare the alternatives below, and remember that every number here is uncertain.");
    var rows = r.alternatives.map(function (a) {
      return "<tr" + (a.project === x.project ? " class='is-current'" : "") + "><th scope='row'>" + a.label + (a.project === x.project ? " <span class='pill pill-on'>Selected</span>" : "") + "</th><td>" + money(a.npv) + "</td></tr>";
    }).join("");
    var extra = "<h2 class='lab-sub'>Compare alternatives at a " + pct(x.discount) + " discount rate</h2><p class='hint'>Each project uses its own starting values (not your edits), money benefits only.</p>" +
      "<div class='sim-table-wrap'><table class='ec-table sim-table'><thead><tr><th scope='col'>Project</th><th scope='col'>NPV</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
    return { summary: summary, notes: notes, extra: extra, charts: [{
      title: "Project cash flows", desc: summary, xLabel: "Year", yLabel: "Dollars", yPrefix: "$", x: [-0.6, x.years + 0.6], y: niceRange(lo, hi),
      xInteger: true, series: s,
      legend: [["bar-3", "Net cash flow, discounted"], ["bar-4", "Upfront cost"], ["lc-1", "Cumulative, discounted"], ["lc-muted dashed", "Cumulative, not discounted"]] }] };
  };

  function ticksFor(lo, hi, count, integer) {
    var span = hi - lo;
    if (span <= 0) return [lo];
    var raw = span / count, exp = Math.pow(10, Math.floor(Math.log10(raw))), step = exp;
    (integer ? [1, 2, 5, 10] : [1, 2, 2.5, 5, 10]).some(function (m) { step = m * exp; return m * exp >= raw - 1e-12; });
    if (integer) step = Math.max(1, Math.round(step));
    var out = [], start = Math.ceil(lo / step - 1e-9) * step;
    for (var v = start; v <= hi + 1e-9 * step; v += step) out.push(Math.round(v / step) * step);
    return out;
  }

  // ------------------------------------------------------------------ SVG chart
  var NS = "http://www.w3.org/2000/svg", W = 560, H = 350, PL = 66, PR = 20, PT = 34, PB = 50;
  var FRAME = { W: W, H: H, PL: PL, PR: PR, PT: PT, PB: PB };
  var COMPACT = { W: 380, H: 320, PL: 60, PR: 14, PT: 34, PB: 50 };   // narrow screens: fewer pixels per label, so text renders larger
  function tick(v, prefix, suffix) {
    var a = Math.abs(v), t;
    if (a >= 1e6) t = (Math.round(v / 1e5) / 10) + "M";
    else if (a >= 1e4) t = (Math.round(v / 100) / 10) + "k";
    else t = String(Math.round(v * 100) / 100);
    if (prefix && v < 0) t = "-" + prefix + t.slice(1); else if (prefix) t = prefix + t;
    return t + (suffix || "");
  }
  function scale(o, f) {
    f = f || FRAME;
    return {
      X: function (v) { return f.PL + (v - o.x[0]) / (o.x[1] - o.x[0]) * (f.W - f.PL - f.PR); },
      Y: function (v) { return f.H - f.PB - (v - o.y[0]) / (o.y[1] - o.y[0]) * (f.H - f.PT - f.PB); }
    };
  }
  function geometry(o, f) {
    /* Pure: returns the list of SVG primitives (in pixels) for a chart spec. Tests use this to check coordinates. */
    var sc = scale(o, f), X = sc.X, Y = sc.Y, out = [];
    var px = function (p) { return [Math.round(X(p[0]) * 10) / 10, Math.round(Y(p[1]) * 10) / 10]; };
    (o.series || []).forEach(function (s) {
      if (s.type === "line") out.push({ kind: "polyline", cls: s.cls, pts: s.pts.map(px), label: s.label, data: s.pts });
      else if (s.type === "poly") out.push({ kind: "polygon", cls: s.cls, pts: s.pts.map(px) });
      else if (s.type === "area") out.push({ kind: "polygon", cls: s.cls, pts: [px([s.pts[0][0], 0])].concat(s.pts.map(px), [px([s.pts[s.pts.length - 1][0], 0])]) });
      else if (s.type === "band") out.push({ kind: "polygon", cls: s.cls, pts: s.upper.map(px).concat(s.lower.slice().reverse().map(px)) });
      else if (s.type === "hline") out.push({ kind: "polyline", cls: s.cls, pts: [px([o.x[0], s.y]), px([o.x[1], s.y])], label: s.label, data: [[o.x[0], s.y], [o.x[1], s.y]], hline: true });
      else if (s.type === "seg") out.push({ kind: "polyline", cls: s.cls, pts: [px([s.x1, s.y1]), px([s.x2, s.y2])], data: [[s.x1, s.y1], [s.x2, s.y2]] });
      else if (s.type === "dot") out.push({ kind: "dot", cls: s.cls, at: px([s.x, s.y]), label: s.label, anchor: s.anchor, below: s.below, data: [s.x, s.y] });
      else if (s.type === "bars") s.bars.forEach(function (bar) {
        var x0 = X(bar.x - s.width / 2), x1 = X(bar.x + s.width / 2), y0 = Y(0), y1 = Y(bar.y);
        out.push({ kind: "rect", cls: bar.cls, x: Math.round(x0 * 10) / 10, y: Math.round(Math.min(y0, y1) * 10) / 10,
                   w: Math.round((x1 - x0) * 10) / 10, h: Math.round(Math.abs(y1 - y0) * 10) / 10, data: [bar.x, bar.y] });
      });
    });
    return out;
  }

  function svgEl(name, attrs, parent, text) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) if (attrs[k] !== undefined && attrs[k] !== null) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  }
  var uid = 0;
  function renderChart(o, compact) {
    uid += 1;
    var f = compact ? COMPACT : FRAME, W = f.W, H = f.H, PL = f.PL, PR = f.PR, PT = f.PT, PB = f.PB;
    var fig = document.createElement("figure"); fig.className = "lab-chart";
    var cap = document.createElement("figcaption"); cap.className = "lab-chart-title"; cap.textContent = o.title; fig.appendChild(cap);
    var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-labelledby": "lc-t" + uid + " lc-d" + uid });
    svgEl("title", { id: "lc-t" + uid }, svg, o.title);
    svgEl("desc", { id: "lc-d" + uid }, svg, o.desc || "");
    var sc = scale(o, f), X = sc.X, Y = sc.Y;
    var clip = svgEl("clipPath", { id: "lc-c" + uid }, svgEl("defs", {}, svg));
    svgEl("rect", { x: PL, y: PT - 2, width: W - PL - PR + 2, height: H - PT - PB + 4 }, clip);
    var yt = ticksFor(o.y[0], o.y[1], compact ? 4 : 5), xt = o.xTicks || ticksFor(Math.max(o.x[0], o.xInteger ? 0 : o.x[0]), o.x[1], compact ? 4 : 6, o.xInteger).map(function (v) { return { v: v, label: tick(v, o.xPrefix, o.xSuffix) }; });
    yt.forEach(function (v) {
      svgEl("line", { "class": "gr-grid", x1: PL, x2: W - PR, y1: Y(v), y2: Y(v) }, svg);
      svgEl("text", { "class": "gr-tick", x: PL - 8, y: Y(v) + 4, "text-anchor": "end" }, svg, tick(v, o.yPrefix, o.ySuffix));
    });
    xt.forEach(function (t) {
      var atRight = X(t.v) > W - PR - 14;
      svgEl("text", { "class": "gr-tick", x: atRight ? W - PR : X(t.v), y: H - PB + 18, "text-anchor": atRight ? "end" : "middle" }, svg, t.label);
    });
    svgEl("line", { "class": "gr-axis", x1: PL, y1: PT, x2: PL, y2: H - PB }, svg);
    var y0 = o.y[0] <= 0 && o.y[1] >= 0 ? Y(0) : H - PB;
    svgEl("line", { "class": "gr-axis", x1: PL, y1: H - PB, x2: W - PR, y2: H - PB }, svg);
    svgEl("text", { "class": "gr-axis-label", x: 4, y: PT - 16, "text-anchor": "start" }, svg, o.yLabel);
    svgEl("text", { "class": "gr-axis-label", x: W - PR, y: H - 10, "text-anchor": "end" }, svg, o.xLabel);
    var g = svgEl("g", { "clip-path": "url(#lc-c" + uid + ")" }, svg), labels = svgEl("g", {}, svg);
    geometry(o, f).forEach(function (p) {
      if (p.kind === "polygon") svgEl("polygon", { "class": "lab-shape " + p.cls, points: p.pts.map(function (q) { return q.join(","); }).join(" ") }, g);
      else if (p.kind === "polyline") {
        svgEl("polyline", { "class": "lab-line " + p.cls, points: p.pts.map(function (q) { return q.join(","); }).join(" ") }, g);
        if (p.label && p.hline) svgEl("text", { "class": "lab-label " + p.cls, x: W - PR - 4, y: p.pts[0][1] + 20, "text-anchor": "end" }, labels, p.label);
      } else if (p.kind === "rect") svgEl("rect", { "class": "lab-bar " + p.cls, x: p.x, y: p.y, width: p.w, height: Math.max(p.h, 0.5), rx: 2 }, g);
      else if (p.kind === "dot") {
        svgEl("circle", { "class": "lab-dot " + p.cls, cx: p.at[0], cy: p.at[1], r: 6 }, g);
        if (p.label) {
          var right = p.anchor !== "end" && p.at[0] < W - PR - 90;
          svgEl("text", { "class": "lab-label", x: p.at[0] + (right ? 10 : -10), y: p.at[1] + (p.below ? 22 : -9), "text-anchor": right ? "start" : "end" }, labels, p.label);
        }
      }
    });
    if (y0 !== H - PB) svgEl("line", { "class": "gr-zero", x1: PL, x2: W - PR, y1: y0, y2: y0 }, svg);
    fig.appendChild(svg);
    if (o.legend && o.legend.length) {
      var ul = document.createElement("ul"); ul.className = "lab-legend";
      o.legend.forEach(function (l) {
        var li = document.createElement("li"), sw = document.createElement("span");
        sw.className = "lab-swatch " + l[0]; sw.setAttribute("aria-hidden", "true");
        li.appendChild(sw); li.appendChild(document.createTextNode(l[1])); ul.appendChild(li);
      });
      fig.appendChild(ul);
    }
    return fig;
  }

  // ------------------------------------------------------------------ page controller
  function init(rootEl) {
    var simId = rootEl.getAttribute("data-lab"), spec = JSON.parse(rootEl.getAttribute("data-spec"));
    var defaults = JSON.parse(rootEl.getAttribute("data-defaults")), projects = JSON.parse(rootEl.getAttribute("data-projects"));
    var form = rootEl.querySelector(".sim-form"), ctls = rootEl.querySelectorAll(".sim-ctl");
    var summary = rootEl.querySelector("[data-role=summary]"), chartsBox = rootEl.querySelector("[data-role=charts]");
    var table = rootEl.querySelector("[data-role=table]"), notesBox = rootEl.querySelector("[data-role=notes]"), extraBox = rootEl.querySelector("[data-role=extra]");
    var base = null, last = null;
    function isCompact(n) {   // width of one chart: the grid puts two side by side from 774px (2 × 380 + gap)
      var w = chartsBox.clientWidth;
      if (!w) return false;
      return (n > 1 && w >= 774 ? (w - 14) / 2 : w) < 520;
    }

    function read() {
      var raw = {};
      ctls.forEach(function (c) { var f = c.querySelector("[data-role=number], [data-role=select]"); raw[c.getAttribute("data-name")] = f.value; });
      return raw;
    }
    function setValues(values) {
      ctls.forEach(function (c) {
        var name = c.getAttribute("data-name");
        if (!(name in values)) return;
        var f = c.querySelector("[data-role=number], [data-role=select]"), rg = c.querySelector("[data-role=range]");
        f.value = values[name];
        if (rg) rg.value = values[name];
      });
    }
    function renderTable(res) {
      var bres = base ? base.results : null, head = "<tr><th scope='col'>Result</th>" + (bres ? "<th scope='col'>Baseline</th>" : "") + "<th scope='col'>Now</th>" + (bres ? "<th scope='col'>Change</th>" : "") + "</tr>";
      table.querySelector("thead").innerHTML = head;
      var body = table.querySelector("tbody"); body.innerHTML = "";
      spec.rows.forEach(function (row) {
        var key = row[0], unit = row[2], now = typeof res[key] === "number" ? res[key] : null, was = bres && typeof bres[key] === "number" ? bres[key] : null;
        if (now === null && was === null) return;
        var tr = document.createElement("tr"), cells = [row[1]];
        if (bres) cells.push(fmtUnit(was, unit));
        cells.push(fmtUnit(now, unit));
        if (bres) cells.push(now === null || was === null ? "–" : (Math.abs(now - was) < 1e-9 ? "No change" : signed(now - was, unit)));
        cells.forEach(function (text, i) { var td = document.createElement(i ? "td" : "th"); if (!i) td.scope = "row"; td.textContent = text; tr.appendChild(td); });
        body.appendChild(tr);
      });
    }
    function update() {
      var out = M.run(simId, spec, read(), projects);
      ctls.forEach(function (c) {
        var name = c.getAttribute("data-name"), f = c.querySelector("[data-role=number], [data-role=select]"), err = c.querySelector(".sim-err");
        var bad = !out.ok && out.field === name;
        f.setAttribute("aria-invalid", bad ? "true" : "false");
        err.textContent = bad ? out.message : "";
      });
      if (!out.ok) { summary.textContent = "Check your input: " + out.message; rootEl.dataset.state = "invalid"; return; }
      if (!base) base = out;
      last = out;
      var view = V[simId](out.inputs, out.results, base === out ? null : base, projects);
      summary.textContent = view.summary;
      chartsBox.innerHTML = "";
      var compact = isCompact(view.charts.length);
      view.charts.forEach(function (c) { chartsBox.appendChild(renderChart(c, compact)); });
      renderTable(out.results);
      extraBox.innerHTML = view.extra || "";
      notesBox.innerHTML = "<p class='sim-notes-title'>What it means</p>";
      var ul = document.createElement("ul"); ul.className = "ec-list";
      view.notes.forEach(function (t) { var li = document.createElement("li"); li.textContent = t; ul.appendChild(li); });
      notesBox.appendChild(ul);
      rootEl.dataset.state = out.results.status;
      try {
        var q = new URLSearchParams(); Object.keys(out.inputs).forEach(function (k) { q.set(k, out.inputs[k]); });
        history.replaceState(null, "", location.pathname + "?" + q.toString());
      } catch (e) { /* history may be unavailable */ }
    }
    ctls.forEach(function (c) {
      var rg = c.querySelector("[data-role=range]"), f = c.querySelector("[data-role=number], [data-role=select]");
      if (rg) {
        rg.removeAttribute("tabindex");
        rg.addEventListener("input", function () { f.value = rg.value; update(); });
        f.addEventListener("input", function () { var v = M.parseNumber(f.value); if (v !== null) rg.value = Math.min(Math.max(v, +rg.min), +rg.max); update(); });
      } else {
        f.addEventListener("change", function () {
          if (simId === "sdg-project" && c.getAttribute("data-name") === "project") setValues(projects[f.value].values);
          update();
        });
      }
    });
    rootEl.querySelectorAll("[data-preset]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setValues(spec.presets[+btn.getAttribute("data-preset")].values);
        rootEl.querySelectorAll("[data-preset]").forEach(function (b) { b.setAttribute("aria-pressed", b === btn ? "true" : "false"); });
        update();
      });
    });
    rootEl.querySelector("[data-action=baseline]").addEventListener("click", function () { if (last) { base = last; update(); } });
    rootEl.querySelector("[data-action=reset]").addEventListener("click", function () {
      setValues(defaults); base = null;
      rootEl.querySelectorAll("[data-preset]").forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
      update();
    });
    var linkBtn = rootEl.querySelector("[data-action=link]");
    linkBtn.textContent = "Copy scenario link";
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var done = function (ok) { linkBtn.textContent = ok ? "Link copied" : "Copy the address bar to share"; setTimeout(function () { linkBtn.textContent = "Copy scenario link"; }, 2500); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(location.href).then(function () { done(true); }, function () { done(false); });
      else done(false);
    });
    update();
    var lastMode = isCompact(chartsBox.children.length), timer = null;
    window.addEventListener("resize", function () {
      clearTimeout(timer);
      timer = setTimeout(function () { if (isCompact(chartsBox.children.length) !== lastMode) { lastMode = !lastMode; update(); } }, 150);
    });
  }

  var api = { views: V, geometry: geometry, fmtUnit: fmtUnit, ticksFor: ticksFor, W: W, H: H, PL: PL, PR: PR, PT: PT, PB: PB };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else {
    root.EconovaLabUI = api;
    document.querySelectorAll("[data-lab]").forEach(init);
  }
})(typeof window !== "undefined" ? window : this);
