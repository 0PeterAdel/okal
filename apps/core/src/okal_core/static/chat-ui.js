"use strict";
/* OKAL chat-first surface. Never stores message text in browser storage. */
let chatSequence = 0;
let chatAbort = null;
let chatTurns = [];
let chatPending = false;

/* Displays the exact saved daily brief already fetched by the dashboard.
 * Does not claim live Google/Gmail status and never displays made-up activity.
 */
function renderChatDailySummary(data) {
  const target = document.getElementById("chat-daily-points");
  const caveat = document.getElementById("chat-source-caveat");
  if (!target || !caveat) return;
  target.replaceChildren();
  const items = Array.isArray(data?.brief_points)
    ? data.brief_points.filter(v => typeof v === "string" && v.trim()).slice(0,4)
    : [];
  for (const value of items.length ? items : ["مفيش موجز محلي متاح حاليًا."]) {
    const item = document.createElement("li");
    item.textContent = value; // Cached labels and model output stay text.
    target.append(item);
  }
  caveat.textContent = data?.mail_sync_stale
    ? "Gmail: التحديث غير مؤكد؛ تفاصيل اليوم من النسخ المحفوظة فقط."
    : "البيانات المحفوظة قد تكون ناقصة؛ ما تعتمدش عليها كدليل إن التقويم فاضي.";
}
function updateChatSessionCount() {
  const marker = document.getElementById("chat-memory-count");
  if (marker) marker.textContent = String(chatTurns.length) + " رسائل";
}


function clearChatUI() {
  chatSequence += 1;
  if (chatAbort) chatAbort.abort();
  chatAbort = null;
  chatTurns = [];
  chatPending = false;
  updateChatSessionCount();
  const log = document.getElementById("chat-messages");
  if (log) log.replaceChildren();
  const prompt = document.getElementById("chat-input");
  if (prompt) prompt.value = "";
  const send = document.getElementById("chat-send");
  if (send) send.disabled = false;
  const greeting = document.getElementById("chat-greeting");
  if (greeting) greeting.hidden = false;
  const status = document.getElementById("chat-status");
  if (status) status.textContent = "";
}

(function initChatHome() {
  const get = id => document.getElementById(id);
  const log = get("chat-messages");
  const entry = get("chat-input");
  const send = get("chat-send");
  const status = get("chat-status");
  if (!log || !entry || !send || !status) return;

  function bubble(role, content) {
    const box = document.createElement("article");
    box.className = "chat-bubble";
    box.setAttribute("data-role", role);
    const label = document.createElement("span");
    label.className = "chat-bubble-role";
    label.textContent = role === "user" ? "أنت" : "OKAL · local";
    const text = document.createElement("div");
    text.className = "chat-message-content";
    if (role === "assistant" && typeof renderOKALMarkdown === "function") {
      renderOKALMarkdown(text, content);
    } else {
      text.textContent = content;
    }
    box.append(label, text);
    log.append(box);
    get("chat-greeting").hidden = true;
    log.scrollTop = log.scrollHeight;
    return box;
  }

  function cairoISO(localValue) {
    // datetime-local has no zone. Resolve explicitly in Africa/Cairo instead
    // of assuming the browser's timezone (especially remote owner devices).
    if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(localValue))
      throw new Error("اختر تاريخ ووقت صالحين.");
    const naive = Date.parse(localValue + ":00Z");
    if (!Number.isFinite(naive)) throw new Error("وقت غير صالح.");
    const formatter = new Intl.DateTimeFormat("en-GB", {
      timeZone:"Africa/Cairo", year:"numeric",month:"2-digit",
      day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23",
    });
    const matches = [];
    for (const hours of [2,3]) {
      const stamp = naive - hours * 3600000;
      const parts = Object.fromEntries(formatter.formatToParts(new Date(stamp))
        .map(p => [p.type,p.value]));
      const rendered = parts.year + "-" + parts.month + "-" + parts.day +
        "T" + parts.hour + ":" + parts.minute;
      if (rendered === localValue) matches.push(stamp);
    }
    if (matches.length !== 1) throw new Error(
      "الوقت غير واضح بسبب تغيير التوقيت الصيفي؛ اختار وقت تاني من التقويم.");
    return new Date(matches[0]).toISOString();
  }

  function proposalForm(proposal, parent) {
    if (proposal.kind !== "event" || proposal.destination !== "okal_local_only"
        || !proposal.requires_confirmation) return;
    const form = document.createElement("form");
    form.className = "chat-proposal";
    const head = document.createElement("strong");
    head.textContent = "مراجعة موعد · غير محفوظ حتى الآن";
    const fields = {};
    for (const [name,label,value,type] of [
      ["title","اسم الموعد",proposal.title,"text"],
      ["start","البداية · بتوقيت القاهرة",proposal.start.slice(0,16),"datetime-local"],
      ["end","النهاية · بتوقيت القاهرة",proposal.end.slice(0,16),"datetime-local"]
    ]) {
      const wrapper = document.createElement("label");
      wrapper.textContent = label;
      const input = document.createElement("input");
      input.type = type;
      input.name = name;
      input.value = value;
      input.required = true;
      if (name === "title") input.maxLength = 250;
      wrapper.append(input);
      fields[name] = input;
      form.append(wrapper);
    }
    const action = document.createElement("button");
    action.type = "submit";
    action.textContent = "أؤكد — احفظ في تقويم OKAL المحلي";
    const note = document.createElement("p");
    note.className = "chat-save-note";
    note.textContent = "تقدر تعدّل التفاصيل قبل التأكيد. لن يُنشأ موعد في Google Calendar.";
    const feedback = document.createElement("p");
    feedback.setAttribute("role","status");
    feedback.className = "chat-save-note";
    // Insert heading before editable fields.
    form.prepend(head);
    form.append(note, action, feedback);
    let id = null; // Stable across uncertain retries; local Calendar is idempotent.
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (action.disabled) return;
      let start, end;
      try {
        start = cairoISO(fields.start.value);
        end = cairoISO(fields.end.value);
        if (Date.parse(end) <= Date.parse(start)) throw new Error(
          "النهاية لازم تكون بعد البداية.");
      } catch (error) {
        feedback.textContent = error.message || "راجع الموعد والوقت.";
        return; // Client validation is safely retryable; no write attempted.
      }
      action.disabled = true;
      feedback.textContent = "براجع الوقت وبحفظ الموعد محليًا...";
      try {
        if (!id) id = crypto.randomUUID().replaceAll("-", "");
        const response = await fetch("/api/v1/calendar/local/save", {
          method:"POST",credentials:"same-origin",cache:"no-store",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({
            id,revision:0,kind:"event",title:fields.title.value,
            notes:"Owner-confirmed from OKAL chat",
            start,end,target_date:null,reminder_minutes:null
          }),
        });
        if (!response.ok) throw new Error(response.status === 409
          ? "الطلب اتغيّر بعد محاولة سابقة. راجع التقويم قبل إعادة الحفظ."
          : "تعذر تأكيد الحفظ؛ افحص التقويم قبل تكرار المحاولة.");
        const saved = await response.json();
        if (saved.id !== id || (saved.revision !== 1 && !saved.replayed))
          throw new Error("نتيجة الحفظ غير مؤكدة، راجع التقويم.");
        feedback.textContent = "اتحفظ الموعد في تقويم OKAL المحلي فقط.";
        action.textContent = "تم الحفظ محليًا";
        for (const input of Object.values(fields)) input.disabled = true;
        if (typeof load === "function") await load(true);
      } catch (error) {
        feedback.textContent = error.message || "تعذر الحفظ. راجع التقويم أولًا.";
        // Do not retry a potentially ambiguous write with a different payload.
        // A same-ID exact replay can only be safely inspected through Calendar.
        action.disabled = true;
      }
    });
    parent.append(form);
  }

  async function sendMessage(value) {
    const message = String(value || "").trim();
    if (!message || chatPending || message.length > 900) return;
    const history = chatTurns.slice(-8);
    chatTurns.push({role:"user",content:message});
    updateChatSessionCount();
    bubble("user",message);
    entry.value = "";
    chatPending = true;
    send.disabled = true;
    status.textContent = "OKAL بيحلّل سؤالك محليًا...";
    const seq = ++chatSequence;
    chatAbort = new AbortController();
    try {
      const response = await fetch("/api/v1/chat", {
        method:"POST",credentials:"same-origin",cache:"no-store",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({message,history}),
        signal:chatAbort.signal,
      });
      if (!response.ok) throw new Error(response.status === 401 || response.status === 403
        ? "محتاج تفتح جلسة OKAL المحمية الأول."
        : "تعذر رد المحادثة المحلية. راجع خدمة OKAL وحالة Ollama.");
      const data = await response.json();
      if (seq !== chatSequence) return;
      if (!data || typeof data.answer !== "string")
        throw new Error("الرد المحلي غير صالح.");
      chatTurns.push({role:"assistant",content:data.answer.slice(0,900)});
      updateChatSessionCount();
      const box = bubble("assistant",data.answer);
      if (data.proposal) proposalForm(data.proposal,box);
      status.textContent = data.mode === "pinned_local_ollama"
        ? "رد من Ollama المحلي · تم استخدام البيانات المحفوظة فقط"
        : "رد من البيانات المحلية · المحادثة الحرة تحتاج Ollama المعتمد";
    } catch (error) {
      if (seq === chatSequence && error.name !== "AbortError") {
        bubble("assistant","الطلب ما اكتملش. " + (error.message || "حاول مرة تانية."));
        status.textContent = "لم تُنفّذ أي إجراءات بناءً على الطلب.";
      }
    } finally {
      if (seq === chatSequence) {
        chatPending = false;
        send.disabled = false;
        chatAbort = null;
        entry.focus();
      }
    }
  }

  get("chat-form").addEventListener("submit", event => {
    event.preventDefault();
    sendMessage(entry.value);
  });
  entry.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendMessage(entry.value);
    }
  });
  get("chat-new").addEventListener("click", () => {
    clearChatUI();
    entry.focus();
  });
  for (const button of document.querySelectorAll("[data-chat-prompt]")) {
    button.addEventListener("click",() => sendMessage(button.getAttribute("data-chat-prompt")));
  }
})();
