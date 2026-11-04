"use strict";
/**
 * OKAL offline Markdown presentation, modeled on familiar assistant responses.
 * Uses vendored markdown-it 13.0.2, HTML disabled, no remote images, no plugins.
 * Responses are capped by the server. This is presentation only, not a tool.
 */
function buildOKALMarkdownRenderer() {
  if (typeof markdownit !== "function") return null;
  const md = markdownit({
    html: false, linkify: false, typographer: false, breaks: true,
  });
  // Do not let an AI reply cause automatic cross-origin image requests.
  md.renderer.rules.image = (tokens, index) =>
    md.utils.escapeHtml(tokens[index].content || "");
  const allowedURL = value => {
    if (typeof value !== "string" || value.length > 2048) return false;
    try {
      const parsed = new URL(value);
      return parsed.protocol === "https:" || parsed.protocol === "http:";
    } catch (_) {
      return false;
    }
  };
  // Never allow javascript:, data:, file:, blob:, local host paths or custom URI.
  md.validateLink = allowedURL;
  const originalOpen = md.renderer.rules.link_open ||
    ((tokens, i, options, env, self) => self.renderToken(tokens, i, options));
  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const link = tokens[idx];
    const href = link.attrGet("href");
    if (!allowedURL(href)) return '<span class="okal-md-link-text">';
    link.attrSet("target", "_blank");
    link.attrSet("rel", "noopener noreferrer nofollow");
    return originalOpen(tokens, idx, options, env, self);
  };
  const originalClose = md.renderer.rules.link_close ||
    ((tokens, i, options, env, self) => self.renderToken(tokens, i, options));
  md.renderer.rules.link_close = (tokens, idx, options, env, self) => {
    // markdown-it validates addresses before generating link tokens.
    return originalClose(tokens, idx, options, env, self);
  };
  return md;
}
const okalMarkdown = buildOKALMarkdownRenderer();

function formatOKALMarkdown(markdown) {
  if (typeof markdown !== "string" || !okalMarkdown) return null;
  // Chat API already limits answers. Client also caps total parsed material.
  return okalMarkdown.render(markdown.slice(0, 6000));
}

function renderOKALMarkdown(root, markdown) {
  if (!root) return;
  const rendered = formatOKALMarkdown(markdown);
  if (rendered === null) {
    root.textContent = String(markdown ?? "");
    return;
  }
  // Only markdown-it's escaped output is inserted, html:false, images disabled,
  // and links are restricted to plain http(s). No raw model HTML is trusted.
  root.innerHTML = rendered;
  if (typeof root.querySelectorAll !== "function") return;
  for (const table of root.querySelectorAll("table")) {
    const wrapper = document.createElement("div");
    wrapper.className = "okal-table-wrap";
    table.parentNode.insertBefore(wrapper, table);
    wrapper.append(table);
  }
  // A scrolling viewport keeps Markdown tables readable on narrow screens.
  for (const table of root.querySelectorAll("table")) {
    if (!table.parentNode || table.parentNode.classList?.contains("okal-table-wrap")) continue;
    const wrapper = document.createElement("div");
    wrapper.className = "okal-table-wrap";
    table.parentNode.insertBefore(wrapper, table);
    wrapper.append(table);
  }
  for (const pre of root.querySelectorAll("pre")) {
    const code = pre.querySelector("code");
    if (!code) continue;
    const match = /\blanguage-([a-zA-Z0-9_+#.-]{1,24})\b/.exec(code.className);
    const header = document.createElement("div");
    header.className = "okal-code-header";
    const language = document.createElement("span");
    language.textContent = match ? match[1] : "Code";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "okal-copy-code";
    button.textContent = "نسخ الكود";
    button.setAttribute("aria-label", "نسخ محتوى الكود");
    button.addEventListener("click", async () => {
      const payload = code.textContent || "";
      try {
        if (!navigator.clipboard?.writeText) throw Error("clipboard_not_available");
        await navigator.clipboard.writeText(payload);
        button.textContent = "تم النسخ ✓";
      } catch (_) {
        button.textContent = "حدّد الكود وانسخه يدويًا";
      }
    });
    header.append(language, button);
    pre.parentNode.insertBefore(header, pre);
    pre.classList.add("okal-code-body");
  }
}
if (typeof module !== "undefined" && module.exports) {
  module.exports = {formatOKALMarkdown, renderOKALMarkdown};
}
