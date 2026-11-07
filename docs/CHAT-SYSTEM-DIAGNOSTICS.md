# OKAL Chat local-device diagnostics

Issue #130. Scoped to computer diagnostics; this PR is not a Production deployment.

## Behavior

- Explicit owner questions about attached hard drives, number of block devices,
  `lsblk`, `df -h` and disk/free storage in Arabic or English route to a
  **deterministic `system.status` plan**, not a speculative conversational reply.
- The plan uses the existing owner-only Actions API, policy, durable action ledger
  and receipts. The UI starts read-only ready actions and renders exact evidence.
- The status adapter reads bounded Linux sysfs block-device metadata and the
  running service's mount information/statvfs. It excludes partitions as devices,
  loop/ram/zram, private service mounts and root-level pseudo-filesystems.
  Attached disks are *block devices*, not necessarily individual physical bays.
  Container/service mounts can differ from the owner's desktop view.
- Results are safely text-rendered, maximum 32 disks and 16 mounted entries.
  No shell, sudo, password, cloud query or filesystem write is invoked.
- If `system.status` has not been granted in Actions, the chat says exactly
  which permission must be enabled. No implicit permission migration.

## Verification

Run local full Python/Node suites and governance checks. Focused commands:

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p 'test_chat_system_diagnostics.py' -v
node --test apps/core/tests/test_computer_ui.cjs
```

Manual owner acceptance after a reviewed deployment: ask `عندي كام هارد
متوصل؟` and `Show disk space on my computer` from Chat; confirm the
receipt lists observed disks and capacity, then disable the tool and verify
the same request fails without any fabricated result. Compare against
`lsblk` and `df -h` locally: the OS's physical inventory and systemd
namespace mount views may differ. No change to live SQLite schema or action
grants is authorized by this PR.

## Remaining

- General web discovery/search and arbitrary URL reading remain a separate
  reviewed browser extension. The present browser adapter requires grants
  for exact origins.
- Owner-authorized terminal access is a separate high-risk design: the
  existing `system.command` executes owner-configured profiles only, in
  a namespace with exact approval and no unrestricted shell/root authority.
- Memory V2 Production cutover acceptance remains open under #128; owner
  confirmed live schema 2 but an older code SHA. Do not re-run migration.
