# Gmail Live Acceptance on Omarchy (owner-only)

This runbook is for [PR #42](https://github.com/0PeterAdel/okal/pull/42).
Automated GitHub tests are **not** evidence of a connected real Gmail account.
Do not merge #39, #41 or #42 before the owner has completed this gate.
The live probe is **read-only against Gmail**. It never sends mail. Only the
explicit outage commands stop/start `okal-core.service`.

## 0. Preserve your existing checkout and state

On the actual Omarchy laptop:

```bash
cd /home/okal/Projects/okal
git status --short --branch
systemctl --user status okal-core.service --no-pager
```

Review any tracked modifications and keep every private/untracked file. Do NOT
`git clean`, `git reset --hard`, force checkout, or overwrite private files.
Only after reviewing checkout and service configuration:

```bash
systemctl --user stop okal-core.service
backup_dir="$(mktemp -d /home/okal/Projects/okal-mail-backup-XXXXXXXX)"
bash scripts/run-okal-core.sh backup "$backup_dir/core.sqlite3"
echo "A private SQLite backup was created outside the repository."
git fetch origin feat/gmail-unattended-history-sync
git switch --track origin/feat/gmail-unattended-history-sync
.venv-okal-core/bin/python -m pip install --require-hashes -r apps/core/requirements-mail.lock
```

If the feature branch already exists locally, use `git switch
feat/gmail-unattended-history-sync` and a safe `git merge --ff-only
origin/feat/gmail-unattended-history-sync`. If checkout or dependency install
fails, **stop** and inspect; do not force or reset. The user service's ExecStart
must still point to the reviewed `/home/okal/Projects/okal` checkout and to
the same local state directory as the acceptance commands. The default state
is `~/.local/state/okal-core`; if using a custom state path, pass
`--state-dir /absolute/private/path` to the acceptance script.

The SQLite backup does **not** substitute for keeping private Gmail OAuth files
and config; preserve the original private state directory separately.

## 1. Local Gmail + Ollama identity checks

If Gmail is not configured, follow [MAIL-BACKEND.md](MAIL-BACKEND.md) for the
private mail config and Google Desktop OAuth client setup. Do not paste the
client JSON, token, consent URL, Gmail subjects, or private summaries into
GitHub or ChatGPT. Read-only authorization command:

```bash
bash scripts/run-okal-core.sh mail authorize --client /absolute/private/google-desktop.json
```

After authorization and with local Ollama running, use:

```bash
.venv-okal-core/bin/python scripts/mail-live-acceptance.py preflight
.venv-okal-core/bin/python scripts/mail-live-acceptance.py baseline
```

`preflight` actually invokes Gmail profile validation + local model verification.
It checks that a locally retained refresh credential exists; it **does not**
prove it will stay valid for months. External Google consent apps in Testing
often get Gmail-scope refresh tokens expiring in seven days.

`baseline` invokes a real Gmail incremental read, saves a valid history
checkpoint, and opts in to the ~five-minute automatic sync. Both print only
safe status fields, **not** email text, account address, OAuth credentials,
message IDs, or private filesystem paths. Do not proceed if either reports
`status: blocked`.

## 2. Live shutdown and bilingual message proof

Start Core if it is stopped (and make sure the service is using the same
reviewed branch/state as the CLI):

```bash
systemctl --user start okal-core.service
systemctl --user is-active okal-core.service
.venv-okal-core/bin/python scripts/mail-live-acceptance.py outage-start
```

This last command intentionally stops **only** `okal-core.service`, then
prints two distinct random **subjects**, one with suffix `-AR`, the other
`-EN`. While Core is stopped, use **another email account** to send two
genuine incoming emails to the authorized Gmail address:

- Exact first subject: the displayed `arabic_test_subject`. Body in Arabic:
  request a specific deadline and ask for a clear next action.
- Exact second subject: the displayed `english_test_subject`. Body in English:
  ask for an explicit follow-up and date.

Neither message should carry spam, trash, sent, or draft labels in the connected
Gmail account. Keep the mail bodies private; write your own realistic content.
There is no need to wait three literal hours: shutdown/restart exercises
the identical persisted Gmail History cursor. For a real three-hour observation
you can leave the service stopped as long as desired. Manual terminal
`mail sync now` must **not** be run while the service is intentionally stopped.

Then:

```bash
.venv-okal-core/bin/python scripts/mail-live-acceptance.py outage-finish
# After the local background worker processes both messages:
.venv-okal-core/bin/python scripts/mail-live-acceptance.py check
```

**Safety guard:** `outage-finish` now checks the two **exact** subject markers
in native Gmail metadata first and verifies both messages arrived after
`outage-start`. Gmail message **bodies are not downloaded** for this preflight.
If they are absent, from an older test, sent from the connected account, or
arrived before the outage, it prints
`test_messages_missing_or_not_sent_during_core_outage` and keeps Core
**stopped**, so the owner can send the correct messages and retry the SAME
`outage-finish`. Do not run `outage-start` again while this probe is pending.
A Gmail read/auth failure prints a safe code; inspect locally without pasting
private credentials or messages. The background worker must not be manually
started until verification succeeds, except as an emergency owner recovery.

Once the two subjects are verified, `outage-finish` starts Core and automatic
sync runs inside the service. `check` reads **local SQLite only**, without
querying Gmail or invoking Ollama. It
requires the two unique test subjects to appear as **one classified message
each**, an advanced completed Gmail checkpoint, and no recorded sync failure.
Exit 0 means this narrow catch-up proof succeeded; exit 2 means a still-pending
or incomplete result. If the worker is handling a large backlog, run `check`
again later. Do not delete state or artificially advance the cursor to pass.
For diagnostics use `bash scripts/run-okal-core.sh mail sync status`, and
review the local journal privately. Safe error codes may be shared, never
raw messages/tokens/DB contents.

The operator probe state lives in a private 0600
`mail/live-acceptance.json`; it contains test subject markers, checkpoint
and timestamps, **not** account credentials or message bodies. Backups may
include previous markers.

## Alternative: read-only evidence audit, without sending test emails

For owners who already have live Gmail messages in the OKAL inbox and do not
want to send artificial email repeatedly, run the **independent native-source
reconciliation**:

```bash
.venv-okal-core/bin/python scripts/mail-live-readonly-audit.py
```

This is a **single, no-send** command. It checks the saved SQLite checkpoint
and dedupe ledger, locally recorded source IDs and strict AI output, selected
source message IDs against Gmail's **native metadata** (not mail bodies),
current Gmail History deltas and recent visible-mail coverage. It prints
**only counters, safe status and booleans**, not message IDs, account names,
subjects, text, OAuth material or source links. Access-token refresh may still
update the existing private token file. This command does **not** stop/restart
`okal-core.service`, alter the inbox DB or approve outgoing sends.

A true `mail_reconciliation_passed: true` verifies existing messages, the
live Gmail identity and that recorded message IDs still match Gmail; it is
**not** retrospective proof of arrivals during a *specific* powered-off period,
nor does it certify that every historical email has been processed. The report
explicitly says `specific_outage_catchup_proven: false` and
`bilingual_summary_quality_reviewed: false`. Do not fake/override either
status. A passing audit can be accepted as operational evidence for a
**limited read-only rollout**, with the separate unattended catch-up guarantee
proven by synthetic restart tests and monitored during normal future outages.
The owner still must review summary quality and privacy before permitting
automatic actions or final release acceptance.

If native Gmail history has expired, Gmail responds with `history_cursor_expired`
and the audit ends **incomplete**; run ordinary sync/status and the documented
expired-history recovery instead of fabricating missing events. A large mailbox
may exceed the audit's bounded recent query; narrow the audit time window with
a reviewed code change, not by deleting local messages.

## 3. Human review, security acceptance, and merge gates

Open `http://127.0.0.1:8766` on the laptop, pair locally with the owner-only
read key, and check both mail entries. Confirm the Arabic and English summaries
capture intent and next steps without inventing dates, money, approvals or
unrequested actions. Verify source links open the correct Gmail messages.
Review at least five ordinary real emails privately; look for missed,
misclassified, repeated or malformed summaries. Do not treat classifier output
as a trusted instruction.

Also verify: restart after logout/login, private SQLite and token permissions,
refresh token behavior after a normal access-token expiration, no unintended
Gmail sends, no LAN exposure, and that the real Ollama daemon has cloud
disabled. Google can revoke refresh credentials and may require re-consent.
A successful test **today** cannot prove indefinite OAuth validity.

**Accept only when all are true:**
- [ ] Real preflight validates the right Google account and local model.
- [ ] Baseline saves a real Gmail history checkpoint.
- [ ] Two controlled incoming test emails arrive after the Core shutdown.
- [ ] `check` reports `gmail_sync_probes_passed: true`.
- [ ] Owner approves the actual Arabic and English summary quality.
- [ ] Dashboard pairing, source links, restart and privacy checks pass.
- [ ] Security/diff review is complete and CI passes at each merge head.

Only after those gates: review/merge #39 to `main`, reconcile/re-run #41,
merge #41, reconcile/re-run #42, then merge #42. A stacked PR's green CI is
not a substitute for review against its **final** base. Neither live
acceptance nor merges have been performed by this runbook itself.

## Emergency pause

```bash
bash scripts/run-okal-core.sh mail sync off
systemctl --user restart okal-core.service
```

To disable only the Core service: `systemctl --user stop okal-core.service`.
Do not restore an older live database over the current state; use the
documented out-of-tree restore procedure and account for revoked session
tokens. Read-only sync never sends, archives, trashes or marks Gmail messages
as read.
