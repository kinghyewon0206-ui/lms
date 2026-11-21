/* ECONOVA landing: one hypothetical market (Qd = 120(1+i) - 15P, Qs = 15P). Progressive enhancement only. */
(function () {
  "use strict";
  /* market instrument (hypothetical lemonade market): Qd = 120(1+i) - 15P, Qs = 15P */
  var mk = document.querySelector("[data-market]");
  if (mk) {
    var X0 = 44, X1 = 404, Y0 = 244, Y1 = 20, QMAX = 160, PMAX = 9;
    var qx = function (q) { return X0 + (q / QMAX) * (X1 - X0); };
    var py = function (p) { return Y0 - (p / PMAX) * (Y0 - Y1); };
    var $ = function (s) { return mk.querySelector(s); };
    var slider = $("[data-income]");
    var draw = function () {
      var inc = Number(slider.value) / 100, a = 120 * (1 + inc);
      var P = a / 30, Q = 15 * P;
      var dP0 = Math.max(0.4, (a - QMAX + 4) / 15), dP1 = Math.min(PMAX - .3, a / 15 - .3);
      var d = "M" + qx(a - 15 * dP1).toFixed(1) + " " + py(dP1).toFixed(1) + " L" + qx(a - 15 * dP0).toFixed(1) + " " + py(dP0).toFixed(1);
      var s = "M" + qx(15 * .35).toFixed(1) + " " + py(.35).toFixed(1) + " L" + qx(15 * 8.6).toFixed(1) + " " + py(8.6).toFixed(1);
      $("[data-d]").setAttribute("d", d); $("[data-d-glow]").setAttribute("d", d);
      $("[data-s]").setAttribute("d", s); $("[data-s-glow]").setAttribute("d", s);
      var ex = qx(Q), ey = py(P);
      ["[data-eq]", "[data-halo]"].forEach(function (sel) { $(sel).setAttribute("cx", ex.toFixed(1)); $(sel).setAttribute("cy", ey.toFixed(1)); });
      var gx = $("[data-gx]"), gy = $("[data-gy]");
      gx.setAttribute("x1", ex); gx.setAttribute("x2", ex); gx.setAttribute("y1", ey); gx.setAttribute("y2", Y0);
      gy.setAttribute("x1", X0); gy.setAttribute("x2", ex); gy.setAttribute("y1", ey); gy.setAttribute("y2", ey);
      var dl = $("[data-dl]"); dl.setAttribute("x", (qx(a - 15 * dP0) + 8).toFixed(1)); dl.setAttribute("y", (py(dP0) + 4).toFixed(1)); dl.setAttribute("text-anchor", "start");
      var sl = $("[data-sl]"); sl.setAttribute("x", (qx(15 * 8.6) - 14).toFixed(1)); sl.setAttribute("y", (py(8.6) + 4).toFixed(1)); sl.setAttribute("text-anchor", "end");
      $("[data-p]").textContent = "$" + P.toFixed(2);
      $("[data-q]").innerHTML = Math.round(Q) + "<small>cups</small>";
      $("[data-r]").textContent = "$" + Math.round(P * Q);
      $("[data-inc]").textContent = (inc > 0 ? "+" : "") + Math.round(inc * 100) + "%";
    };
    slider.addEventListener("input", draw);
    draw();
  }

})();
