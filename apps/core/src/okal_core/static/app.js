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

function updateTrashSelection() {
  el("trash-count").textContent =
    `${selectedInfo.size} محدد من Information · آخر خطوة تتطلب موافقتك في Terminal`;
  el("trash-selected").disabled = selectedInfo.size === 0;
  el("trash-command").hidden = true;
  el("trash-command").textContent = "";
}


function resetMailStatus() {
  selectedInfo.clear();
  updateTrashSelection();
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

function renderTriage(result) {
  if (!result || !Array.isArray(result.items)) throw new Error("invalid triage payload");
  const groups = el("triage-groups");
  groups.replaceChildren();
  selectedInfo.clear();
  updateTrashSelection();
  const categories = [
    ["manual_review", "00", "مراجعة يدوية", "Manual review"],
    ["action", "01", "يحتاج إجراء", "Action required"],
    ["information", "02", "للاطلاع", "Information"],
    ["low_priority", "03", "لاحقًا", "Low priority"],
  ];
  const counts = categories.map(([key]) => result.items.filter((item) => item.category === key).length);
  el("triage-count").textContent = `${result.items.length} رسالة مرصودة · ${counts[0]} للمراجعة اليدوية · ${counts[1]} تحتاج متابعة`;
  el("triage-note").textContent = "الترتيب اقتراح AI محلي، وليس دليلًا على أهمية الرسالة أو صحتها. افتح Gmail للتحقق قبل أي قرار.";
  for (let index = 0; index < categories.length; index += 1) {
    const [key, number, arabic, english] = categories[index];
    const items = result.items.filter((item) => item.category === key);
    if (!items.length) continue;
    const column = document.createElement("section");
    column.className = `triage-column triage-${key}`;
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
      if (item.suggested_action) {
        article.append(text("p", `Next step · ${item.suggested_action}`, "triage-action"));
      }
      if (item.has_unread_attachments) {
        article.append(text("p", "مرفقات لم تُحلَّل · Attachments not reviewed", "triage-warning"));
      }
      const link = document.createElement("a");
      link.textContent = "فتح الرسالة الأصلية في Gmail";
      link.href = item.link;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      article.append(link);
      if (key === "information" && typeof item.id === "string" &&
          /^[a-fA-F0-9]{1,64}$/.test(item.id) &&
          !((item.labels || []).some((v) =>
            ["SENT", "DRAFT", "SPAM", "TRASH", "STARRED", "IMPORTANT"].includes(v)))) {
        const selection = document.createElement("label");
        selection.className = "trash-selector";
        const check = document.createElement("input");
        check.type = "checkbox";
        check.checked = false;
        check.addEventListener("change", () => {
          if (check.checked) {
            if (selectedInfo.size >= 20) {
              check.checked = false;
              el("trash-help").textContent = "20 رسالة كحد أقصى في كل طلب.";
              return;
            }
            selectedInfo.add(item.id);
          } else {
            selectedInfo.delete(item.id);
          }
          updateTrashSelection();
        });
        selection.append(check, text("span", "اختيار لنقلها إلى Trash"));
        article.append(selection);
      }
      column.append(article);
    }
    groups.append(column);
  }
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
el("trash-selected").addEventListener("click", async () => {
  const ids = [...selectedInfo].filter((mid) => /^[a-fA-F0-9]{1,64}$/.test(mid));
  if (!ids.length || ids.length > 20) return;
  const command =
    "bash scripts/run-okal-core.sh mail trash --ids " + ids.join(" ");
  el("trash-command").hidden = false;
  el("trash-command").textContent = command;
  el("trash-help").textContent =
    "الأمر مجرد معاينة. انسخه للـ Terminal ثم راجع العناوين. للتنفيذ أضف --apply ووافِق على كل الرسائل. لا حذف من المتصفح.";
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(command);
      el("trash-count").textContent = "تم نسخ أمر المعاينة فقط · راجعه محليًا";
    } catch (_) {
      // Command is displayed for manual copy; don't claim clipboard success.
    }
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
