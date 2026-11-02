"use strict";
// Navigate from a local OKAL document, never along Google's cross-site 303
// redirect chain. Replace the callback URL to avoid retaining OAuth codes
// in the browser's visible history. The fragment carries NO auth data.
window.location.replace("/#calendar-connected");
