"use strict";
let localEdit = null;
let localRequestId = null;
function resetLocalCalendarView() {
  newLocalCommitment();
  el("local-calendar-items").replaceChildren();
  el("morning-details").replaceChildren();
  el("local-feedback").textContent = "";
}
function localKindFields() {
  const event = el("local-kind").value === "event";
  el("local-event-fields").hidden = !event;
  el("local-goal-fields").hidden = event;
  el("local-start").required = event;
  el("local-end").required = event;
}
function newLocalCommitment() {
  localEdit = null;
  localRequestId = null;
  el("local-calendar-form").reset();
  localKindFields();
  el("local-save").textContent = "حفظ في OKAL";
}
function editLocalCommitment(item) {
  localEdit = item;
  el("local-kind").value = item.kind;
  el("local-title").value = item.title;
  el("local-notes").value = item.notes;
  el("local-start").value = dateInputValue(item.start_ts);
  el("local-end").value = dateInputValue(item.end_ts);
  el("local-target").value = item.target_date || "";
  el("local-reminder").value = item.reminder_minutes === null ? "" : String(item.reminder_minutes);
  el("local-save").textContent = "حفظ التعديل";
  localKindFields();
  el("local-calendar-panel").open = true;
  el("local-title").focus();
}
async function loadLocalCalendar(options, active) {
  const target = el("local-calendar-items");
  try {
    const response = await fetch("/api/v1/calendar/local", options);
    if (!response.ok) throw new Error("local_calendar_unavailable");
    const data = await response.json();
    if (active !== generation) return;
    target.replaceChildren();
    for (const item of data.items) {
      const detail = document.createElement("details");
      detail.className = "calendar-focus-entry";
      const summary = document.createElement("summary");
      summary.textContent = (item.kind === "event" ? "موعد · " : "هدف · ") + item.title;
      const when = item.kind === "event" ? cairoDate(item.start_ts) + " — " + cairoDate(item.end_ts) : item.target_date || "بدون تاريخ مستهدف";
      detail.append(summary, text("p", when), text("p", item.notes));
      if (item.kind === "event") detail.append(text("p", "حالة التذكير: " + ({none:"بدون تذكير",scheduled:"مجدول",attempting:"نتيجة الإرسال غير مؤكدة",sent:"تم الإرسال",failed:"تعذر الإرسال",missed:"فات موعد التذكير",cancelled:"ملغي"}[item.reminder_status] || item.reminder_status), "muted"));
      const edit = document.createElement("button"); edit.type = "button";
      edit.className = "btn-secondary"; edit.textContent = "تعديل";
      edit.addEventListener("click", () => editLocalCommitment(item)); detail.append(edit);
      for (const [status, label] of [["done", "تم"], ["cancelled", "إلغاء العنصر"]]) {
        const button = document.createElement("button"); button.type = "button";
        button.className = "btn-secondary"; button.textContent = label;
        button.addEventListener("click", async () => {
          if (status === "cancelled" && !window.confirm("إلغاء هذا العنصر وتذكيره المحلي؟")) return;
          button.disabled = true;
          try {
            await taskPost("/api/v1/calendar/local/transition", {id:item.id,revision:item.revision,status});
            if (localEdit?.id === item.id) newLocalCommitment();
            await load(true);
          } catch (error) {el("local-feedback").textContent = "تعذر التحديث. حدّث القائمة لو العنصر اتغيّر: " + error.message;}
          finally {button.disabled = false;}
        }); detail.append(button);
      }
      target.append(detail);
    }
    if (!data.items.length) target.append(text("p", "لسه مفيش مواعيد أو أهداف محلية. أضف أول عنصر فوق.", "muted"));
    if (data.limit_reached) target.append(text("p", "القائمة محدودة؛ مش كل العناصر ظاهرة.", "muted"));
  } catch (error) {
    if (active === generation) target.textContent = "تعذر تحميل التقويم المحلي.";
  }
}
function renderDailyPoints(data) {
  if (!Array.isArray(data.brief_points)) return;
  const list = document.createElement("ul");
  for (const point of data.brief_points) list.append(text("li", point));
  el("morning-text").replaceChildren(list);
  const details = el("morning-details"); details.replaceChildren();
  for (const row of data.details || []) {
    const item = document.createElement("details");
    const title = document.createElement("summary");
    title.textContent = row.title + " · " + row.source;
    item.append(title, text("p", row.when), text("p", row.notes)); details.append(item);
  }
  if (!data.details?.length) details.append(text("p", "مفيش تفاصيل إضافية محفوظة حاليًا."));
  if (data.details_limited) details.append(text("p", "التفاصيل محدودة؛ افتح التقويم أو المهام لباقي العناصر."));
  const sourceState = value => ({unverified:"التحديث غير مؤكد",recent_checkpoint:"آخر تحديث مكتمل حديث",recent_cache:"نسخة محفوظة حديثة",unverified_cache:"نسخة محفوظة غير مؤكدة التحديث"}[value] || value);
  const status = text("p", "المصادر · Gmail: " + sourceState(data.sources.gmail) + " · Google Calendar: " + sourceState(data.sources.google_calendar) + " · Google Tasks: " + sourceState(data.sources.google_tasks), "muted");
  details.append(status);
}
el("local-kind").addEventListener("change", localKindFields);
el("local-new").addEventListener("click", newLocalCommitment);
el("local-calendar-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = el("local-save"); button.disabled = true;
  try {
    if (!localEdit && !localRequestId) localRequestId = crypto.randomUUID().replaceAll("-", "");
    const isEvent = el("local-kind").value === "event";
    await taskPost("/api/v1/calendar/local/save", {
      id:localEdit?.id || localRequestId, revision:localEdit?.revision || 0,
      kind:el("local-kind").value, title:el("local-title").value, notes:el("local-notes").value,
      start:isEvent ? taskDueIso("local-start") : null,
      end:isEvent ? taskDueIso("local-end") : null,
      target_date:isEvent ? null : el("local-target").value || null,
      reminder_minutes:isEvent && el("local-reminder").value !== "" ? Number(el("local-reminder").value) : null
    });
    newLocalCommitment(); el("local-feedback").textContent = "اتحفظ محليًا في OKAL.";
    await load(true);
  } catch (error) {el("local-feedback").textContent = "تعذر الحفظ. راجع الوقت أو حدّث العنصر قبل إعادة المحاولة: " + error.message;}
  finally {button.disabled = false;}
});
