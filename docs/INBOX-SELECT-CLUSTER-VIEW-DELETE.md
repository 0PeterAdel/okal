# OKAL Inbox V3 — Multiselect, Gmail Reader, and Owner-approved Trash

This is a stacked **draft** feature on PR #47, based on dashboard PR #46 and
earlier unmerged Core/Gmail branches. No Gmail messages were modified during
development. Use a backup and review CI before deploying it to the personal
Omarchy Core service.

## Browser workflow

Open http://127.0.0.1:8766 from Firefox on the owner's workstation.

- **Click** a row in Action, Information, Low Priority or Manual Review to
  select one message, provided it has a saved or quarantined native Gmail ID.
- **Ctrl/Cmd+Click** toggles one selection; **Shift+Click** selects a range.
  **Ctrl/Cmd+Shift+Click** adds a range. Native checkboxes and keyboard
  Enter/Space work as well.
- Select all chooses the first 20 eligible messages. Gmail labels STARRED,
  IMPORTANT, SENT, DRAFT, SPAM, TRASH are protected by default, irrespective
  of the model's classification, and cannot be selected for Trash.
- A series of related GitHub PR notifications and identical sender/subject
  alerts is presented as a closed **details** group; expand to see every
  original message. Grouping only affects UI presentation and never removes
  a saved message or changes Gmail.
- Click a message **subject** to open its native Gmail content in OKAL,
  separately from its AI summary. Gmail is queried **only on explicit click**.
  The full Gmail MIME text/HTML is rendered in a sandboxed iframe with JS,
  form submissions and direct navigation disabled. CID images and small
  image attachments load using authenticated inline data URLs. External
  HTTPS-hosted images stay blocked until you explicitly tick the remote image
  box, because loading them may expose information to senders or trackers.
  Unsupported/large images and non-image attachments still require Gmail.
  This is not an byte-for-byte Gmail UI implementation; complex remote CSS,
  interactive content and large attachments are intentionally limited.
  Live reading requires Gmail network connectivity.

## Enable the real Delete button

The local dashboard is intentionally passwordless for reading, but that
**must not authorize mailbox modification**. Delete is a separate, opt-in
capability, gated with a strong owner PIN and Gmail's modify scope.

One time on the owner terminal:

```bash
cd /home/okal/Projects/okal
bash scripts/run-okal-core.sh mail ui-delete-pin set
```

Choose a distinct 12–128 character Delete PIN, enter twice (input hidden).
This is **not** the former read-key. PIN is salted, PBKDF2-hashed in the
owner-private mail directory with a local failed-attempt lockout. Do not
publish or share the PIN or browser request bodies.

If Gmail still uses read-only OAuth, explicitly authorize an approved
existing private Desktop OAuth client file with the broader
`gmail.modify` scope (replace the path with your own):

```bash
bash scripts/run-okal-core.sh mail authorize \
  --client /absolute/path/to/your-existing-google-desktop-client.json \
  --enable-trash
```

Google does not offer a Trash-only OAuth scope: this scope can modify other
Gmail labels, but OKAL's reviewed browser endpoint is limited to **recoverable
Trash**, and requires the PIN. This operation may replace the current
read-only authorization; keep a private backup of configuration and tokens.
To return to Gmail read-only permission, reauthorize without
`--enable-trash` using the same client path.

Then select messages across categories and click **Delete · إلى Trash**:

1. OKAL obtains a **read-only preview** of native Gmail sender/subject for
   each selected ID, recomputes an approval digest and shows the exact list.
2. Enter the owner Delete PIN in the approval dialog.
3. Only then will OKAL revalidate the selected Gmail IDs, category/source
   provenance and protected labels against native Gmail, and submit a single
   recoverable Trash call for each message, with no silent retry of an
   ambiguous write. Gmail may permanently remove messages from Trash after
   its normal retention period; OKAL does **not** call Gmail permanent-delete.
4. Confirmed moves disappear from local inbox triage, including previously
   quarantined manual-review items. If a batch is interrupted, inspect Gmail
   Trash manually before attempting any other deletion.

The on-screen count and selection do not grant delete permission by
themselves. If the owner PIN or `gmail.modify` is not configured, the
request must fail closed without deleting. A local malware process with the
owner's OS privileges is outside this trust boundary; don't open this service
to the network, reverse proxies or port forwarding.

## Known limitations

- Up to 20 message IDs per deletion batch.
- Remote-image opt-in is per open message; no persistent tracking setting.
- Very large MIME content/image attachments are bounded to protect the Core
  process; use Gmail for oversized or unsupported messages.
- GitHub grouping is deterministic and conservative by sender, repository,
  PR number or repeated subject; it may not combine every semantically
  similar email. This is a UI cluster, not AI-generated deletion suggestions.
- Owner acceptance on Firefox/Omarchy with a real Gmail message is pending.
- CI uses mocked provider data and does not perform a destructive live Gmail
  test or alter owner OAuth.
