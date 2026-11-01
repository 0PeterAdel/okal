"use strict";
// Read-only shell. Tokens and reports stay in memory, never browser storage.
const el = (id) => document.getElementById(id);
let token = "";
let keyProtected = false;
let trashPermissionConfigured = null;
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
  trashPermissionConfigured = null;
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

let lastTriageResult = null;
let lastAssistantResult = null;
const viewedThisSession = new Set();
function renderTriage(result) {
  if (!result || !Array.isArray(result.items)) throw new Error("invalid triage payload");
  lastTriageResult = result;
  result = {...result, items:result.items.filter(item => !viewedThisSession.has(item.id))};
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
          // Protected mail is still readable: only Trash selection is blocked.
          article.tabIndex = 0;
          article.addEventListener("click", (event) => {
            if (!event?.target?.closest?.("a, button, label, input"))
              openMailViewer(item);
          });
          article.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && event.target === article) {
              event.preventDefault();
              openMailViewer(item);
            }
          });
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
  lastAssistantResult = result;
  const items = result.items.filter(item => !viewedThisSession.has(item.source_id));
  const counts = {};
  for (const item of items) counts[item.bucket] = (counts[item.bucket]||0)+1;
  result = {...result,items,counts,total_in_sample:items.length};
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

let currentEditingTask = null;
let taskHistoryExpanded = false;

function taskDueIso(field) {
  const raw = el(field).value;
  if (!raw) return null;
  const parsed = new Date(raw);
  if (!Number.isFinite(parsed.getTime())) throw new Error("اختار وقت صالح.");
  return parsed.toISOString(); // includes UTC offset; no invented timezone
}
function reminderChoice(field, hasDue) {
  const raw = el(field).value;
  if (!raw) return null;
  const value = Number(raw);
  if (!hasDue) throw new Error("اختار موعدًا صريحًا قبل التذكير.");
  if (![0,5,15,60,1440].includes(value))
    throw new Error("قيمة التذكير غير مدعومة.");
  return value;
}
function taskLocalDate(unixSeconds) {
  const date = new Date(unixSeconds*1000);
  return new Intl.DateTimeFormat("ar-EG",{
    timeZone:"Africa/Cairo",year:"numeric",month:"short",
    day:"numeric",hour:"2-digit",minute:"2-digit"
  }).format(date);
}
function dateInputValue(unixSeconds) {
  if (unixSeconds === null || unixSeconds === undefined) return "";
  const date = new Date(unixSeconds*1000);
  const local = new Date(date.getTime()-date.getTimezoneOffset()*60000);
  return local.toISOString().slice(0,16);
}
async function taskPost(path,payload) {
  const response = await fetch(path,{
    method:"POST",credentials:"same-origin",cache:"no-store",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(payload)
  });
  const output = await response.json().catch(()=>({}));
  if (!response.ok) {
    const code = String(output.detail || "request_failed");
    // Only safe validated local error identifiers, not private stack traces.
    throw new Error(/^[a-z0-9_]{1,80}$/.test(code) ? code :
      "تعذر حفظ التغيير المحلي.");
  }
  return output;
}
function renderPlanner(result) {
  if (!result || !result.counts) throw new Error("invalid agenda");
  const counts = result.counts;
  el("planner-today").textContent = "اليوم · " + (counts.today || 0);
  el("planner-overdue").textContent = "متأخر · " + (counts.overdue || 0);
  el("planner-upcoming").textContent = "الأسبوع · " + (counts.upcoming || 0);
  el("planner-unscheduled").textContent = "بدون موعد · " +
    (counts.unscheduled || 0);
}
function taskCard(item,history=false) {
  const article=document.createElement("article");
  article.className="task-card";
  article.append(text("h4",item.title));
  if (item.notes) article.append(text("p",item.notes,"muted"));
  article.append(text("p",
    item.due_at === null || item.due_at === undefined
      ? "بدون موعد محدد" : "الموعد المؤكد · " + taskLocalDate(item.due_at),
    item.due_at && item.due_at < Date.now()/1000 ? "task-overdue":"task-due"));
  if(item.reminder){
    const labels={scheduled:"تم جدولة التنبيه المحلي",
      sent:"تم إرسال التنبيه إلى النظام",missed:"فات وقت التنبيه",
      failed:"التنبيه لم يصل للنظام",cancelled:"التنبيه متوقف",
      attempting:"جارٍ تسليم التنبيه"};
    article.append(text("p",
      (labels[item.reminder.status] || "التذكير") +
      " · " + item.reminder.lead_minutes + " دقيقة قبل الموعد",
      "task-reminder-state"));
  }
  if(item.source_link){
    const link=document.createElement("a");
    link.href=item.source_link;
    link.target="_blank";
    link.rel="noopener noreferrer";
    link.textContent="الرسالة المصدر في Gmail";
    article.append(link);
  }
  const tools=document.createElement("div");
  tools.className="task-card-actions";
  function control(label,handler) {
    const button=document.createElement("button");
    button.type="button";
    button.className="btn-secondary";
    button.textContent=label;
    button.addEventListener("click",handler);
    tools.append(button);
  }
  if(!history){
    control("تم ✓",()=>changeTaskStatus(item.id,"done"));
    control("تعديل",()=>openTaskEditor(item));
    control("استبعاد",()=>changeTaskStatus(item.id,"dismissed"));
  } else {
    control("إعادة فتح",()=>changeTaskStatus(item.id,"open"));
  }
  article.append(tools);
  return article;
}
function renderTasks(result) {
  if (!result || !Array.isArray(result.items))
    throw new Error("invalid local tasks payload");
  const list=el("tasks-list");
  list.replaceChildren();
  el("tasks-count").textContent =
    result.total_in_sample + " مفتوحة · " +
    (result.overdue_in_sample || 0) + " متأخرة";
  el("metric-tasks").textContent=String(result.total_in_sample);
  el("tasks-note").textContent =
    "مهام في SQLite ومواعيدك المؤكدة. تذكير Desktop اختياري؛ لا اتصال بـ Google Calendar.";
  for(const item of result.items) list.append(taskCard(item));
  if(!result.items.length)
    list.append(text("p","لا توجد مهام مفتوحة. أضف مهمة فوق.","muted"));
}
async function changeTaskStatus(id,status) {
  try {
    await taskPost("/api/v1/tasks/transition",{task_id:id,status});
    await load(true);
    if(taskHistoryExpanded) await loadTaskHistory();
  } catch(error) {
    el("tasks-note").textContent = "تعذر تغيير حالة المهمة: " +
      String(error.message).slice(0,85);
  }
}
function openTaskEditor(item) {
  currentEditingTask=item.id;
  el("task-edit-name").value=item.title;
  el("task-edit-notes").value=item.notes || "";
  el("task-edit-due").value=dateInputValue(item.due_at);
  el("task-edit-reminder").value =
    item.reminder?.status==="scheduled"
      ? String(item.reminder.lead_minutes) : "";
  el("task-edit-feedback").textContent="";
  el("task-edit-dialog").showModal();
}
async function loadTaskHistory() {
  try {
    const response=await fetch("/api/v1/tasks/history",{
      credentials:"same-origin",cache:"no-store",
      headers:token?{Authorization:"Bearer "+token}:{}
    });
    if(!response.ok) throw new Error("history_unavailable");
    const data=await response.json();
    const list=el("tasks-history-list");
    list.replaceChildren();
    const past=(data.items || []).filter(item=>item.status!=="open");
    for(const item of past)list.append(taskCard(item,true));
    if(!past.length) list.append(text("p","لا توجد مهام مكتملة أو مستبعدة.","muted"));
  } catch(_) {
    el("tasks-history-list").replaceChildren(text("p",
      "تعذر قراءة سجل المهام.","muted"));
  }
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
  if (el("mail-action-dialog").open) el("mail-action-dialog").close();
  if (el("mail-send-dialog").open) el("mail-send-dialog").close();
  if (el("task-edit-dialog").open) el("task-edit-dialog").close();
  el("tasks-history-list").replaceChildren();
  el("tasks-history-list").hidden=true;
  taskHistoryExpanded=false;
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
    trashPermissionConfigured =
      typeof caps.ui_trash_available === "boolean" ? caps.ui_trash_available : null;
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
      const plannerResponse = await fetch("/api/v1/planner", options);
      if (active !== generation) return;
      if (plannerResponse.ok) renderPlanner(await plannerResponse.json());
    } catch (error) {
      if (active !== generation || error.name === "AbortError") return;
      el("planner-today").textContent="الجدول غير متاح";
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
let pendingMailAction = null;
let currentReplyDraft = null;
let savedReplyBody = "";
let pendingMailSend = null;
const escapeHtml = (value) => String(value || "").replace(/[&<>"']/g,
  (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));

// A single Gmail message can contain a complete <html><head><body> tree.
// Keep in-email styles while avoiding nested document wrappers inside srcdoc.
// Keep the sender's own <html>, <head>, <body> attributes and newsletter
// media-query CSS. Stripping the body/head tags caused fixed-width LinkedIn
// and Alison templates to fall back to raw links, text and broken tables.
// Newsletter lazy image attributes are inert without sender JavaScript.
// Rehydrate ONLY image URLs after explicit consent. Decode the common HTML
// ampersand entity before escaping again: double-escaping &amp; breaks CDN
// signature/query URLs, which can leave newsletters with blank pictures.
function newsletterImageUrl(value) {
  if (!value || value.length > 4096) return null;
  const decoded = value.replace(/&amp;/gi, "&")
    .replace(/&#(?:0*38|x0*26);/gi, "&");
  return /^(?:https?:\/\/|\/\/)[^\s<>"'\x00-\x1f]+$/i.test(decoded)
    ? decoded : null;
}
function newsletterAttr(tag, namePattern) {
  const match = new RegExp("\\s" + namePattern +
    "\\s*=\\s*([\"'])([^\"']{1,4096})\\1", "i").exec(tag);
  return match ? match[2] : null;
}
function setNewsletterAttr(tag, name, value) {
  const safe = escapeHtml(value);
  const pattern = new RegExp("\\s" + name +
    "\\s*=\\s*(?:([\"'])(.*?)\\1|[^\\s>]+)", "i");
  if (pattern.test(tag))
    return tag.replace(pattern, " " + name + '="' + safe + '"');
  return tag.replace(/^<(img|source)\b/i,
    (head) => head + ' ' + name + '="' + safe + '"');
}
function newsletterSrcset(value) {
  if (!value || value.length > 4096) return null;
  const candidates = value.split(",");
  if (!candidates.length || candidates.length > 8) return null;
  const cleaned = [];
  for (const candidate of candidates) {
    const match = /^([^\s]+)(?:\s+([1-9][0-9]{0,4}(?:w|x)))?$/i.exec(candidate.trim());
    if (!match) return null;
    const url = newsletterImageUrl(match[1]);
    if (!url) return null;
    cleaned.push(url + (match[2] ? " " + match[2] : ""));
  }
  return cleaned.join(", ");
}
function enableConsentedLazyImages(html) {
  return html.replace(/<(?:img|source)\b[^>]*>/gi, (original) => {
    let tag = original;
    if (/^<img\b/i.test(tag)) {
      const lazy = newsletterAttr(tag, "data-(?:src|original|lazy-src)");
      const src = newsletterImageUrl(lazy);
      if (src) tag = setNewsletterAttr(tag, "src", src);
    }
    // <picture><source data-srcset> and <img data-srcset> are common in
    // responsive newsletters; a sandboxed no-script viewer cannot activate
    // these itself. Reject non-HTTP, oversized and malformed candidates.
    const deferredSet = newsletterAttr(tag, "data-(?:srcset|lazy-srcset)");
    const srcset = newsletterSrcset(deferredSet);
    if (srcset) tag = setNewsletterAttr(tag, "srcset", srcset);
    return tag;
  });
}

function nativeMailBody(message) {
  const source = message.html || ("<pre>" + escapeHtml(message.text ||
    "محتوى الرسالة غير متوفر بصيغة مقروءة") + "</pre>");
  // Do not allow meta refresh or <base> to navigate/redirect the untrusted
  // document. Sandbox and CSP also disallow script, form and top navigation.
  return source
    .replace(/<base\b[^>]*>/gi, "")
    .replace(/<meta\b(?=[^>]*\bhttp-equiv\s*=\s*["']?refresh\b)[^>]*>/gi, "");
}

function viewerDocument(message) {
  // Remote images are a per-message opt-in. The original HTML stays inside
  // an opaque-origin, no-script iframe, never inserted in the parent DOM.
  const imagePolicy = "data: https: http:";
  const csp = "default-src 'none'; script-src 'none'; connect-src 'none'; " +
    "font-src data:; media-src data:; img-src " + imagePolicy + "; " +
    "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none';";
  const securityHead = '<meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<meta http-equiv="Content-Security-Policy" content="' + escapeHtml(csp) + '">' +
    '<meta name="referrer" content="no-referrer"><style>' +
    'html{max-width:100%;overflow-x:auto}body{max-width:100%;box-sizing:border-box;' +
    'overflow-wrap:break-word}img{max-width:100%!important}' +
    'table{max-width:100%}td,th{overflow-wrap:break-word}' +
    'pre{white-space:pre-wrap;overflow-wrap:anywhere}' +
    '@media(max-width:600px){body{margin:0!important;padding:8px!important}}' +
    '</style>';
  const original = enableConsentedLazyImages(nativeMailBody(message));
  // Full email document: insert CSP BEFORE any sender-owned tags/resources,
  // preserving sender's head styles, body bgcolor and table layout.
  if (/<html\b/i.test(original)) {
    const html = original.replace(/<!doctype[^>]*>/gi, "");
    let withCsp;
    if (/<head\b/i.test(html)) {
      withCsp = html.replace(/<head\b[^>]*>/i, (head) => head + securityHead);
    } else {
      withCsp = html.replace(/<html\b[^>]*>/i,
        (head) => head + "<head>" + securityHead + "</head>");
    }
    return "<!doctype html>" + withCsp;
  }
  // Templates with a body root keep all sender-owned body attributes.
  if (/<body\b/i.test(original))
    return "<!doctype html><html><head>" + securityHead +
      "</head>" + original + "</html>";
  return "<!doctype html><html><head>" + securityHead +
    "</head><body>" + original + "</body></html>";
}

let viewerFocus = false;
function setViewerFocus(value) {
  viewerFocus = Boolean(value);
  if (viewerFocus) el("mail-viewer").classList.add("reader-focus");
  else el("mail-viewer").classList.remove("reader-focus");
  el("viewer-focus-toggle").textContent = viewerFocus
    ? "الرجوع للتفاصيل" : "توسيع القراءة";
  el("viewer-focus-toggle").setAttribute("aria-pressed", String(viewerFocus));
}
function imageDisplayStatus(message, pending=false) {
  const internal = Number(message.inline_images) || 0;
  const skipped = Number(message.skipped_inline_images) || 0;
  const parts = [];
  if (internal) parts.push("صور داخلية: " + internal);
  if (skipped) parts.push(skipped + " صورة داخلية كبيرة لم تُحمّل؛ افتحها في Gmail");
  parts.push("الصور الخارجية مفعّلة تلقائيًا عند فتح الرسالة (قد يتم تتبع فتح البريد)");
  if (message.external_images_detected === true)
    parts.push("ظهور الصور يعتمد على مصدرها وإعدادات Firefox");
  if (pending) parts.push("جارٍ عرض محتوى الرسالة...");
  return parts.join(" · ");
}
function refreshViewerDocument() {
  if (!currentViewerMessage) return;
  el("viewer-image-status").textContent = imageDisplayStatus(currentViewerMessage, true);
  // Remote image requests happen only inside the opened, script-disabled iframe.
  el("viewer-frame").srcdoc = viewerDocument(currentViewerMessage);
}
el("viewer-frame").addEventListener("load", () => {
  if (!currentViewerMessage || !el("mail-viewer").open) return;
  el("viewer-image-status").textContent = imageDisplayStatus(currentViewerMessage);
});
el("viewer-focus-toggle").addEventListener("click", () => {
  setViewerFocus(!viewerFocus);
});

async function openMailViewer(item) {
  const id = typeof item === "string" ? item : item?.id;
  if (!/^[a-fA-F0-9]{1,64}$/.test(String(id || ""))) return;
  viewerItem = typeof item === "object" ? item : null;
  el("viewer-ai-summary").textContent = "جارٍ جلب التلخيص المحفوظ...";
  el("viewer-ai-action").textContent = "";
  el("viewer-category").textContent = "";
  el("viewer-action-note").textContent = "";
  for (const name of ["viewer-copy-summary","viewer-select","viewer-delete",
                      "viewer-mark-read","viewer-mark-unread","viewer-archive",
                      "viewer-create-task","viewer-reply-generate"])
    el(name).disabled = true;
  currentReplyDraft = null;
  savedReplyBody = "";
  el("viewer-reply-send").disabled = true;
  el("viewer-reply-body").value = "";
  el("viewer-reply-to").textContent = "";
  el("viewer-reply-state").textContent = "";
  el("viewer-reply-copy").disabled = true;
  el("viewer-reply-save").disabled = true;
  el("viewer-title").textContent = "جارٍ تحميل الرسالة الأصلية...";
  el("viewer-from").textContent = "";
  el("viewer-to").textContent = "";
  el("viewer-date").textContent = "";
  el("viewer-frame").srcdoc = "";
  el("viewer-attachments").replaceChildren();
  el("viewer-note").textContent = "بنقرأ Gmail مباشرة عند الطلب؛ مش ملخص AI.";
  el("viewer-image-status").textContent =
    "صور الرسالة الخارجية تُحمّل تلقائيًا؛ قد يتعرّف المرسل على فتح البريد.";
  setViewerFocus(false);
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
    // Viewing marks messages locally Seen and removes their Smart Inbox rows.
    // Native reader Trash eligibility must NOT depend on informationRows.
    const selectable = informationRows.has(id);
    el("viewer-select").disabled = !selectable;
    const nativeLabels = Array.isArray(data.labels) ? data.labels : [];
    const protectedLabels = ["TRASH","DRAFT","SENT","SPAM","STARRED","IMPORTANT"];
    const canTrash = nativeLabels.includes("INBOX") &&
      !nativeLabels.some(label => protectedLabels.includes(label));
    el("viewer-delete").disabled = !canTrash || trashPermissionConfigured === false;
    const writable = trashPermissionConfigured !== false &&
      !nativeLabels.some(label => ["TRASH","DRAFT","SENT","SPAM"].includes(label));
    el("viewer-mark-read").disabled = !writable || !nativeLabels.includes("UNREAD");
    el("viewer-mark-unread").disabled = !writable || nativeLabels.includes("UNREAD");
    el("viewer-archive").disabled = !writable || !nativeLabels.includes("INBOX");
    el("viewer-create-task").disabled = data.ai_category === "manual_review";
    el("viewer-reply-generate").disabled = data.ai_category === "manual_review";
    if (!canTrash)
      el("viewer-action-note").textContent =
        "الرسالة محمية أو خارج Inbox ولا يمكن نقلها إلى Trash من OKAL.";
    el("viewer-title").textContent = data.subject || "بدون عنوان";
    el("viewer-from").textContent = data.from || "غير معروف";
    el("viewer-to").textContent = data.to || "غير معروف";
    el("viewer-date").textContent = data.date || "غير معروف";
    el("viewer-gmail").href = data.gmail_link;
    el("viewer-note").textContent = "محتوى Gmail الأصلي داخل إطار معزول بلا سكربتات. " +
      "الصور الخارجية مفعّلة تلقائيًا وفق اختيارك، وقد تُبلغ المرسل بفتح البريد.";
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
    // Images are enabled on every message, independent of old SQLite prefs.
    refreshViewerDocument();
    // Mark local Viewed only after original Gmail was read successfully.
    // This is a local-only operation; Gmail labels remain unchanged.
    try {
      const seenResponse = await fetch("/api/v1/mail/viewed", {
        method:"POST",credentials:"same-origin",cache:"no-store",
        headers:{"Content-Type":"application/json",
                 ...(token?{Authorization:"Bearer "+token}:{})},
        body:JSON.stringify({message_id:id})
      });
      if (seenResponse.ok && requestGeneration === viewerGeneration) {
        viewedThisSession.add(id);
        if (lastTriageResult) renderTriage(lastTriageResult);
        if (lastAssistantResult) renderAssistant(lastAssistantResult);
      } else if (!seenResponse.ok)
        el("viewer-action-note").textContent =
          "الرسالة اتفتحت لكن لم تُحفظ علامة Viewed؛ راجع حالة OKAL.";
    } catch (_) {
      if (requestGeneration === viewerGeneration)
        el("viewer-action-note").textContent =
          "تعذر حفظ Viewed محليًا؛ الرسالة ستظل ظاهرة حتى مزامنة القراءة.";
    }
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
  for (const name of ["viewer-copy-summary","viewer-select","viewer-delete",
                      "viewer-mark-read","viewer-mark-unread","viewer-archive",
                      "viewer-create-task","viewer-reply-generate",
                      "viewer-reply-save","viewer-reply-copy"])
    el(name).disabled = true;
  currentReplyDraft = null;
  savedReplyBody = "";
  el("viewer-reply-send").disabled = true;
  el("viewer-reply-body").value = "";
  el("viewer-reply-to").textContent = "";
  el("viewer-reply-state").textContent = "";
  for (const id of ["viewer-from","viewer-to","viewer-date","viewer-note"])
    el(id).textContent = "";
  el("viewer-attachments").replaceChildren();
  el("viewer-frame").srcdoc = "";
  el("viewer-image-status").textContent = "";

  setViewerFocus(false);
});
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
  if (!/^[a-fA-F0-9]{1,64}$/.test(String(id || "")) ||
      el("viewer-delete").disabled) return;
  // Same native Gmail preview + single-use confirmation as bulk Trash.
  // Works after opening this message removes its Smart Inbox card.
  await showTrashPreview([id]);
});


// Privileged Gmail operations always start from an explicit user click.
// The native preview is read-only; a separate confirmation button executes
// a one-time, exact-selection, digest-bound action. Never auto-retry writes.
const actionNames = {mark_read:"Mark as read",mark_unread:"Mark as unread",
  archive:"Archive from Inbox"};
async function fetchMailAgent(url, payload) {
  const response = await fetch(url, {
    method:"POST", credentials:"same-origin",cache:"no-store",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(payload)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const code = typeof data.detail === "string" &&
      /^[a-z][a-z0-9_]{1,100}$/.test(data.detail) ? data.detail : "";
    if (code === "mail_operation_already_running")
      throw new Error("المزامنة مشغولة حاليًا. أعد المحاولة بعد اكتمالها.");
    if (code === "gmail_modify_scope_required" ||
        code === "scope_or_send_permission_mismatch")
      throw new Error("صلاحية gmail.modify غير متاحة؛ راجع تفويض Google.");
    if (code === "action_already_attempted_review_gmail")
      throw new Error("العملية دي لها محاولة سابقة. راجع Gmail يدويًا قبل أي إعادة محاولة.");
    if (code === "mail_action_confirmation_expired")
      throw new Error("انتهت صلاحية التأكيد. افتح المعاينة مجددًا.");
    if (code === "send_needs_reconciliation_do_not_resend" ||
        code === "send_still_uncertain_manual_native_review_required")
      throw new Error("نتيجة إرسال Gmail غير مؤكدة؛ لا ترسل نسخة ثانية قبل مراجعة Sent.");
    if (code === "mail_send_confirmation_expired")
      throw new Error("انتهت صلاحية الموافقة على الإرسال؛ راجع المسودة من جديد.");
    if (code === "action_write_uncertain_check_gmail_no_auto_retry")
      throw new Error("تعديل Gmail غير مؤكد. راجع البريد يدويًا قبل أي إجراء جديد.");
    throw new Error("تعذر تنفيذ العملية (" + (code || "HTTP " + response.status) + ")");
  }
  return data;
}

async function showMailActionPreview(action) {
  const id = currentViewerMessage?.id;
  if (!id || !actionNames[action] || trashPermissionConfigured === false) {
    el("viewer-action-note").textContent =
      "Gmail modify غير مفعّل أو الرسالة غير متاحة للتعديل.";
    return;
  }
  el("viewer-action-note").textContent = "جارٍ قراءة حالة Gmail للمراجعة...";
  try {
    const data = await fetchMailAgent("/api/v1/mail/actions/preview",
      {ids:[id],action});
    if (data.action !== action || data.count !== 1 ||
        !/^[a-f0-9]{64}$/.test(data.approval_digest) ||
        typeof data.confirmation_token !== "string") throw new Error("معاينة غير صالحة");
    pendingMailAction = {
      ids:[id], action, digest:data.approval_digest,
      ticket:data.confirmation_token
    };
    el("mail-action-title").textContent = actionNames[action];
    el("mail-action-preview-list").replaceChildren();
    for (const item of data.items)
      el("mail-action-preview-list").append(
        text("p", item.subject + " · " + item.labels.join(", "))
      );
    el("mail-action-result").textContent = "";
    el("mail-action-dialog").showModal();
    el("viewer-action-note").textContent = "راجع النافذة ثم أكد الإجراء.";
  } catch (error) {
    el("viewer-action-note").textContent = String(error.message).slice(0,220);
  }
}
for (const [button,action] of [
  ["viewer-mark-read","mark_read"],
  ["viewer-mark-unread","mark_unread"],
  ["viewer-archive","archive"]
]) el(button).addEventListener("click", () => showMailActionPreview(action));
el("mail-action-cancel").addEventListener("click", () =>
  el("mail-action-dialog").close());
el("mail-action-dialog").addEventListener("close", () => {
  pendingMailAction = null;
});
el("mail-action-confirm").addEventListener("click", async () => {
  if (!pendingMailAction) return;
  const chosen = pendingMailAction;
  // Cancel the local ticket on close, including ambiguous network outcomes.
  pendingMailAction = null;
  el("mail-action-confirm").disabled = true;
  el("mail-action-result").textContent = "جارٍ التحقق والتنفيذ في Gmail...";
  try {
    const result = await fetchMailAgent("/api/v1/mail/actions/commit",{
      ids:chosen.ids, action:chosen.action,
      approval_digest:chosen.digest,confirmation_token:chosen.ticket,
      confirmed:true
    });
    if (result.status !== "confirmed") throw new Error("رد Gmail غير مؤكد");
    el("mail-action-result").textContent = "تم تنفيذ " + actionNames[chosen.action] + " بنجاح.";
    if (currentViewerMessage && currentViewerMessage.id === chosen.ids[0]) {
      const labels = new Set(currentViewerMessage.labels || []);
      if (chosen.action === "mark_read") labels.delete("UNREAD");
      if (chosen.action === "mark_unread") labels.add("UNREAD");
      if (chosen.action === "archive") labels.delete("INBOX");
      currentViewerMessage.labels = [...labels];
      const writable = trashPermissionConfigured !== false;
      el("viewer-mark-read").disabled = !writable || !labels.has("UNREAD");
      el("viewer-mark-unread").disabled = !writable || labels.has("UNREAD");
      el("viewer-archive").disabled = !writable || !labels.has("INBOX");
    }
    if (chosen.action === "mark_unread") {
      viewedThisSession.delete(chosen.ids[0]);
    }
    if (chosen.action === "archive") {
      el("mail-action-dialog").close();
      if (el("mail-viewer").open) el("mail-viewer").close();
      load(true);
    }
  } catch (error) {
    el("mail-action-result").textContent = String(error.message).slice(0,220);
  } finally {
    el("mail-action-confirm").disabled = false;
  }
});

el("viewer-create-task").addEventListener("click", async () => {
  if (!currentViewerMessage) return;
  el("viewer-create-task").disabled = true;
  try {
    const due = taskDueIso("viewer-task-due");
    const reminder_minutes = reminderChoice("viewer-task-reminder",due!==null);
    const result = await fetchMailAgent("/api/v1/mail/tasks/from-message",{
      message_id:currentViewerMessage.id,due,reminder_minutes
    });
    el("viewer-action-note").textContent = result.status === "already_recorded"
      ? "المهمة مسجلة بالفعل في OKAL." : "تم إنشاء Task محلي من الرسالة.";
    load(true);
  } catch (error) {
    el("viewer-action-note").textContent = String(error.message).slice(0,200);
  } finally {
    el("viewer-create-task").disabled = false;
  }
});
el("viewer-reply-generate").addEventListener("click", async () => {
  if (!currentViewerMessage) return;
  el("viewer-reply-generate").disabled = true;
  el("viewer-reply-state").textContent = "جارٍ إنشاء مسودة على Ollama المحلي...";
  try {
    const draft = await fetchMailAgent("/api/v1/mail/reply-drafts/generate",{
      message_id: currentViewerMessage.id,
      language:el("viewer-reply-language").value || "ar"
    });
    currentReplyDraft = draft.draft_id;
    savedReplyBody = draft.body;
    el("viewer-reply-send").disabled = false;
    el("viewer-reply-to").textContent =
      "To: " + draft.recipient + " · Subject: " + draft.subject;
    el("viewer-reply-body").value = draft.body;
    el("viewer-reply-save").disabled = false;
    el("viewer-reply-copy").disabled = false;
    el("viewer-reply-state").textContent = "مسودة محفوظة محليًا — لم يتم إرسالها.";
  } catch (error) {
    el("viewer-reply-state").textContent = String(error.message).slice(0,220);
  } finally {
    el("viewer-reply-generate").disabled = false;
  }
});
el("viewer-reply-save").addEventListener("click", async () => {
  if (!currentReplyDraft) return;
  el("viewer-reply-save").disabled = true;
  try {
    const result = await fetchMailAgent("/api/v1/mail/reply-drafts/revise",{
      draft_id:currentReplyDraft,body:el("viewer-reply-body").value
    });
    currentReplyDraft = result.draft_id;
    savedReplyBody = el("viewer-reply-body").value;
    el("viewer-reply-send").disabled = false;
    el("viewer-reply-state").textContent =
      "تم حفظ مسودة جديدة محليًا؛ لا إرسال تلقائي.";
  } catch (error) {
    el("viewer-reply-state").textContent = String(error.message).slice(0,200);
  } finally {
    el("viewer-reply-save").disabled = false;
  }
});
el("viewer-reply-send").addEventListener("click", async () => {
  if (!currentReplyDraft) return;
  if (el("viewer-reply-body").value !== savedReplyBody) {
    el("viewer-reply-state").textContent =
      "النص اتعدل. احفظ التعديل محليًا أولًا قبل مراجعة الإرسال.";
    return;
  }
  el("viewer-reply-state").textContent = "جارٍ تجهيز معاينة الإرسال...";
  try {
    const draft = await fetchMailAgent(
      "/api/v1/mail/reply-drafts/preview-send",
      {draft_id:currentReplyDraft}
    );
    if (draft.draft_id !== currentReplyDraft ||
        draft.body !== savedReplyBody ||
        !/^[a-f0-9]{64}$/.test(draft.approval_digest) ||
        typeof draft.confirmation_token !== "string")
      throw new Error("مسودة الإرسال مختلفة عن النص المراجع.");
    pendingMailSend = {draft_id:draft.draft_id,
      digest:draft.approval_digest,ticket:draft.confirmation_token};
    el("mail-send-to").textContent = draft.recipient;
    el("mail-send-subject").textContent = draft.subject;
    el("mail-send-body").textContent = draft.body;
    el("mail-send-result").textContent = "";
    el("mail-send-dialog").showModal();
    el("viewer-reply-state").textContent =
      "راجع المستلم والنص بعناية قبل تأكيد الإرسال.";
  } catch (error) {
    el("viewer-reply-state").textContent = String(error.message).slice(0,240);
  }
});
el("mail-send-cancel").addEventListener("click", () =>
  el("mail-send-dialog").close());
el("mail-send-dialog").addEventListener("close", () => {
  pendingMailSend = null;
});
el("mail-send-confirm").addEventListener("click", async () => {
  if (!pendingMailSend) return;
  const approval = pendingMailSend;
  pendingMailSend = null;
  el("mail-send-confirm").disabled = true;
  el("mail-send-result").textContent = "جارٍ الإرسال والتحقق من Gmail...";
  try {
    const result = await fetchMailAgent(
      "/api/v1/mail/reply-drafts/confirm-send",{
        draft_id:approval.draft_id,
        approval_digest:approval.digest,
        confirmation_token:approval.ticket,confirmed:true
      });
    if (result.status !== "sent_verified")
      throw new Error("نتيجة الإرسال غير مؤكدة. راجع Gmail Sent.");
    el("mail-send-result").textContent = "تم الإرسال والتحقق من Gmail.";
    el("viewer-reply-state").textContent =
      "تم إرسال الرد فعليًا بعد موافقتك والتحقق من Gmail.";
    el("viewer-reply-send").disabled = true;
    el("viewer-reply-save").disabled = true;
    currentReplyDraft = null;
  } catch (error) {
    el("mail-send-result").textContent =
      "لا تكرر الإرسال تلقائيًا. راجع Gmail Sent ثم سجل المسودة. " +
      String(error.message).slice(0,160);
  } finally {
    el("mail-send-confirm").disabled = true;
  }
});

el("viewer-reply-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(el("viewer-reply-body").value);
    el("viewer-reply-state").textContent = "تم نسخ نص الرد؛ لم يتم إرساله.";
  } catch (_) {
    el("viewer-reply-state").textContent = "استخدم تحديد النص وCtrl+C.";
  }
});

// Task Board forms only write the owner-approved local SQLite database.
el("task-create-form").addEventListener("submit",async (event)=>{
  event.preventDefault();
  el("task-create-submit").disabled=true;
  try {
    const due=taskDueIso("task-new-due");
    const reminder_minutes=reminderChoice("task-new-reminder",due!==null);
    const result=await taskPost("/api/v1/tasks/create",{
      title:el("task-new-title").value,notes:el("task-new-notes").value,
      due,reminder_minutes
    });
    if(result.status!=="open")throw new Error("task_creation_unconfirmed");
    el("task-create-feedback").textContent="تم حفظ المهمة في OKAL.";
    el("task-new-title").value="";
    el("task-new-notes").value="";
    el("task-new-due").value="";
    el("task-new-reminder").value="";
    await load(true);
  } catch(error) {
    el("task-create-feedback").textContent=String(error.message).slice(0,120);
  } finally {
    el("task-create-submit").disabled=false;
  }
});
el("task-edit-close").addEventListener("click",()=>el("task-edit-dialog").close());
el("task-edit-dialog").addEventListener("close",()=>{currentEditingTask=null;});
el("task-edit-form").addEventListener("submit",async (event)=>{
  event.preventDefault();
  if(!currentEditingTask)return;
  el("task-edit-save").disabled=true;
  try {
    const due=taskDueIso("task-edit-due");
    const reminder_minutes=reminderChoice("task-edit-reminder",due!==null);
    const result=await taskPost("/api/v1/tasks/edit",{
      task_id:currentEditingTask,
      title:el("task-edit-name").value,notes:el("task-edit-notes").value,
      due,reminder_minutes
    });
    if(result.updated!==true)throw new Error("task_update_unconfirmed");
    el("task-edit-dialog").close();
    await load(true);
  } catch(error) {
    el("task-edit-feedback").textContent=String(error.message).slice(0,130);
  } finally {el("task-edit-save").disabled=false;}
});
el("tasks-history-toggle").addEventListener("click",async ()=>{
  taskHistoryExpanded=!taskHistoryExpanded;
  el("tasks-history-list").hidden=!taskHistoryExpanded;
  el("tasks-history-toggle").textContent=taskHistoryExpanded
    ? "إخفاء سجل المهام" : "عرض المكتملة والمستبعدة";
  if(taskHistoryExpanded)await loadTaskHistory();
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
    const needsGooglePermission = trashPermissionConfigured === false;
    el("trash-confirm").disabled = needsGooglePermission;
    el("trash-result").textContent = needsGooglePermission
      ? "صلاحية الحذف في Gmail غير مفعّلة. وافق على gmail.modify مرة واحدة باستخدام mail authorize --enable-trash، ثم حدّث OKAL."
      : "";
    el("trash-dialog").showModal();
    el("trash-help").textContent = needsGooglePermission
      ? "المعاينة متاحة، لكن النقل محتاج موافقة Google على صلاحية gmail.modify."
      : "راجع كل العناوين، واضغط تأكيد للنقل الفعلي إلى Trash. بدون PIN.";
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
  if (trashPermissionConfigured === false) {
    el("trash-result").textContent =
      "لازم تفعل Gmail modify من إعداد OAuth قبل النقل. لا توجد أي رسالة حُذفت.";
    return;
  }
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
    const movedIds = approvedTrash.ids;
    el("trash-dialog").close();
    if (el("mail-viewer").open && currentViewerMessage &&
        movedIds.includes(currentViewerMessage.id))
      el("mail-viewer").close();
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
    el("trash-confirm").disabled = trashPermissionConfigured === false;
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
