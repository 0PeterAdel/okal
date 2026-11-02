"use strict";
// Same-origin top-level navigation strips Gmail OAuth callback code/state.
// Never expose refresh or access tokens to JavaScript.
window.location.replace("/#gmail-connected");
