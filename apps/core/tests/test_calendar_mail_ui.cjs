"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const script=fs.readFileSync(path.join(__dirname,
  "../src/okal_core/static/calendar-mail-proposal.js"),"utf8");
function harness(){
  const nodes=new Map(), calls=[];
  function el(id){
    if(!nodes.has(id)){
      const value={
        textContent:"",disabled:false,open:id==="mail-viewer",
        children:[],events:{},
        replaceChildren(){this.children=[];},
        append(...entries){this.children.push(...entries);},
        addEventListener(event,handler){this.events[event]=handler;},
      };
      nodes.set(id,value);
    }
    return nodes.get(id);
  }
  const ctx={
    el,
    text:(tag,value)=>({tag,textContent:String(value)}),
    currentViewerMessage:{id:"aabb"},
    viewerGeneration:1,
    fetchMailAgent:async(url,body)=>{
      calls.push({url,body});
      return {
        calendar_event_created:false,owner_review_required:true,
        external_writes:false,status:"source_iso_times_need_owner_review",
        title:"<img onerror=alert(1)>",
        evidence_quote:"Appointment 2026-11-03T10:00+02:00 to 2026-11-03T11:00+02:00",
        start_iso:"2026-11-03T08:00:00+00:00",
        end_iso:"2026-11-03T09:00:00+00:00",
      };
    }
  };
  vm.createContext(ctx);vm.runInContext(script,ctx);
  return {ctx,el,calls};
}
test("Gmail proposal requires a click and renders untrusted text inert",async()=>{
  const {ctx,el,calls}=harness();
  assert.equal(calls.length,0);
  el("viewer-calendar-propose").disabled=false;
  await el("viewer-calendar-propose").events.click();
  assert.equal(calls.length,1);
  assert.equal(calls[0].url,"/api/v1/calendar/mail-proposal");
  assert.equal(calls[0].body.message_id,"aabb");
  const children=el("viewer-calendar-propose-details").children;
  assert.equal(children[0].textContent,"<img onerror=alert(1)>");
  assert.ok(children[1].textContent.includes("2026-11-03"));
  assert.match(el("viewer-calendar-propose-status").textContent,/للمراجعة فقط/);
  el("mail-viewer").events.close();
  assert.equal(el("viewer-calendar-propose").disabled,true);
  assert.equal(el("viewer-calendar-propose-details").children.length,0);
});
test("Invalid provider/model result never renders or creates events",()=>{
  const {ctx,el,calls}=harness();
  assert.throws(()=>ctx.showMailCalendarSuggestion({
    calendar_event_created:true,owner_review_required:true,
    external_writes:false,status:"owner_must_set_time"
  }),/invalid_mail_calendar_proposal/);
  assert.equal(calls.length,0);
  assert.equal(el("viewer-calendar-propose-details").children.length,0);
});
