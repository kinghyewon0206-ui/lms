/* ECONOVA simulation UI: sliders and number inputs, live SVG graph, comparison table, interpretation panel.
   Math runs in econova-sim.js (EconovaSim); on save the server recomputes with the same formulas. */
(function () {
  "use strict";
  var S = window.EconovaSim, NS = "http://www.w3.org/2000/svg";
  var W = 520, H = 340, PAD = 46;

  function fmt(v) { return (Math.round(v * 1e4) / 1e4).toString(); }
  // Money: "$" units go before the number ($30, -$5, $6 per unit); other units go after (40 units, 12 kg)
  function money(v) { var n = Math.round(v * 1e4) / 1e4; return (n < 0 ? "-$" : "$") + fmt(Math.abs(n)); }
  function withUnit(v, unit) {
    if (unit && unit.charAt(0) === "$") return money(v) + unit.slice(1);
    if (unit && unit.slice(0, 5) === "units" && Math.abs(v) === 1) unit = "unit" + unit.slice(5);   // 1 unit, 2 units
    return fmt(v) + (unit ? " " + unit : "");
  }
  function el(name, attrs, parent, text) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  }

  /* Draw the line Q = q0 + slope·P clipped to the axes (same method as econova/graphs.py) */
  function segment(q0, slope, pMax, qMax) {
    // price interval where 0 ≤ Q ≤ qMax and 0 ≤ P ≤ pMax
    var lo, hi;
    if (slope < 0) { lo = (qMax - q0) / slope; hi = q0 / -slope; }   // demand: Q falls as P rises
    else { lo = -q0 / slope; hi = (qMax - q0) / slope; }              // supply: Q rises as P rises
    lo = Math.max(0, lo); hi = Math.min(pMax, hi);
    if (lo >= hi) return null;
    return [[q0 + slope * lo, lo], [q0 + slope * hi, hi]];
  }

  function draw(container, sim, x, r, base, baseRes) {
    var pTop = Math.max(x.a / x.b, 1), pMax = S.niceMax(pTop * 1.1);
    var qMax = S.niceMax(Math.max(x.a, x.c + x.d * pTop, 1) * 1.1);
    var X = function (q) { return PAD + q / qMax * (W - 2 * PAD); };
    var Y = function (p) { return H - PAD - p / pMax * (H - 2 * PAD); };
    container.innerHTML = "";
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-labelledby": "" }, null);
    var desc = el("desc", {}, svg, summaryText(sim, x, r));
    desc.id = "d" + Math.random().toString(36).slice(2);
    svg.setAttribute("aria-labelledby", desc.id);
    for (var i = 0; i <= 4; i++) {
      var pv = pMax * i / 4, qv = qMax * i / 4;
      el("line", { "class": "gr-grid", x1: PAD, y1: Y(pv), x2: W - PAD, y2: Y(pv) }, svg);
      el("text", { "class": "gr-tick", x: PAD - 8, y: Y(pv) + 4, "text-anchor": "end" }, svg, fmt(pv));
      el("text", { "class": "gr-tick", x: X(qv), y: H - PAD + 18, "text-anchor": "middle" }, svg, fmt(qv));
    }
    el("line", { "class": "gr-axis", x1: PAD, y1: PAD, x2: PAD, y2: H - PAD }, svg);
    el("line", { "class": "gr-axis", x1: PAD, y1: H - PAD, x2: W - PAD, y2: H - PAD }, svg);
    el("text", { "class": "gr-axis-label", x: PAD, y: PAD - 14, "text-anchor": "middle" }, svg, "Price P ($)");
    el("text", { "class": "gr-axis-label", x: W - PAD, y: H - PAD + 36, "text-anchor": "end" }, svg, "Quantity Q (units)");
    function line(q0, slope, cls, label, dashed, left) {
      var s = segment(q0, slope, pMax, qMax);
      if (!s) return;
      el("line", { "class": cls + (dashed ? " gr-base" : ""), x1: X(s[0][0]), y1: Y(s[0][1]), x2: X(s[1][0]), y2: Y(s[1][1]) }, svg);
      if (label) el("text", { "class": "gr-label " + cls + "-label", x: X(s[1][0]) + (left ? -6 : 4), "text-anchor": left ? "end" : "start", y: Y(s[1][1]) + (cls === "gr-demand" ? 14 : -4) }, svg, label);
    }
    function point(p, q) { el("circle", { "class": "gr-eq", cx: X(q), cy: Y(p), r: 4.5 }, svg); }
    if (sim === "supply-demand") {
      var changed = base && (base.a !== x.a || base.b !== x.b || base.c !== x.c || base.d !== x.d);
      if (changed) {
        line(base.a, -base.b, "gr-demand", null, true);
        line(base.c, base.d, "gr-supply", null, true);
        if (baseRes && baseRes.status === "interior") el("circle", { "class": "gr-eq gr-eq-base", cx: X(baseRes.quantity), cy: Y(baseRes.price), r: 4 }, svg);
      }
      line(x.a, -x.b, "gr-demand", "D");
      line(x.c, x.d, "gr-supply", "S");
      if (r.status === "interior") point(r.price, r.quantity);
    } else {
      line(x.a, -x.b, "gr-demand", "D");
      line(x.c, x.d, "gr-supply", "S", x.t > 0);
      if (x.t > 0) line(x.c - x.d * x.t, x.d, "gr-supply", "S+t", false, true);
      var b0 = r.baseline;
      if (b0 && b0.status === "interior") el("circle", { "class": "gr-eq gr-eq-base", cx: X(b0.quantity), cy: Y(b0.price), r: 4 }, svg);
      if (r.status === "interior") {
        var xq = X(r.quantity);
        el("line", { "class": "gr-price", x1: PAD, y1: Y(r.consumer_price), x2: xq, y2: Y(r.consumer_price) }, svg);
        el("line", { "class": "gr-price", x1: PAD, y1: Y(r.producer_price), x2: xq, y2: Y(r.producer_price) }, svg);
        el("line", { "class": "gr-wedge", x1: xq, y1: Y(r.consumer_price), x2: xq, y2: Y(r.producer_price) }, svg);
        el("text", { "class": "gr-price-label", x: xq + 6, y: Y(r.producer_price) + 16 }, svg, "↑ Tax wedge t");
        el("text", { "class": "gr-price-label", x: PAD + 4, y: Y(r.consumer_price) - 5 }, svg, "Consumer price");
        el("text", { "class": "gr-price-label", x: PAD + 4, y: Y(r.producer_price) + 14 }, svg, "Producer price");
        point(r.consumer_price, r.quantity);
      }
    }
    container.appendChild(svg);
  }

  function summaryText(sim, x, r) {
    if (sim === "supply-demand") {
      return r.status === "interior" ? "Equilibrium price " + money(r.price) + ", equilibrium quantity " + fmt(r.quantity) + " units." : r.reason;
    }
    return r.status === "interior"
      ? "Tax " + money(x.t) + ": consumer price " + money(r.consumer_price) + ", producer price " + money(r.producer_price) + ", quantity " + fmt(r.quantity) + " units, tax revenue " + money(r.revenue) + "."
      : r.reason;
  }

  function table(tbody, thead, sim, x, r, baseRes) {
    var rows = [];
    if (sim === "supply-demand") {
      thead.innerHTML = "<tr><th scope='col'>Item</th><th scope='col'>Baseline</th><th scope='col'>Now</th><th scope='col'>Change</th></tr>";
      [["price", "Equilibrium price", "$"], ["quantity", "Equilibrium quantity", "units"], ["consumer_surplus", "Consumer surplus", "$"],
       ["producer_surplus", "Producer surplus", "$"], ["total_surplus", "Total surplus", "$"]].forEach(function (k) {
        var b = baseRes && baseRes.status === "interior" ? baseRes[k[0]] : null, n = r.status === "interior" ? r[k[0]] : null;
        rows.push([k[1], b === null ? "–" : withUnit(b, k[2]), n === null ? "–" : withUnit(n, k[2]),
                   b === null || n === null ? "–" : (n - b > 0 ? "+" : "") + fmt(n - b)]);
      });
    } else {
      thead.innerHTML = "<tr><th scope='col'>Item</th><th scope='col'>Before tax</th><th scope='col'>After tax</th><th scope='col'>Change</th></tr>";
      var b0 = r.baseline, ok = r.status === "interior", bi = b0 && b0.status === "interior";
      var add = function (label, before, after, unit) {
        rows.push([label, before === null ? "–" : withUnit(before, unit), after === null ? "–" : withUnit(after, unit),
                   before === null || after === null ? "–" : (after - before > 0 ? "+" : "") + fmt(after - before)]);
      };
      add("Price paid by consumers", bi ? b0.price : null, ok ? r.consumer_price : null, "$ per unit");
      add("Price received by producers", bi ? b0.price : null, ok ? r.producer_price : null, "$ per unit");
      add("Quantity", bi ? b0.quantity : null, ok ? r.quantity : null, "units");
      add("Tax revenue", bi ? 0 : null, ok ? r.revenue : null, "$");
      if (ok) {
        add("Emissions (assumed)", r.emissions_before, r.emissions_after, "kg");
        rows.push(["Consumer burden (per unit · share)", "–", withUnit(r.consumer_burden_per_unit, "$ per unit") + " · " + fmt(r.consumer_share * 100) + "%", "–"]);
        rows.push(["Producer burden (per unit · share)", "–", withUnit(r.producer_burden_per_unit, "$ per unit") + " · " + fmt(r.producer_share * 100) + "%", "–"]);
        rows.push(["Deadweight loss (assuming no external damage)", "–", money(r.deadweight_loss_private), "–"]);
        if (r.social_welfare_change !== undefined) {
          rows.push(["Avoided external damage (assumed)", "–", money(r.avoided_damage), "–"]);
          rows.push(["Change in social welfare (assumed)", "–", (r.social_welfare_change > 0 ? "+" : "") + money(r.social_welfare_change), "–"]);
        }
      }
    }
    tbody.innerHTML = "";
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      row.forEach(function (cell, i) { var c = document.createElement(i === 0 ? "th" : "td"); if (i === 0) c.scope = "row"; c.textContent = cell; tr.appendChild(c); });
      tbody.appendChild(tr);
    });
  }

  function notes(box, sim, x, r, base) {
    var list = [];
    if (sim === "supply-demand") {
      list = S.interpret(base, x);
      if (!list.length) list = ["Change a value and this panel explains how the result differs from the baseline."];
    } else if (r.status === "interior") {
      list.push("The " + money(x.t) + " tax drives a wedge between the price consumers pay and the price producers receive (" + fmt(r.consumer_price) + " − " + fmt(r.producer_price) + " = " + fmt(x.t) + ").");
      list.push("The less price-sensitive side bears more of the tax. Consumer share of the tax = d/(b+d) = " + fmt(r.consumer_share * 100) + "%.");
      list.push("Quantity falls by " + fmt(-r.quantity_change) + " units, and emissions fall by " + fmt(-r.emissions_change) + " kg (assumed emissions per unit).");
      if (r.social_welfare_change === undefined) list.push("You did not enter an external damage (md). The only loss shown is the deadweight loss, which assumes there is no externality.");
      else if (r.social_welfare_change > 0) list.push("With the assumed external damage, the avoided damage is larger than the deadweight loss, so total social welfare rises by " + money(r.social_welfare_change) + ".");
      else if (r.social_welfare_change < 0) list.push("The assumed external damage is small, so in this model total social welfare falls by " + money(-r.social_welfare_change) + ".");
      else list.push("The assumed avoided damage equals the deadweight loss, so the change in total social welfare is 0.");
    } else {
      list.push(r.reason);
    }
    box.innerHTML = "<p class='sim-notes-title'>What it means</p>";
    var ul = document.createElement("ul"); ul.className = "ec-list";
    list.forEach(function (t) { var li = document.createElement("li"); li.textContent = t; ul.appendChild(li); });
    box.appendChild(ul);
  }

  function init(root) {
    var sim = root.getAttribute("data-sim"), defaults = JSON.parse(root.getAttribute("data-defaults"));
    var ctls = root.querySelectorAll(".sim-ctl"), graph = root.querySelector("[data-role=graph]");
    var summary = root.querySelector("[data-role=summary]"), tableEl = root.querySelector("[data-role=table]");
    var notesBox = root.querySelector("[data-role=notes]");
    var tbody = tableEl.querySelector("tbody"), thead = tableEl.querySelector("thead");
    var base = null, baseRes = null;

    function read() {
      var raw = {};
      ctls.forEach(function (c) { raw[c.getAttribute("data-name")] = c.querySelector("[data-role=number]").value; });
      return raw;
    }
    function update() {
      var out = S.run(sim, read());
      ctls.forEach(function (c) {
        var name = c.getAttribute("data-name"), input = c.querySelector("[data-role=number]"), err = c.querySelector(".sim-err");
        var bad = !out.ok && out.field === name;
        input.setAttribute("aria-invalid", bad ? "true" : "false");
        err.textContent = bad ? out.message : "";
      });
      if (!out.ok) { summary.textContent = "Check your input: " + out.message; return; }
      if (!base) { base = out.inputs; baseRes = sim === "supply-demand" ? out.results : null; }
      draw(graph, sim, out.inputs, out.results, base, baseRes);
      summary.textContent = summaryText(sim, out.inputs, out.results);
      table(tbody, thead, sim, out.inputs, out.results, baseRes);
      notes(notesBox, sim, out.inputs, out.results, base);
      root.dataset.lastStatus = out.results.status;
    }
    ctls.forEach(function (c) {
      var range = c.querySelector("[data-role=range]"), number = c.querySelector("[data-role=number]");
      range.addEventListener("input", function () { number.value = range.value; update(); });
      number.addEventListener("input", function () {
        var v = S.parseNumber(number.value);
        if (v !== null) range.value = Math.min(Math.max(v, +range.min), +range.max);
        update();
      });
    });
    root.querySelector("[data-action=baseline]").addEventListener("click", function () {
      var out = S.run(sim, read());
      if (out.ok) { base = out.inputs; baseRes = sim === "supply-demand" ? out.results : null; update(); }
    });
    root.querySelector("[data-action=reset]").addEventListener("click", function () {
      ctls.forEach(function (c) {
        var name = c.getAttribute("data-name"), v = defaults[name];
        c.querySelector("[data-role=number]").value = v === undefined || v === null ? "" : v;
        c.querySelector("[data-role=range]").value = v === undefined || v === null ? 0 : v;
      });
      base = null; update();
    });
    root.querySelectorAll("[data-role=range]").forEach(function (r) { r.removeAttribute("tabindex"); });
    update();
  }

  document.querySelectorAll(".sim-widget").forEach(init);
})();
