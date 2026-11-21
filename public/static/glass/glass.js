/* ECONOVA Glass prototype behaviours. Progressive enhancement only: every page works without this file. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var fine = window.matchMedia && window.matchMedia("(pointer: fine)").matches;

  /* pointer-following sheen on glass objects (desktop pointers only) */
  if (fine && !reduce) {
    document.querySelectorAll(".glass.sheen").forEach(function (el) {
      el.addEventListener("pointermove", function (e) {
        var r = el.getBoundingClientRect();
        el.style.setProperty("--mx", ((e.clientX - r.left) / r.width * 100).toFixed(1) + "%");
        el.style.setProperty("--my", ((e.clientY - r.top) / r.height * 100).toFixed(1) + "%");
      });
    });
  }

  /* segmented controls: slide the lens under the current item */
  function placeLens(seg) {
    var lens = seg.querySelector(".lens");
    var cur = seg.querySelector('[aria-current="page"], [aria-selected="true"]');
    if (!lens || !cur) return;
    lens.style.width = cur.offsetWidth + "px";
    lens.style.transform = "translateX(" + cur.offsetLeft + "px)";
  }
  document.querySelectorAll("[data-seg]").forEach(function (seg) {
    var lens = seg.querySelector(".lens");
    if (lens) { lens.style.transition = "none"; placeLens(seg); lens.getBoundingClientRect(); lens.style.transition = ""; }
    seg.querySelectorAll('[role="tab"]').forEach(function (tab) {
      tab.addEventListener("click", function () {
        seg.querySelectorAll('[role="tab"]').forEach(function (t) { t.setAttribute("aria-selected", t === tab ? "true" : "false"); });
        placeLens(seg);
      });
    });
  });
  window.addEventListener("resize", function () { document.querySelectorAll("[data-seg]").forEach(placeLens); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { document.querySelectorAll("[data-seg]").forEach(placeLens); });

  /* mobile menu */
  document.querySelectorAll("[data-menu]").forEach(function (btn) {
    var links = document.getElementById(btn.getAttribute("aria-controls"));
    btn.addEventListener("click", function () {
      var open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      links.classList.toggle("open", open);
    });
  });

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

  /* lesson: scroll-spy, viewed sections, quiz unlock (preview only, nothing is saved) */
  var toc = document.querySelector("[data-toc]");
  var sections = Array.prototype.slice.call(document.querySelectorAll(".paper > section[id]"));
  if (sections.length && "IntersectionObserver" in window) {
    var links = {}, seen = {};
    document.querySelectorAll('.toc a, .mobile-toc a').forEach(function (a) {
      var id = a.getAttribute("href").slice(1);
      (links[id] = links[id] || []).push(a);
    });
    var bar = document.querySelector("[data-read-bar]"), count = document.querySelector("[data-read-count]");
    var quiz = document.querySelector("[data-quiz-btn]"), check = document.querySelector('[data-check="material"]');
    var update = function () {
      var n = Object.keys(seen).length;
      if (bar) bar.style.setProperty("--v", Math.round(n / sections.length * 100) + "%");
      if (count) count.textContent = String(n);
      if (n === sections.length && quiz) {
        quiz.removeAttribute("aria-disabled"); quiz.classList.remove("locked", "secondary"); quiz.classList.add("primary"); quiz.textContent = "Start the quiz";
        if (check) check.classList.add("done");
      }
    };
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        var id = en.target.id, idx = sections.indexOf(en.target);
        sections.forEach(function (sec, i) { if (i <= idx) seen[sec.id] = true; });   /* scrolling past a section counts as viewing it */
        Object.keys(links).forEach(function (k) { links[k].forEach(function (a) { a.classList.toggle("active", k === id); if (seen[k]) a.classList.add("read"); }); });
        update();
      });
    }, { rootMargin: "-30% 0px -55% 0px" });
    sections.forEach(function (s) { io.observe(s); });
  }
})();
