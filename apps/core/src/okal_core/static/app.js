"use strict";
// Read-only shell. Tokens and reports stay in memory, never browser storage.
const el = (id) => document.getElementById(id);
let token = "";
let cursor = null;
let controller = null;
let generation = 0;
let busy = false;

function resetMailStatus() {
  el("mail-status").textContent = "افتح الصندوق لعرض الحالة";
  el("integration-status").textContent =
    "افتح الصندوق لعرض حالة البريد المسجلة محليًا. لا يتم فحص Google أو تشغيل الموديل بمجرد فتح الصفحة.";
  el("sync").textContent = "لم يتم التحديث بعد";
  el("triage-groups").replaceChildren();
  el("triage-count").textContent = "لا توجد بيانات بعد";
  el("triage-note").textContent = "الواجهة تعرض نتائج محفوظة فقط؛ لا تُنفّذ أفعالًا على Gmail.";
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
    if (sync?.last_error) parts.push("آخر فحص فشل؛ التقدم السابق محفوظ ولم نفترض التعافي.");
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
  const categories = [
    ["action", "01", "يحتاج إجراء", "Action required"],
    ["information", "02", "للإطلاع", "Information"],
    ["low_priority", "03", "لاحقًا", "Low priority"],
  ];
  const counts = categories.map(([key]) => result.items.filter((item) => item.category === key).length);
  el("triage-count").textContent = `${result.items.length} رسالة تم تحليلها سابقًا · ${counts[0]} تحتاج متابعة`;
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
      column.append(article);
    }
    groups.append(column);
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
  el("login-panel").hidden = false;
  el("connection").textContent = "غير متصل";
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
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      credentials: "omit",
      signal: controller.signal,
    };
    const [response, capsResponse] = await Promise.all([
      fetch(`/api/v1/summaries?${query}`, options),
      fetch("/api/v1/capabilities", options),
    ]);
    if (active !== generation) return;
    if (response.status === 401 || capsResponse.status === 401) {
      lock();
      el("message").textContent =
        "المفتاح غير صالح أو انتهت مدته أو تم إلغاؤه. أنشئ مفتاحًا محليًا جديدًا.";
      return;
    }
    if (!response.ok || !capsResponse.ok) throw new Error("read failed");
    const [result, caps] = await Promise.all([response.json(), capsResponse.json()]);
    if (active !== generation) return;
    renderMailStatus(caps.mail);
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
    if (reset) el("items").replaceChildren();
    for (const item of result.items) el("items").append(card(item));
    cursor = result.next_cursor;
    el("more").hidden = !cursor;
    el("empty").hidden = el("items").childElementCount !== 0;
    el("sync").textContent =
      `آخر قراءة للملخصات المحفوظة: ${new Date(result.fetched_at * 1000).toLocaleString("ar-EG")} · زر التحديث لا يجلب بريدًا جديدًا من Gmail`;
    el("inbox-panel").hidden = false;
    el("login-panel").hidden = true;
    el("connection").textContent = "متصل · قراءة فقط";
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

el("login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (busy) return;
  token = el("token").value.trim();
  el("token").value = "";
  load(true);
});
el("refresh").addEventListener("click", () => load(true));
el("more").addEventListener("click", () => load(false));
el("logout").addEventListener("click", () => {
  lock();
  el("message").textContent = "تم قفل الصندوق ومسح بيانات الصفحة.";
});
window.addEventListener("pagehide", lock);
