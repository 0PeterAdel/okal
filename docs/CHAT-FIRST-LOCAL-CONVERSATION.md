# OKAL Chat-First Home — local conversation v1

## Product decision

The default page (opening / without a hash) is now **Chat**, not Overview.
Overview, Gmail, Tasks, Calendar and Settings are still reachable from the
sidebar, preserving their existing routes and capabilities. The new chat uses
a separate stylesheet and a self-hosted frontend module, without rebuilding
the existing dashboard or taking over the other development agent's components.

The official owner-supplied **approved OKAL logo** now has a committed
1254 × 1254 transparent high-resolution WebP export at
`apps/core/src/okal_core/static/assets/okal-master-hq.webp` (440,846 bytes).
It is a faithful compressed export from the supplied original, not a
redrawn mark or upscaled thumbnail. The original PNG is unchanged and
not committed. The older `okal-master.webp` thumbnail is preserved only for
legacy compatibility and is **not** the default identity anymore.
The UI's `/assets/okal-identity?brand=1254-v1` route serves the bundled
high-resolution export on fresh clones, including Production after deploy,
unless a separate validated owner-only private PNG is installed.
The browser revision query refreshes stale image caches.

The visual identity follows `OKAL_Brand_Guidelines` (2026), not the
image-generation mockup's fabricated tool statistics or subscription labels:
Obsidian `#070A10`, Midnight `#121A25`, Stone `#303A47`,
Royal Gold `#D5A24C`, Radiant Gold `#F0C778`, Ice Glass `#B9DBF6`,
Ivory `#F3EFE8`. Rough balance: 70% dark, 20% stone, 8% glass, 2%
gold focus. CSS supplies limited 14px glass blur, layered spatial depth,
fine HUD rings, and a reduced-motion fallback.

The right contextual panel uses actual saved morning brief points from the
existing `GET /api/v1/morning` dashboard fetch. It has ephemeral
session-message count, functional shortcuts to existing tools, a truthful
owner-review notice, and explicit data freshness caveats. **No invented
task progress, lifetime memory, paid Pro plan, microphone capability or
external web tool execution appears.**

## Glass refinement and collapsible sidebar (PR #113)

The existing approved logo image, its dimensions and placement remain
unchanged. The faint full/partial fog disk behind the emblem is removed:
the hero radial fill and glow shadows are disabled, while the small HUD
ring outlines retain their current size and position and their existing
bottom-open clipped arc shape.

The chat room, context cards, composer, buttons and the existing dashboard
widgets use a restrained Liquid Glass material: translucent midnight-blue
surfaces, thin icy-blue luminous edges, inset white highlights and small
gold active accents. No decorative panel claims imaginary task or model
activity. Blur is reduced in accessibility modes, and forced colors retain
visible borders. The visual reference is inspiration, not a literal
screenshot replacement.

The left sidebar now has a native button with `aria-controls`,
`aria-expanded` and an accessible changing label. On desktop widths
greater than 900px it toggles between its normal layout and a 76px
icon-only rail. Navigation remains fully functional and each link has a
stable accessible Arabic/English name and hover tooltip. Small-screen
navigation remains the original horizontal layout; the toggle is hidden
there. Sidebar state is **tab-local and ephemeral**, never stored in
browser storage or on the server. Reloading starts expanded.

Try the preview from the exact reviewed branch, without modifying the
checkout used by Production:

    bash scripts/preview-chat-pr113.sh

From an owner-side independent checkout of the feature branch, open
<http://127.0.0.1:8767/#chat-home>. Test collapsing and re-expanding on
Chat, Gmail, Calendar and Overview, keyboard access to the button/links,
and that no ring backdrop collides with the logo/Arabic headings.
The accepted visual review is still required before squash merge.

## Unified workspace glass and stable left navigation

The shared offline asset `workspace-glass.css` is loaded after
`style.css`, `chat.css` and `chat-glass.css`. It keeps the existing
HTML structure, interactions, provider behavior and source data unchanged,
while matching the Chat home identity on Overview, Gmail, Tasks, Calendar,
Assistant, Activity, Integrations and Settings.

Desktop shell direction is **always LTR for grid placement**, so the
sidebar occupies the left column on every route. Within that shell, the
sidebar and content workspace are **RTL**, preserving Arabic readability.
This fixes the previous route-dependent right/left jump. The existing
76px collapsed icon rail remains on the left after navigating across tabs,
without changing or persisting the user's presentation preference.
Below the existing 900px breakpoint the original horizontal/mobile
navigation is retained.

The color/material vocabulary uses Obsidian/Midnight foundations,
translucent navy/icy-glass panels, thin illuminated edges and gold primary
actions. Gmail source filters and triage cards, task forms, agenda and
read-only calendar cards, activity summaries, provider connection cards
and secure-access settings now use the same glass system.

Important preserved boundaries: status/warning/error meaning, trash
confirmation, manual-review prompts, disabled states, calendar source
freshness text and the sandboxed original Gmail message reader are not
re-themed into misleading claims. No external fonts, CDNs, JS feature
libraries, data writes, or provider permissions are introduced.

Visual review acceptance: open each non-Chat page and verify the sidebar
stays left in expanded/collapsed states; the cards have matching material,
buttons remain legible and tab-operable, calendar day/week/month readable,
Gmail source chips clearly show selected state, and forms remain accessible.

Run local static/interaction tests before owner review:

    node --check apps/core/src/okal_core/static/sidebar-ui.js
    node --test apps/core/tests/test_sidebar_ui.cjs apps/core/tests/test_workspace_glass.cjs

## How conversation works

- The browser explicitly POSTs the user's turn and up to 8 recent
  same-session turns to /api/v1/chat. It stores no transcript in
  localStorage, indexedDB, cookies or SQLite. New Chat and Lock clear it.
- Python builds a **bounded snapshot** from already-saved daily briefing
  details, tasks, local appointments, Google Calendar cached events,
  Google Tasks cache and Gmail summaries. It also sends source freshness
  warnings. No Gmail or Google APIs are called during a chat request.
- Natural-language replies use the preexisting **reviewed pinned local
  Ollama model** and only the existing local model transport
  127.0.0.1:11434. It requires the Gmail AI model configuration to be
  present and locally verified. If the model is unavailable, deterministic
  limited cached-data answers still work; the UI clearly identifies that
  fallback instead of pretending to be a full LLM.
- The text model is told not to invent deadlines or provider coverage.
  Message/event titles and notes are treated as untrusted data; the model
  cannot execute tools, send mail, change tasks, or write calendars.
- A request to add an appointment with title, explicit date, time, and
  end/duration may produce a **draft preview** only. The Python server
  independently validates owner intent, explicit date/time cues, finite
  Cairo timezone aware times, correct ordering and duration <=24 hours.
  If these are missing, the user gets a follow-up request for details.
- The review card lets the owner edit the title and times. The explicit
  confirmation button uses the preexisting owner-browser-only
  POST /api/v1/calendar/local/save endpoint, stable new ID and revision=0
  idempotency. It writes **only** OKAL local SQLite, **never** Google
  Calendar. A failed/uncertain save is not retried automatically.
- No voice recording, microphone capture, TTS, speech model or remote
  tunnel is enabled. The voice-ready reply text provides a future hook;
  do not label voice "ready to use" until separately implemented.

## Trust and privacy boundaries

- No remote APIs, model install/pull, paid services or external provider
  write scopes added.
- Chat POST follows the existing same-origin JSON owner session gate,
  including protected-mode browser pairing and Cloudflare Access JWT gate
  when remote access is explicitly enabled. A raw read-only device
  bearer token cannot use the chat POST in protected mode.
- An owner can still be on a passwordless local loopback workspace; this
  is the existing product's deliberate local mode. Don't publish
  127.0.0.1:8766 or the passwordless local host to the internet.
- Model interpretations remain proposals, not source-of-truth. Cached
  external data may be incomplete; missing events do not prove free time.
- Message bodies/credentials are not included in the prompt. The snapshot
  is capped to 24 brief metadata records and model context has budgets.
- Conversation state is ephemeral (current browser tab only); cross-chat
  long-term memory and validated conversation actions are follow-up work.
- Safety note: an intent draft is not a trustworthy signed instruction
  and never bypasses human review.

## Checks / manual acceptance

    PYTHONPATH=apps/core/src python -m unittest apps.core.tests.test_chat -v
    node --test apps/core/tests/test_chat_ui.cjs
    node --test apps/core/tests/test_inbox_status.cjs
    node --check apps/core/src/okal_core/static/chat-ui.js

Then run all Core and Governance CI checks.

On the owner Omarchy device, **first test the unmerged PR in an isolated
checkout on port 8767**. Do not deploy or update Production until the owner
explicitly approves the merge. After a separately approved merge:

1. Open `/` or <https://okal/>; Chat should be the default, and the Overview
   link should still open the existing dashboard.
2. Ask "إيه مواعيدي بكرة؟" and "إيه المهام الموجودة عندي؟".
   Verify the cached-data caveat and no fabricated live syncing.
3. Request "أضف اجتماع بكرة الساعة 5 مساء لمدة ساعة", check the
   preview. Verify no calendar write before clicking Confirm.
4. Edit time and title; confirm once. Verify the new record under the
   **local** Calendar, and no event added to Google Calendar.
5. New Chat and Lock should erase the visible previous transcript.
   Refreshing the tab should also start a fresh session.
6. Deny the local Ollama service temporarily; check the fallback is
   transparently limited instead of silently faking full conversation.
7. Check same-origin / protected-mode rejection tests, CSS mobile
   layout, keyboard Enter/Shift+Enter and reading order.

Do not deploy the feature branch. Merge only through a reviewed
squash PR with all checks passing, back up SQLite, then update the
single production checkout to latest main. If an independent coding
agent changes the same HTML/API/JS files, inspect the combined diff.


## Approved brand master and restrained spatial glass

The repo now bundles the approved **full-resolution WebP** so all
clones and Production deployments show the detailed logo without manual
file installation. The separate original full-resolution PNG remains private
unless the owner explicitly installs it in OKAL state. The public repo
contains only an optimized transparent export from that supplied original.

To register the approved original PNG for a local state directory:

    bash scripts/install-okal-master.sh "/path/to/OKAL_APPROVED_ORIGINAL_UNEDITED.png" "$HOME/.local/state/okal-core"

The script checks the PNG signature, dimensions and owner-only
permissions, then installs it atomically. The app serves
`/assets/okal-identity` using the private PNG when present, and falls back
to the **bundled high-resolution WebP** otherwise. The original PNG stays
outside the repository. Private override is optional, not required.

The separate `chat-glass.css` layer and existing `chat.css` keep the
chat layout, adding translucent panels, subtle icy reflections, HUD
details and gold focus. No fake telemetry or active-voice claims.

## Familiar rich Markdown answers

Assistant answers use pinned locally vendored `markdown-it` 13.0.2
(MIT license retained), without external CDNs or paid APIs. Supported
formatting includes headings, paragraphs, lists, emphasis, blockquotes,
tables, fenced code blocks, inline code and HTTP(S) links. Code blocks
have a language label and Copy Code action; wide tables scroll.

The parser has raw HTML disabled, autolinks disabled, remote images
disabled and non-HTTP(S) links rejected. External links use
`noopener noreferrer nofollow`. User messages remain literal text;
only assistant responses are formatted. Both server and client cap
answer length. This follows familiar ChatGPT Markdown presentation
conventions but is not a copy of ChatGPT's private renderer, math
engine or executable code previews.

The current pinned parser is used only with constrained, short model
answers; review the upstream version before expanding untrusted input
limits substantially.

## Owner preview — always before merge

From the exact PR feature branch:

    bash scripts/preview-chat-pr113.sh "/home/okal/Downloads/OKAL_APPROVED_ORIGINAL_UNEDITED(1).png"

Without a logo argument the script searches Downloads for known master
filenames, warning if none exists. It uses temporary SQLite and model
metadata only, does not copy OAuth credentials, and binds only to
127.0.0.1:8767. Production 8766 remains untouched.

Test an AI response containing a heading, ordered list, Markdown
table and fenced Python block. Confirm Copy Code appears and model
text is not treated as executable HTML. Open the local browser at
`http://127.0.0.1:8767/#chat-home`.
