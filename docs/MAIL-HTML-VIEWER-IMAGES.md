# OKAL Gmail HTML viewer — newsletter images and focused reading

## Why images were broken

The original on-demand Gmail viewer intentionally denied **remote HTTPS
image hosts** until the owner checked "تحميل الصور الخارجية" in the
message viewer. Newsletter banners, thumbnails and icons are frequently
hosted on separate domains, so default preview shows HTML/text with blank
images. Existing CID support also recognized only simple quoted
`cid:...` references and did not resolve `Content-Location`-backed MIME
images.

The old modal had *nested scrollable areas*: an 86vh dialog and a ~55vh
iframe. Long newsletters were difficult to read or inspect.

## New behavior

- Gmail MIME image bytes available directly in `image/png`,
  `image/jpeg`, `image/webp`, `image/avif`, `image/gif` are embedded as
  verified local `data:image/...;base64` references if they fit strict
  limits. Handles quoted, bare, CSS `cid:`, percent-encoded CID and exact
  Gmail `Content-Location` attributes without contacting image hosts.
- For **remote** image sources, the UI now explicitly displays that such
  sources were detected and blocked. Tick **تحميل صور الرسالة الخارجية**
  *only after deciding to allow remote loads for that message*. HTTPS
  images may then load inside the sandbox; they can reveal an open event,
  viewer IP or tracking parameters. Remote opt-in resets when the message
  closes or another message opens. The app never silently changes this
  policy, proxies remote images or stores image-host permissions.
- If an embedded image exceeds safety limits, its absence is shown and
  the owner can open the original Gmail message. MIME images are bounded
  individually and in total; broken URLs, revoked links, http-only
  sources, remote fonts/scripts and blocked third-party hosts may still
  be unavailable.
- A **توسيع القراءة** button switches to a large focused reader
  (near-fullscreen, single iframe scroll), with a prominent return
  button for AI actions/Task/Reply; default view remains integrated into
  the inbox. Email HTML document shells are normalized and responsive
  constraints applied to images and tables.
- No scripts, JS event handlers or forms can execute from email HTML:
  still `<iframe sandbox="">` with CSP `script-src 'none'`,
  `default-src 'none'`, `connect-src 'none'`, `form-action 'none'`,
  `base-uri 'none'`. No untrusted HTML enters the parent DOM.

## Owner rollout (after CI)

The patch is a stacked Draft PR #52 based on #51. Owner's local machine
is unchanged until the branch is checked out.

```bash
cd /home/okal/Projects/okal
git status --short --branch
backup_dir=$(mktemp -d "$HOME/okal-core-backup-XXXXXXXX")
bash scripts/run-okal-core.sh backup "$backup_dir/core.sqlite3"
git fetch origin fix/mail-viewer-images-responsive-reader

systemctl --user stop okal-core.service
git switch --track origin/fix/mail-viewer-images-responsive-reader
systemctl --user start okal-core.service
systemctl --user is-active okal-core.service
```

If the branch already exists locally, switch to it and fast-forward only;
don't reset or delete local uncommitted work. In Firefox open
http://127.0.0.1:8766 and hard-refresh with Ctrl+Shift+R.

With one large real newsletter, verify the MIME picture previews; keep
remote checkbox *off* at first to verify privacy notice. Check
**توسيع القراءة** and scroll content, then opt in to remote images and
check whether hosted graphics appear. Close and reopen the message and
verify remote permission is **off again**. When a host still blocks
images, use **فتح في Gmail**. No Gmail writes are required.

## Verification limits

- Automated offline tests verify MIME substitution, CSP string,
  per-message privacy reset and UI button behavior. Real Firefox visual
  layout, live Gmail HTML, remote host restrictions and system-wide
  content blockers still require owner testing.
- This only affects **displaying** messages, not how long messages are
  analyzed (the separate PR #51) or Gmail write authorization.
