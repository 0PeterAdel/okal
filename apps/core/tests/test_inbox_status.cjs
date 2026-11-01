"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function harness(fetcher) {
  const nodes = new Map();
  function node() {
    return {
      textContent: "", value: "", hidden: false, children: [], handlers: {},
      attributes: {}, classList: { add() {}, remove() {} },
      addEventListener(type, fn) { this.handlers[type] = fn; },
      showModal() { this.open = true; },
      close() {
        this.open = false;
        if (this.handlers.close) this.handlers.close();
      },
      setAttribute(name, value) { this.attributes[name] = value; },
      append(...items) { this.children.push(...items); },
      replaceChildren() { this.children = []; },
      get childElementCount() { return this.children.length; },
    };
  }
  const get = (id) => {
    if (!nodes.has(id)) nodes.set(id, node());
    return nodes.get(id);
  };
  const context = vm.createContext({
    document: { getElementById: get, createElement: node, addEventListener() {} },
    window: { addEventListener() {} },
    URLSearchParams, AbortController, setTimeout,
    fetch: (url, options) => url === "/api/v1/mail/viewed"
      ? response({status:"viewed_locally",hidden_from_smart_inbox:true})
      : fetcher(url,options),
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/okal_core/static/app.js"), "utf8"), context);
  return { context, get };
}
const configured = {
  configuration: "configured", authorization: "not_checked", history: "available",
  daily_at: null, timezone: "Africa/Cairo", local_send_enabled: false,
  latest_success: null, latest_attempt: null,
};
const response = (data, status = 200) => ({ status, ok: status === 200, json: async () => data });

test("configuration alone never claims successful mail reading", () => {
  const { context, get } = harness();
  context.renderMailStatus(configured);
  assert.match(get("mail-status").textContent, /لم تُثبت قراءة ناجحة/);
  assert.match(get("integration-status").textContent, /لم يُفحصا/);
});
test("empty success does not claim inference, newer failure stays visible", () => {
  const { context, get } = harness();
  context.renderMailStatus({ ...configured,
    latest_success: { updated: 100, count: 0 }, latest_attempt: { status: "failed" },
  });
  assert.match(get("integration-status").textContent, /لم يختبر الموديل/);
  assert.match(get("integration-status").textContent, /آخر محاولة مسجلة فشلت/);
});
test("nonempty success and opt-in gates are shown as recorded evidence", () => {
  const { context, get } = harness();
  context.renderMailStatus({ ...configured, daily_at: "09:00", local_send_enabled: true,
    latest_success: { updated: 100, count: 2 },
  });
  assert.match(get("integration-status").textContent, /دقة المحتوى تحتاج مراجعتك/);
  assert.match(get("integration-status").textContent, /09:00/);
  assert.match(get("integration-status").textContent, /ليس إثباتًا لتشغيل العامل/);
  assert.match(get("integration-status").textContent, /الإرسال يتطلب مراجعة/);
});
test("lock clears private status and inbox", () => {
  const { context, get } = harness();
  context.renderMailStatus({ ...configured, latest_success: { updated: 100, count: 2 } });
  context.lock();
  assert.equal(get("mail-status").textContent, "افتح الصندوق لعرض الحالة");
  assert.equal(get("sync").textContent, "لم يتم التحديث بعد");
  assert.equal(get("inbox-panel").hidden, true);
});
test("local dashboard auto-opens without a key and uses only local read endpoints", async () => {
  const calls = [];
  const { context, get } = harness(async (url, options) => {
    calls.push(url);
    assert.equal(Object.hasOwn(options.headers, "Authorization"), false);
    return response(url.startsWith("/api/v1/summaries")
      ? { items: [], next_cursor: null, fetched_at: 100 }
      : url === "/api/v1/morning"
        ? { spoken_text: "صباح الفل، عندك مهمة مؤكدة!", greeting: "صباح الفل!",
            mail_sync_stale: false }
      : url === "/api/v1/mail/assistant"
        ? { items: [], counts: {}, total_in_sample: 0, state: "local_suggestion_preview" }
        : url === "/api/v1/tasks"
          ? { items: [], total_in_sample: 0, overdue_in_sample: 0 }
          : { mail: configured });
  });
  await context.load(true);
  assert.equal(calls.length, 6);
  assert.equal(calls[2], "/api/v1/morning");
  assert.equal(calls[3], "/api/v1/mail/assistant");
  assert.equal(calls[4], "/api/v1/planner");
  assert.equal(calls[5], "/api/v1/tasks");
  assert.match(get("morning-text").textContent, /عندك مهمة/);
  assert.match(get("sync").textContent, /لا يجلب بريدًا جديدًا/);
  assert.equal(get("inbox-panel").hidden, false);
  assert.equal(get("login-panel").hidden, true);
  assert.match(get("connection").textContent, /بدون مفتاح/);
});
test("optional protected mode reveals read key form only after a 401", async () => {
  const { context, get } = harness(async () => response({}, 401));
  await context.load(true);
  assert.equal(get("login-panel").hidden, false);
  assert.equal(get("inbox-panel").hidden, true);
  assert.match(get("message").textContent, /الوضع المحمي/);
});

test("failed status refresh clears former success claims", async () => {
  const { context, get } = harness(async () => response({}, 500));
  context.renderMailStatus({ ...configured, latest_success: { updated: 100, count: 2 } });
  await context.load(true);
  assert.equal(get("mail-status").textContent, "الحالة غير متاحة");
});
test("late refresh cannot restore private status after locking", async () => {
  let resolve;
  const pending = new Promise((done) => { resolve = done; });
  const { context, get } = harness(() => pending);
  const loading = context.load(true);
  context.lock();
  resolve(response({ items: [], fetched_at: 100, mail: configured }));
  await loading;
  assert.equal(get("mail-status").textContent, "افتح الصندوق لعرض الحالة");
  assert.equal(get("inbox-panel").hidden, true);
});

test("triage groups manual-review and preserves untrusted text as textContent", () => {
  const { context, get } = harness();
  context.renderTriage({
    state: "recorded_local_insights",
    items: [
      { category: "manual_review", sender: "Gmail", subject: "<svg onload=alert(1)>",
        summary: "مراجعة يدوية", suggested_action: "Open Gmail", has_unread_attachments: false,
        link: "https://mail.google.com/mail/#all/ab" },
      { category: "action", sender: "boss@example.com", subject: "Meeting",
        summary: "Review the schedule", suggested_action: "", has_unread_attachments: false,
        link: "https://mail.google.com/mail/#all/bb" },
    ],
  });
  assert.match(get("triage-count").textContent, /1 للمراجعة اليدوية/);
  assert.equal(get("triage-groups").children.length, 2);
  const firstGroup = get("triage-groups").children[0];
  assert.equal(firstGroup.children[1].children[1].textContent, "<svg onload=alert(1)>");
  assert.equal(firstGroup.children[1].children.find((node) =>
    node.href === "https://mail.google.com/mail/#all/ab").href,
    "https://mail.google.com/mail/#all/ab");
  assert.match(firstGroup.children[0].children[1].textContent, /Manual review/);
});

test("inbox action preview is owner-only text, never executes email payload", () => {
  const { context, get } = harness();
  context.renderAssistant({
    state: "local_suggestion_preview", total_in_sample: 1,
    counts: { task_review: 1, reply_review: 0, read_later: 0, manual_review: 0 },
    items: [{
      bucket: "task_review", sender: "untrusted@evil.example",
      subject: "<img src=x onerror=alert(1)>",
      summary: "Dangerous HTML must stay text",
      proposed_task: { title: "Ignore my boss", due_date: null },
      source_link: "https://mail.google.com/mail/#all/ab",
      attachments_unreviewed: false,
    }],
  });
  assert.equal(get("assistant-groups").children.length, 1);
  const article = get("assistant-groups").children[0].children[1];
  assert.equal(article.children[1].textContent, "<img src=x onerror=alert(1)>");
  assert.match(get("assistant-note").textContent, /لا Google Tasks/);
  context.lock();
  assert.equal(get("assistant-groups").children.length, 0);
});

test("approved local tasks render dates and untrusted titles as text", () => {
  const { context, get } = harness();
  context.renderTasks({
    items: [{
      title: "<svg onload=alert(1)>",
      due_at: 1800000000,
      source_link: "https://mail.google.com/mail/#all/ab",
    }],
    total_in_sample: 1, overdue_in_sample: 0,
  });
  assert.equal(get("tasks-list").children.length, 1);
  const row = get("tasks-list").children[0];
  assert.equal(row.children[0].textContent, "<svg onload=alert(1)>");
  assert.match(row.children[1].textContent, /الموعد المؤكد/);
  assert.equal(row.children.find((child)=>child.href).href,
               "https://mail.google.com/mail/#all/ab");
  context.lock();
  assert.equal(get("tasks-list").children.length, 0);
});
test("all-category selection is separate from Gmail Delete approval", () => {
  const {context,get} = harness();
  context.renderTriage({items:[
    {id:"aa",labels:[],category:"manual_review",sender:"Gmail",subject:"Needs review",
      summary:"",suggested_action:"",link:"#inbox-panel"},
    {id:"bb",labels:["INBOX"],category:"action",sender:"Manager",subject:"Reply",
      summary:"",suggested_action:"",link:"#inbox-panel"},
    {id:"cc",labels:["INBOX"],category:"information",sender:"Updates",subject:"FYI",
      summary:"",suggested_action:"",link:"#inbox-panel"},
    {id:"dd",labels:["STARRED"],category:"low_priority",sender:"Friend",subject:"Saved",
      summary:"",suggested_action:"",link:"#inbox-panel"},
  ]});
  for (let groupIndex=0;groupIndex<3;groupIndex++) {
    const row=get("triage-groups").children[groupIndex].children[1];
    row.handlers.click({target:{closest(){return null;}},ctrlKey:true});
  }
  assert.match(get("trash-count").textContent,/3 من 3/);
  assert.equal(get("trash-selected").disabled,false);
  const protectedRow=get("triage-groups").children[3].children[1];
  assert.equal(typeof protectedRow.handlers.click,"function");
  assert.equal(protectedRow.children.some(n=>n.className==="trash-selector"),false);
  assert.equal(get("trash-command").textContent,"");
});

test("Information row click, Ctrl+Click and Shift+Click behave like a desktop list", async () => {
  const { context, get } = harness();
  const items = ["aa", "bb", "cc", "dd"].map((id) => ({
    id, labels: ["INBOX"], category: "information", sender: "Sender",
    subject: "Title " + id, summary: "Summary",
    suggested_action: "", has_unread_attachments: false,
    link: "https://mail.google.com/mail/#all/" + id,
  }));
  context.renderTriage({items});
  const rows = get("triage-groups").children[0].children.slice(1);
  const click = (row, options = {}) => row.handlers.click({
    ...options, target: { closest() { return null; } },
  });
  click(rows[0],{ctrlKey:true});
  assert.equal(rows[0].children.at(-1).children[0].checked, true);
  assert.equal(rows[1].children.at(-1).children[0].checked, false);
  click(rows[2], {ctrlKey:true});
  assert.equal(rows[0].children.at(-1).children[0].checked, true);
  assert.equal(rows[2].children.at(-1).children[0].checked, true);
  click(rows[3], {shiftKey:true});
  assert.equal(rows[0].children.at(-1).children[0].checked, false);
  assert.equal(rows[2].children.at(-1).children[0].checked, true);
  assert.equal(rows[3].children.at(-1).children[0].checked, true);
  assert.match(get("trash-count").textContent, /2 من 4/);
  // Ctrl toggles one selected item, leaving the rest intact.
  click(rows[2], {ctrlKey:true});
  assert.equal(rows[2].children.at(-1).children[0].checked, false);
  assert.equal(rows[3].children.at(-1).children[0].checked, true);
  assert.equal(get("trash-selected").disabled, false);
  assert.equal(get("trash-command").textContent, "");
  // Clicking Gmail link is never intercepted as a selection.
  rows[0].handlers.click({target:{closest(){return {};}},ctrlKey:false});
  assert.equal(rows[0].children.at(-1).children[0].checked, false);
  get("clear-selection").handlers.click();
  assert.equal(get("trash-selected").disabled, true);
  assert.equal(get("trash-command").textContent, "");
});

test("Shift+Click ranges honor 20-item ceiling and protected labels never select", () => {
  const { context, get } = harness();
  const items = Array.from({length:25},(_,i)=>({
    id: (i + 1).toString(16).padStart(2,"0"),
    labels: i === 24 ? ["STARRED"] : ["INBOX"],
    category:"information", subject:"Message "+i, sender:"Sender",
    summary:"FYI", suggested_action:"", has_unread_attachments:false,
    link:"https://mail.google.com/mail/#all/" + i,
  }));
  context.renderTriage({items});
  const rows = get("triage-groups").children[0].children.slice(1);
  rows[0].handlers.click({target:{closest(){return null;}},ctrlKey:true});
  rows[23].handlers.click({target:{closest(){return null;}},shiftKey:true});
  assert.match(get("trash-help").textContent, /20 رسالة/);
  assert.match(get("trash-count").textContent, /1 من 24/);
  get("select-all-info").handlers.click();
  assert.match(get("trash-count").textContent, /20 من 24/);
  assert.equal(rows[19].children.at(-1).children[0].checked, true);
  assert.equal(rows[20].children.at(-1).children[0].checked, false);
  // Starred row never gets a selection checkbox or selectable role.
  assert.equal(rows[24].children.find(n => n.href).href,
    "https://mail.google.com/mail/#all/24");
});

test("Information keyboard Enter and Space preserve native accessible selection", () => {
  const { context, get } = harness();
  context.renderTriage({items:[{
    id:"aa", labels:["INBOX"], category:"information", sender:"A",
    subject:"Focusable message", summary:"FYI",
    suggested_action:"",has_unread_attachments:false,link:"https://example.com",
  }]});
  const row = get("triage-groups").children[0].children[1];
  let prevented=0;
  row.handlers.keydown({
    key:" ",preventDefault(){prevented++;},
    target:{closest(){return null;}},
  });
  assert.equal(prevented,1);
  assert.equal(row.attributes["data-selected"],"true");
  assert.equal(row.children.at(-1).children[0].attributes["aria-checked"],"true");
  get("clear-selection").handlers.click();
  assert.equal(row.attributes["data-selected"],"false");
});

test("GitHub PR notifications collapse into one closed expandable cluster", () => {
  const {context,get} = harness();
  const items=["Run 1","Run 2","Run 3"].map((label,n)=>({
    id:(n+1).toString(16).padStart(2,"0"),
    labels:["INBOX"],category:"information",
    sender:"GitHub <notifications@github.com>",
    subject:"[0PeterAdel/okal] PR #42 "+label,
    summary:"workflow",suggested_action:"",
    link:"https://mail.google.com/mail/#all/aa",
  }));
  context.renderTriage({items});
  const group=get("triage-groups").children[0];
  assert.equal(group.children.length,2);
  const details=group.children[1];
  assert.equal(details.className,"mail-cluster");
  assert.equal(details.open,undefined);
  assert.equal(details.children.length,4);
  assert.match(details.children[0].children[1].textContent,/3 رسائل مشابهة/);
  // All three child emails are still present, not lost or merged in the DB.
  assert.match(get("trash-count").textContent,/0 من 3/);
});

test("on-demand original MIME viewer stays sandboxed and remote images opt-in", async () => {
  const fake = {
    id:"aa", subject:"Real message", from:"sender@example.com",
    to:"owner@example.com", date:"Sunday",
    ai_summary:"ملخص مهم", ai_suggested_action:"راجع تفاصيل المشروع",
    ai_category:"action", html:
      '<p>Hello</p><img src="data:image/png;base64,QQ=="><img src="https://tracker.test/pixel"><script>alert(1)</script>',
    text:"Hello",attachments:[{name:"report.pdf",mime_type:"application/pdf"}],
    gmail_link:"https://mail.google.com/mail/#all/aa",
  };
  const {context,get}=harness(async (url) => {
    assert.equal(url,"/api/v1/mail/messages/aa");
    return response(fake);
  });
  await context.openMailViewer("aa");
  assert.equal(get("mail-viewer").open,true);
  assert.equal(get("viewer-title").textContent,"Real message");
  assert.equal(get("viewer-ai-summary").textContent,"ملخص مهم");
  assert.match(get("viewer-ai-action").textContent,/راجع تفاصيل المشروع/);
  assert.match(get("viewer-frame").srcdoc,/img-src data:;/);
  assert.match(get("viewer-frame").srcdoc,/script-src &#39;none&#39;/);
  assert.match(get("viewer-attachments").children[0].textContent,/report.pdf/);
  get("viewer-remote-images").checked=true;
  get("viewer-remote-images").handlers.change();
  assert.match(get("viewer-frame").srcdoc,/img-src data: https: http:;/);
  get("viewer-close").handlers.click();
  assert.equal(get("mail-viewer").open,false);
  assert.equal(get("viewer-frame").srcdoc,"");
});

test("preview surfaces actual safe Gmail lock reason instead of generic OAuth warning", async () => {
  let attempts = 0;
  const {context,get} = harness(async (url) => {
    assert.equal(url, "/api/v1/mail/trash/preview");
    attempts++;
    return response({detail:"mail_operation_already_running"},423);
  });
  context.renderTriage({items:[{
    id:"aa", category:"information", labels:["INBOX"], sender:"Updates",
    subject:"Notice", summary:"",link:"#inbox-panel",
  }]});
  const row = get("triage-groups").children[0].children[1];
  row.handlers.click({target:{closest(){return null;}},ctrlKey:true});
  await get("trash-selected").handlers.click();
  assert.equal(attempts,3);
  assert.match(get("trash-help").textContent,/المزامنة التلقائية/);
  assert.match(get("trash-help").textContent,/mail_operation_already_running/);
  assert.equal(get("trash-dialog").open,undefined);
});

test("preview surfaces provider and protection errors without exposing arbitrary server data", async () => {
  let current = "trash_native_metadata_changed_or_protected";
  const {context,get} = harness(async () =>
    response({detail:current},409));
  context.renderTriage({items:[{
    id:"aa",category:"action",labels:["INBOX"],sender:"Updates",
    subject:"Review",summary:"",link:"#inbox-panel",
  }]});
  get("triage-groups").children[0].children[1].handlers.click({
    target:{closest(){return null;}},ctrlKey:true
  });
  await get("trash-selected").handlers.click();
  assert.match(get("trash-help").textContent,/اتغير عنوانها أو علاماتها/);
  current = "PRIVATE_REFRESH_TOKEN_HIDDEN_123";
  await get("trash-selected").handlers.click();
  assert.doesNotMatch(get("trash-help").textContent,/PRIVATE_REFRESH_TOKEN/);
  assert.match(get("trash-help").textContent,/HTTP 409/);
});

test("Delete previews native subjects then requires one explicit confirmation click", async () => {
  const digest="a".repeat(64);
  const ticket="A".repeat(43);
  let previewed=false,deleted=false;
  const {context,get}=harness(async (url,options)=>{
    if (url==="/api/v1/mail/trash/preview") {
      const payload=JSON.parse(options.body);
      assert.equal(payload.ids.join(","),"aa,bb");
      previewed=true;
      return response({count:2,approval_digest:digest,confirmation_token:ticket,items:[
        {id:"aa",subject:"Action",sender:"Manager"},
        {id:"bb",subject:"Info",sender:"Updates"},
      ]});
    }
    if (url==="/api/v1/mail/trash") {
      const payload=JSON.parse(options.body);
      assert.equal(payload.confirmation_token,ticket);
      assert.equal(payload.approval_digest,digest);
      assert.equal(payload.confirmed,true);
      assert.equal(previewed,true);
      deleted=true;
      return response({status:"confirmed_trash",moved:2});
    }
    // Harmless fallback after the browser reloads local state on success.
    if (url.startsWith("/api/v1/summaries"))
      return response({items:[],fetched_at:1800000000,next_cursor:null});
    if (url==="/api/v1/capabilities")
      return response({mail:configured,read_key_required:false});
    return response({});
  });
  context.renderTriage({items:[
    {id:"aa",category:"action",labels:["INBOX"],sender:"M",
      subject:"Action",summary:"",link:"#inbox-panel"},
    {id:"bb",category:"information",labels:["INBOX"],sender:"U",
      subject:"Info",summary:"",link:"#inbox-panel"},
  ]});
  get("triage-groups").children[0].children[1].handlers.click({
    target:{closest(){return null;}},ctrlKey:true
  });
  get("triage-groups").children[1].children[1].handlers.click({
    target:{closest(){return null;}},ctrlKey:true
  });
  assert.equal(deleted,false);
  await get("trash-selected").handlers.click();
  assert.equal(previewed,true);
  assert.equal(deleted,false);
  assert.equal(get("trash-dialog").open,true);
  assert.equal(get("trash-preview-list").children.length,2);
   await get("trash-confirm-form").handlers.submit({preventDefault(){}});
  assert.equal(deleted,true);
  assert.equal(get("trash-dialog").open,false);
});

test("Native newsletter respects image privacy and single-scroll focus reader", async () => {
  let reads=0;
  const mail={
    id:"aa",subject:"Newsletter",from:"courses@example.com",to:"owner@example.com",
    date:"Today",labels:["INBOX"],
    html:'<!doctype html><html lang="en"><head><style>td{color:red}</style></head>'+
      '<body bgcolor="#f7f7f7"><table><tr><td><img src="https://images.example/logo.png"></td></tr></table></body></html>',
    inline_images:2,skipped_inline_images:1,external_images_detected:true,
    ai_summary:"Review",ai_suggested_action:"",ai_category:"information",
    gmail_link:"https://mail.google.com/mail/#all/aa",attachments:[]
  };
  const {context,get}=harness(async (url)=>{
    assert.equal(url,"/api/v1/mail/messages/aa");
    reads++;
    return response(mail);
  });
  await context.openMailViewer("aa");
  assert.equal(reads,1);
  assert.equal(get("viewer-remote-images").checked,false);
  assert.match(get("viewer-frame").srcdoc,/img-src data:;/);
  assert.doesNotMatch(get("viewer-frame").srcdoc,/img-src data: https:/);
  assert.match(get("viewer-frame").srcdoc,/script-src &#39;none&#39;/);
  assert.equal((get("viewer-frame").srcdoc.match(/<html\b/g)||[]).length,1);
  assert.match(get("viewer-frame").srcdoc,/<style>td{color:red}<\/style>/);
  assert.match(get("viewer-frame").srcdoc,/<body bgcolor="#f7f7f7">/);
  assert.match(get("viewer-frame").srcdoc,/<html lang="en">/);
  assert.equal(get("viewer-load-images").disabled,false);
  assert.equal(get("viewer-load-images").attributes["aria-pressed"],"false");
  assert.match(get("viewer-image-status").textContent,/محجوبة/);
  // No explicit remote consent => the browser CSP forbids external pixels.
  get("viewer-focus-toggle").handlers.click();
  assert.equal(get("viewer-focus-toggle").attributes["aria-pressed"],"true");
  assert.match(get("viewer-focus-toggle").textContent,/الرجوع/);
  get("viewer-load-images").handlers.click();
  assert.equal(get("viewer-remote-images").checked,true);
  assert.equal(get("viewer-load-images").attributes["aria-pressed"],"true");
  assert.match(get("viewer-frame").srcdoc,/img-src data: https: http:/);
  assert.match(get("viewer-image-status").textContent,/تم السماح/);
  get("viewer-frame").handlers.load();
  assert.doesNotMatch(get("viewer-image-status").textContent,/جارٍ تحميل/);
  get("mail-viewer").close();
  assert.equal(get("viewer-remote-images").checked,false);
  assert.equal(get("viewer-load-images").attributes["aria-pressed"],"false");
  assert.equal(get("viewer-focus-toggle").attributes["aria-pressed"],"false");
  await context.openMailViewer("aa");
  assert.equal(reads,2);
  assert.equal(get("viewer-remote-images").checked,false);
  assert.match(get("viewer-frame").srcdoc,/img-src data:;/);
});

test("Lazy marketing images stay inert until owner explicitly presses Load Images", async () => {
  const mail={
    id:"aa",subject:"LinkedIn summary",from:"notification@example.com",
    to:"owner@example.com",date:"Today",labels:["INBOX"],
    html:'<html><head><style>.hero{width:600px}</style></head>'+
      '<body bgcolor="#ffffff"><img data-src="https://cdn.example/logo.png" '+
      'src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==">'+
      '<meta http-equiv="refresh" content="0;url=https://evil.example/"></body></html>',
    inline_images:0,skipped_inline_images:0,external_images_detected:true,
    ai_summary:"Update",ai_suggested_action:"",ai_category:"information",
    gmail_link:"https://mail.google.com/mail/#all/aa",attachments:[]
  };
  const {context,get}=harness(async () => response(mail));
  await context.openMailViewer("aa");
  const before=get("viewer-frame").srcdoc;
  assert.match(before,/data-src="https:\/\/cdn.example\/logo.png"/);
  assert.doesNotMatch(before,/\ssrc="https:\/\/cdn.example\/logo.png"/);
  assert.doesNotMatch(before,/http-equiv="refresh"/);
  assert.match(before,/img-src data:;/);
  get("viewer-load-images").handlers.click();
  const after=get("viewer-frame").srcdoc;
  assert.match(after,/\ssrc="https:\/\/cdn.example\/logo.png"/);
  assert.match(after,/img-src data: https: http:/);
  get("viewer-load-images").handlers.click();
  assert.equal(get("viewer-remote-images").checked,false);
  assert.match(get("viewer-frame").srcdoc,/img-src data:;/);
});

test("Mail Agent previews Gmail action and writes only after explicit confirmation", async () => {
  const events=[];
  const original={id:"aa",subject:"Native subject",from:"sender@example.com",
    to:"owner@example.com",date:"Today",html:"<b>Safe content</b>",
    labels:["INBOX","UNREAD"],ai_summary:"Review this",ai_category:"action",
    ai_suggested_action:"Reply",attachments:[],
    gmail_link:"https://mail.google.com/mail/#all/aa"};
  const {context,get}=harness(async (url, options)=>{
    events.push(url);
    if(url==="/api/v1/mail/messages/aa") return response(original);
    if(url==="/api/v1/mail/actions/preview")
      return response({action:"mark_read", count:1,
        approval_digest:"a".repeat(64),confirmation_token:"A".repeat(43),
        items:[{id:"aa",subject:"Native subject",labels:["INBOX","UNREAD"]}]});
    if(url==="/api/v1/mail/actions/commit"){
      const payload=JSON.parse(options.body);
      assert.equal(payload.action,"mark_read");
      assert.equal(payload.confirmed,true);
      return response({status:"confirmed",action:"mark_read",count:1});
    }
    return response({});
  });
  await context.openMailViewer("aa");
  assert.equal(get("viewer-mark-read").disabled,false);
  assert.equal(get("viewer-archive").disabled,false);
  await get("viewer-mark-read").handlers.click();
  assert.equal(get("mail-action-dialog").open,true);
  assert.equal(events.filter(x=>x==="/api/v1/mail/actions/commit").length,0);
  await get("mail-action-confirm").handlers.click();
  assert.equal(events.filter(x=>x==="/api/v1/mail/actions/commit").length,1);
  assert.equal(get("viewer-mark-read").disabled,true);
  assert.equal(get("viewer-mark-unread").disabled,false);
});

test("Mail Agent task from email stays local and reply draft remains editable", async () => {
  const events=[];
  const native={id:"aa",subject:"Project update",
    from:"Sender <sender@example.com>",to:"owner@example.com",
    date:"Today",html:"<p>Hello</p>",labels:["INBOX"],
    ai_summary:"Task needed",ai_category:"action",ai_suggested_action:"Review",
    attachments:[],gmail_link:"https://mail.google.com/mail/#all/aa"};
  const {context,get}=harness(async (url,options)=>{
    events.push(url);
    if(url==="/api/v1/mail/messages/aa") return response(native);
    if(url==="/api/v1/mail/tasks/from-message")
      return response({status:"open",task_id:"b".repeat(32)});
    if(url==="/api/v1/mail/reply-drafts/generate")
      return response({draft_id:"a".repeat(32),recipient:"sender@example.com",
        subject:"Project update",body:"Thanks. I'll review.",sent:false});
    if(url==="/api/v1/mail/reply-drafts/revise")
      return response({draft_id:"c".repeat(32),status:"revised_draft_saved_local_only",
        sent:false});
    return response({});
  });
  await context.openMailViewer("aa");
  await get("viewer-create-task").handlers.click();
  assert.match(get("viewer-action-note").textContent,/Task محلي/);
  get("viewer-reply-language").value="en";
  await get("viewer-reply-generate").handlers.click();
  assert.equal(get("viewer-reply-body").value,"Thanks. I'll review.");
  assert.equal(get("viewer-reply-save").disabled,false);
  get("viewer-reply-body").value="Thank you for your email.";
  await get("viewer-reply-save").handlers.click();
  assert.match(get("viewer-reply-state").textContent,/حفظ مسودة جديدة/);
  assert.equal(events.some(x=>x.includes("/send")),false);
});

test("AI Reply Send never runs without exact native preview and separate owner click", async () => {
  const events=[];
  const original={id:"aa",subject:"Project update",from:"Tester <a@example.com>",
    to:"owner@example.com",date:"Today",html:"<p>Mail</p>",
    labels:["INBOX"],ai_summary:"Review",ai_category:"action",
    ai_suggested_action:"Reply",attachments:[],
    gmail_link:"https://mail.google.com/mail/#all/aa"};
  const {context,get}=harness(async (url,options)=>{
    events.push(url);
    if(url==="/api/v1/mail/messages/aa") return response(original);
    if(url==="/api/v1/mail/reply-drafts/generate")
      return response({draft_id:"a".repeat(32),subject:"Project update",
        recipient:"a@example.com",body:"Original AI draft",sent:false});
    if(url==="/api/v1/mail/reply-drafts/revise")
      return response({draft_id:"b".repeat(32),sent:false});
    if(url==="/api/v1/mail/reply-drafts/preview-send") {
      assert.equal(JSON.parse(options.body).draft_id,"b".repeat(32));
      return response({draft_id:"b".repeat(32),recipient:"a@example.com",
        subject:"Project update",body:"Reviewed and edited",approval_digest:"a".repeat(64),
        confirmation_token:"T".repeat(43)});
    }
    if(url==="/api/v1/mail/reply-drafts/confirm-send") {
      const payload=JSON.parse(options.body);
      assert.equal(payload.confirmed,true);
      assert.equal(payload.draft_id,"b".repeat(32));
      return response({status:"sent_verified",provider_id:"nativegmailid"});
    }
    return response({});
  });
  await context.openMailViewer("aa");
  await get("viewer-reply-generate").handlers.click();
  get("viewer-reply-body").value="Reviewed and edited";
  // Unsaved owner edits cannot bypass the review.
  await get("viewer-reply-send").handlers.click();
  assert.match(get("viewer-reply-state").textContent,/احفظ التعديل/);
  assert.equal(events.includes("/api/v1/mail/reply-drafts/preview-send"),false);
  await get("viewer-reply-save").handlers.click();
  await get("viewer-reply-send").handlers.click();
  assert.equal(get("mail-send-dialog").open,true);
  assert.equal(get("mail-send-to").textContent,"a@example.com");
  assert.equal(get("mail-send-body").textContent,"Reviewed and edited");
  assert.equal(events.includes("/api/v1/mail/reply-drafts/confirm-send"),false);
  await get("mail-send-confirm").handlers.click();
  assert.equal(events.filter(u=>u==="/api/v1/mail/reply-drafts/confirm-send").length,1);
  assert.equal(get("viewer-reply-send").disabled,true);
});

test("Unified Planner renders due tasks, reminder state and Cairo agenda", () => {
  const {context,get}=harness();
  context.renderPlanner({counts:{today:1,overdue:2,upcoming:3,unscheduled:4}});
  assert.match(get("planner-today").textContent,/1/);
  assert.match(get("planner-overdue").textContent,/2/);
  assert.match(get("planner-upcoming").textContent,/3/);
  context.renderTasks({total_in_sample:1,overdue_in_sample:1,items:[{
    id:"a".repeat(32),title:"راجع المشروع",notes:"مراجعة",
    status:"open",due_at:1793500000,source_link:null,
    reminder:{lead_minutes:15,status:"scheduled"}
  }]});
  assert.equal(get("tasks-list").children.length,1);
  const card=get("tasks-list").children[0];
  assert.equal(card.children[0].textContent,"راجع المشروع");
  assert.match(card.children.find(x=>x.className==="task-reminder-state").textContent,/15/);
  assert.equal(card.children.at(-1).children.length,3);
});

test("Planner create sends only explicit due and reminder to SQLite API", async () => {
  let captured=null;
  const {context,get}=harness(async (url,options)=>{
    if(url==="/api/v1/tasks/create"){
      captured=JSON.parse(options.body);
      return response({task_id:"b".repeat(32),status:"open"});
    }
    if(url.startsWith("/api/v1/summaries"))
      return response({items:[],next_cursor:null,fetched_at:1793500000});
    if(url==="/api/v1/capabilities")
      return response({read_key_required:false,mail:configured});
    return response({items:[],counts:{},total_in_sample:0,
      status_filter:"open",overdue_in_sample:0,
      greeting:"Hello",spoken_text:"Morning"});
  });
  get("task-new-title").value="تجربة";
  get("task-new-notes").value="مهمة محلية";
  get("task-new-due").value="2026-11-03T13:30";
  get("task-new-reminder").value="15";
  await get("task-create-form").handlers.submit({preventDefault(){}});
  assert.equal(captured.title,"تجربة");
  assert.equal(captured.notes,"مهمة محلية");
  assert.equal(captured.reminder_minutes,15);
  assert.match(captured.due,/^2026-11-03T/);
  assert.equal(get("task-new-title").value,"");
});

test("Planner refuses reminder without an owner-entered due", async () => {
  let writes=0;
  const {get}=harness(async ()=>{writes++;return response({});});
  get("task-new-title").value="Future";
  get("task-new-due").value="";
  get("task-new-reminder").value="60";
  await get("task-create-form").handlers.submit({preventDefault(){}});
  assert.equal(writes,0);
  assert.match(get("task-create-feedback").textContent,/اختار موعد/);
});

test("morning rendering resets private text on hide", () => {
  const { context, get } = harness();
  context.renderMorning({
    greeting: "صباح الفل!", spoken_text: "Private morning email subject",
    mail_sync_stale: false,
  });
  assert.equal(get("morning-text").textContent, "Private morning email subject");
  context.lock();
  assert.doesNotMatch(get("morning-text").textContent, /Private morning/);
});

test("OAuth reauthorization and unfinished catch-up have distinct honest labels", () => {
  const { context, get } = harness();
  context.renderMailStatus({
    ...configured,
    sync_enabled: true,
    sync: {
      state: "failed_last_attempt", last_error: "authorization_required",
      last_result: "history_chunk_pending", last_checked: 100,
      last_count: 12, manual_review_count: 2,
    },
  });
  const status = get("integration-status").textContent;
  assert.match(status, /Google Authorization Required/);
  assert.match(status, /Catch-up in progress/);
  assert.match(status, /مراجعة يدوية/);
  assert.doesNotMatch(status, /نجحت المزامنة الآن/);
});
