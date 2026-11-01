# Gmail Newsletter Renderer + Owner Voice (PR #53)

## Observed by the owner

LinkedIn and Alison newsletters still displayed broken icons / alt-text and
odd table layout. Older OKAL AI summaries occasionally said "Rizon أرسلت
إيميل ترويجي لبيتر" instead of addressing the owner ("أرسلت لك").

The screenshots showed remote image sources were blocked. Old renderer also
removed original HTML head/body tags and attributes, damaging sender-authored
newsletter styles; lazy images need script-based activation that a safe
viewer **must not execute**.

## Implementation

**HTML reader**

- Preserve full HTML/head/body and the sender's in-email CSS, tables and body
  attributes; inject a strict CSP FIRST, and remove meta-refresh and base tags.
- Run all original HTML in the same `iframe sandbox=""` with script/connect/
  form/top-navigation disabled. Never insert sender HTML in OKAL parent DOM.
- **Prominent "عرض صور الرسالة"** button next to the reader controls, not
  buried below long metadata. It enables external images only on that
  message's explicit click; clicking again turns it off; closing/reopening
  or opening another message resets to OFF.
- The backend now detects remote image URLs in `src`, `srcset`, `data-src`,
  `background` and CSS `url(...)`, including protocol-relative URLs.
- Only AFTER owner consent, a safe, bounded `data-src`/`data-original`
  image URL can be shown in a real `src` attribute, without executing any
  embedded sender JavaScript.
- Existing local-only CID/Content-Location MIME image embedding remains.
- Hosts can still refuse cross-site hotlinks, third-party trackers may be
  blocked by Firefox/uBlock, and expired/removed assets cannot be restored.
  In those cases, **فتح في Gmail** remains the accurate fallback.
- No server-side untrusted URL fetching, proxy bypass, Gmail writes or
  automatic external image consent.

**AI wording**

- Local private `Config.owner_name` defaults to `بيتر` and can be changed
  by the owner, without downloading any data or enabling model cloud.
- Both single-pass and chunked Ollama summaries are explicitly addressed to
  the inbox owner in second-person Egyptian Arabic.
- A narrow, deterministic post-processing pass converts recipient phrases
  like `لبيتر` to `لك`, without blindly removing legitimate third-party
  references such as `عن بيتر`.
- Old stored insights are transformed **for display only** in Smart Inbox,
  message details and morning brief; historical SQLite evidence is not
  rewritten, so no Gmail resync is needed for the wording fix.

## Install on the owner's Omarchy

Branch: `fix/mail-render-original-images-owner-voice`, stacked on PR #52.

```bash
cd /home/okal/Projects/okal
git status --short --branch
backup_dir=$(mktemp -d "$HOME/okal-core-backup-XXXXXXXX")
bash scripts/run-okal-core.sh backup "$backup_dir/core.sqlite3"
git fetch origin fix/mail-render-original-images-owner-voice

systemctl --user stop okal-core.service
if git show-ref --verify --quiet refs/heads/fix/mail-render-original-images-owner-voice; then
  git switch fix/mail-render-original-images-owner-voice &&
  git merge --ff-only origin/fix/mail-render-original-images-owner-voice
else
  git switch --track origin/fix/mail-render-original-images-owner-voice
fi
systemctl --user start okal-core.service
systemctl --user is-active okal-core.service
```

In Firefox refresh http://127.0.0.1:8766 with Ctrl+Shift+R.
Open the affected LinkedIn/Alison email and inspect initial safe rendering.
Click **عرض صور الرسالة** to allow external image hosts explicitly. Try
**توسيع القراءة** for a larger reading area. Close/reopen and verify remote
consent is OFF again.

Check a previously summarized Rizon message in Smart Inbox; the summary
should now address "لك" directly, without reanalysing the original email.

## Acceptance limits

CI tests use synthetic Gmail MIME + browser stubs. A real Firefox/Omarchy
session with the actual email and any ad/tracking blocker is still required
before merging this stacked Draft. Missing sender assets, blocked HTTP hosts
or external CSS cannot be guaranteed to appear exactly as in Gmail.
