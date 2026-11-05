# Owner-device Stage 3 rollout

Task [#119](https://github.com/0PeterAdel/okal/issues/119). The owner explicitly
authorized production deployment and broad owner-home access in Assisted mode.
No new memory engine is selected or implemented.

## Reviewed permission adjustment

The installed unit has `ProtectSystem=strict`, `ProtectHome=read-only`,
`NoNewPrivileges=true`, private temporary storage and a writable private Core
StateDirectory. The historical tracked unit is not the installed configuration.
Only inspect environment key presence; never publish unit secrets or OAuth state.

`apps/core/tools/render_action_service_scope.py` renders a separate additive
drop-in after explicit `--owner-authorized-wide-home`. It does not install it,
change credentials, start services, grant tools or approve plans. It permits
writes beneath the owner's home, retaining strict system protection, read-only
home protection and no privilege elevation. Deeper read-only mounts protect all
existing hidden home entries, known credential/config directories and deployed
application code. The existing, deeper StateDirectory write carve-out remains.
No external volume is implicitly authorized. Regenerate/review the drop-in when
adding private top-level directories; this is a deployment snapshot, not a
universal secret classifier. Newly created hidden paths remain denied by Files.

Security impact: the Core UID can now write ordinary home files. Exact owner
plan approval in Assisted mode, typed operations, no-clobber writes, inode/hash
previews, hidden-path/symlink exclusions and receipts remain mandatory. This
boundary does not sandbox trusted desktop applications against their own UID.
Desktop launch still needs an explicit application grant. Browser origins and
command profiles remain separately granted. Command profiles reject roots that
contain the home or private state: their directory mounts cannot inherit Files'
hidden-path filtering. Broad home grants cannot modify the source checkout,
enforced by Files as well as the service's read-only deployment mount.

Literal root-only files, hidden paths, symlinks, multiply-linked files, files
over 8 MiB, unapproved volumes and private runtime data remain unsupported.
No sudo, root execution, unrestricted shell or personal browser profile is added.

## Deployment and rollback

Use the owner's supplied bootstrap only after inspection. Its original clean
preflight returned status 1; use an adapted private copy with a positive clean
assertion. Stage without deploying first. Online SQLite backup must pass
`quick_check` and `foreign_key_check`, with backup directory 0700 and DB 0600.
Save old/target SHAs, checksum and actual installed unit privately. Create a new
hash-locked environment; never update the serving environment in place.

After the security PR's current-head CI and documented AI verification pass,
render the drop-in privately, inspect it, validate the composed unit, and install
only that drop-in plus an interpreter override. Preserve other unit/environment
settings. Stop only Core, fast-forward the clean main checkout to the reviewed
SHA and start Core. Require real service receipts and browser UI acceptance.
Offline synthetic tests alone do not satisfy rollout acceptance.

Rollback: revoke action grants and cancel work through the owner UI; stop Core;
move only the new Stage 3 drop-ins to the private backup (do not remove previous
drop-ins); restore the prior reviewed code/interpreter using an inspected clean
checkout; daemon-reload and start Core. Preserve the current database and
filesystem receipts. Never restore an old SQLite snapshot over newer owner data.
Additive schema tables can remain. Record any reconciliation needs explicitly.

## Verification

Targeted regression covers unit-path injection, symlink checkout rejection,
retained hardening, private entries, source-code write denial and command mount
exclusions. Run full Core Python/Node regressions and governance checks. Then
validate actual home writes, unchanged private/code read-only mounts, browser
sandbox and desktop session through the Production service. Release evidence is
recorded separately after live execution; this document is not proof of it.

## Read-device transport boundary

Live acceptance also tests a read bearer combined with a matching Origin. Owner
POST authorization explicitly rejects any Authorization header, including local
auto-unlock mode; a paired read device cannot borrow the browser-owner path.
Normal UI requests use the configured owner session/origin path without bearer
headers. Read-only GET behavior and remote Access requirements are unchanged.

Observed owner-device outcomes are in [Stage 3 release evidence](STAGE3-RELEASE.md).
