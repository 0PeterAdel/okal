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
