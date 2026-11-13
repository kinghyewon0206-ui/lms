/* ECONOVA AI 화면 (튜터 대화, 추천 설명). 서버가 검사한 JSON 만 받아 textContent 로만 그린다 (HTML 로 해석하지 않음).
   브라우저는 질문 글과 본인 대화 id 만 보낸다. 키·자료·시스템 지시문은 서버에만 있다. */
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
    label.appendChild(el("span", "pill pill-ai", "AI 생성"));
    label.appendChild(document.createTextNode(" "));
    label.appendChild(el("span", "tutor-grounding g-" + m.grounding, m.grounding_label));
    box.appendChild(label);
    box.appendChild(el("p", "tutor-answer", m.answer));
    if (m.beyond_sources) {
      var b = el("p", "tutor-beyond");
      b.appendChild(el("strong", null, "자료 밖 AI 추가 설명: "));
      b.appendChild(document.createTextNode(m.beyond_sources));
      box.appendChild(b);
    }
    if (m.sources && m.sources.length) {
      var s = el("p", "tutor-sources", "근거로 쓴 확인된 출처: ");
      m.sources.forEach(function (src) {
        s.appendChild(el("span", "src-chip", src.title + (src.container ? " · " + src.container : "")));
      });
      box.appendChild(s);
    }
    if (m.limitations) box.appendChild(el("p", "tutor-limits", "한계: " + m.limitations));
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

    function updateCount() { if (count) count.textContent = input.value.length + " / " + max + "자"; }
    input.addEventListener("input", updateCount);
    panel.querySelectorAll("[data-suggest]").forEach(function (b) {
      b.addEventListener("click", function () { input.value = b.textContent; updateCount(); input.focus(); });
    });

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (busy) return;
      var text = input.value.trim();
      if (!text) { status.textContent = "질문을 입력해 주세요."; return; }
      busy = true;
      button.disabled = true;
      status.textContent = "AI 튜터가 답을 준비하고 있어요…";
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
        return res.json().catch(function () { return { ok: false, error: "응답을 읽을 수 없어요. 잠시 후 다시 시도해 주세요." }; });
      }).then(function (data) {
        if (!data.ok) {   // 실패해도 학생이 쓴 질문은 입력칸에 그대로 둔다
          status.textContent = data.error || "AI 답변을 받지 못했어요.";
          return;
        }
        var empty = log.querySelector(".tutor-empty");
        if (empty) empty.remove();
        var mine = el("div", "tutor-msg tutor-me");
        mine.appendChild(el("p", "tutor-label", "나"));
        mine.appendChild(el("p", null, text));
        log.appendChild(mine);
        log.appendChild(renderAnswer(data.message));
        log.scrollTop = log.scrollHeight;
        panel.setAttribute("data-conversation", data.conversation_id);
        input.value = "";
        updateCount();
        status.textContent = "답변을 받았어요.";
      }).catch(function () {
        status.textContent = "네트워크 오류로 보내지 못했어요. 입력한 질문은 그대로 있어요.";
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
      out.textContent = "AI 설명을 준비하고 있어요…";
      var body = new FormData();
      body.append("csrf_token", button.getAttribute("data-csrf"));
      fetch(button.getAttribute("data-endpoint"), {
        method: "POST", body: body, credentials: "same-origin",
        headers: { "X-CSRF-Token": button.getAttribute("data-csrf"), "Accept": "application/json" }
      }).then(function (res) { return res.json(); }).then(function (data) {
        out.textContent = "";
        if (!data.ok) { out.textContent = data.error || "AI 설명을 받지 못했어요."; return; }
        var label = el("p", "tutor-label");
        label.appendChild(el("span", "pill pill-ai", "AI 조언 (참고)"));
        out.appendChild(label);
        out.appendChild(el("p", null, data.message));
        if (data.tips && data.tips.length) {
          var ul = el("ul", "ec-list");
          data.tips.forEach(function (t) { ul.appendChild(el("li", null, t)); });
          out.appendChild(ul);
        }
      }).catch(function () { out.textContent = "네트워크 오류로 AI 설명을 받지 못했어요."; })
        .then(function () { button.disabled = false; });
    });
  }

  document.querySelectorAll("[data-tutor]").forEach(initTutor);
  document.querySelectorAll("[data-recs]").forEach(initRecs);
})();
