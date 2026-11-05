# Stage 3 owner-device release evidence

Verified on the owner's Omarchy computer, 2026-11-05. Task
[#119](https://github.com/0PeterAdel/okal/issues/119). No new memory engine was
chosen, installed or implemented. No Gmail send or external calendar write was
performed. All modifying acceptance scenarios used synthetic resources.

## Five gates

| Gate | Result | Observed evidence |
| --- | --- | --- |
| 1. Production/dependency audit | Passed | Actual installed unit, drop-ins, PID/cwd/interpreter, clean FF-only main, native binaries and desktop environment inspected. |
| 2. Private online backup | Passed | Live SQLite backup API; quick_check ok, zero foreign-key errors; directory 0700, DB 0600; old code/unit and rollback preserved privately. |
| 3. Staged deployment | Passed | Detached archive and fresh hash-locked environment tested before deploying; healthy real service, exact logo, persistent UI Chat/Memory and legacy workflows verified. |
| 4. Broad owner capabilities | Passed within explicit supported scope | Assisted home write grant, separately reviewed mount carve-out, actual file receipts and native private/code EROFS denials. Literal root/all-files access remains unavailable. |
| 5. Real service E2E | Passed | 32-scenario reproducible HTTP audit, additional legacy writes, real English/Arabic UI approval/recovery, read-bearer denial, policy revision and restart checks. |

These results certify the bounded supported capabilities below. They do not
claim root access, complete access to every file, provider sending, cold boot or
authentication/MFA bypass.

## Release identity and installed service

Production checkout: `/home/okal/Projects/Okal`, branch `main`. Before deployment:
`4aba4f3ff09c34e26c343f1818917df9d5170f8b`. Stage 1 and Stage 2 had merged but
were not deployed there. First reviewed deployment:
`d0946631f1609590a4a7b19545cdaf5bc8ae22e6` via security
[PR #120](https://github.com/0PeterAdel/okal/pull/120). Accepted application code:
`efd3cb52f672877823e4b4f95850f4c7c8c50a29` after transport
[PR #121](https://github.com/0PeterAdel/okal/pull/121) and read-bearer hardening
[PR #122](https://github.com/0PeterAdel/okal/pull/122). This evidence PR adds only
the opt-in audit runner and this report; the final checkout SHA is recorded on
the rollout issue after its reviewed merge.

Installed base unit: `~/.config/systemd/user/okal-core.service`. Existing
`90-okal-main-release.conf` and `90-okal-single-home.conf` were preserved.
New overrides: `90-okal-stage3-python.conf`, `90-okal-stage3-home.conf`, mode 0600.
Only Core was restarted. Its effective cwd and PYTHONPATH use the Production
checkout; its interpreter uses the newly staged environment at
`~/.local/state/okal-core/stage3-venv-d4eae648a80f/bin/python`. The environment
name records the dependency baseline; the unchanged action lock's SHA-256 is
`50da4d788a0326797344ba7fbbd78d66e5d6b0375924fe8ae28db51536a77fd1`.

The installed service's live mount table showed home writable, `.config` and
`.local` read-only, private Core state writable through its deeper carve-out,
and the deployed repository read-only. Native exclusive-create attempts through
`/proc/<MainPID>/root` returned `EROFS` in configuration and deployed code;
neither probe created a file. `ProtectSystem=strict`, `ProtectHome=read-only`,
`NoNewPrivileges`, private temporary storage and existing address-family
restrictions remain. The composed unit passed `systemd-analyze --user verify`.
Hyprland, Wayland, DBus and XDG runtime variables were present in the service.

## Backup, dependencies and regression evidence

Private pre-deploy backup:
`~/.local/state/okal-core/owner-backups/stage3-deploy-20261104T235711Z/`.
SQLite SHA-256:
`685d9af0db24d6c6570ed79ec56d656267aa52883cbc0b3c20db4e70186923da`.
An earlier verified online snapshot is preserved separately. Installed unit
copies, old source archive, manifest and rollback instructions remain private.
The active DB was never replaced; final quick_check and foreign_key_check pass.

Runtime: Python 3.14, Playwright 1.64.1, Chromium 156.0.8078.79, Bubblewrap
0.13.1, pdftotext 26.10.0, Hyprland 0.57.0 and Ollama 0.40.13. Hash-locked
installation succeeded in a new environment; `pip check` found no broken
requirements. No dependency or license change beyond reviewed Stage 2 was made.

The final isolated application regression passed 481 Python tests and 79 Node
tests. A detached archive passed the preceding 479-test suite under umask 077,
process restart smoke and real synthetic action acceptance before the initial
deployment. The HTTP policy regression brought the count to 480; the matching-Origin
read-bearer regression brought it to 481.
Native PDF parsing ran on this host; CI's missing-native skip is not host proof.
Governance and whitespace checks passed.

All six current-head GitHub checks passed on each runtime PR: Core Python
3.12/3.14, TaskBoard Python 3.12/3.14, Repository policy and Markdown. Review and
expected-head squash evidence is on the PRs. Initial PR-template failure was
corrected and rerun; no failed check or protection was bypassed. The owner was
assigned and AI verification was recorded before merge without claiming human
approval. The supplied bootstrap's clean-preflight exit bug was corrected in a
private copy; its umask-dependent security fixture was fixed in PR #120.

## Real Production acceptance

The standalone runner uses only HTTP against `127.0.0.1:8766`, with the same
owner-origin gate as the UI. It never imports Store/Engine, launches a scheduler
or grants standing permissions. The final hardened run recorded 32 passing scenarios (31 without the optional
real read-token check):

- List/read; new file/directory; copy and move/rename; source and preview hashes.
- Rename, trash and extension-organization recovery, with unchanged hashes.
- Non-overwrite collision; scope escape, traversal, symlink and private-state
  denial; missing-origin 401 and cross-origin 403.
- Hostile synthetic document read as inert evidence, unchanged policy, and a
  real local comparison report with pinned-model interpretation and source hashes.
- Isolated Chromium local/public reads, form submission and verified download.
- Cancellation before a write and during a real slow browser request.
- Revoke/regrant changed the policy generation; the old approved preview was
  denied and created no file. Stale synthetic previews were cancelled afterward.
- Existing Tasks/Calendar reads and system status.
- Actual window IDs, allowlisted Foot launch, observation of its new window,
  verified focus and closure of only that synthetic window.

Representative final receipt IDs: file chain
`34ad7fe5c40e439d828e356cbb5d6381`; organization/recovery
`a953b4f3047e4d88860bdebfcccf0f31`; browser download
`1253ff1f04e048e7b7ec600756fdcd0a`; running cancellation
`464d0911eb7944428ac43c05b7761997`; revoked preview
`fbd2015564e345808ec462cd493e5883`; native focus
`55e73112e7d544a3b2336058d0a76091`. Full receipts stay private in the backup
directory. The final HTTP receipt bundle SHA-256 is
`fe43a595fdf7e9de69e44ee9a835d677f75310af07f0419a50a032eef3dc44e9`.

Additional actual HTTP writes created/read back a synthetic Task, then dismissed
it; saved/read back a local Calendar goal, then cancelled it. Cached Gmail read
worked. The existing Gmail doctor made the real provider account check and
verified the pinned local model; send_enabled remained false. OAuth and provider
configuration were preserved. Existing calendar caches and local views remain;
Google's historical `primary` sync failure warning predates rollout and is not
evidence that all connected calendars failed.

The real Chat UI saved permissions and generated English/Arabic file plans.
The Arabic destination did not exist before exact approval; both approved files
matched their requested UTF-8 contents afterward. An initial English plan tried
to mkdir an existing folder and failed honestly without execution; stating that
the folder already existed yielded a valid one-step plan. This remains a model
planning limitation, not guaranteed natural-language success.

The UI saved a synthetic scoped memory, recalled “silver ibis”, and showed both
verified action cards after reload/restart. Exact chat/memory/action-history
payloads matched before/after restart (shared SHA-256
`2a54d4e3734516054fab6e7dbf2eda61e25cd2c5c800093841b97ccc287683c4`).
localStorage/sessionStorage contained zero entries. The synthetic memory was
then forgotten through the UI; associated recall text was redacted as designed.
UI receipt recovery preserved both English and Arabic files in private recovery
with their original hashes; Arabic recovery was repeated on the hardened service. Synthetic workspaces and receipts are retained for inspection.

A real temporary `inbox:read` device token could read summaries (200) but its
Actions and Chat requests were denied (401), including when combined with a
matching owner Origin. Both synthetic test tokens were revoked.
Production retains the existing local auto-unlock mode. It was not changed into
key-protected mode to manufacture session evidence. Remote Access is unconfigured
and stopped; existing remote authentication requirements remain unchanged.

During acceptance a real defect was found: policy saves returned 422 because
the transport passed `policy` to the engine's `payload` argument. PR #121 fixed
the binding and added HTTP save/readback/stale-revision coverage. Real policy
save, UI save, revocation and regrant passed after reviewed deployment.

A stricter negative test then found that the local auto-unlock owner gate ignored
an Authorization header when Origin matched. PR #122 explicitly rejects bearer
headers on owner POST routes. It passed 481 Python/79 Node tests and fresh CI;
after reviewed deployment, the full 32-scenario audit and actual UI recovery
passed. Normal owner-browser behavior and read-device GETs remain available.

## Approved scope and remaining limits

Final policy: Assisted, writable `/home/okal`, 26 of 29 typed tools enabled;
browser origin `https://docs.python.org`; desktop app `foot`; no command profiles
or action mail accounts. The temporary loopback test origin was removed and its
server stopped. Existing independent grants were preserved. No additional
mounted volume was found/implicitly approved. Additional origins/apps need
separate explicit owner grants through Actions.

Home access excludes hidden components, symlinks, foreign/special/multiply-linked
files, private state and deployed-code writes; files are bounded to 8 MiB.
Enumeration is capped. Root-only/system files, literal `/`, unsupported formats,
personal browser profiles, credential/financial form filling and MFA/CAPTCHA
bypass remain unavailable. No unrestricted root/shell capability exists.
Command mounts cannot expose a broad home/private-state ancestor.

The inherited optional FullCalendar vendor asset is absent and logs 404;
existing calendar fallback/local save/readback work. This rollout does not add
that optional frontend dependency. Desktop launch acceptance alone does not mean
readiness: the audit separately observed the actual synthetic Foot window.
No cold-boot, suspend or phone/remote acceptance is claimed by these five gates.

## Reproduce and recover

Use the tested interpreter, with Actions idle. Through the owner UI temporarily
grant `http://127.0.0.1:8798` alongside the public origin, Foot, and the tested
typed tools. Keep Assisted mode. The runner temporarily revokes/restores
`files.write`, invalidating older pending plans; it never widens standing grants.
If interrupted just after revocation, restore the intended grant in the UI;
never overwrite a concurrent policy revision. Use a new workspace name and an
owner-private output directory:

```bash
python apps/core/tools/production_actions_acceptance.py --execute --prepare \
  --workspace /home/okal/OKAL-Stage3-Acceptance-NEW-UNIQUE \
  --output /OWNER-PRIVATE-DIRECTORY/receipts.json
```

The runner refuses an existing workspace with `--prepare`, never removes test
data, closes its loopback-only server and closes only its observed new Foot
window. Remove the temporary loopback grant afterward. A protected-mode owner
may provide a private session-cookie file with `--cookie-file`; no credential is
printed or placed in a URL. For the 32nd scenario pass `--read-token-file` with
private JSON from the normal `device-add` operator command; revoke that temporary
device afterward. No fixture runner sends email. Do not run it on personal folders.

For code/unit rollback use the privately saved old code/interpreter and unit
instructions in `ROLLBACK.md`; remove only new Stage 3 drop-ins after cancelling
work/revoking grants. Preserve the current DB, OAuth and action receipts. Never
blindly restore an old SQLite snapshot over newer owner writes. Receipt-based
recovery is separately authorized and refuses changed/occupied resources.
