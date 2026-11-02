"use strict";
// Owner-entered estimates + bounded local day-plan approval. No external I/O.
let dayPlanRows = [];
let dayPlanTicket = null;

function invalidateDayPlanApproval() {
  dayPlanTicket = null;
  el("day-plan-save").disabled = true;
  el("day-plan-review").replaceChildren();
}
function resetDayPlanUI() {
  dayPlanRows = [];
  invalidateDayPlanApproval();
  el("day-plan-tasks").replaceChildren();
  el("day-plan-saved").replaceChildren();
  el("day-plan-feedback").textContent = "الخطة محلية؛ لا تغييرات في Google.";
}
function newPlanChoice(values, selected, label) {
  const select = document.createElement("select");
  select.setAttribute("aria-label", label);
  for (const [value, title] of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = title;
    select.append(option);
  }
  select.value = selected;
  select.addEventListener("change", invalidateDayPlanApproval);
  return select;
}
function renderDayPlanTaskOptions(tasks) {
  invalidateDayPlanApproval();
  dayPlanRows = [];
  const list = el("day-plan-tasks");
  list.replaceChildren();
  for (const item of tasks.slice(0,12)) {
    const row = document.createElement("div");
    row.className = "day-plan-task-row";
    const label = document.createElement("label");
    const selected = document.createElement("input");
    selected.type = "checkbox";
    selected.checked = false;
    selected.addEventListener("change", invalidateDayPlanApproval);
    label.append(selected, text("span",item.title));
    const minutes = newPlanChoice([
      ["","اختار المدة"],["15","15 دقيقة"],["30","30 دقيقة"],
      ["45","45 دقيقة"],["60","ساعة"],["90","ساعة ونصف"],
      ["120","ساعتان"],["180","3 ساعات"],["240","4 ساعات"]
    ],"","مدة: "+item.title);
    const priority = newPlanChoice([
      ["normal","عادية"],["high","مهمة جدًا"],["low","مرنة"]
    ],"normal","أولوية: "+item.title);
    row.append(label,minutes,priority);
    list.append(row);
    dayPlanRows.push({id:item.id,selected,minutes,priority});
  }
  if (!tasks.length) list.append(text("p",
    "أضف مهمة من قائمة المهام، وبعدها اختار مدتها وأولويتها.","muted"));
  if (tasks.length>12) list.append(text("p",
    "الأداة تعرض أول 12 مهمة؛ خطط على دفعات صغيرة.","muted"));
}
function renderDayPlanProposal(data) {
  const root = el("day-plan-review");
  root.replaceChildren();
  root.append(text("p",data.blocks.length+" فترة مقترحة · "+
    data.unplaced.length+" مهمة تحتاج مراجعة · التفرغ غير مؤكد.","muted"));
  for (const block of data.blocks) {
    const entry=document.createElement("article");
    entry.className="day-plan-proposed-block";
    entry.append(text("h5",block.title),
      text("p",cairoDate(block.start_ts)+" — "+cairoDate(block.end_ts)+
      " · "+block.minutes+" دقيقة · اقتراح فقط"));
    root.append(entry);
  }
  for (const item of data.unplaced)
    root.append(text("p","لم تُجدول: "+item.title+
      " · لا توجد فترة مناسبة داخل ساعاتك أو قبل موعد التسليم.",
      "day-plan-unscheduled"));
  if (!data.blocks.length) root.append(text("p",
    "لا توجد فترات مناسبة. جرّب تغيير الساعات أو مدة المهمة.","muted"));
}
async function previewDayPlan(event) {
  if (event && event.preventDefault) event.preventDefault();
  invalidateDayPlanApproval();
  const button=el("day-plan-preview");
  button.disabled=true;
  const active=generation;
  try {
    if (!calendarSnapshot) throw new Error("افتح بيانات التقويم أولًا.");
    const chosen=dayPlanRows.filter(row=>row.selected.checked);
    if (!chosen.length) throw new Error("اختار مهمة واحدة على الأقل.");
    const tasks=chosen.map(row=>{
      if (!row.minutes.value) throw new Error("اختار مدة كل مهمة.");
      return {task_id:row.id,minutes:Number(row.minutes.value),
        priority:row.priority.value};
    });
    const day=calendarFocusedDate;
    const response=await taskPost("/api/v1/calendar/day-plan/preview",{
      date:day,work_start:el("day-plan-start").value,
      work_end:el("day-plan-end").value,tasks
    });
    if (active!==generation || !calendarSnapshot || day!==calendarFocusedDate)
      return;
    renderDayPlanProposal(response);
    dayPlanTicket=response.confirmation_token;
    el("day-plan-save").disabled=false;
    el("day-plan-feedback").textContent=
      "راجع خطة اليوم. الحفظ محلي فقط، ومواعيد Google لا تتغير.";
  } catch(error) {
    if(active===generation) el("day-plan-feedback").textContent=
      "تعذر اقتراح الخطة: "+String(error.message).slice(0,90);
  } finally {button.disabled=false;}
}
async function confirmDayPlan() {
  const ticket=dayPlanTicket;
  if (!ticket) return;
  const active=generation;
  invalidateDayPlanApproval();
  try {
    const result=await taskPost("/api/v1/calendar/day-plan/confirm",{
      confirmation_token:ticket,confirmed:true
    });
    if (active!==generation) return;
    el("day-plan-feedback").textContent=
      "تم حفظ "+result.blocks_saved+" فترات في OKAL محليًا فقط. Google لم يتغير.";
    await showSavedDayPlans();
  } catch(_) {
    if(active===generation) el("day-plan-feedback").textContent=
      "الخطة تغيرت أو انتهت صلاحية المعاينة. اعمل Preview جديدًا.";
  }
}
async function showSavedDayPlans() {
  const root=el("day-plan-saved");
  root.replaceChildren();
  const active=generation;
  try {
    const response=await fetch("/api/v1/calendar/day-plan/saved",{
      cache:"no-store",credentials:"same-origin",
      headers:token?{Authorization:"Bearer "+token}:{}
    });
    if (!response.ok) throw new Error("unavailable");
    const data=await response.json();
    if(active!==generation) return;
    for (const plan of data.items.slice(0,3)) {
      const section=document.createElement("section");
      section.className="day-plan-saved-item";
      section.append(text("h5","خطة "+plan.date+" · "+plan.blocks.length+" فترات"));
      for (const block of plan.blocks.slice(0,12))
        section.append(text("p",block.title+" · "+cairoDate(block.start_ts)+
          " — "+cairoDate(block.end_ts)));
      root.append(section);
    }
    if (!data.items.length)
      root.append(text("p","لا توجد خطط محفوظة.","muted"));
  } catch(_) {
    if(active===generation)
      root.append(text("p","تعذر قراءة الخطط المحلية.","muted"));
  }
}
el("day-plan-form").addEventListener("submit",previewDayPlan);
el("day-plan-save").addEventListener("click",confirmDayPlan);
el("day-plan-history").addEventListener("click",showSavedDayPlans);
el("day-plan-start").addEventListener("change",invalidateDayPlanApproval);
el("day-plan-end").addEventListener("change",invalidateDayPlanApproval);
