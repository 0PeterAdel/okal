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
      textContent: "", value: "", hidden: false, children: [],
      classList: { add() {}, remove() {} },
      addEventListener() {},
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
    document: { getElementById: get, createElement: node },
    window: { addEventListener() {} },
    URLSearchParams, AbortController, fetch: fetcher,
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
test("refresh requests local summaries and capabilities only", async () => {
  const calls = [];
  const { context, get } = harness(async (url, options) => {
    calls.push(url);
    assert.equal(options.headers.Authorization, "Bearer synthetic");
    return response(url.startsWith("/api/v1/summaries")
      ? { items: [], next_cursor: null, fetched_at: 100 } : { mail: configured });
  });
  vm.runInContext('token = "synthetic"', context);
  await context.load(true);
  assert.equal(calls.length, 2);
  assert.match(get("sync").textContent, /لا يجلب بريدًا جديدًا/);
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
