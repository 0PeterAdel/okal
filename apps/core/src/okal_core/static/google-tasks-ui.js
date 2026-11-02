"use strict";
// Google Tasks date-only snapshot viewer: never invent an exact clock time.
let googleTasksSnapshot = null;
let googleTasksRequest = 0;
function resetGoogleTasksView() {
  googleTasksSnapshot = null;
  googleTasksRequest++;
  el("google-tasks-items").replaceChildren();
  el("google-tasks-state").textContent = "بيانات Google Tasks غير محملة.";
}
function renderGoogleTasksDay(date) {
  const root = el("google-tasks-items");
  root.replaceChildren();
  if (!googleTasksSnapshot) return;
  const rows = googleTasksSnapshot.items.filter(item=>
    item.scheduled_day === date);
  for (const item of rows.slice(0,30)) {
    const entry = document.createElement("article");
    entry.className = "calendar-focus-entry";
    entry.append(text("p","Google Tasks · يوم "+item.scheduled_day+
      " · بدون ساعة محددة"),text("h5",item.title));
    root.append(entry);
  }
  if (!rows.length) root.append(text("p",
    "لا توجد Google Tasks محفوظة لهذا اليوم؛ قد تكون البيانات ناقصة.","muted"));
}
async function loadGoogleTasksSnapshot(options, active) {
  const seq = ++googleTasksRequest;
  try {
    const response = await fetch("/api/v1/google-tasks/cached",options);
    if (!response.ok) throw Error("cached_source_unavailable");
    const payload = await response.json();
    if (active!==generation || seq!==googleTasksRequest) return;
    if (!Array.isArray(payload.items) || payload.date_only!==true)
      throw Error("invalid_tasks_snapshot");
    googleTasksSnapshot=payload;
    el("google-tasks-state").textContent = payload.connected
      ? "مهام Google محفوظة للقراءة فقط؛ اليوم وليس وقتًا أو Deadline. لا يوجد مزامنة حية في هذا العرض."
      : "Google Tasks غير مربوط بعد. اربطه من قسم Integrations.";
    renderGoogleTasksDay(calendarFocusedDate);
  } catch (_) {
    if (active!==generation || seq!==googleTasksRequest) return;
    resetGoogleTasksView();
    el("google-tasks-state").textContent =
      "تعذر قراءة مهام Google المحفوظة؛ لا تفترض خلو اليوم.";
  }
}
async function loadTasksGoogleStatus() {
  const status=el("google-tasks-connect-state");
  const button=el("google-tasks-connect");
  if (!status || !button) return;
  try {
    const response=await fetch("/api/v1/google-tasks/status",{
      credentials:"same-origin",cache:"no-store",
      headers:token?{Authorization:"Bearer "+token}:{}
    });
    if (!response.ok) throw Error("unavailable");
    const data=await response.json();
    const sync=data.sync;
    status.textContent=sync.authorization==="cached"
      ? "Read-only · آخر مزامنة محفوظة · "+sync.task_count+" مهمة"
      : sync.authorization==="configured_not_verified"
      ? "تم التفويض؛ المزامنة الأولى لم تتأكد"
      : "غير مربوط · نحتاج موافقة Google Tasks منفصلة";
    button.disabled = !data.oauth_client_ready;
    button.textContent=sync.authorization==="cached"?"إعادة تفويض Tasks":"ربط Google Tasks";
  } catch (_) {
    status.textContent="تعذر فحص حالة Tasks";
    button.disabled=true;
  }
}
async function connectGoogleTasks() {
  const button=el("google-tasks-connect");
  button.disabled=true;
  try {
    const response=await fetch("/api/v1/google-tasks/oauth/start",{
      method:"POST",credentials:"same-origin",cache:"no-store",
      headers:{"Content-Type":"application/json",
        ...(token?{Authorization:"Bearer "+token}:{})},
      body:"{}"
    });
    if (!response.ok) throw Error("unavailable");
    const data=await response.json();
    const url=new URL(data.authorization_url);
    if (url.protocol!=="https:" || url.hostname!=="accounts.google.com")
      throw Error("untrusted_target");
    window.location.assign(url.href);
  } catch (_) {
    button.disabled=false;
    el("google-tasks-connect-state").textContent=
      "تعذر ربط Google Tasks؛ تأكد من OAuth Desktop client واتصال الإنترنت.";
  }
}
el("google-tasks-connect").addEventListener("click",connectGoogleTasks);
window.addEventListener("DOMContentLoaded",loadTasksGoogleStatus);
