"use strict";
// FullCalendar Standard MIT, installed once from pinned npm package.
// No provider writes, drag/drop, remote event sources or implicit scheduling.
let fullCalendarInstance=null;
let fullCalendarSnapshot=null;
let fullCalendarSavedPlans=[];
function timelineDateKey(seconds) {
  return cairoDayKey(seconds);
}
function buildTimelineEvents(plan, saved=[], googleTasks=[]) {
  const events=[];
  if (!plan || !Array.isArray(plan.items)) return events;
  for (const item of plan.items) {
    if (item.kind==="calendar_event") {
      events.push({
        id:"provider-"+JSON.stringify(item.id),
        title:item.title,
        start:new Date(item.start_ts*1000).toISOString(),
        ...(item.end_ts>item.start_ts?
          {end:new Date(item.end_ts*1000).toISOString()}:{}),
        allDay:item.all_day===true,
        display:item.end_ts===item.start_ts?"list-item":"auto",
        editable:false,
        extendedProps:{source:"provider_cache",busy:item.busy===true}
      });
    } else if (item.kind==="local_task") {
      events.push({
        id:"deadline-"+item.id,
        title:"موعد تسليم مهمة · "+item.title,
        start:new Date(item.start_ts*1000).toISOString(),
        display:"list-item",editable:false,
        extendedProps:{source:"owner_local_deadline",isBusy:false}
      });
    }
  }
  for (const task of googleTasks) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(task.scheduled_day || "")) continue;
    events.push({
      id:"google-task-"+task.list_id+"-"+task.task_id,
      title:"Google Tasks · يوم فقط · "+task.title,
      start:task.scheduled_day,allDay:true,display:"list-item",
      editable:false,extendedProps:{source:"date_only_tasks",isBusy:false}
    });
  }
  for (const planItem of saved.slice(0,5)) {
    for (const block of (planItem.blocks||[]).slice(0,12)) {
      events.push({
        id:"local-plan-"+planItem.id+"-"+block.task_id+"-"+block.start_ts,
        title:"مقترح محلي غير مؤكد · "+block.title,
        start:new Date(block.start_ts*1000).toISOString(),
        end:new Date(block.end_ts*1000).toISOString(),
        editable:false,
        extendedProps:{source:"reviewed_local_intent",isBusy:false}
      });
    }
  }
  return events;
}
function renderFullCalendar(plan) {
  const target=el("fullcalendar-view");
  fullCalendarSnapshot=plan;
  if (!window.FullCalendar?.Calendar) {
    target.textContent="FullCalendar مش متثبت محليًا بعد. شغّل scripts/install-fullcalendar-standard.sh مرة واحدة ثم حدّث OKAL. واجهة Day Focus الأساسية شغالة.";
    return;
  }
  if (fullCalendarInstance) {
    fullCalendarInstance.destroy();
    fullCalendarInstance=null;
  }
  target.replaceChildren();
  fullCalendarInstance=new window.FullCalendar.Calendar(target,{
    initialView:"timeGridWeek",
    timeZone:"Africa/Cairo",
    locale:"ar",
    direction:"rtl",
    height:"auto",
    firstDay:6,
    nowIndicator:true,
    selectable:false,
    editable:false,
    eventStartEditable:false,
    eventDurationEditable:false,
    droppable:false,
    navLinks:false,
    dayMaxEvents:4,
    headerToolbar:{
      start:"prev,next today",center:"title",
      end:"timeGridDay,timeGridWeek,dayGridMonth,listWeek"
    },
    buttonText:{today:"اليوم",day:"يوم",week:"أسبوع",month:"شهر",list:"قائمة"},
    events:buildTimelineEvents(plan,fullCalendarSavedPlans,
      (typeof googleTasksSnapshot!=="undefined" && googleTasksSnapshot)?
       googleTasksSnapshot.items:[]),
    dateClick(info) {
      // Clicks within *cached* week only; no mutation of Google events.
      if(typeof chooseCalendarFocusDate==="function")
        chooseCalendarFocusDate(info.dateStr.slice(0,10));
    },
  });
  fullCalendarInstance.render();
  el("fullcalendar-status").textContent=
    "عرض محلي للبيانات المحفوظة فقط. أوقات الفراغ غير مؤكدة؛ السحب والتعديل الخارجي متوقفان.";
}
function refreshFullCalendar() {
  if(fullCalendarSnapshot) renderFullCalendar(fullCalendarSnapshot);
}
function clearFullCalendar() {
  fullCalendarSnapshot=null;
  fullCalendarSavedPlans=[];
  if(fullCalendarInstance){fullCalendarInstance.destroy();fullCalendarInstance=null;}
  el("fullcalendar-view").replaceChildren();
  el("fullcalendar-status").textContent="تم إخفاء بيانات الخط الزمني.";
}
async function loadFullCalendarSavedPlans(options, active){
  try{
    const response=await fetch("/api/v1/calendar/day-plan/saved",options);
    if(!response.ok) return;
    const data=await response.json();
    if(active!==generation || !Array.isArray(data.items)) return;
    fullCalendarSavedPlans=data.items;
    refreshFullCalendar();
  }catch(_){ /* Existing timeline stays sourced from local cached events. */ }
}
