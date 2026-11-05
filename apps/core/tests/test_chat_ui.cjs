"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function harness(reply, fixtures={}) {
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
  let turns=[];
  const cid="a".repeat(32);
  const context=vm.createContext({
    document:{
      getElementById:get,createElement:node,
      querySelectorAll:s=>s==="[data-chat-prompt]"?prompts:[],
    },
    AbortController, Date,Intl,
    confirm:message=>fixtures.confirm ? fixtures.confirm(message) : true,
    crypto:{randomUUID:()=>"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
    load:async()=>{reloads++;},
    fetch:async(url,options)=>{
      calls.push({url,options});
      if(fixtures.routes?.[url])return response(await fixtures.routes[url](JSON.parse(options.body)));
      if(url==="/api/v1/chat/create") return response({id:cid});
      if(url==="/api/v1/chat/turn") {
        const payload=JSON.parse(options.body);
        turns=[{request_id:payload.request_id,message:payload.message,status:"complete",response:reply}];
        return response(reply);
      }
      if(url==="/api/v1/chat/get") return response({id:cid,turns,next_before:null});
      if(url==="/api/v1/chat/conversations") return response({items:[{id:cid,title:"Saved"}],next_before:null});
      if(url==="/api/v1/chat/memories") return response({items:[]});
      if(url==="/api/v1/chat/projects") return response({items:[]});
      if(url==="/api/v1/chat/memory-health") return response({configured:false});
      if(url==="/api/v1/chat/conversation-state") return response({project_id:null,revision:0,state:{}});
      if(url==="/api/v1/chat/settings") return response({retention_days:90});
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

test("forget clears displayed sources and fences an older source response",async()=>{
  const memory={id:"b".repeat(32),revision:1,key:"communication.style",kind:"instruction",
    content:"I prefer brief answers.",scope:"owner",source:"owner_message",assertion:"remembered",expires_at:0};
  let entries=[memory],release;
  const delayed=new Promise(resolve=>{release=resolve;});
  const h=harness({}, {routes:{
    "/api/v1/chat/memory-health":()=>({configured:true,worker:"idle",jobs:{done:1},index:{current:1},vault:{current:1}}),
    "/api/v1/chat/projects":()=>({items:[]}),
    "/api/v1/chat/memories":()=>({items:entries}),
    "/api/v1/chat/memory-versions":()=>delayed,
    "/api/v1/chat/memory-delete":()=>{entries=[];return {deleted:true};},
  }});
  h.get("chat-memory-manager").open=true;h.get("chat-memory-manager").handlers.toggle();await flush();
  const row=h.get("chat-memory-list").children[0];assert.ok(row);
  h.get("chat-memory-source-list").append({textContent:"Old cached preference"});
  h.get("chat-archive-query").value="Old cached preference";
  row.children.find(n=>n.textContent==="المصدر والإصدارات").handlers.click();await flush();
  row.children.find(n=>n.textContent==="نسيان").handlers.click();await flush();
  release({items:[{status:"current",revision:1,snapshot:{content:memory.content}}],sources:[]});await flush();
  assert.equal(h.get("chat-memory-source-list").children.length,0);
  assert.equal(h.get("chat-memory-list").children.length,0);
  assert.equal(h.get("chat-vault-import").hidden,true);
  assert.equal(h.get("chat-archive-query").value,"");
});

test("archive excerpts remain inert and opening a source returns to fullscreen chat",async()=>{
  const content="<img src=x onerror=alert(1)>";
  const h=harness({}, {routes:{"/api/v1/chat/memory-search":()=>({items:[{
    conversation_id:"a".repeat(32),title:"History",created_at:1800000000,
    owner_excerpt:content,assistant_excerpt:"<script>untrusted</script>"}],next_before:null})}});
  h.get("chat-archive-query").value="history";h.get("chat-archive-scope").value="all";
  h.get("chat-memory-manager").open=true;
  h.get("chat-archive-form").handlers.submit({preventDefault(){}});await flush();
  const result=h.get("chat-archive-results").children[0];
  assert.ok(result.children[0].textContent.includes(content));
  assert.equal(result.children[0].innerHTML,undefined);
  result.children.find(n=>n.tag==="button").handlers.click();await flush();
  assert.equal(h.get("chat-memory-manager").open,false);
  assert.equal(h.get("chat-archive-more").hidden,true);
});

test("vault edits require preview and explicit confirmation with its exact revision",async()=>{
  let confirmed=false;
  const h=harness({}, {confirm:()=>confirmed,routes:{
    "/api/v1/chat/vault-preview":()=>({memory_id:"b".repeat(32),revision:7,content:"Edited preference",changed:true}),
    "/api/v1/chat/vault-import":()=>({changed:true,revision:8}),
    "/api/v1/chat/memory-health":()=>({configured:true,worker:"idle"}),
    "/api/v1/chat/projects":()=>({items:[]}),
  }});
  h.get("chat-vault-memory").value="b".repeat(32);
  h.get("chat-vault-preview").handlers.click();await flush();
  assert.equal(h.get("chat-vault-preview-text").textContent,"Edited preference");
  h.get("chat-vault-import").handlers.click();await flush();
  assert.equal(h.calls.filter(c=>c.url.endsWith("vault-import")).length,0);
  confirmed=true;h.get("chat-vault-import").handlers.click();await flush();
  const call=h.calls.find(c=>c.url.endsWith("vault-import"));
  assert.equal(JSON.parse(call.options.body).revision,7);
  assert.equal(h.get("chat-vault-import").hidden,true);
});

test("prompt produces real local chat POST and displays text safely",async()=>{
  const h=harness({answer:"<img src=x onerror=alert(1)>",mode:"saved_fallback",proposal:null});
  h.prompts[0].handlers.click();
  await flush();
  const call=h.calls.find(c=>c.url==="/api/v1/chat/turn");
  assert.ok(call);
  assert.equal(call.options.method,"POST");
  const p=JSON.parse(call.options.body);
  assert.equal(p.message,"إيه مواعيدي النهارده؟");
  assert.equal(p.history,undefined);
  assert.match(p.request_id,/^[a-f0-9]{32}$/);
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
  assert.equal(h.calls.filter(c=>c.url.includes("calendar/local/save")).length,0);
  const bubble=h.get("chat-messages").children[1];
  const form=bubble.children.find(x=>x.tag==="form");
  assert.ok(form);
  const inputs=form.children.filter(x=>x.tag==="label")
    .map(x=>x.children[0]);
  assert.equal(inputs.length,3);
  assert.equal(inputs[1].value,"2026-11-05T17:00");
  form.handlers.submit({preventDefault(){}});
  await flush();
  const call=h.calls.find(c=>c.url==="/api/v1/calendar/local/save");
  assert.ok(call);
  const request=JSON.parse(call.options.body);
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
  assert.equal(h.calls.filter(c=>c.url==="/api/v1/chat/turn").length,1);
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

test("displayed message count reflects persisted turns and clears on new conversation",async()=>{
  const h=harness({answer:"تم عرض النسخة المحفوظة",mode:"saved_fallback",proposal:null});
  assert.equal(h.get("chat-memory-count").textContent,"");
  h.prompts[0].handlers.click();
  await flush();
  assert.equal(h.get("chat-memory-count").textContent,"2 رسائل");
  h.get("chat-new").handlers.click();
  assert.equal(h.get("chat-memory-count").textContent,"0 رسائل");
  assert.equal(h.get("chat-messages").children.length,0);
});
