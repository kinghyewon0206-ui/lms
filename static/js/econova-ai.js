/* ECONOVA AI UI (tutor chat, recommendation explanations). Renders only server-validated JSON, via textContent (never as HTML).
   The browser sends only the question text and its own conversation id. Keys, materials and system prompts stay on the server. */
(function () {
  "use strict";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }

  function csrf(form) {
    var input = form.querySelector('input[name="csrf_token"]');
    return input ? input.value : "";
  }

  function renderAnswer(m) {
    var box = el("div", "tutor-msg tutor-ai");
    var label = el("p", "tutor-label");
    label.appendChild(el("span", "pill pill-ai", "AI-generated"));
    label.appendChild(document.createTextNode(" "));
    label.appendChild(el("span", "tutor-grounding g-" + m.grounding, m.grounding_label));
    box.appendChild(label);
    box.appendChild(el("p", "tutor-answer", m.answer));
    if (m.beyond_sources) {
      var b = el("p", "tutor-beyond");
      b.appendChild(el("strong", null, "Extra AI explanation beyond the sources: "));
      b.appendChild(document.createTextNode(m.beyond_sources));
      box.appendChild(b);
    }
    if (m.sources && m.sources.length) {
      var s = el("p", "tutor-sources", "Verified sources used: ");
      m.sources.forEach(function (src) {
        s.appendChild(el("span", "src-chip", src.title + (src.container ? " · " + src.container : "")));
      });
      box.appendChild(s);
    }
    if (m.limitations) box.appendChild(el("p", "tutor-limits", "Limitations: " + m.limitations));
    if (m.follow_up_questions && m.follow_up_questions.length) {
      var ul = el("ul", "tutor-follow");
      m.follow_up_questions.forEach(function (q) { ul.appendChild(el("li", null, q)); });
      box.appendChild(ul);
    }
    return box;
  }

  function initTutor(panel) {
    var form = panel.querySelector(".tutor-form");
    if (!form) return;
    var log = panel.querySelector(".tutor-log");
    var input = form.querySelector("textarea");
    var status = form.querySelector("[data-status]");
    var count = form.querySelector("[data-count]");
    var button = form.querySelector('button[type="submit"]');
    var max = parseInt(panel.getAttribute("data-max"), 10) || 600;
    var busy = false;

    function updateCount() { if (count) count.textContent = input.value.length + " / " + max + " characters"; }
    input.addEventListener("input", updateCount);
    panel.querySelectorAll("[data-suggest]").forEach(function (b) {
      b.addEventListener("click", function () { input.value = b.textContent; updateCount(); input.focus(); });
    });

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (busy) return;
      var text = input.value.trim();
      if (!text) { status.textContent = "Please type a question."; return; }
      busy = true;
      button.disabled = true;
      status.textContent = "The AI Tutor is preparing an answer…";
      panel.setAttribute("aria-busy", "true");
      var body = new FormData();
      body.append("csrf_token", csrf(form));
      body.append("course_id", panel.getAttribute("data-course"));
      body.append("lesson_id", panel.getAttribute("data-lesson"));
      body.append("level", panel.getAttribute("data-level"));
      body.append("message", text);
      var conv = panel.getAttribute("data-conversation");
      if (conv) body.append("conversation_id", conv);
      fetch(panel.getAttribute("data-endpoint"), {
        method: "POST", body: body, credentials: "same-origin",
        headers: { "X-CSRF-Token": csrf(form), "Accept": "application/json" }
      }).then(function (res) {
        return res.json().catch(function () { return { ok: false, error: "Could not read the response. Please try again in a moment." }; });
      }).then(function (data) {
        if (!data.ok) {   // keep the student's question in the input box even on failure
          status.textContent = data.error || "Could not get an AI answer.";
          return;
        }
        var empty = log.querySelector(".tutor-empty");
        if (empty) empty.remove();
        var mine = el("div", "tutor-msg tutor-me");
        mine.appendChild(el("p", "tutor-label", "You"));
        mine.appendChild(el("p", null, text));
        log.appendChild(mine);
        log.appendChild(renderAnswer(data.message));
        log.scrollTop = log.scrollHeight;
        panel.setAttribute("data-conversation", data.conversation_id);
        input.value = "";
        updateCount();
        status.textContent = "Answer received.";
      }).catch(function () {
        status.textContent = "A network error stopped your question from being sent. Your question is still in the box.";
      }).then(function () {
        busy = false;
        button.disabled = false;
        panel.removeAttribute("aria-busy");
      });
    });
  }

  function initRecs(box) {
    var button = box.querySelector("[data-recs-explain]");
    var out = box.querySelector("[data-recs-out]");
    if (!button) return;
    button.addEventListener("click", function () {
      button.disabled = true;
      out.textContent = "Preparing an AI explanation…";
      var body = new FormData();
      body.append("csrf_token", button.getAttribute("data-csrf"));
      fetch(button.getAttribute("data-endpoint"), {
        method: "POST", body: body, credentials: "same-origin",
        headers: { "X-CSRF-Token": button.getAttribute("data-csrf"), "Accept": "application/json" }
      }).then(function (res) { return res.json(); }).then(function (data) {
        out.textContent = "";
        if (!data.ok) { out.textContent = data.error || "Could not get an AI explanation."; return; }
        var label = el("p", "tutor-label");
        label.appendChild(el("span", "pill pill-ai", "AI advice (for reference)"));
        out.appendChild(label);
        out.appendChild(el("p", null, data.message));
        if (data.tips && data.tips.length) {
          var ul = el("ul", "ec-list");
          data.tips.forEach(function (t) { ul.appendChild(el("li", null, t)); });
          out.appendChild(ul);
        }
      }).catch(function () { out.textContent = "A network error prevented the AI explanation from loading."; })
        .then(function () { button.disabled = false; });
    });
  }

  document.querySelectorAll("[data-tutor]").forEach(initTutor);
  document.querySelectorAll("[data-recs]").forEach(initRecs);
})();
