"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const code=fs.readFileSync(path.join(__dirname,
  "../src/okal_core/static/fullcalendar-ui.js"),"utf8");

function fixture(){
  const nodes={};
  const options=[];
  const context={window:{},el:id=>(nodes[id] ||= {
    textContent:"",replaceChildren(){this.textContent="";}
  }),generation:0,googleTasksSnapshot:null,
    cairoDayKey:()=> "2026-11-02",chooseCalendarFocusDate:()=>false};
  context.window.FullCalendar={Calendar:class{
    constructor(target,opts){options.push(opts);this.target=target;}
    render(){} destroy(){}
  }};
  vm.createContext(context);
  vm.runInContext(code,context);
  return {context,options,nodes};
}

test("event and task sources remain non-writable with date-only semantics",()=>{
  const {context}=fixture();
  const plan={items:[
    {kind:"calendar_event",id:["google","default","primary","a",""],
     title:"Meeting",start_ts:1793610000,end_ts:1793613600,
     all_day:false,busy:true},
    {kind:"local_task",id:"abc",title:"Deadline",
     start_ts:1793610000,end_ts:null}
  ]};
  const records=context.buildTimelineEvents(plan,[
    {id:"owner-approved",blocks:[{task_id:"abc",title:"Focus",
      start_ts:1793620000,end_ts:1793623600}]}
  ],[
    {list_id:"L",task_id:"T",title:"Day-only",
     scheduled_day:"2026-11-03"}
  ]);
  assert.equal(records.length,4);
  assert.equal(records.filter(x=>x.extendedProps.source==="provider_cache").length,1);
  const deadline=records.find(x=>x.extendedProps.source==="owner_local_deadline");
  assert.equal(deadline.display,"list-item");
  const task=records.find(x=>x.extendedProps.source==="date_only_tasks");
  assert.equal(task.allDay,true);
  assert.equal(task.start,"2026-11-03");
  assert.equal(task.display,"list-item");
  const tentative=records.find(x=>x.extendedProps.source==="reviewed_local_intent");
  assert.match(tentative.title,/غير مؤكد/);
  assert.equal(records.every(x=>x.editable===false),true);
});
test("FullCalendar is read-only with no remote event sources",()=>{
  const {context,options}=fixture();
  context.renderFullCalendar({items:[],date:"2026-11-02"});
  assert.equal(options.length,1);
  const opts=options[0];
  assert.equal(opts.timeZone,"Africa/Cairo");
  assert.equal(opts.editable,false);
  assert.equal(opts.eventStartEditable,false);
  assert.equal(opts.eventDurationEditable,false);
  assert.equal(opts.selectable,false);
  assert.equal(opts.droppable,false);
  assert.equal(opts.navLinks,false);
  assert.ok(Array.isArray(opts.events));
  assert.ok(!("eventSources" in opts));
  assert.ok(!("eventDrop" in opts));
  context.clearFullCalendar();
  assert.equal(options.length,1);
});
test("Without installed MIT bundle, safe fallback keeps app usable",()=>{
  const {context,nodes}=fixture();
  context.window.FullCalendar=null;
  context.renderFullCalendar({items:[]});
  assert.match(nodes["fullcalendar-view"].textContent,/متثبت محليًا/);
  assert.doesNotMatch(nodes["fullcalendar-view"].textContent,/https?:\/\//);
});
