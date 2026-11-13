/* ECONOVA 시뮬레이션 화면: 슬라이더·숫자 입력, 실시간 SVG 그래프, 비교 표, 해석 패널.
   계산은 econova-sim.js(EconovaSim)가 하고, 저장할 때는 서버가 같은 공식으로 다시 계산한다. */
(function () {
  "use strict";
  var S = window.EconovaSim, NS = "http://www.w3.org/2000/svg";
  var W = 520, H = 340, PAD = 46;

  function fmt(v) { return (Math.round(v * 1e4) / 1e4).toString(); }
  function el(name, attrs, parent, text) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  }

  /* 직선 Q = q0 + slope·P 를 축 범위 안에서 잘라 그린다 (econova/graphs.py 와 같은 방식) */
  function segment(q0, slope, pMax, qMax) {
    // 0 ≤ Q ≤ qMax 이고 0 ≤ P ≤ pMax 인 가격 구간
    var lo, hi;
    if (slope < 0) { lo = (qMax - q0) / slope; hi = q0 / -slope; }   // 수요: Q 가 P 에 따라 줄어듦
    else { lo = -q0 / slope; hi = (qMax - q0) / slope; }              // 공급: Q 가 P 에 따라 늘어남
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
    el("text", { "class": "gr-axis-label", x: PAD, y: PAD - 14, "text-anchor": "middle" }, svg, "가격 P (원)");
    el("text", { "class": "gr-axis-label", x: W - PAD, y: H - PAD + 36, "text-anchor": "end" }, svg, "수량 Q (개)");
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
        el("text", { "class": "gr-price-label", x: xq + 6, y: Y(r.producer_price) + 16 }, svg, "↑ 세금 쐐기 t");
        el("text", { "class": "gr-price-label", x: PAD + 4, y: Y(r.consumer_price) - 5 }, svg, "소비자 가격");
        el("text", { "class": "gr-price-label", x: PAD + 4, y: Y(r.producer_price) + 14 }, svg, "생산자 가격");
        point(r.consumer_price, r.quantity);
      }
    }
    container.appendChild(svg);
  }

  function summaryText(sim, x, r) {
    if (sim === "supply-demand") {
      return r.status === "interior" ? "균형 가격 " + fmt(r.price) + "원, 균형 거래량 " + fmt(r.quantity) + "개." : r.reason;
    }
    return r.status === "interior"
      ? "세금 " + fmt(x.t) + "원: 소비자 가격 " + fmt(r.consumer_price) + "원, 생산자 가격 " + fmt(r.producer_price) + "원, 거래량 " + fmt(r.quantity) + "개, 세수 " + fmt(r.revenue) + "원."
      : r.reason;
  }

  function table(tbody, thead, sim, x, r, baseRes) {
    var rows = [];
    if (sim === "supply-demand") {
      thead.innerHTML = "<tr><th scope='col'>항목</th><th scope='col'>비교 기준</th><th scope='col'>지금</th><th scope='col'>변화</th></tr>";
      [["price", "균형 가격", "원"], ["quantity", "균형 거래량", "개"], ["consumer_surplus", "소비자 잉여", "원"],
       ["producer_surplus", "생산자 잉여", "원"], ["total_surplus", "총잉여", "원"]].forEach(function (k) {
        var b = baseRes && baseRes.status === "interior" ? baseRes[k[0]] : null, n = r.status === "interior" ? r[k[0]] : null;
        rows.push([k[1], b === null ? "–" : fmt(b) + " " + k[2], n === null ? "–" : fmt(n) + " " + k[2],
                   b === null || n === null ? "–" : (n - b > 0 ? "+" : "") + fmt(n - b)]);
      });
    } else {
      thead.innerHTML = "<tr><th scope='col'>항목</th><th scope='col'>세금 전</th><th scope='col'>세금 뒤</th><th scope='col'>변화</th></tr>";
      var b0 = r.baseline, ok = r.status === "interior", bi = b0 && b0.status === "interior";
      var add = function (label, before, after, unit) {
        rows.push([label, before === null ? "–" : fmt(before) + " " + unit, after === null ? "–" : fmt(after) + " " + unit,
                   before === null || after === null ? "–" : (after - before > 0 ? "+" : "") + fmt(after - before)]);
      };
      add("소비자가 내는 가격", bi ? b0.price : null, ok ? r.consumer_price : null, "원/개");
      add("생산자가 받는 가격", bi ? b0.price : null, ok ? r.producer_price : null, "원/개");
      add("거래량", bi ? b0.quantity : null, ok ? r.quantity : null, "개");
      add("세수", bi ? 0 : null, ok ? r.revenue : null, "원");
      if (ok) {
        add("배출량 (가정)", r.emissions_before, r.emissions_after, "kg");
        rows.push(["소비자 부담 (단위당 · 비율)", "–", fmt(r.consumer_burden_per_unit) + " 원/개 · " + fmt(r.consumer_share * 100) + "%", "–"]);
        rows.push(["생산자 부담 (단위당 · 비율)", "–", fmt(r.producer_burden_per_unit) + " 원/개 · " + fmt(r.producer_share * 100) + "%", "–"]);
        rows.push(["시장 내부 손실 (외부효과 없다고 가정)", "–", fmt(r.deadweight_loss_private) + " 원", "–"]);
        if (r.social_welfare_change !== undefined) {
          rows.push(["피한 외부 피해 (가정)", "–", fmt(r.avoided_damage) + " 원", "–"]);
          rows.push(["사회적 후생 변화 (가정)", "–", (r.social_welfare_change > 0 ? "+" : "") + fmt(r.social_welfare_change) + " 원", "–"]);
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
      if (!list.length) list = ["값을 바꾸면 비교 기준과 달라진 점을 여기서 설명해요."];
    } else if (r.status === "interior") {
      list.push("세금 " + fmt(x.t) + "원이 소비자가 내는 가격과 생산자가 받는 가격 사이에 쐐기를 만들어요 (" + fmt(r.consumer_price) + " − " + fmt(r.producer_price) + " = " + fmt(x.t) + ").");
      list.push("부담은 덜 민감한 쪽이 더 져요. 소비자 부담 비율 = d/(b+d) = " + fmt(r.consumer_share * 100) + "%.");
      list.push("거래량이 " + fmt(-r.quantity_change) + "개 줄고, 배출량도 " + fmt(-r.emissions_change) + "kg 줄어요 (배출 계수 가정).");
      if (r.social_welfare_change === undefined) list.push("외부 피해(md)를 넣지 않았어요. 이때 보이는 손실은 외부효과가 없다고 가정한 시장 내부 손실뿐이에요.");
      else if (r.social_welfare_change > 0) list.push("외부 피해를 가정하면, 피한 피해가 시장 내부 손실보다 커서 사회 전체 후생이 " + fmt(r.social_welfare_change) + "원 늘어요.");
      else if (r.social_welfare_change < 0) list.push("가정한 외부 피해가 작아서, 이 모형에서는 사회 전체 후생이 " + fmt(-r.social_welfare_change) + "원 줄어요.");
      else list.push("가정한 외부 피해와 시장 내부 손실이 같아 사회 전체 후생 변화가 0이에요.");
    } else {
      list.push(r.reason);
    }
    box.innerHTML = "<p class='sim-notes-title'>해석</p>";
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
      if (!out.ok) { summary.textContent = "입력을 확인해 주세요: " + out.message; return; }
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
