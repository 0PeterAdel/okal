"use strict";
/* Owner-side presentation only; deliberately no persistent browser state or provider calls,
 * or dependencies on the chat transport. The full nav remains in the DOM
 * and each item has a title/accessible name when collapsed. */
(function initOKALSidebar() {
  function connect() {
    const button = document.getElementById("sidebar-toggle");
    const sidebar = document.getElementById("okal-sidebar");
    if (!button || !sidebar || !document.body) return;
    let collapsed = false;
    const update = () => {
      const label = collapsed ? "فتح القائمة الجانبية" : "طي القائمة الجانبية";
      document.body.setAttribute("data-sidebar", collapsed ? "collapsed" : "expanded");
      button.setAttribute("aria-expanded", String(!collapsed));
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
      button.querySelector(".sidebar-toggle-text").textContent =
        collapsed ? "فتح القائمة" : "طي القائمة";
    };
    button.addEventListener("click", () => {
      collapsed = !collapsed;
      update();
    });
    update();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", connect, { once: true });
  } else {
    connect();
  }
})();
