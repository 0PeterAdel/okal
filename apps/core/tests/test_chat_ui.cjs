"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function harness(reply) {
  const nodes = new Map(), calls = [];
  const node = tag => ({
    tag, textContent:"",value:"",hidden:false,disabled:false,children:[],
    handlers:{},attributes:{},
    setAttribute(k,v){this.attributes[k]=v;},
    getAttribute(k){return this.attributes[k];},
    addEventListener(type,fn){this.handlers[type]=fn;},
    append(...values){this.children.push(...values);},
    prepend(...values){this.children.unshift(...values);},
    replaceChildren(...values){this.children=[...values];},
    focus(){this.focused=true;},
    scrollTop:0,scrollHeight:100,
  });
  const get = id => {
    if (!nodes.has(id)) nodes.set(id,node("element"));
    return nodes.get(id);
  };
  const prompts=[node("button")];
  prompts[0].attributes["data-chat-prompt"]="إيه مواعيدي النهارده؟";
  const response = data => ({ok:true,status:200,json:async()=>data});
  let reloads=0;
  const context=vm.createContext({
    document:{
      getElementById:get,createElement:node,
      querySelectorAll:s=>s==="[data-chat-prompt]"?prompts:[],
    },
    AbortController, Date,Intl,
    crypto:{randomUUID:()=>"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
    load:async()=>{reloads++;},
    fetch:async(url,options)=>{
      calls.push({url,options});
      if(url==="/api/v1/chat") return response(reply);
      if(url==="/api/v1/calendar/local/save")return response({
        id:"aaaaaaaabbbbccccddddeeeeeeeeeeee",revision:1,replayed:false
      });
      throw Error("Unexpected URL "+url);
    },
  });
  vm.runInContext(fs.readFileSync(
    path.join(__dirname,"../src/okal_core/static/chat-ui.js"),"utf8"),context);
  return {context,get,calls,prompts,reloads:()=>reloads};
}

async function flush(){await new Promise(resolve=>setTimeout(resolve,0));}

test("prompt produces real local chat POST and displays text safely",async()=>{
  const h=harness({answer:"<img src=x onerror=alert(1)>",mode:"saved_fallback",proposal:null});
  h.prompts[0].handlers.click();
  await flush();
  assert.equal(h.calls.length,1);
  assert.equal(h.calls[0].url,"/api/v1/chat");
  assert.equal(h.calls[0].options.method,"POST");
  const p=JSON.parse(h.calls[0].options.body);
  assert.equal(p.message,"إيه مواعيدي النهارده؟");
  assert.deepEqual(p.history,[]);
  const bubbles=h.get("chat-messages").children;
  assert.equal(bubbles.length,2);
  assert.equal(bubbles[1].children[1].textContent,"<img src=x onerror=alert(1)>");
  assert.equal(h.get("chat-greeting").hidden,true);
  assert.equal(h.get("chat-send").disabled,false);
  h.get("chat-new").handlers.click();
  assert.equal(h.get("chat-messages").children.length,0);
  assert.equal(h.get("chat-greeting").hidden,false);
});

test("appointment is only saved after review form submit, Cairo offset explicit",async()=>{
  const h=harness({
    answer:"جهزت لك موعد للمراجعة",mode:"pinned_local_ollama",
    proposal:{kind:"event",title:"اجتماع",start:"2026-11-05T17:00+02:00",
      end:"2026-11-05T18:00+02:00",destination:"okal_local_only",
      requires_confirmation:true,saved:false}
  });
  h.get("chat-input").value="أضف اجتماع بكرة من 5 إلى 6 مساء";
  h.get("chat-form").handlers.submit({preventDefault(){}});
  await flush();
  assert.equal(h.calls.length,1); // No calendar write yet.
  const bubble=h.get("chat-messages").children[1];
  const form=bubble.children.find(x=>x.tag==="form");
  assert.ok(form);
  const inputs=form.children.filter(x=>x.tag==="label")
    .map(x=>x.children[0]);
  assert.equal(inputs.length,3);
  assert.equal(inputs[1].value,"2026-11-05T17:00");
  form.handlers.submit({preventDefault(){}});
  await flush();
  assert.equal(h.calls.length,2);
  assert.equal(h.calls[1].url,"/api/v1/calendar/local/save");
  const request=JSON.parse(h.calls[1].options.body);
  assert.equal(request.title,"اجتماع");
  assert.equal(request.kind,"event");
  assert.equal(request.start,"2026-11-05T15:00:00.000Z");
  assert.equal(request.end,"2026-11-05T16:00:00.000Z");
  assert.equal(request.reminder_minutes,null);
  assert.equal(h.reloads(),1);
});

test("enter sends and shift-enter allows multiline; lock clears private turns",async()=>{
  const h=harness({answer:"أهلاً",mode:"pinned_local_ollama",proposal:null});
  const input=h.get("chat-input");
  input.value="السلام عليكم";
  let prevented=0;
  input.handlers.keydown({key:"Enter",shiftKey:true,preventDefault(){prevented++;}});
  assert.equal(prevented,0);
  input.handlers.keydown({key:"Enter",shiftKey:false,preventDefault(){prevented++;}});
  await flush();
  assert.equal(prevented,1);
  assert.equal(h.calls.length,1);
  h.context.clearChatUI();
  assert.equal(h.get("chat-messages").children.length,0);
  assert.equal(h.get("chat-input").value,"");
});

test("right-panel summary renders cached details as inert text and reports freshness",()=>{
  const h=harness({answer:"ok",mode:"saved_fallback",proposal:null});
  const value="<img src=x onerror=alert(1)>";
  h.context.renderChatDailySummary({
    brief_points:[value,"موعد محفوظ","مهمة محلية","تحديث تقويم","معلومة إضافية"],
    mail_sync_stale:true,
  });
  const rows=h.get("chat-daily-points").children;
  assert.equal(rows.length,4);
  assert.equal(rows[0].tag,"li");
  assert.equal(rows[0].textContent,value);
  assert.match(h.get("chat-source-caveat").textContent,/غير مؤكد/);
  h.context.renderChatDailySummary({brief_points:[],mail_sync_stale:false});
  assert.equal(h.get("chat-daily-points").children.length,1);
  assert.match(h.get("chat-daily-points").children[0].textContent,/مفيش/);
});

test("session memory count reflects only in-tab turns and resets",async()=>{
  const h=harness({answer:"تم عرض النسخة المحفوظة",mode:"saved_fallback",proposal:null});
  assert.equal(h.get("chat-memory-count").textContent,"");
  h.prompts[0].handlers.click();
  await flush();
  assert.equal(h.get("chat-memory-count").textContent,"2 رسائل");
  h.get("chat-new").handlers.click();
  assert.equal(h.get("chat-memory-count").textContent,"0 رسائل");
  assert.equal(h.get("chat-messages").children.length,0);
});
