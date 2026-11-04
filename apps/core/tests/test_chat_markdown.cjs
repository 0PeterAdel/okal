"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const staticRoot = path.join(__dirname, "../src/okal_core/static");
global.markdownit = require(path.join(staticRoot, "vendor/markdown-it.min.js"));
const {formatOKALMarkdown, renderOKALMarkdown} = require(path.join(staticRoot, "chat-markdown.js"));

test("assistant Markdown renders clear headings, emphasis, lists and code", () => {
  const tick = String.fromCharCode(96);
  const html = formatOKALMarkdown([
    "## الخطة", "",
    "- **تجهيز PR**",
    "- مراجعة " + tick + "pytest" + tick, "",
    "~~~python",
    "print('ok')",
    "~~~"
  ].join("\n"));
  assert.match(html, /<h2>الخطة<\/h2>/);
  assert.match(html, /<li><strong>تجهيز PR<\/strong><\/li>/);
  assert.match(html, /<code>pytest<\/code>/);
  assert.match(html, /<pre><code class="language-python">/);
  assert.match(html, /print\('ok'\)/);
});

test("GFM-style table, quote, rule and links render locally", () => {
  const html = formatOKALMarkdown(
    "| Task | Status |\n|---|---|\n| Chat | Done |\n\n> Cached only\n\n---\n\n[Docs](https://example.com/docs)"
  );
  assert.match(html, /<table>/);
  assert.match(html, /<th>Task<\/th>/);
  assert.match(html, /<td>Done<\/td>/);
  assert.match(html, /<blockquote>/);
  assert.match(html, /<hr/);
  assert.match(html, /href="https:\/\/example.com\/docs"/);
  assert.match(html, /rel="noopener noreferrer nofollow"/);
  assert.match(html, /target="_blank"/);
});

test("never treats model text as HTML, scripts or remotely fetched images", () => {
  const html = formatOKALMarkdown(
    '<script>alert("x")</script>\n\n' +
    '<img src=x onerror=alert(1)>\n\n' +
    '![tracker](https://tracker.invalid/pixel.png)\n\n' +
    '[unsafe](javascript:alert(1))\n\n' +
    '[unsafe2](data:text/html,xxx)'
  );
  assert.doesNotMatch(html, /<script\b|<img\b|href="javascript:|href="data:/i);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(html, /tracker/);
});

test("parser is locally pinned and model HTML never becomes a DOM element", () => {
  const root = {textContent:"",innerHTML:""};
  renderOKALMarkdown(root, "**OKAL**");
  assert.match(root.innerHTML, /<strong>OKAL<\/strong>/);
  assert.equal(root.textContent, "");
  assert.equal(formatOKALMarkdown(null), null);
  const tick = String.fromCharCode(96);
  const unsafe = formatOKALMarkdown(tick+"<svg onload=alert(1)>"+tick);
  assert.match(unsafe, /&lt;svg onload=alert\(1\)&gt;/);
});

test("bounded markdown never parses an unbounded response", () => {
  const html = formatOKALMarkdown("a".repeat(100_000));
  assert.ok(html.length < 7_000);
});
