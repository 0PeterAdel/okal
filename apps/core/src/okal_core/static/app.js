"use strict";
// Read-only shell. Tokens and reports stay in memory, never browser storage.
const el = (id) => document.getElementById(id);
let token = "";
let keyProtected = false;
let cursor = null;
let controller = null;
let generation = 0;
let busy = false;
const selectedInfo = new Set();
let selectableInfoIds = [];
let selectionAnchor = null;
const informationRows = new Map();

function updateTrashSelection() {
  el("trash-count").textContent =
    `${selectedInfo.size} من ${selectableInfoIds.length} رسالة قابلة للتحديد (من كل الأقسام، حد أقصى 20)`;
  el("trash-selected").disabled = selectedInfo.size === 0;
  el("clear-selection").disabled = selectedInfo.size === 0;
  el("select-all-info").disabled = selectableInfoIds.length === 0 ||
    selectedInfo.size === Math.min(20, selectableInfoIds.length);
  // Any edit invalidates the previously copied approval preview.
  el("trash-command").hidden = true;
  el("trash-command").textContent = "";
  for (const [mid, entry] of informationRows) {
    const active = selectedInfo.has(mid);
    entry.article.className =
      "triage-message is-selectable" + (active ? " is-selected" : "");
    entry.checkbox.checked = active;
    entry.checkbox.setAttribute("aria-checked", String(active));
    entry.article.setAttribute("data-selected", String(active));
  }
}

function clearInformationSelection() {
  selectedInfo.clear();
  selectionAnchor = null;
  updateTrashSelection();
}

function commitSelection(next) {
  if (next.size > 20) {
    el("trash-help").textContent =
      "لا يمكن تحديد أكثر من 20 رسالة مرة واحدة. قلّل النطاق أو استخدم دفعات.";
    updateTrashSelection();
    return false;
  }
  selectedInfo.clear();
  for (const mid of next) selectedInfo.add(mid);
  el("trash-help").textContent =
    "حدد الرسائل ثم راجع أمر النقل محليًا. النقل إلى Trash قابل للاسترجاع، مش حذف نهائي.";
  updateTrashSelection();
  return true;
}

function chooseInformation(mid, modifiers = {}, checkboxToggle = false) {
  const index = selectableInfoIds.indexOf(mid);
  if (index < 0) return false;
  const additive = Boolean(modifiers.ctrlKey || modifiers.metaKey);
  const shift = Boolean(modifiers.shiftKey);
  const next = (additive || checkboxToggle) ? new Set(selectedInfo) : new Set();
  if (shift && selectionAnchor && selectableInfoIds.includes(selectionAnchor)) {
    const start = selectableInfoIds.indexOf(selectionAnchor);
    const from = Math.min(start, index), to = Math.max(start, index);
    for (let i = from; i <= to; i += 1) next.add(selectableInfoIds[i]);
  } else if (additive || checkboxToggle) {
    if (next.has(mid)) next.delete(mid);
    else next.add(mid);
  } else {
    next.add(mid);
  }
  if (commitSelection(next)) {
    if (!shift || selectionAnchor === null) selectionAnchor = mid;
    return true;
  }
  return false;
}


function resetMailStatus() {
  selectedInfo.clear();
  selectionAnchor = null;
  selectableInfoIds = [];
  informationRows.clear();
  updateTrashSelection();
  el("metric-mail").textContent = "—";
  el("metric-tasks").textContent = "—";
  el("metric-action").textContent = "—";
  el("morning-title").textContent = "صباحك فل!";
  el("morning-text").textContent = "افتح OKAL لعرض موجز يومك المحلي.";
  el("morning-status").textContent = "مهام مؤكدة وبريد محفوظ؛ مش متصل بتقويم Google.";
  el("mail-status").textContent = "افتح الصندوق لعرض الحالة";
  el("integration-status").textContent =
    "افتح الصندوق لعرض حالة البريد المسجلة محليًا. لا يتم فحص Google أو تشغيل الموديل بمجرد فتح الصفحة.";
  el("sync").textContent = "لم يتم التحديث بعد";
  el("triage-groups").replaceChildren();
  el("triage-count").textContent = "لا توجد بيانات بعد";
  el("triage-note").textContent = "الواجهة تعرض نتائج محفوظة فقط؛ لا تُنفّذ أفعالًا على Gmail.";
  el("assistant-groups").replaceChildren();
  el("assistant-count").textContent = "لم يتم التحميل";
  el("assistant-note").textContent = "اقتراحات محلية فقط؛ لا إرسال أو إنشاء مهام خارج OKAL.";
  el("tasks-list").replaceChildren();
  el("tasks-count").textContent = "لم يتم التحميل";
  el("tasks-note").textContent = "مهام محلية بموافقتك؛ لا إنشاء أحداث في Google Calendar.";
}

function renderMorning(data) {
  if (!data || typeof data.spoken_text !== "string")
    throw new Error("invalid daily briefing");
  el("morning-title").textContent = data.greeting;
  el("morning-text").textContent = data.spoken_text;
  el("morning-status").textContent = data.mail_sync_stale
    ? "آخر مزامنة بريد قديمة؛ الموجز ممكن يكون ناقص. مفيش أي مواعيد من Google Calendar."
    : "ملخص من البريد المحفوظ والمهام المؤكدة محليًا، جاهز للصوت فيما بعد.";
}

function renderMailStatus(mail) {
  if (!mail) throw new Error("missing mail status");
  if (mail.configuration !== "configured") {
    el("mail-status").textContent = mail.configuration === "invalid"
      ? "إعداد غير صالح" : "غير مهيأ";
    el("integration-status").textContent =
      "البريد غير مهيأ للتشغيل حاليًا. الملخصات القديمة، إن وجدت، لا تثبت اتصالًا حاليًا.";
    return;
  }
  const success = mail.latest_success;
  el("mail-status").textContent = success
    ? "مهيأ · توجد قراءة ناجحة سابقة" : "مهيأ · لم تُثبت قراءة ناجحة";
  const parts = ["حالة محلية مسجلة؛ صلاحية اتصال Google وتوفر الموديل الآن لم يُفحصا."];
  if (mail.history === "unavailable") {
    el("mail-status").textContent = "مهيأ · تعذر قراءة سجل التشغيل";
    parts.push("تعذر قراءة سجل التشغيل؛ لا نفترض النجاح.");
  } else if (success) {
    parts.push(`آخر جلب وحفظ ناجح: ${new Date(success.updated * 1000).toLocaleString("ar-EG")}، عدد الرسائل: ${success.count}.`);
    if (success.count === 0) parts.push("الفترة كانت فارغة؛ هذا التشغيل لم يختبر الموديل.");
    else parts.push("اكتمل التلخيص؛ دقة المحتوى تحتاج مراجعتك.");
  }
  const attempt = mail.latest_attempt;
  if (attempt && attempt.status !== "succeeded") {
    parts.push(attempt.status === "failed"
      ? "آخر محاولة مسجلة فشلت؛ النجاح السابق لا يعني نجاحها."
      : "توجد محاولة مسجلة غير مكتملة؛ قد تكون جارية أو توقفت.");
  }
  if (mail.sync_enabled) {
    const sync = mail.sync;
    if (sync?.last_checked) parts.push(`آخر Sync محفوظ: ${new Date(sync.last_checked * 1000).toLocaleString("ar-EG")} — ${sync.last_count} رسالة جديدة.`);
    else parts.push("المزامنة المستمرة مفعّلة بالإعداد، ولم يثبت نجاح دورة بعد.");
    if (sync?.last_error === "authorization_required") {
      parts.push("Google Authorization Required · تحتاج إعادة تفويض Gmail محليًا. لم نفترض أن الاتصال صالح.");
    } else if (sync?.last_error) {
      parts.push("آخر فحص فشل؛ التقدم السابق محفوظ ولم نفترض التعافي. استخدم mail sync status وmail doctor.");
    }
    if (sync?.last_result === "history_chunk_pending") {
      parts.push("Catch-up in progress · توجد رسائل إضافية لم تُعالج، والـ History Cursor لم يتقدم عنها.");
    }
    if (sync?.last_result === "history_expired_visible_mail_backfill") {
      parts.push("استُعيد البريد الظاهر بعد انتهاء History Cursor؛ لا يمكن ضمان استرجاع الرسائل المحذوفة.");
    }
    if (sync?.manual_review_count) parts.push(`${sync.manual_review_count} رسالة تحتاج مراجعة يدوية؛ لم ينجح تحليل محتواها.`);
  }
  parts.push(mail.daily_at
    ? `الجدولة مفعّلة في الإعداد: ${mail.daily_at} (${mail.timezone})؛ هذا ليس إثباتًا لتشغيل العامل.`
    : "الجدولة متوقفة في الإعداد.");
  parts.push(mail.local_send_enabled
    ? "بوابة الإرسال المحلي مفعّلة في الإعداد؛ صلاحية Google لم تُفحص، والإرسال يتطلب مراجعة من سطر الأوامر."
    : "الإرسال المحلي مقفول في الإعداد.");
  el("integration-status").textContent = parts.join(" ");
}

function clusterKey(item) {
  const sender = String(item.sender || "").toLowerCase();
  const subject = String(item.subject || "").trim();
  const cleaned = subject.replace(/^(re:|fwd:|fw:)\s*/ig, "").trim();
  if (sender.includes("github.com")) {
    const repo = cleaned.match(/([a-z0-9_.-]+\/[a-z0-9_.-]+)/i)?.[1]?.toLowerCase();
    const pr = cleaned.match(/(?:pull\/?|pr\s*#|#)(\d{1,7})\b/i)?.[1];
    if (repo && pr) return `github-pr:${repo}:${pr}`;
    // Same workflow/repo, but never mix different PRs or workflows.
    if (repo) {
      const workflow = cleaned.replace(/\([a-f0-9]{7,40}\)/ig, "")
        .replace(/20\d\d[-/]\d\d[-/]\d\d/g, "")
        .replace(/\s+/g," ").toLowerCase();
      return "github-workflow:" + repo + ":" + workflow.slice(0, 95);
    }
  }
  if (cleaned.length < 8) return null;
  const normalized = cleaned.toLowerCase().replace(/\s+/g," ");
  const domain = sender.match(/@([a-z0-9.-]+)/)?.[1];
  return domain ? domain + ":" + normalized : null;
}

function renderTriage(result) {
  if (!result || !Array.isArray(result.items)) throw new Error("invalid triage payload");
  const groups = el("triage-groups");
  groups.replaceChildren();
  selectedInfo.clear();
  informationRows.clear();
  selectableInfoIds = [];
  selectionAnchor = null;
  updateTrashSelection();
  const categories = [
    ["manual_review", "00", "مراجعة يدوية", "Manual review"],
    ["action", "01", "يحتاج إجراء", "Action required"],
    ["information", "02", "للاطلاع", "Information"],
    ["low_priority", "03", "لاحقًا", "Low priority"],
  ];
  const eligible = (item) => (
    item && typeof item.id === "string" &&
    /^[a-fA-F0-9]{1,64}$/.test(item.id) && Array.isArray(item.labels) &&
    !item.labels.some((v) => ["SENT","DRAFT","SPAM","TRASH","STARRED","IMPORTANT"].includes(v))
  );
  const counts = categories.map(([key]) =>
    result.items.filter((item) => item.category === key).length);
  el("triage-count").textContent =
    `${result.items.length} رسالة · ${counts[1]} تحتاج إجراء · ${counts[0]} للمراجعة اليدوية`;
  el("triage-note").textContent =
    "حدد من أي تصنيف؛ الرسائل المحمية في Gmail غير قابلة للحذف. اضغط على عنوان الرسالة لعرض محتواها هنا.";
  el("metric-mail").textContent = String(result.items.length);
  el("metric-action").textContent = String(counts[0] + counts[1]);
  for (const [key, number, arabic, english] of categories) {
    const items = result.items.filter((item) => item.category === key);
    if (!items.length) continue;
    const column = document.createElement("section");
    column.className = `triage-column triage-${key}`;
    column.setAttribute("aria-label", `${arabic} — تحديد الرسائل وفتحها`);
    const head = document.createElement("div");
    head.className = "triage-column-head";
    head.append(text("span", number, "triage-number"),
      text("h4", `${arabic} · ${english}`),
      text("span", String(items.length), "triage-number"));
    column.append(head);
    const buckets = new Map();
    for (const item of items) {
      const cluster = clusterKey(item);
      // Messages without a strong source+subject match must remain separate.
      const clusterId = cluster || `single-${item.id || buckets.size}`;
      if (!buckets.has(clusterId)) buckets.set(clusterId, []);
      buckets.get(clusterId).push(item);
    }
    for (const clusterItems of buckets.values()) {
      let target = column;
      if (clusterItems.length > 1) {
        const details = document.createElement("details");
        details.className = "mail-cluster";
        const summary = document.createElement("summary");
        const leader = clusterItems[0];
        summary.append(
          text("strong", String(leader.subject).slice(0,150)),
          text("span", `${clusterItems.length} رسائل مشابهة · اضغط للعرض`,
            "cluster-count"),
        );
        details.append(summary);
        target = details;
        column.append(details);
      }
      for (const item of clusterItems) {
        const article = document.createElement("article");
        article.className = "triage-message";
        article.append(text("span", item.sender, "triage-sender"));
        const title = document.createElement("button");
        title.className = "message-open";
        title.textContent = item.subject;
        title.type = "button";
        title.addEventListener("click", (event) => {
          event?.stopPropagation?.();
          openMailViewer(item);
        });
        article.append(title, text("p", item.summary, "triage-summary"));
        if (item.suggested_action)
          article.append(text("p", `Next step · ${item.suggested_action}`, "triage-action"));
        if (item.has_unread_attachments)
          article.append(text("p", "مرفقات تحتاج مراجعة", "triage-warning"));
        const link = document.createElement("a");
        link.textContent = "فتح في Gmail";
        link.href = item.link;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        article.append(link);

        if (eligible(item) && !informationRows.has(item.id)) {
          const selection = document.createElement("label");
          selection.className = "trash-selector";
          const check = document.createElement("input");
          check.type = "checkbox";
          check.checked = false;
          check.setAttribute("aria-label", `تحديد: ${String(item.subject).slice(0,120)}`);
          let checkboxModifiers = {};
          check.addEventListener("click", (event) => {
            checkboxModifiers = {ctrlKey: !!event?.ctrlKey, metaKey: !!event?.metaKey,
              shiftKey: !!event?.shiftKey};
            event?.stopPropagation?.();
          });
          check.addEventListener("change", () => {
            if (checkboxModifiers.shiftKey) chooseInformation(item.id, checkboxModifiers);
            else {
              const next = new Set(selectedInfo);
              if (check.checked) next.add(item.id); else next.delete(item.id);
              if (commitSelection(next)) selectionAnchor = item.id;
            }
            checkboxModifiers = {};
          });
          selection.append(check, text("span", "تحديد الرسالة"));
          article.append(selection);
          article.className = "triage-message is-selectable";
          article.tabIndex = 0;
          article.setAttribute("aria-label", `رسالة: ${String(item.subject).slice(0,120)}`);
          article.addEventListener("click", (event) => {
            if (event?.target?.closest?.("a, label, input, button, summary")) return;
            // Regular click reads the full message. Ctrl/Shift select rows.
            if (event?.ctrlKey || event?.metaKey || event?.shiftKey)
              chooseInformation(item.id, event);
            else openMailViewer(item);
          });
          article.addEventListener("keydown", (event) => {
            if (event?.target?.closest?.("a, label, input, button")) return;
            if (event.key === "Enter") {
              event.preventDefault();
              if (event.ctrlKey || event.metaKey || event.shiftKey)
                chooseInformation(item.id, event);
              else openMailViewer(item);
            } else if (event.key === " ") {
              event.preventDefault();
              chooseInformation(item.id, {...event, ctrlKey:true});
            }
          });
          selectableInfoIds.push(item.id);
          informationRows.set(item.id, {article,checkbox:check});
        } else if (!eligible(item)) {
          article.append(text("p", "محمي من النقل التلقائي إلى Trash",
            "triage-warning"));
        }
        target.append(article);
      }
    }
    groups.append(column);
  }
  updateTrashSelection();
}

function renderAssistant(result) {
  if (!result || !Array.isArray(result.items) || !result.counts)
    throw new Error("invalid assistant preview");
  const groups = el("assistant-groups");
  groups.replaceChildren();
  const buckets = [
    ["manual_review", "00", "مراجعة يدوية", "Manual review"],
    ["reply_review", "01", "رد يحتاج موافقة", "Reply review"],
    ["task_review", "02", "مهام مقترحة", "Suggested tasks"],
    ["read_later", "03", "اقرأ لاحقًا", "Read later"],
  ];
  el("assistant-count").textContent =
    `${result.total_in_sample} رسالة · ${result.counts.task_review || 0} مهام · ${result.counts.reply_review || 0} ردود للمراجعة`;
  el("assistant-note").textContent =
    "قواعد محلية فوق نتائج AI المحفوظة؛ لا Google Tasks أو Calendar أو Send. التواريخ غير مؤكدة ولا تُضاف تلقائيًا.";
  if (result.state === "awaiting_saved_gmail_insights") {
    el("assistant-count").textContent = "بانتظار أول مزامنة محفوظة";
    return;
  }
  for (const [bucket, number, arabic, english] of buckets) {
    const items = result.items.filter((item) => item.bucket === bucket);
    if (!items.length) continue;
    const column = document.createElement("section");
    column.className = `triage-column triage-${bucket}`;
    const head = document.createElement("div");
    head.className = "triage-column-head";
    head.append(text("span", number, "triage-number"),
      text("h4", `${arabic} · ${english}`),
      text("span", String(items.length), "triage-number"));
    column.append(head);
    for (const item of items) {
      const article = document.createElement("article");
      article.className = "triage-message";
      article.append(text("span", item.sender, "triage-sender"),
        text("h5", item.subject),
        text("p", item.summary, "triage-summary"));
      if (item.proposed_task) {
        article.append(text("p",
          `مقترح فقط · ${item.proposed_task.title} · بدون موعد تلقائي`,
          "triage-action"));
      } else if (bucket === "reply_review") {
        article.append(text("p",
          "مسودة الرد لم تُنشأ؛ محتاجة تعليماتك ومراجعتك قبل الإرسال.",
          "triage-action"));
      }
      if (item.attachments_unreviewed) {
        article.append(text("p",
          "المرفقات لم تُراجع · Attachments not reviewed",
          "triage-warning"));
      }
      const link = document.createElement("a");
      link.href = item.source_link;
      link.textContent = "مراجعة البريد الأصلي في Gmail";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      article.append(link);
      column.append(article);
    }
    groups.append(column);
  }
}

function renderTasks(result) {
  if (!result || !Array.isArray(result.items))
    throw new Error("invalid local tasks payload");
  const list = el("tasks-list");
  list.replaceChildren();
  el("tasks-count").textContent =
    `${result.total_in_sample} مهمة مفتوحة · ${result.overdue_in_sample || 0} فات موعدها`;
  el("metric-tasks").textContent = String(result.total_in_sample);
  el("tasks-note").textContent =
    "المواعيد أدخلتها أنت؛ بدون Google Calendar أو تنبيهات نظام مجدولة حتى الآن.";
  for (const item of result.items) {
    const article = document.createElement("article");
    article.className = "task-card";
    article.append(text("h4", item.title));
    if (item.due_at !== null && item.due_at !== undefined) {
      const due = new Date(item.due_at * 1000);
      if (!Number.isNaN(due.getTime())) {
        article.append(text("p",
          `الموعد المؤكد · ${due.toLocaleString("ar-EG")}`, "task-due"));
      }
    } else {
      article.append(text("p", "بدون موعد محدد", "muted"));
    }
    if (item.source_link) {
      const link = document.createElement("a");
      link.textContent = "الرسالة الأصلية في Gmail";
      link.href = item.source_link;
      link.rel = "noopener noreferrer";
      link.target = "_blank";
      article.append(link);
    }
    list.append(article);
  }
  if (!result.items.length)
    list.append(text("p", "لسه مفيش مهام مؤكدة. اقتراحات البريد موجودة فوق.",
      "muted"));
}

function lock() {
  generation += 1;
  if (controller) controller.abort();
  token = "";
  cursor = null;
  el("token").value = "";
  el("items").replaceChildren();
  el("inbox-panel").hidden = true;
  // Hide content; this does not revoke access in auto-unlock mode.
  el("login-panel").hidden = true;
  el("connection").textContent = "العرض مخفي";
  el("connection").classList.remove("connected");
  resetMailStatus();
  if (el("mail-viewer").open) el("mail-viewer").close();
  if (el("trash-dialog").open) el("trash-dialog").close();
  setBusy(false);
}

function setBusy(value) {
  busy = value;
  for (const id of ["connect", "refresh", "more"]) el(id).disabled = value;
}

function text(tag, value, className) {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
}

function card(item) {
  const article = document.createElement("article");
  article.className = "summary";
  const meta = document.createElement("div");
  meta.className = "summary-meta";
  meta.append(
    text(
      "span",
      item.data_kind === "fixture"
        ? "بيانات تجريبية · ليست من حسابك"
        : "ملخص محفوظ",
      item.data_kind === "fixture" ? "fixture" : "",
    ),
  );
  meta.append(
    text("time", new Date(item.created_at * 1000).toLocaleString("ar-EG")),
  );
  article.append(meta, text("h3", item.title), text("p", item.body, "body"));
  article.append(text("p", `حُفظ في المركز · ${item.workflow}`, "run-state"));
  return article;
}

async function load(reset) {
  if (busy) return;
  setBusy(true);
  el("message").textContent = "";
  controller = new AbortController();
  const active = ++generation;
  try {
    const query = new URLSearchParams({ limit: "20" });
    if (!reset && cursor) query.set("cursor", cursor);
    const options = {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      cache: "no-store",
      credentials: "same-origin",
      signal: controller.signal,
    };
    const [response, capsResponse] = await Promise.all([
      fetch(`/api/v1/summaries?${query}`, options),
      fetch("/api/v1/capabilities", options),
    ]);
    if (active !== generation) return;
    if (response.status === 401 || capsResponse.status === 401) {
      lock();
      keyProtected = true;
      el("login-panel").hidden = false;
      el("message").textContent =
        "الوضع المحمي مفعّل؛ أدخل مفتاح القراءة المحلي للمتصفح.";
      return;
    }
    if (!response.ok || !capsResponse.ok) throw new Error("read failed");
    const [result, caps] = await Promise.all([response.json(), capsResponse.json()]);
    if (active !== generation) return;
    keyProtected = caps.read_key_required === true;
    renderMailStatus(caps.mail);
    try {
      const morningResponse = await fetch("/api/v1/morning", options);
      if (active !== generation) return;
      if (!morningResponse.ok) throw new Error("morning unavailable");
      renderMorning(await morningResponse.json());
    } catch (error) {
      if (active !== generation || error.name === "AbortError") return;
      el("morning-text").textContent = "تعذر قراءة الموجز الصباحي من البيانات المحلية.";
    }
    if (caps.mail?.sync_enabled) {
      try {
        const triageResponse = await fetch("/api/v1/mail/triage", options);
        if (active !== generation) return;
        if (!triageResponse.ok) throw new Error("triage read failed");
        renderTriage(await triageResponse.json());
      } catch (error) {
        if (active !== generation || error.name === "AbortError") return;
        el("triage-groups").replaceChildren();
        el("triage-count").textContent = "تعذر قراءة التصنيف المحفوظ";
      }
    } else {
      el("triage-groups").replaceChildren();
      el("triage-count").textContent = "المزامنة المستمرة غير مفعّلة";
    }
    if (caps.mail?.configuration === "configured") {
      try {
        const actionsResponse = await fetch("/api/v1/mail/assistant", options);
        if (active !== generation) return;
        if (!actionsResponse.ok) throw new Error("assistant read failed");
        renderAssistant(await actionsResponse.json());
      } catch (error) {
        if (active !== generation || error.name === "AbortError") return;
        el("assistant-groups").replaceChildren();
        el("assistant-count").textContent = "تعذر قراءة الاقتراحات المحلية";
      }
    } else {
      el("assistant-groups").replaceChildren();
      el("assistant-count").textContent = "البريد غير مهيأ";
    }
    try {
      const tasksResponse = await fetch("/api/v1/tasks", options);
      if (active !== generation) return;
      if (!tasksResponse.ok) throw new Error("task board unavailable");
      renderTasks(await tasksResponse.json());
    } catch (error) {
      if (active !== generation || error.name === "AbortError") return;
      el("tasks-list").replaceChildren();
      el("tasks-count").textContent = "تعذر تحميل المهام المحلية";
    }
    if (reset) el("items").replaceChildren();
    for (const item of result.items) el("items").append(card(item));
    cursor = result.next_cursor;
    el("more").hidden = !cursor;
    el("empty").hidden = el("items").childElementCount !== 0;
    el("sync").textContent =
      `آخر قراءة للملخصات المحفوظة: ${new Date(result.fetched_at * 1000).toLocaleString("ar-EG")} · زر التحديث لا يجلب بريدًا جديدًا من Gmail`;
    el("inbox-panel").hidden = false;
    el("login-panel").hidden = true;
    el("connection").textContent = keyProtected
      ? "متصل · وضع محمي" : "متصل محليًا · بدون مفتاح";
    el("connection").classList.add("connected");
  } catch (error) {
    if (active !== generation || error.name === "AbortError") return;
    resetMailStatus();
    el("mail-status").textContent = "الحالة غير متاحة";
    el("integration-status").textContent = "تعذر تحديث الحالة؛ لا نعتمد على آخر حالة معروضة كدليل اتصال حالي.";
    el("connection").textContent = "تعذر الاتصال";
    el("connection").classList.remove("connected");
    el("message").textContent =
      "تعذر تحديث الصندوق. البيانات الظاهرة إن وجدت قديمة؛ آخر قراءة موضحة أعلاه. تحقق أن خدمة المركز تعمل ثم أعد المحاولة.";
  } finally {
    if (active === generation) setBusy(false);
  }
}

el("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  const oneTimeKey = el("token").value.trim();
  el("token").value = "";
  setBusy(true);
  try {
    const response = await fetch("/api/v1/session", {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: oneTimeKey }),
    });
    if (!response.ok) throw new Error("pairing failed");
    token = ""; // Never keep the pairing key in JS after the exchange.
    el("message").textContent = "";
  } catch (_) {
    el("message").textContent = "تعذر ربط هذا المتصفح. تحقق من مفتاح القراءة المحلي أو صلاحيته.";
    setBusy(false);
    return;
  }
  setBusy(false);
  load(true);
});
el("clear-selection").addEventListener("click", () => clearInformationSelection());
el("select-all-info").addEventListener("click", () => {
  const next = new Set(selectableInfoIds.slice(0, 20));
  if (commitSelection(next)) selectionAnchor = selectableInfoIds[0] || null;
});
document.addEventListener("keydown", (event) => {
  // Only intercept Ctrl/Cmd+A when focus is inside a Gmail message group,
  // not in the entire document or an editable field.
  const inside = event.target?.closest?.(".triage-column");
  if (inside && (event.ctrlKey || event.metaKey) &&
      event.key?.toLowerCase() === "a") {
    event.preventDefault();
    const next = new Set(selectableInfoIds.slice(0, 20));
    if (commitSelection(next)) selectionAnchor = selectableInfoIds[0] || null;
  }
  if (inside && event.key === "Escape") clearInformationSelection();
});
try {
  el("current-date").textContent = new Intl.DateTimeFormat("ar-EG", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
    timeZone: "Africa/Cairo",
  }).format(new Date());
} catch (_) {
  el("current-date").textContent = "Your local command center";
}

// MIME reader is an on-demand Gmail API read, not part of automatic sync.
// Render untrusted original HTML ONLY inside a sandboxed, script-disabled
// iframe with a restrictive per-message CSP.
let currentViewerMessage = null;
let viewerItem = null;
let viewerGeneration = 0;
let approvedTrash = null;
const escapeHtml = (value) => String(value || "").replace(/[&<>"']/g,
  (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));

function viewerDocument(message, remote) {
  const imagePolicy = remote ? "data: https:" : "data:";
  const csp = "default-src 'none'; script-src 'none'; connect-src 'none'; " +
    "font-src data:; media-src data:; img-src " + imagePolicy + "; " +
    "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none';";
  const head = '<!doctype html><html><head><meta charset="utf-8">' +
    '<meta http-equiv="Content-Security-Policy" content="' + escapeHtml(csp) + '">' +
    '<meta name="referrer" content="no-referrer"><style>' +
    'body{margin:20px;color:#111;background:white;font-family:system-ui,Arial,sans-serif;' +
    'font-size:15px;line-height:1.65;overflow-wrap:anywhere}img{max-width:100%;height:auto}' +
    'table{max-width:100%;}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style></head><body>';
  const body = message.html || "<pre>" + escapeHtml(message.text ||
    "محتوى الرسالة غير متوفر بصيغة مقروءة") + "</pre>";
  return head + body + "</body></html>";
}

function refreshViewerDocument() {
  if (!currentViewerMessage) return;
  el("viewer-frame").srcdoc = viewerDocument(
    currentViewerMessage, el("viewer-remote-images").checked
  );
}

async function openMailViewer(item) {
  const id = typeof item === "string" ? item : item?.id;
  if (!/^[a-fA-F0-9]{1,64}$/.test(String(id || ""))) return;
  viewerItem = typeof item === "object" ? item : null;
  el("viewer-ai-summary").textContent = "جارٍ جلب التلخيص المحفوظ...";
  el("viewer-ai-action").textContent = "";
  el("viewer-category").textContent = "";
  el("viewer-action-note").textContent = "";
  for (const name of ["viewer-copy-summary","viewer-select","viewer-delete"])
    el(name).disabled = true;
  el("viewer-title").textContent = "جارٍ تحميل الرسالة الأصلية...";
  el("viewer-from").textContent = "";
  el("viewer-to").textContent = "";
  el("viewer-date").textContent = "";
  el("viewer-frame").srcdoc = "";
  el("viewer-attachments").replaceChildren();
  el("viewer-note").textContent = "بنقرأ Gmail مباشرة عند الطلب؛ مش ملخص AI.";
  el("viewer-remote-images").checked = false;
  currentViewerMessage = null;
  const requestGeneration = ++viewerGeneration;
  el("mail-viewer").showModal();
  try {
    const response = await fetch("/api/v1/mail/messages/" + id, {
      credentials:"same-origin", cache:"no-store",
      headers: token ? {Authorization: "Bearer " + token} : {},
    });
    if (!response.ok) throw new Error("read " + response.status);
    const data = await response.json();
    if (requestGeneration !== viewerGeneration || !el("mail-viewer").open) return;
    if (data.id !== id) throw new Error("source mismatch");
    currentViewerMessage = data;
    el("viewer-ai-summary").textContent =
      data.ai_summary || "مافيش ملخص AI محفوظ لهذه الرسالة؛ راجع النص الأصلي.";
    el("viewer-ai-action").textContent = data.ai_suggested_action
      ? "الإجراء المقترح · " + data.ai_suggested_action
      : "مافيش إجراء مطلوب بشكل مؤكد.";
    const labels = {action:"يحتاج إجراء",information:"للاطلاع",
      low_priority:"أولوية منخفضة",manual_review:"مراجعة يدوية"};
    el("viewer-category").textContent = labels[data.ai_category] || "غير مصنّف";
    el("viewer-copy-summary").disabled = !data.ai_summary;
    const selectable = informationRows.has(id);
    el("viewer-select").disabled = !selectable;
    el("viewer-delete").disabled = !selectable;
    if (!selectable)
      el("viewer-action-note").textContent =
        "الرسالة محمية أو غير مؤهلة للنقل الجماعي إلى Trash.";
    el("viewer-title").textContent = data.subject || "بدون عنوان";
    el("viewer-from").textContent = data.from || "غير معروف";
    el("viewer-to").textContent = data.to || "غير معروف";
    el("viewer-date").textContent = data.date || "غير معروف";
    el("viewer-gmail").href = data.gmail_link;
    el("viewer-note").textContent = "محتوى Gmail الأصلي في إطار معزول. " +
      "الصور الداخلية متاحة، والصور الخارجية تحتاج موافقتك بسبب احتمالية التتبع.";
    for (const attachment of data.attachments || []) {
      el("viewer-attachments").append(text("p",
        "مرفق: " + attachment.name + " (" + attachment.mime_type + ")" +
        (attachment.too_large_for_preview ? " — الصورة كبيرة، افتحها في Gmail" :
          attachment.data_url ? " — معاينة الصورة محفوظة مؤقتًا داخل الصفحة" :
          " — للتحميل افتح Gmail"), "muted"));
      if (typeof attachment.data_url === "string" &&
          /^data:image\/(png|jpeg|webp|gif|avif);base64,[A-Za-z0-9+/=]+$/.test(attachment.data_url)) {
        const image = document.createElement("img");
        image.src = attachment.data_url;
        image.alt = "مرفق صورة: " + attachment.name;
        image.className = "viewer-attached-image";
        image.loading = "lazy";
        el("viewer-attachments").append(image);
      }
    }
    refreshViewerDocument();
  } catch (_) {
    if (requestGeneration !== viewerGeneration || !el("mail-viewer").open) return;
    el("viewer-ai-summary").textContent =
      viewerItem?.summary || "ملخص محفوظ غير متاح.";
    el("viewer-ai-action").textContent = viewerItem?.suggested_action || "";
    el("viewer-title").textContent = "تعذر فتح الرسالة";
    el("viewer-note").textContent =
      "لم نقدر نقرأ محتوى الرسالة من Gmail حاليًا؛ تحقق من الاتصال وصلاحية Google.";
  }
}
el("viewer-close").addEventListener("click", () => el("mail-viewer").close());
el("mail-viewer").addEventListener("close", () => {
  viewerGeneration += 1;
  currentViewerMessage = null;
  viewerItem = null;
  for (const name of ["viewer-ai-summary","viewer-ai-action","viewer-category",
                      "viewer-action-note"]) el(name).textContent = "";
  for (const name of ["viewer-copy-summary","viewer-select","viewer-delete"])
    el(name).disabled = true;
  for (const id of ["viewer-from","viewer-to","viewer-date","viewer-note"])
    el(id).textContent = "";
  el("viewer-attachments").replaceChildren();
  el("viewer-frame").srcdoc = "";
});
el("viewer-remote-images").addEventListener("change", refreshViewerDocument);
el("viewer-copy-summary").addEventListener("click", async () => {
  const summary = currentViewerMessage?.ai_summary;
  if (!summary) return;
  try {
    await navigator.clipboard.writeText(summary);
    el("viewer-action-note").textContent = "تم نسخ التلخيص.";
  } catch (_) {
    el("viewer-action-note").textContent =
      "نسخ الملخص غير متاح؛ تقدر تحدد النص وتنسخه يدويًا.";
  }
});
el("viewer-select").addEventListener("click", () => {
  const id = currentViewerMessage?.id;
  if (!id || !informationRows.has(id)) return;
  const next = new Set(selectedInfo);
  next.add(id);
  if (commitSelection(next))
    el("viewer-action-note").textContent = "تمت إضافة الرسالة للتحديد.";
});
el("viewer-delete").addEventListener("click", async () => {
  const id = currentViewerMessage?.id;
  if (!id || !informationRows.has(id)) return;
  await showTrashPreview([id]);
});


// Human-readable, safe diagnostics only. Never expose provider payloads,
// private subjects, tokens or arbitrary exception strings in the UI.
const trashPreviewCodes = Object.freeze({
  "mail_operation_already_running":
    "المزامنة التلقائية شغالة دلوقتي؛ OKAL هيحاول القراءة تاني، ولو استمر التعارض جرب بعد اكتمال المزامنة.",
  "authorization_required":
    "جلسة Gmail OAuth محتاجة تفويض جديد من نفس الحساب.",
  "scope_or_send_permission_mismatch":
    "صلاحيات Gmail المحفوظة مش متطابقة مع إعدادات OKAL. راجع تفويض OAuth الحالي.",
  "wrong_google_account":
    "حساب Gmail المتصل مختلف عن الحساب المضبوط في OKAL.",
  "provider_read_failed":
    "Gmail رجّع خطأ أثناء قراءة العناوين. اتأكد من الاتصال وإتاحة Gmail API، وجرب المعاينة تاني.",
  "trash_protected_or_outdated_saved_labels":
    "فيه رسالة عليها علامة حماية (Starred / Important / Sent / Draft / Trash)، أو بياناتها قديمة. شيلها من التحديد.",
  "trash_native_metadata_changed_or_protected":
    "واحدة من الرسائل اتغير عنوانها أو علاماتها داخل Gmail، أو أصبحت محمية. حدّث القائمة وراجع اختيارك.",
  "trash_source_unavailable":
    "واحدة من الرسائل مش موجودة على Gmail بالـ ID المحفوظ. حدّث القائمة.",
  "trash_source_not_in_saved_inbox":
    "رسالة من المحدد مش مثبتة في بيانات OKAL المحلية. حدّث القائمة.",
  "trash_previously_attempted_or_confirmed_review_gmail":
    "سبق محاولة نقل واحدة من الرسائل إلى Trash. راجع Gmail Trash يدويًا قبل أي إعادة محاولة.",
  "trash_unknown_classification":
    "واحدة من الرسائل تصنيفها غير مؤكد. راجعها منفردة.",
  "trash_permission_disabled_reauthorize":
    "يجب تفعيل صلاحية نقل Gmail إلى Trash مرة واحدة عبر OAuth باستخدام --enable-trash؛ إلغاء PIN لا يلغي صلاحية Google. (code: trash_permission_disabled_reauthorize)",
  "trash_confirmation_expired_or_invalid":
    "انتهت صلاحية التأكيد أو اتغيرت الرسائل. افتح معاينة Delete جديدة وراجع القائمة من الأول. (code: trash_confirmation_expired_or_invalid)",
  "trash_requires_1_to_20_unique_message_ids":
    "اختار من رسالة واحدة إلى 20 رسالة مختلفة.",
  "trash_untrusted_saved_evidence_invalid":
    "بيانات المصدر المحلي لرسالة غير متطابقة؛ المعاينة اتوقفت لحمايتك.",
  "unsafe_lock_file":
    "ملف قفل عمليات البريد صلاحياته غير آمنة؛ راجعه محليًا.",
});
function trashPreviewProblem(status, detail) {
  const code = typeof detail === "string" &&
    /^[a-z][a-z0-9_]{1,100}$/.test(detail) ? detail : "";
  const explanation = trashPreviewCodes[code];
  if (explanation) return explanation + " (code: " + code + ")";
  if (status === 403) return "المتصفح مش مسموح له ينفذ الطلب من العنوان الحالي. افتح OKAL من http://127.0.0.1:8766 مباشرة.";
  if (status === 401) return "وضع الحماية مفعل أو جلسة القراءة انتهت. افتح OKAL مجددًا.";
  if (status === 429 || status === 423)
    return "خدمة Gmail مشغولة حاليًا. أعد المعاينة بعد انتهاء العملية الجارية.";
  if (status >= 500) return "حصل خطأ داخلي في OKAL Core أثناء المعاينة. افحص سجل okal-core.service.";
  return "تعذر تجهيز معاينة Gmail (HTTP " + status + "). افحص سجل OKAL لمعرفة السبب.";
}

async function postTrashPreview(ids) {
  // Safe bounded retries only for non-mutating preview when history sync
  // temporarily owns operation.lock. Never retry any DELETE/Trash write.
  for (let attempt = 0; attempt < 3; attempt++) {
    const response = await fetch("/api/v1/mail/trash/preview", {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ids}),
    });
    if (response.ok) return response.json();
    const body = await response.json().catch(() => ({}));
    const code = typeof body?.detail === "string" ? body.detail : "";
    if (code === "mail_operation_already_running" && attempt < 2) {
      await new Promise((resolve) => setTimeout(resolve, 700));
      continue;
    }
    throw new Error(trashPreviewProblem(response.status, code));
  }
  throw new Error(trashPreviewProblem(423, "mail_operation_already_running"));
}

async function showTrashPreview(ids) {
  if (!ids.length || ids.length > 20) return;
  el("trash-selected").disabled = true;
  el("trash-help").textContent = "جارٍ التأكد من العناوين مباشرة من Gmail...";
  try {
    const data = await postTrashPreview(ids);
    if (data.count !== ids.length ||
        !/^[a-f0-9]{64}$/.test(data.approval_digest) ||
        typeof data.confirmation_token !== "string" ||
        !/^[a-zA-Z0-9_-]{40,90}$/.test(data.confirmation_token))
      throw new Error("unsafe preview");
    approvedTrash = {
      ids, digest:data.approval_digest, ticket:data.confirmation_token
    };
    el("trash-preview-list").replaceChildren();
    for (const message of data.items)
      el("trash-preview-list").append(
        text("p", message.subject + " — " + message.sender)
      );
    el("trash-result").textContent = "";
    el("trash-dialog").showModal();
    el("trash-help").textContent =
      "راجع كل العناوين، واضغط تأكيد للنقل الفعلي إلى Trash. بدون PIN.";
  } catch (error) {
    approvedTrash = null;
    const message = String(error?.message || "");
    el("trash-help").textContent =
      message.startsWith("تعذر") || message.includes("(code:")
        ? message : trashPreviewProblem(500, "");
  } finally {
    el("trash-selected").disabled = selectedInfo.size === 0;
  }
}
el("trash-selected").addEventListener("click", async () => {
  await showTrashPreview(selectableInfoIds.filter(
    (mid) => selectedInfo.has(mid)
  ));
});
el("trash-cancel").addEventListener("click", () => el("trash-dialog").close());
el("trash-dialog").addEventListener("close", () => {
  approvedTrash = null;
});
el("trash-confirm-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!approvedTrash) return;
  // No PIN/password: this button is the explicit, user-reviewed confirmation.
  el("trash-confirm").disabled = true;
  el("trash-result").textContent = "جارٍ النقل إلى Trash...";
  try {
    const response = await fetch("/api/v1/mail/trash", {
      method:"POST", credentials:"same-origin", cache:"no-store",
      headers: {"Content-Type":"application/json"},
      body:JSON.stringify({
        ids: approvedTrash.ids, approval_digest:approvedTrash.digest,
        confirmation_token:approvedTrash.ticket, confirmed:true,
      }),
    });
    if (!response.ok) {
      const safe = await response.json();
      const code = typeof safe?.detail === "string" ? safe.detail : "";
      throw new Error(trashPreviewProblem(response.status, code));
    }
    const result = await response.json();
    if (result.status !== "confirmed_trash")
      throw new Error("provider result was not confirmed");
    el("trash-dialog").close();
    el("trash-help").textContent =
      "تم نقل " + result.moved + " رسالة إلى Gmail Trash القابل للاسترجاع.";
    clearInformationSelection();
    load(true);
  } catch (error) {
    // Never retry a Gmail write: outcome could be partial/uncertain.
    el("trash-result").textContent =
      String(error.message).startsWith("يجب تفعيل") ||
      String(error.message).includes("(code:") ||
      String(error.message).startsWith("المتصفح")
        ? String(error.message)
        : "لم يتم تأكيد نقل كل الرسائل. راجع Gmail Trash قبل المحاولة مجددًا. " +
          String(error.message).slice(0,120);
  } finally {
    el("trash-confirm").disabled = false;
  }
});

el("refresh").addEventListener("click", () => load(true));
el("more").addEventListener("click", () => load(false));
el("logout").addEventListener("click", async () => {
  let revoked = false;
  if (keyProtected) {
    try {
      const response = await fetch("/api/v1/session", {
        method: "DELETE", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" },
      });
      revoked = response.ok;
    } catch (_) {
      // Do not claim that the protected session has been revoked.
    }
  }
  lock();
  if (keyProtected) {
    el("login-panel").hidden = false;
    el("message").textContent = revoked
      ? "تم إلغاء جلسة المتصفح. للوصول مجددًا أدخل مفتاح القراءة."
      : "أُخفي المحتوى، ولكن لم يُؤكَّد إلغاء الجلسة على الخادم.";
  } else {
    el("message").textContent =
      "تم إخفاء العرض مؤقتًا فقط، وليس قفلًا أمنيًا. أعد تحميل الصفحة لفتحه تلقائيًا.";
  }
});
window.addEventListener("pagehide", lock);

// Default single-user loopback mode auto-opens; protected mode falls back to pairing.
window.addEventListener("DOMContentLoaded", () => load(true));

// Re-read the local snapshot after the Gmail history worker updates SQLite.
// Never invoke Gmail from this timer. Preserve the owner's current selection
// and never replace an open message or a Delete approval dialog mid-review.
function refreshLocalInboxIfIdle() {
  if (busy || selectedInfo.size ||
      el("inbox-panel").hidden ||
      el("mail-viewer").open || el("trash-dialog").open ||
      document.hidden) return;
  load(true);
}
if (typeof window.setInterval === "function")
  window.setInterval(refreshLocalInboxIfIdle, 90000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshLocalInboxIfIdle();
});
