"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm");
const source=fs.readFileSync(require("node:path").join(__dirname,"../src/okal_core/static/computer-ui.js"),"utf8");
function context(){return vm.createContext({document:{getElementById:()=>null}});}
test("mixed directory grants preserve read versus write and reject implicit scope",()=>{
  const ctx=context();vm.runInContext(source,ctx);
  const roots=ctx.computerRootsFromText("read /owner/reports\nwrite /owner/synthetic-output");
  assert.equal(roots[0].write,false);assert.equal(roots[1].write,true);
  assert.throws(()=>ctx.computerRootsFromText("/owner/implicit-write"));
});
test("computer UI renders untrusted plan, preview and receipts as text",()=>{
  assert.doesNotMatch(source,/\.innerHTML\s*=/);
  assert.match(source,/pre\.textContent=JSON\.stringify/);
  assert.match(source,/approval_digest:run\.approval_digest/);
  assert.doesNotMatch(source,/localStorage|sessionStorage/);
});

test("system diagnostics are rendered as observed receipts, never model guesses",()=>{
  assert.match(source,/step\.tool==="system\.status"/);
  assert.match(source,/evidence\.block_devices/);
  assert.match(source,/evidence\.mounted_space/);
  assert.match(source,/prettyBytes/);
  assert.match(source,/record\.status==="verified"/);
  assert.doesNotMatch(source,/\.innerHTML\s*=/);
});

test("verified public browser receipts show text excerpts and safe user-clicked source links",()=>{
  assert.match(source,/browser\.search/);
  assert.match(source,/browser\.public_read/);
  assert.match(source,/record\.status==="verified"/);
  assert.match(source,/new URL\(url\)/);
  assert.match(source,/parsed\.protocol!=="https:"/);
  assert.match(source,/anchor\.rel="noopener noreferrer"/);
  assert.doesNotMatch(source,/\.innerHTML\s*=/);
});

test("terminal plans show exact argv before owner approval and bounded stdout receipts",()=>{
  assert.match(source,/step\.tool==="system\.terminal"/);
  assert.match(source,/JSON\.stringify\(run\.preview\[i\]\?\.argv/);
  assert.match(source,/record\.result\?\.evidence\?\.stdout/);
  assert.match(source,/approval_digest:run\.approval_digest/);
  assert.doesNotMatch(source,/\.innerHTML\s*=/);
});

test("owner API controls tool readiness summary instead of fake static capability badges",()=>{
  assert.match(source,/get\("chat-action-readiness"\)/);
  assert.match(source,/data\.readiness\?\.browser/);
  assert.match(source,/data\.readiness\?\.command_sandbox/);
  assert.match(source,/tools\.has\(name\)/);
  assert.doesNotMatch(source,/localStorage|sessionStorage/);
});

function receiptHarness(receipt){
  const element=tag=>({
    tag,className:"",textContent:"",children:[],handlers:{},attrs:{},
    append(...items){this.children.push(...items);},
    replaceChildren(...items){this.children=[...items];},
    setAttribute(key,value){this.attrs[key]=value;},
    addEventListener(key,callback){this.handlers[key]=callback;}
  });
  const parent=element("article");
  const ctx=vm.createContext({
    document:{getElementById:()=>null,createElement:element},
    fetch:async()=>({ok:true,json:async()=>receipt}),
    URL,confirm:()=>false,setTimeout:()=>0,clearTimeout:()=>{}
  });
  vm.runInContext(source,ctx);
  ctx.renderComputerRun(parent,"verified-local-synthetic");
  return new Promise(resolve=>setImmediate(()=>resolve(parent)));
}
function descendants(node){
  return [node,...(node.children||[]).flatMap(descendants)];
}
test("real read-only disk evidence expands its bubble and shows no false Recover button",async()=>{
  const parent=await receiptHarness({
    status:"succeeded",approval_digest:"synthetic",preview:[{}],
    plan:{steps:[{tool:"system.status",arguments:{}}]},
    steps:[{status:"verified",result:{
      summary:"Read verified local device and storage information.",
      evidence:{block_device_count:2,block_devices:[
        {name:"nvme0n1",size_bytes:512110190592,removable:false},
        {name:"nvme1n1",size_bytes:1024209543168,removable:false}],
        mounted_space:[{mountpoint:"/",available_bytes:50000000000,total_bytes:990000000000}]},
      recovery:[]
    }}]
  });
  assert.match(parent.className,/chat-bubble--action/);
  const nodes=descendants(parent);
  assert.ok(nodes.some(n=>String(n.textContent).includes("Block devices: 2")));
  const buttons=nodes.filter(n=>n.tag==="button").map(n=>n.textContent);
  assert.ok(buttons.some(x=>x.includes("Refresh")));
  assert.ok(!buttons.some(x=>x.includes("Recover")));
  assert.ok(nodes.some(n=>n.className==="computer-run-actions"));
});
test("Recover remains available only for a receipt with actual reversible changes",async()=>{
  const parent=await receiptHarness({
    status:"succeeded",approval_digest:"synthetic",preview:[{}],
    plan:{steps:[{tool:"files.move",arguments:{source:"/docs/a",destination:"/docs/b"}}]},
    steps:[{status:"verified",result:{
      summary:"Moved verified synthetic file.",evidence:{},
      recovery:[{action:"move_back",source:"/docs/b",destination:"/docs/a",sha256:"abc"}]
    }}]
  });
  const buttons=descendants(parent).filter(n=>n.tag==="button").map(n=>n.textContent);
  assert.ok(buttons.some(x=>x.includes("Recover")));
});
test("Action bubble remains wide and responsive in static glass CSS",()=>{
  const css=fs.readFileSync(require("node:path").join(__dirname,
    "../src/okal_core/static/chat-glass.css"),"utf8");
  assert.match(css,/\.chat-bubble--action\s*\{/);
  assert.match(css,/width:min\(900px,96%\)/);
  assert.match(css,/@media\(max-width:650px\)/);
  assert.match(css,/\.computer-run-actions/);
});
