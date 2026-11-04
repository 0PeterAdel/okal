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
