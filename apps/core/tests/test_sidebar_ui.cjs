"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const staticDir = path.join(__dirname, "../src/okal_core/static");

function sidebarHarness(readyState = "complete") {
  const handlers = {};
  const attrs = new Map();
  const buttonAttrs = new Map();
  const buttonLabel = { textContent:"" };
  const toggle = {
    handlers,
    setAttribute(name, value) { buttonAttrs.set(name, String(value)); },
    getAttribute(name) { return buttonAttrs.get(name); },
    querySelector(selector) {
      assert.equal(selector, ".sidebar-toggle-text");
      return buttonLabel;
    },
    addEventListener(event, fn) { handlers[event] = fn; },
  };
  const sidebar = {};
  const body = {
    setAttribute(name, value) { attrs.set(name, value); },
    getAttribute(name) { return attrs.get(name); },
  };
  const ready = {};
  const document = {
    readyState, body,
    getElementById(id) {
      return id === "sidebar-toggle" ? toggle
        : id === "okal-sidebar" ? sidebar : null;
    },
    addEventListener(name, fn, options) { ready[name] = {fn,options}; },
  };
  const context = vm.createContext({ document });
  vm.runInContext(fs.readFileSync(path.join(staticDir, "sidebar-ui.js"), "utf8"), context);
  return { handlers, attrs, buttonAttrs, buttonLabel, ready };
}

test("sidebar opens by default then collapses to accessible icon rail and reopens", () => {
  const h = sidebarHarness();
  assert.equal(h.attrs.get("data-sidebar"), "expanded");
  assert.equal(h.buttonAttrs.get("aria-expanded"), "true");
  assert.equal(h.buttonAttrs.get("aria-label"), "طي القائمة الجانبية");
  assert.equal(h.buttonLabel.textContent, "طي القائمة");
  h.handlers.click();
  assert.equal(h.attrs.get("data-sidebar"), "collapsed");
  assert.equal(h.buttonAttrs.get("aria-expanded"), "false");
  assert.equal(h.buttonAttrs.get("aria-label"), "فتح القائمة الجانبية");
  assert.equal(h.buttonAttrs.get("title"), "فتح القائمة الجانبية");
  assert.equal(h.buttonLabel.textContent, "فتح القائمة");
  h.handlers.click();
  assert.equal(h.attrs.get("data-sidebar"), "expanded");
  assert.equal(h.buttonAttrs.get("aria-expanded"), "true");
});

test("sidebar initializes when DOM is ready without storing its state", () => {
  const h = sidebarHarness("loading");
  assert.equal(h.attrs.has("data-sidebar"), false);
  assert.equal(h.ready.DOMContentLoaded.options.once, true);
  h.ready.DOMContentLoaded.fn();
  assert.equal(h.attrs.get("data-sidebar"), "expanded");
  assert.equal(h.buttonAttrs.get("aria-expanded"), "true");
  const js = fs.readFileSync(path.join(staticDir,"sidebar-ui.js"),"utf8");
  assert.equal(js.includes("localStorage"),false);
  assert.equal(js.includes("sessionStorage"),false);
  assert.equal(js.includes("fetch("),false);
});

test("collapsed navigation retains all links and accessible names", () => {
  const html = fs.readFileSync(path.join(staticDir, "index.html"), "utf8");
  const css = fs.readFileSync(path.join(staticDir, "chat-glass.css"), "utf8");
  const routes = [
    "#chat-home", "#overview", "#inbox-panel", "#task-section",
    "#calendar-section", "#assistant-section", "#activity-section",
    "#settings-section", "#integrations",
  ];
  for (const route of routes) {
    const anchor = html.split("\n").find(line =>
      line.includes('href="' + route + '"') && line.includes('class="nav-item'));
    assert.ok(anchor, "Missing navigation route: " + route);
    assert.ok(anchor.includes('aria-label="'));
    assert.ok(anchor.includes('title="'));
  }
  assert.ok(html.includes('id="sidebar-toggle"'));
  assert.ok(html.includes('aria-controls="okal-sidebar"'));
  assert.ok(html.includes('src="/sidebar-ui.js"'));
  assert.ok(css.includes('body[data-sidebar="collapsed"] .app-layout'));
  assert.ok(css.includes('.sidebar-toggle{display:none!important}'));
  assert.ok(css.includes('.chat-hero-stage::before,'));
  assert.ok(css.includes('.chat-hero-stage::after'));
  assert.ok(css.includes('box-shadow:none!important'));
});
