"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const staticDir = path.join(__dirname, "../src/okal_core/static");

test("OAuth return navigates from same-origin document and strips callback URL", () => {
  let replaced = null;
  const source = fs.readFileSync(path.join(staticDir, "calendar-oauth-return.js"), "utf8");
  vm.runInNewContext(source, {
    window: { location: { replace: url => { replaced = url; } } },
  });
  assert.equal(replaced, "/#calendar-connected");
  assert.doesNotMatch(source, /(?:googleusercontent|access_token|refresh_token)/);
});

test("OAuth completion and denial are standalone local HTML pages", () => {
  for (const [name, expected] of [
    ["calendar-oauth-complete.html", "calendar-oauth-return.js"],
    ["calendar-oauth-error.html", "العودة إلى OKAL"],
  ]) {
    const html = fs.readFileSync(path.join(staticDir, name), "utf8");
    assert.match(html, /<html lang="ar" dir="rtl">/);
    assert.ok(html.includes(expected));
    assert.doesNotMatch(html, /(?:client_secret|refresh_token|authorization_code)/);
    assert.doesNotMatch(html, /<script\s+[^>]*>[^<]+<\/script>/);
  }
});
