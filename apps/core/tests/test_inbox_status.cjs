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
  const navLinks = [
    "#overview", "#inbox-panel", "#task-section", "#calendar-section",
    "#assistant-section", "#activity-section", "#integrations",
  ].map((href) => {
    const activeClasses = new Set();
    const attributes = {href};
    return {
      activeClasses, attributes,
      getAttribute(name) { return attributes[name] || null; },
      setAttribute(name, value) { attributes[name] = value; },
      removeAttribute(name) { delete attributes[name]; },
      classList: {
        add(name) { activeClasses.add(name); },
        remove(name) { activeClasses.delete(name); },
      },
    };
  });
  const context = vm.createContext({
    document: {
      getElementById: get, createElement: node, addEventListener() {},
      querySelectorAll(selector) {
        return selector === ".side-nav .nav-item, .sidebar-system .nav-item" ? navLinks : [];
      },
    },
    window: { location: {hash:"#overview"}, addEventListener() {} },
    URLSearchParams, AbortController, setTimeout,
    fetch: (url, options) => url === "/api/v1/mail/viewed"
      ? response({status:"viewed_locally",hidden_from_smart_inbox:true})
      : fetcher(url,options),
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/okal_core/static/app.js"), "utf8"), context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/okal_core/static/day-plan.js"), "utf8"), context);
  return { context, get, navLinks };
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
          : url.startsWith("/api/v1/calendar/plan?")
            ? { window_days: 7, items: [], conflicts: [], candidate_slots: [],
                counts: {calendar_events:0}, coverage: {last_sync:null,
                  recent_successful_sync:false, calendar_limit_reached:false,
                  task_limit_reached:false, conflicts_truncated:false} }
            : { mail: configured });
  });
  await context.load(true);
  assert.equal(calls.length, 7);
  assert.equal(calls[2], "/api/v1/morning");
  assert.equal(calls[3], "/api/v1/mail/assistant");
  assert.equal(calls[4], "/api/v1/planner");
  assert.equal(calls[5], "/api/v1/tasks");
  assert.equal(calls[6], "/api/v1/calendar/plan?days=7");
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

test("original Gmail viewer enables hosted images immediately and retains sandbox", async () => {
  const fake={id:"aa",subject:"Real message",from:"sender@example.com",
    to:"owner@example.com",date:"Sunday",labels:["INBOX"],
    ai_summary:"ملخص مهم",ai_suggested_action:"راجع تفاصيل المشروع",
    ai_category:"action",
    html:'<p>Hello</p><img src="https://tracker.test/pixel"><script>alert(1)</script>',
    attachments:[{name:"report.pdf",mime_type:"application/pdf"}],
    gmail_link:"https://mail.google.com/mail/#all/aa"};
  const {context,get}=harness(async url=>{
    assert.equal(url,"/api/v1/mail/messages/aa");
    return response(fake);
  });
  await context.openMailViewer("aa");
  assert.equal(get("viewer-title").textContent,"Real message");
  assert.match(get("viewer-frame").srcdoc,/img-src data: https: http:/);
  assert.match(get("viewer-frame").srcdoc,/script-src &#39;none&#39;/);
  assert.match(get("viewer-attachments").children[0].textContent,/report.pdf/);
  const html=fs.readFileSync(path.join(__dirname,"../src/okal_core/static/index.html"),"utf8");
  assert.doesNotMatch(html,/id="viewer-(?:remote-images|remember-images|load-images)"/);
  assert.match(get("viewer-image-status").textContent,/تلقائيًا/);
  get("viewer-close").handlers.click();
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

test("Native newsletter automatically loads external images and keeps fullscreen reader", async () => {
  const mail={
    id:"aa",subject:"Newsletter",from:"courses@example.com",to:"owner@example.com",
    date:"Today",labels:["INBOX"],
    html:'<!doctype html><html lang="en"><head><style>td{color:red}</style></head>'+
      '<body bgcolor="#f7f7f7"><table><tr><td><img src="https://images.example/logo.png"></td></tr></table></body></html>',
    inline_images:2,skipped_inline_images:1,external_images_detected:true,
    ai_summary:"Review",ai_suggested_action:"",ai_category:"information",
    gmail_link:"https://mail.google.com/mail/#all/aa",attachments:[]
  };
  let reads=0;
  const {context,get}=harness(async url=>{
    assert.equal(url,"/api/v1/mail/messages/aa");
    reads++;
    return response(mail);
  });
  await context.openMailViewer("aa");
  assert.equal(reads,1);
  assert.match(get("viewer-frame").srcdoc,/img-src data: https: http:/);
  assert.match(get("viewer-frame").srcdoc,/script-src &#39;none&#39;/);
  assert.equal((get("viewer-frame").srcdoc.match(/<html\b/g)||[]).length,1);
  assert.match(get("viewer-frame").srcdoc,/<style>td{color:red}<\/style>/);
  assert.match(get("viewer-frame").srcdoc,/<body bgcolor="#f7f7f7">/);
  assert.match(get("viewer-frame").srcdoc,/<html lang="en">/);
  get("viewer-focus-toggle").handlers.click();
  assert.equal(get("viewer-focus-toggle").attributes["aria-pressed"],"true");
  get("viewer-frame").handlers.load();
  assert.doesNotMatch(get("viewer-image-status").textContent,/جارٍ/);
  get("mail-viewer").close();
  assert.equal(get("viewer-focus-toggle").attributes["aria-pressed"],"false");
  await context.openMailViewer("aa");
  assert.equal(reads,2);
  assert.match(get("viewer-frame").srcdoc,/img-src data: https: http:/);
});

test("Marketing lazy image and safe responsive srcset activate without buttons", async () => {
  const mail={
    id:"aa",subject:"LinkedIn summary",from:"notification@example.com",
    to:"owner@example.com",date:"Today",labels:["INBOX"],
    html:'<html><head><style>.hero{width:600px}</style></head><body bgcolor="#fff">'+
      '<picture><source data-srcset="https://cdn.example/one.png 1x, https://cdn.example/two.png 2x">'+
      '<img data-original="https://cdn.example/hero.jpg?x=1&amp;y=2" '+
      'src="data:image/gif;base64,AA==">'+
      '<img data-lazy-src="javascript:alert(1)"></picture>'+
      '<meta http-equiv="refresh" content="0;url=https://evil.example/"></body></html>',
    inline_images:0,skipped_inline_images:0,external_images_detected:true,
    ai_summary:"Update",ai_suggested_action:"",ai_category:"information",
    gmail_link:"https://mail.google.com/mail/#all/aa",attachments:[]
  };
  const {context,get}=harness(async () => response(mail));
  await context.openMailViewer("aa");
  const html=get("viewer-frame").srcdoc;
  assert.match(html,/img-src data: https: http:/);
  assert.match(html,/\ssrc="https:\/\/cdn.example\/hero.jpg\?x=1&amp;y=2"/);
  assert.ok(!html.includes("&amp;amp;"));
  assert.match(html,/srcset="https:\/\/cdn.example\/one.png 1x, https:\/\/cdn.example\/two.png 2x"/);
  assert.doesNotMatch(html,/\ssrc="javascript:/);
  assert.match(html,/data-lazy-src="javascript:alert\(1\)"/);
  assert.doesNotMatch(html,/http-equiv="refresh"/);
});

test("Legacy remote-image preference never disables user-requested default", async () => {
  const mail={
    id:"aa",subject:"Newsletter",from:"example@example.com",to:"owner@example.com",
    date:"Today",labels:["INBOX"],remote_image_preference:false,
    html:'<img src="https://images.example.net/pic.png">',
    ai_summary:"Hello",ai_category:"information",attachments:[],
    gmail_link:"https://mail.google.com/mail/#all/aa"
  };
  const calls=[];
  const {context,get}=harness(async url=>{
    calls.push(url);
    if(url==="/api/v1/mail/image-preference") throw Error("obsolete settings write");
    return response(mail);
  });
  await context.openMailViewer("aa");
  assert.match(get("viewer-frame").srcdoc,/img-src data: https: http:/);
  assert.ok(!calls.includes("/api/v1/mail/image-preference"));
});

test("Viewing a saved Gmail email removes it immediately from active Smart Inbox", async () => {
  const mail={id:"aa",subject:"Workflow Alert",from:"sender@example.com",
    to:"owner@example.com",date:"Today",html:"<p>Original email</p>",
    labels:["INBOX","UNREAD"],ai_summary:"Review",ai_category:"action",
    ai_suggested_action:"",attachments:[],
    gmail_link:"https://mail.google.com/mail/#all/aa"};
  const {context,get}=harness(async (url)=>{
    if (url==="/api/v1/mail/messages/aa") return response(mail);
    return response({});
  });
  context.renderTriage({state:"recorded_local_insights",items:[
    {id:"aa",subject:"Workflow Alert",sender:"sender@example.com",
     received_ms:1800000000000,category:"action",summary:"Review",
     labels:["INBOX","UNREAD"],link:"https://mail.google.com/mail/#all/aa"}
  ]});
  assert.match(get("triage-count").textContent,/1 رسالة/);
  await context.openMailViewer("aa");
  assert.match(get("triage-count").textContent,/0 رسالة/);
  assert.equal(get("viewer-title").textContent,"Workflow Alert");
  // Gmail is untouched; local viewed acknowledgment only.
  get("mail-viewer").close();
  assert.match(get("triage-count").textContent,/0 رسالة/);
});

test("native reader Trash still previews and confirms after opening hides its inbox card", async () => {
  const mail={
    id:"aa",subject:"Original GitHub alert",from:"notifications@github.com",
    to:"owner@example.com",date:"Today",labels:["INBOX","UNREAD"],
    html:"<p>Original</p>",ai_summary:"Review",ai_category:"action",
    ai_suggested_action:"",attachments:[],
    gmail_link:"https://mail.google.com/mail/#all/aa"
  };
  const calls=[];
  const digest="a".repeat(64),ticket="T".repeat(43);
  const {context,get}=harness(async (url,options)=>{
    calls.push(url);
    if(url==="/api/v1/mail/messages/aa") return response(mail);
    if(url==="/api/v1/mail/trash/preview") {
      assert.deepEqual(JSON.parse(options.body).ids,["aa"]);
      return response({count:1,approval_digest:digest,confirmation_token:ticket,
        items:[{id:"aa",subject:"Original GitHub alert",sender:"notifications@github.com"}]});
    }
    if(url==="/api/v1/mail/trash") {
      const body=JSON.parse(options.body);
      assert.deepEqual(body.ids,["aa"]);
      assert.equal(body.confirmation_token,ticket);
      assert.equal(body.approval_digest,digest);
      assert.equal(body.confirmed,true);
      return response({status:"confirmed_trash",moved:1});
    }
    return response({});
  });
  context.renderTriage({items:[{
    id:"aa",subject:"Original GitHub alert",sender:"GitHub",
    labels:["INBOX","UNREAD"],category:"action",
    summary:"Review",link:"https://mail.google.com/mail/#all/aa"
  }]});
  await context.openMailViewer("aa");
  assert.match(get("triage-count").textContent,/0 رسالة/);
  assert.equal(get("trash-count").textContent.includes("من 0"),true);
  assert.equal(get("viewer-delete").disabled,false);
  await get("viewer-delete").handlers.click();
  assert.equal(get("trash-dialog").open,true);
  assert.equal(get("trash-preview-list").children.length,1);
  assert.equal(calls.filter(x=>x==="/api/v1/mail/trash").length,0);
  await get("trash-confirm-form").handlers.submit({preventDefault(){}});
  assert.equal(calls.filter(x=>x==="/api/v1/mail/trash").length,1);
  assert.equal(get("trash-dialog").open,false);
  assert.equal(get("mail-viewer").open,false);
});

test("native reader respects protected labels despite local Seen filtering", async () => {
  const mail={
    id:"aa",subject:"Protected",from:"owner@example.com",to:"owner@example.com",
    date:"Today",labels:["INBOX","STARRED"],
    html:"<p>Do not trash</p>",ai_summary:"Review",ai_category:"action",
    ai_suggested_action:"",attachments:[],
    gmail_link:"https://mail.google.com/mail/#all/aa"
  };
  const calls=[];
  const {context,get}=harness(async url=>{
    calls.push(url);
    if(url==="/api/v1/mail/trash/preview") throw Error("protected message preview");
    return response(mail);
  });
  await context.openMailViewer("aa");
  assert.equal(get("viewer-delete").disabled,true);
  await get("viewer-delete").handlers.click();
  assert.ok(!calls.includes("/api/v1/mail/trash/preview"));
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

test("navigation follows section hashes and exposes one aria-current location", () => {
  const { context, get, navLinks } = harness();
  context.updateNavigationState();
  assert.equal(get("topbar-section-name").textContent, "نظرة عامة");
  assert.equal(navLinks.filter(link => link.attributes["aria-current"] === "location").length, 1);
  context.window.location.hash = "#task-section";
  context.updateNavigationState();
  assert.equal(get("topbar-section-name").textContent, "المهام");
  assert.equal(navLinks[2].attributes["aria-current"], "location");
  assert.equal(navLinks[0].attributes["aria-current"], undefined);
  assert.equal(navLinks[2].activeClasses.has("active"), true);
  assert.equal(navLinks[0].activeClasses.has("active"), false);
  context.window.location.hash = "#missing-section";
  context.updateNavigationState();
  assert.equal(get("topbar-section-name").textContent, "نظرة عامة");
  assert.equal(navLinks[0].attributes["aria-current"], "location");
});

test("dashboard copy reflects confirmation and removes obsolete PIN/voice promises", () => {
  const html = fs.readFileSync(path.join(__dirname, "../src/okal_core/static/index.html"), "utf8");
  const css = fs.readFileSync(path.join(__dirname, "../src/okal_core/static/style.css"), "utf8");
  assert.doesNotMatch(html, /PIN حذف محلي|VOICE READY|لا إرسال أو حذف مباشر/);
  assert.match(html, /نقله إلى Trash يتطلب منك مراجعة وتأكيدًا صريحًا/);
  assert.match(html, /id="topbar-section-name"/);
  assert.match(html, /aria-current="location"/);
  assert.match(css, /\.nav-item\[aria-current="location"\]/);
  assert.match(css, /#integration-status\{[^}]*overflow-wrap:anywhere/);
});

test("unified calendar keeps untrusted event names inert and labels candidate slots", () => {
  const { context, get } = harness();
  context.renderUnifiedCalendar({
    window_days: 7,
    items: [
      { id: ["google","default","primary","r1",""], provider:"google",
        kind:"calendar_event", title:"<svg onload=alert(1)>",
        start_ts:1793617200, end_ts:1793620800, all_day:false },
      { id:"task-1", kind:"local_task", title:"Deadline",
        start_ts:1793619000, end_ts:null },
    ],
    conflicts: [
      {kind:"deadline_during_busy_event", task_id:"task-1",
       event:["google","default","primary","r1",""],start_ts:1793619000},
    ],
    candidate_slots:[{start_ts:1793610000,end_ts:1793611800,
      status:"candidate_not_verified"}],
    counts:{calendar_events:1,scheduled_local_tasks:1},
    coverage:{last_sync:1793600000,recent_successful_sync:true,
      calendar_limit_reached:false,task_limit_reached:false,conflicts_truncated:false},
  });
  assert.equal(get("calendar-items").children.length, 2);
  assert.equal(get("calendar-items").children[0].children[1].textContent,
    "<svg onload=alert(1)>");
  assert.match(get("calendar-conflicts").children[0].textContent,/Deadline/);
  assert.match(get("calendar-slots").children[0].textContent,/مرشح فقط/);
  assert.match(get("calendar-coverage").textContent,/لا يؤكد تفرغك/);
  assert.equal(get("calendar-week").attributes["aria-pressed"], "true");
  context.lock();
  assert.equal(get("calendar-items").children.length, 0);
  assert.equal(get("calendar-conflicts").children.length, 0);
});

test("calendar day and week controls issue only bounded local reads", async () => {
  const calls = [];
  const { context, get } = harness(async (url) => {
    calls.push(url);
    return response({
      window_days: Number(new URL("http://local"+url).searchParams.get("days")),
      items:[],conflicts:[],candidate_slots:[],counts:{},
      coverage:{last_sync:null,recent_successful_sync:false},
    });
  });
  await get("calendar-day").handlers.click();
  await get("calendar-week").handlers.click();
  assert.equal(calls.join("|"),
    "/api/v1/calendar/plan?days=1|/api/v1/calendar/plan?days=7");
  assert.equal(get("calendar-day").attributes["aria-pressed"], "false");
  assert.equal(get("calendar-week").attributes["aria-pressed"], "true");
});

test("unified calendar fails visibly when cached response is invalid", () => {
  const { context, get } = harness();
  assert.throws(() => context.renderUnifiedCalendar({items:[]}),
    /invalid_unified_calendar_payload/);
  context.renderUnifiedCalendar({
    window_days:1,items:[],conflicts:[],candidate_slots:[],counts:{},
    coverage:{last_sync:null,recent_successful_sync:false}
  });
  assert.match(get("calendar-coverage").textContent,/لم تكتمل.*مزامنة/);
  assert.match(get("calendar-slots").children[0].textContent,/لا توجد فترات/);
});

test("unified planner never implies complete sync with fresh single-calendar checkpoint", () => {
  const { context, get } = harness();
  context.renderUnifiedCalendar({
    window_days:7,items:[],conflicts:[],candidate_slots:[],counts:{},
    candidate_slots_status:"disabled_unverified_calendar_sources",
    coverage:{
      last_sync:1793610000,recent_successful_sync:true,
      coverage_verified:false,calendar_limit_reached:false,
      task_limit_reached:false,conflicts_truncated:false,
      source_evidence:{synced_calendar_count:2,recent_calendar_count:1,
        stale_calendar_count:1,recorded_sync_failures:1,
        cached_google_events_in_window:0},
    },
  });
  const status = get("calendar-coverage").textContent;
  assert.match(status,/لأحد التقويمات/);
  assert.match(status,/تقويمات لها سجل مزامنة: 2/);
  assert.match(status,/مزامنتها حديثة: 1/);
  assert.match(status,/فشل مسجل/);
  assert.match(status,/لا توجد أحداث Google محفوظة/);
  assert.match(status,/لم يتم تأكيد تغطية/);
  assert.match(get("calendar-slots").children[0].textContent,/تم إيقاف/);
  assert.match(get("calendar-items").children[0].textContent,/النسخة المحلية/);
  assert.match(get("calendar-conflicts").children[0].textContent,/المصدر قد يكون ناقص/);
});

test("calendar zero-duration event is visibly instant and does not imply booked time", () => {
  const { context, get } = harness();
  context.renderUnifiedCalendar({
    window_days: 7, items: [{
      kind:"calendar_event",id:["google","default","p","instant",""],
      provider:"google",title:"Moment",
      start_ts:1793610000,end_ts:1793610000,all_day:false,busy:false
    }],
    conflicts:[],candidate_slots:[],candidate_slots_status:"disabled_unverified_calendar_sources",
    counts:{calendar_events:1},
    coverage:{last_sync:null,recent_successful_sync:false,
      coverage_verified:false,calendar_limit_reached:false,
      task_limit_reached:false,conflicts_truncated:false,
      source_evidence:{synced_calendar_count:0,recent_calendar_count:0,
        stale_calendar_count:0,recorded_sync_failures:0,
        cached_google_events_in_window:1,partial_window_recovery_count:1}},
  });
  assert.match(get("calendar-items").children[0].children[2].textContent,/حدث لحظي/);
  assert.match(get("calendar-coverage").textContent,/لفترة محدودة/);
  assert.match(get("calendar-slots").children[0].textContent,/تم إيقاف/);
});

test("calendar day focus is Cairo-aware across midnight without missing events", () => {
  const { context, get } = harness();
  const start = Date.parse("2026-11-02T23:30:00+02:00") / 1000;
  const end = Date.parse("2026-11-03T00:30:00+02:00") / 1000;
  context.renderUnifiedCalendar({
    date:"2026-11-02",window_days:7,
    items:[
      {kind:"calendar_event",id:["google","default","p","overnight",""],
        provider:"google",title:"Overnight event",start_ts:start,end_ts:end,
        all_day:false,busy:true},
      {kind:"local_task",id:"one",title:"Deadline on 3rd",
        start_ts:Date.parse("2026-11-03T11:00:00+02:00") / 1000,end_ts:null}
    ],
    conflicts:[],candidate_slots:[],counts:{calendar_events:1},
    coverage:{last_sync:null,recent_successful_sync:false,
      coverage_verified:false,calendar_limit_reached:false,
      task_limit_reached:false,conflicts_truncated:false},
    candidate_slots_status:"disabled_unverified_calendar_sources",
  });
  assert.equal(get("calendar-focus-items").children.some(item=>
    item.children && item.children[1] && item.children[1].textContent === "Overnight event"),true);
  assert.equal(context.chooseCalendarFocusDate("2026-11-03"),true);
  const entries=get("calendar-focus-items").children;
  assert.equal(entries.some(item=>item.children &&
    item.children[1]?.textContent === "Overnight event"),true);
  assert.equal(entries.some(item=>item.children &&
    item.children[1]?.textContent === "Deadline on 3rd"),true);
  assert.match(get("calendar-focus-summary").textContent,/1 حدث محفوظ · 1 مهمة/);
});
test("calendar focus refuses dates outside loaded local week", () => {
  const { context,get } = harness();
  context.renderUnifiedCalendar({
    date:"2026-11-02",window_days:7,items:[],conflicts:[],
    candidate_slots:[],counts:{},
    coverage:{last_sync:null,recent_successful_sync:false},
  });
  assert.equal(context.chooseCalendarFocusDate("2026-11-08"),true);
  assert.equal(context.chooseCalendarFocusDate("2026-11-09"),false);
  assert.equal(context.chooseCalendarFocusDate("2026-11-01"),false);
  assert.equal(context.chooseCalendarFocusDate("<script>"),false);
  assert.match(get("calendar-focus-summary").textContent,/غير مكتملة/);
  assert.match(get("calendar-focus-items").children[0].textContent,/مش دليل/);
});
test("calendar day focus renders untrusted titles inert and clears on lock", () => {
  const { context,get } = harness();
  context.renderUnifiedCalendar({
    date:"2026-11-02",window_days:7,
    items:[{kind:"calendar_event",id:["g","p","i","t",""],provider:"google",
      title:"<img src=x onerror=alert(1)>",start_ts:1793610000,
      end_ts:1793613600,all_day:false,busy:true}],
    conflicts:[],candidate_slots:[],counts:{},
    coverage:{last_sync:null,recent_successful_sync:false},
  });
  const textValue = get("calendar-focus-items").children.find(e=>e.children?.length>1)
    ?.children[1]?.textContent;
  assert.equal(textValue,"<img src=x onerror=alert(1)>");
  context.lock();
  assert.equal(get("calendar-focus-items").children.length,0);
  assert.equal(get("calendar-date-navigator").children.length,0);
});
test("vendored MIT calendar assets are local and credited", () => {
  const base=path.join(__dirname,"../src/okal_core/static");
  const html=fs.readFileSync(path.join(base,"index.html"),"utf8");
  const js=fs.readFileSync(path.join(base,"vendor/vanilla-calendar.min.js"),"utf8");
  const css=fs.readFileSync(path.join(base,"vendor/vanilla-calendar.min.css"),"utf8");
  const license=fs.readFileSync(path.join(base,"vendor/vanilla-calendar.LICENSE"),"utf8");
  assert.match(js,/vanilla-calendar/);
  assert.match(css,/vanilla-calendar/);
  assert.match(license,/MIT License/);
  assert.match(license,/Yury Uvarov/);
  assert.ok(html.indexOf('/vanilla-calendar.min.js')<html.indexOf('/app.js'));
  assert.doesNotMatch(html,/cdn\\.jsdelivr|unpkg\\.com/);
});

test("local Plan My Day requires selected task estimates before preview", async () => {
  const calls=[];
  const {context,get}=harness(async url=>{calls.push(url);return response({});});
  const id="a".repeat(32);
  context.renderTasks({items:[{id,title:"Improve UX",due_at:null}],
    total_in_sample:1,overdue_in_sample:0});
  context.renderUnifiedCalendar({date:"2026-11-02",window_days:7,
    items:[],conflicts:[],candidate_slots:[],counts:{},
    coverage:{last_sync:null,recent_successful_sync:false}});
  const row=get("day-plan-tasks").children[0];
  assert.equal(row.children.length,3);
  assert.equal(row.children[1].value,"");
  await get("day-plan-form").handlers.submit({preventDefault(){}});
  assert.equal(calls.length,0);
  assert.match(get("day-plan-feedback").textContent,/اختار مهمة/);
  row.children[0].children[0].checked=true;
  await get("day-plan-form").handlers.submit({preventDefault(){}});
  assert.equal(calls.length,0);
  assert.match(get("day-plan-feedback").textContent,/اختار مدة/);
});
test("local Plan My Day previews and saves without ever writing to Google",async()=>{
  const calls=[];
  const {context,get}=harness(async (url,options)=>{
    calls.push({url,options});
    if (url==="/api/v1/calendar/day-plan/preview")
      return response({blocks:[{title:"Study",minutes:60,
        start_ts:1793610000,end_ts:1793613600}],
        unplaced:[],confirmation_token:"OWNER_TICKET"});
    if (url==="/api/v1/calendar/day-plan/confirm")
      return response({blocks_saved:1,google_events_created:0,external_writes:false});
    if (url==="/api/v1/calendar/day-plan/saved")
      return response({items:[{date:"2026-11-02",blocks:[{
        title:"Study",start_ts:1793610000,end_ts:1793613600}]}]});
    throw Error("unexpected endpoint:"+url);
  });
  const id="b".repeat(32);
  context.renderTasks({items:[{id,title:"Study",due_at:null}],
    total_in_sample:1,overdue_in_sample:0});
  context.renderUnifiedCalendar({date:"2026-11-02",window_days:7,
    items:[],conflicts:[],candidate_slots:[],counts:{},
    coverage:{last_sync:null,recent_successful_sync:false}});
  const row=get("day-plan-tasks").children[0];
  row.children[0].children[0].checked=true;
  row.children[1].value="60";
  get("day-plan-start").value="09:00";
  get("day-plan-end").value="18:00";
  await get("day-plan-form").handlers.submit({preventDefault(){}});
  assert.equal(calls[0].url,"/api/v1/calendar/day-plan/preview");
  assert.equal(JSON.parse(calls[0].options.body).tasks[0].minutes,60);
  assert.equal(get("day-plan-save").disabled,false);
  assert.match(get("day-plan-review").children[1].children[0].textContent,/Study/);
  await get("day-plan-save").handlers.click();
  assert.deepEqual(calls.map(x=>x.url),[
    "/api/v1/calendar/day-plan/preview",
    "/api/v1/calendar/day-plan/confirm",
    "/api/v1/calendar/day-plan/saved"
  ]);
  assert.equal(JSON.parse(calls[1].options.body).confirmed,true);
  assert.match(get("day-plan-feedback").textContent,/محليًا فقط/);
  assert.match(get("day-plan-saved").children[0].children[1].textContent,/Study/);
  context.lock();
  assert.equal(get("day-plan-saved").children.length,0);
  assert.equal(get("day-plan-save").disabled,true);
});
