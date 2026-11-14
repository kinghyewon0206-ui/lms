/* ECONOVA UI enhancements (progressive; every page works without this file).
   Never changes what forms submit: it only adds visual state, hints and motion. */
(function () {
  "use strict";
  var doc = document, root = doc.documentElement;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || doc).querySelectorAll(sel)); }

  /* ---------- Navigation: scrolled state + mobile menu ---------- */
  var nav = doc.querySelector("[data-nav]"), toggle = doc.querySelector("[data-nav-toggle]");
  if (nav) {
    var onScroll = function () { nav.classList.toggle("is-scrolled", window.scrollY > 4); };
    onScroll(); window.addEventListener("scroll", onScroll, { passive: true });
  }
  if (nav && toggle) {
    var setOpen = function (open) { nav.classList.toggle("is-open", open); toggle.setAttribute("aria-expanded", open ? "true" : "false"); };
    toggle.addEventListener("click", function () { setOpen(!nav.classList.contains("is-open")); });
    doc.addEventListener("keydown", function (e) { if (e.key === "Escape" && nav.classList.contains("is-open")) { setOpen(false); toggle.focus(); } });
    doc.addEventListener("click", function (e) { if (nav.classList.contains("is-open") && !nav.contains(e.target)) setOpen(false); });
  }

  /* ---------- Scroll reveal ---------- */
  var reveal = $$("[data-reveal]");
  if (reveal.length) {
    if (reduce || !("IntersectionObserver" in window)) { reveal.forEach(function (el) { el.classList.add("is-in"); }); }
    else {
      // Anything already above or inside the viewport is shown, so jumping down the page never leaves blank sections.
      var pending = reveal.slice(), queued = false;
      var check = function () {
        queued = false;
        var limit = window.innerHeight * 0.92;
        pending = pending.filter(function (el) {
          if (el.getBoundingClientRect().top < limit) { el.classList.add("is-in"); return false; }
          return true;
        });
        if (!pending.length) { window.removeEventListener("scroll", onRevealScroll); window.removeEventListener("resize", onRevealScroll); }
      };
      var onRevealScroll = function () { if (!queued) { queued = true; setTimeout(check, 16); } };
      window.addEventListener("scroll", onRevealScroll, { passive: true });
      window.addEventListener("resize", onRevealScroll);
      check();
    }
  }

  /* ---------- Count-up numbers (data-count="12") ---------- */
  $$("[data-count]").forEach(function (el) {
    var target = parseFloat(el.getAttribute("data-count"));
    if (!isFinite(target) || reduce || target <= 0 || doc.hidden) return;
    var start = null, dur = 900, finalText = el.getAttribute("data-count");
    el.textContent = "0";
    setTimeout(function () { el.textContent = finalText; }, dur + 200);   // never leave a partial number behind
    function step(ts) {
      if (start === null) start = ts;
      var t = Math.min(1, (ts - start) / dur), eased = 1 - Math.pow(1 - t, 3);
      el.textContent = String(Math.round(target * eased));
      if (t < 1) requestAnimationFrame(step); else el.textContent = el.getAttribute("data-count");
    }
    requestAnimationFrame(step);
  });

  /* ---------- Progress bars & rings grow in ---------- */
  $$(".bar[data-animate]").forEach(function (bar) {
    requestAnimationFrame(function () { requestAnimationFrame(function () { bar.removeAttribute("data-animate"); }); });
  });
  $$(".ring[data-p]").forEach(function (ring) {
    var p = ring.getAttribute("data-p");
    if (reduce) { ring.style.setProperty("--p", p); return; }
    requestAnimationFrame(function () { requestAnimationFrame(function () { ring.style.setProperty("--p", p); }); });
  });

  /* ---------- Lesson: section table of contents + reading progress ---------- */
  var toc = doc.querySelector("[data-lesson-toc]");
  if (toc) {
    var links = $$("a", toc), secs = links.map(function (a) { return doc.getElementById(a.getAttribute("href").slice(1)); });
    var progress = doc.querySelector("[data-reading-progress] span");
    var ticking = false;
    var update = function () {
      ticking = false;
      var y = window.scrollY + 160, active = 0;
      secs.forEach(function (s, i) { if (s && s.offsetTop <= y) active = i; });
      links.forEach(function (a, i) {
        var on = i === active;
        a.classList.toggle("is-active", on);
        if (on) a.setAttribute("aria-current", "location"); else a.removeAttribute("aria-current");
      });
      var act = links[active];
      if (act && toc.scrollWidth > toc.clientWidth) {
        var left = act.offsetLeft - toc.clientWidth / 2 + act.clientWidth / 2;
        toc.scrollTo({ left: left, behavior: reduce ? "auto" : "smooth" });
      }
      if (progress) {
        var h = doc.documentElement.scrollHeight - window.innerHeight;
        progress.style.width = (h > 0 ? Math.min(100, Math.max(0, window.scrollY / h * 100)) : 0) + "%";
      }
    };
    window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
    update();
  }

  /* ---------- Assessments: answered state, live counter, numeric hints ---------- */
  var NUM = /^-?\d{1,3}(,\d{3})*(\.\d+)?$|^-?\d+(\.\d+)?$|^-?\.\d+$/;
  $$("form[data-assessment]").forEach(function (form) {
    var qs = $$("fieldset.dg-question", form), out = form.querySelector("[data-qcount]"), bar = form.querySelector("[data-qbar]");
    function answered(fs) {
      if (fs.querySelector("input[type=radio]:checked")) return true;
      var t = fs.querySelector("input[type=text]");
      return !!(t && t.value.trim());
    }
    function refresh() {
      var n = 0;
      qs.forEach(function (fs) { var a = answered(fs); fs.classList.toggle("is-answered", a); if (a) n++; });
      if (out) out.textContent = n + " of " + qs.length + " questions done";
      if (bar) { bar.style.width = (qs.length ? n / qs.length * 100 : 0) + "%"; bar.parentNode.setAttribute("aria-valuenow", String(n)); }
    }
    form.addEventListener("change", refresh);
    form.addEventListener("input", function (e) {
      var el = e.target;
      if (el.matches && el.matches(".dg-numeric input")) {
        var v = el.value.trim(), msg = el.parentNode.querySelector(".num-msg");
        if (!msg) { msg = doc.createElement("span"); msg.className = "num-msg"; msg.setAttribute("aria-live", "polite"); el.insertAdjacentElement("afterend", msg); }
        var bad = v !== "" && !NUM.test(v);
        el.setAttribute("aria-invalid", bad ? "true" : "false");
        msg.textContent = bad ? "Enter a number only, for example 12.5 or -3 (no $, % or spaces)." : "";
      }
      refresh();
    });
    refresh();
  });

  /* ---------- Auth: show/hide password, strength meter, confirm match ---------- */
  $$("[data-pw-toggle]").forEach(function (btn) {
    var input = doc.getElementById(btn.getAttribute("aria-controls"));
    if (!input) return;
    btn.hidden = false;
    btn.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? "Hide" : "Show";
      btn.setAttribute("aria-pressed", show ? "true" : "false");
    });
  });
  var pw = doc.querySelector("[data-pw-new]"), meter = doc.querySelector("[data-pw-meter]"), pmsg = doc.querySelector("[data-pw-msg]");
  if (pw && meter) {
    pw.addEventListener("input", function () {
      var v = pw.value, lvl = 0;
      if (v.length >= 8) lvl++;
      if (v.length >= 12) lvl++;
      if (/[A-Za-z]/.test(v) && /\d/.test(v)) lvl++;
      if (/[^A-Za-z0-9]/.test(v)) lvl++;
      meter.setAttribute("data-level", v ? String(Math.max(1, lvl)) : "0");
      if (pmsg) { pmsg.textContent = !v ? "" : v.length < 8 ? "Use at least 8 characters." : "Looks good."; pmsg.className = "field-msg " + (!v ? "" : v.length < 8 ? "bad" : "good"); }
    });
  }
  var confirm = doc.querySelector("[data-pw-confirm]"), cmsg = doc.querySelector("[data-confirm-msg]");
  if (pw && confirm && cmsg) {
    var check = function () {
      if (!confirm.value) { cmsg.textContent = ""; cmsg.className = "field-msg"; return; }
      var ok = confirm.value === pw.value;
      cmsg.textContent = ok ? "Passwords match." : "Passwords don't match yet.";
      cmsg.className = "field-msg " + (ok ? "good" : "bad");
    };
    confirm.addEventListener("input", check); pw.addEventListener("input", check);
  }
})();
