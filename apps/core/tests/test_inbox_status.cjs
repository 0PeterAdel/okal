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
    URLSearchParams, AbortController, setTimeout, fetch: fetcher,
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
  assert.equal(calls.length, 5);
  assert.equal(calls[2], "/api/v1/morning");
  assert.equal(calls[3], "/api/v1/mail/assistant");
  assert.equal(calls[4], "/api/v1/tasks");
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
  assert.equal(row.children.at(-1).href,
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
    row.handlers.click({target:{closest(){return null;}},ctrlKey:groupIndex>0});
  }
  assert.match(get("trash-count").textContent,/3 من 3/);
  assert.equal(get("trash-selected").disabled,false);
  const protectedRow=get("triage-groups").children[3].children[1];
  assert.equal(protectedRow.handlers.click,undefined);
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
  click(rows[0]);
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
  rows[0].handlers.click({target:{closest(){return null;}}});
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
    to:"owner@example.com", date:"Sunday", html:
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
  assert.match(get("viewer-frame").srcdoc,/img-src data:;/);
  assert.match(get("viewer-frame").srcdoc,/script-src &#39;none&#39;/);
  assert.match(get("viewer-attachments").children[0].textContent,/report.pdf/);
  get("viewer-remote-images").checked=true;
  get("viewer-remote-images").handlers.change();
  assert.match(get("viewer-frame").srcdoc,/img-src data: https:;/);
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
  row.handlers.click({target:{closest(){return null;}}});
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
    target:{closest(){return null;}}
  });
  await get("trash-selected").handlers.click();
  assert.match(get("trash-help").textContent,/اتغير عنوانها أو علاماتها/);
  current = "PRIVATE_REFRESH_TOKEN_HIDDEN_123";
  await get("trash-selected").handlers.click();
  assert.doesNotMatch(get("trash-help").textContent,/PRIVATE_REFRESH_TOKEN/);
  assert.match(get("trash-help").textContent,/HTTP 409/);
});

test("Delete previews exact native subjects then requires local PIN and consent", async () => {
  const digest="a".repeat(64);
  let previewed=false,deleted=false;
  const {context,get}=harness(async (url,options)=>{
    if (url==="/api/v1/mail/trash/preview") {
      const payload=JSON.parse(options.body);
      assert.equal(payload.ids.join(","),"aa,bb");
      previewed=true;
      return response({count:2,approval_digest:digest,items:[
        {id:"aa",subject:"Action",sender:"Manager"},
        {id:"bb",subject:"Info",sender:"Updates"},
      ]});
    }
    if (url==="/api/v1/mail/trash") {
      const payload=JSON.parse(options.body);
      assert.equal(payload.pin,"my-super-secure-PIN");
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
    target:{closest(){return null;}}
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
  get("trash-pin").value="my-super-secure-PIN";
  await get("trash-confirm-form").handlers.submit({preventDefault(){}});
  assert.equal(deleted,true);
  assert.equal(get("trash-dialog").open,false);
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
