"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "../src/okal_core/static");
const read = filename => fs.readFileSync(path.join(root, filename), "utf8");

test("unified theme is a local stylesheet loaded after Chat styles", () => {
  const html = read("index.html");
  const names = [
    "/style.css", "/chat.css", "/chat-glass.css", "/workspace-glass.css"
  ];
  const positions = names.map(name => html.indexOf('href="' + name + '"'));
  assert.ok(positions.every(pos => pos >= 0), "Missing a local stylesheet");
  for (let i = 1; i < positions.length; ++i) {
    assert.ok(positions[i] > positions[i - 1], "Theme must load after the base");
  }
  assert.ok(fs.existsSync(path.join(root, "workspace-glass.css")));
  const css = read("workspace-glass.css");
  assert.ok(!css.includes("@import"));
  assert.ok(!css.includes("fonts.googleapis"));
  assert.ok(!css.includes("https://"));
});

test("sidebar remains left on Chat, Inbox, Tasks, Calendar and Settings", () => {
  const css = read("workspace-glass.css");
  // One shell orientation for ALL routes; never conditional on data-view.
  assert.ok(css.includes(".app-layout {\n    direction:ltr;"));
  assert.ok(css.includes(".app-layout > .sidebar {\n    direction:rtl;"));
  assert.ok(css.includes(".app-layout > .workspace {\n    direction:rtl;"));
  assert.ok(css.includes('body[data-sidebar="collapsed"] .app-layout'));
  assert.ok(css.includes("grid-template-columns:76px minmax(0,1fr)"));
  assert.ok(css.includes("@media(max-width:900px)"));
  const html = read("index.html");
  for (const href of [
    "#chat-home", "#inbox-panel", "#task-section", "#calendar-section",
    "#settings-section"
  ]) assert.ok(html.includes('href="' + href + '"'));
  const javascript = read("sidebar-ui.js");
  assert.ok(javascript.includes('document.body.setAttribute("data-sidebar"'));
  assert.ok(!javascript.includes('data-view'));
});

test("shared glass theme covers core pages without restyling untrusted mail", () => {
  const css = read("workspace-glass.css");
  const selectors = [
    ".metric",".morning-brief",".mail-panel",".secondary-panel",
    ".calendar-panel",".activity-panel",".sync-strip",
    ".triage-column",".mail-source-chip",".selection-toolbar",
    ".task-card",".calendar-day-focus-body",".fullcalendar-shell",
    ".day-plan-panel",".integrations > div",".remote-settings",
    ".chat-glass-card"
  ];
  // Chat glass card's theme remains in chat-glass.css, not the shared sheet.
  for(const selector of selectors.slice(0,-1))
    assert.ok(css.includes(selector), "Missing glass treatment: " + selector);
  assert.ok(read("chat-glass.css").includes(selectors.at(-1)));
  assert.ok(!css.includes("iframe{"));
  assert.ok(!css.includes("#viewer-frame {"));
  assert.ok(css.includes('aria-pressed="true"'));
  assert.ok(!css.includes(".btn-danger-soft {"));
  assert.ok(css.includes("prefers-reduced-transparency"));
  assert.ok(css.includes("forced-colors:active"));
});
