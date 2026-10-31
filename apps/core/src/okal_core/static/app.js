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
  parts.push(mail.daily_at
    ? `الجدولة مفعّلة في الإعداد: ${mail.daily_at} (${mail.timezone})؛ هذا ليس إثباتًا لتشغيل العامل.`
    : "الجدولة متوقفة في الإعداد.");
  parts.push(mail.local_send_enabled
    ? "بوابة الإرسال المحلي مفعّلة في الإعداد؛ صلاحية Google لم تُفحص، والإرسال يتطلب مراجعة من سطر الأوامر."
    : "الإرسال المحلي مقفول في الإعداد.");
  el("integration-status").textContent = parts.join(" ");
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
