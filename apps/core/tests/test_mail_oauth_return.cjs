"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "../src/okal_core/static");
test("Gmail OAuth success completes on safe same-origin navigation", () => {
  let url = null;
  const js = fs.readFileSync(path.join(root, "mail-oauth-return.js"), "utf8");
  vm.runInNewContext(js, {
    window: { location: { replace(next) { url = next; } } },
  });
  assert.equal(url, "/#gmail-connected");
  assert.doesNotMatch(js, /(?:access_token|client_secret|refresh_token)/);
});
test("Gmail OAuth screens use local assets and do not embed secrets", () => {
  for (const [file, label] of [
    ["mail-oauth-complete.html", "mail-oauth-return.js"],
    ["mail-oauth-error.html", "العودة إلى OKAL"],
  ]) {
    const html = fs.readFileSync(path.join(root, file), "utf8");
    assert.ok(html.includes(label));
    assert.match(html, /<html lang="ar" dir="rtl">/);
    assert.doesNotMatch(html, /(?:access_token|client_secret|refresh_token)/);
    assert.doesNotMatch(html, /<script\s+[^>]*>[^<]+<\/script>/);
  }
});
