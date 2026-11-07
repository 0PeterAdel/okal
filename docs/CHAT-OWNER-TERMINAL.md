# OKAL owner-approved terminal (opt-in)

Issue #134. This is an **isolated terminal command runner**, not an unrestricted
host/root shell, interactive PTY, a general coding agent, or a Production deployment.

## From Chat

- In Actions, switch to **Assisted** or **Autonomous** and enable
  `system.terminal`. This grant does not activate silently on upgrade.
- Type an exact command with an explicit prefix, for example
  `نفذ في الترمينال: df -h` or `Run command: uname -a`.
- The Chat creates a durable proposed action. It displays the **exact argv**
  and narrow mounted-directory list. Every terminal run **always** waits for
  an exact, expiring owner confirmation, even when mode is Autonomous.
- After execution, the Action card displays actual bounded stdout and a
  durable receipt. Nonzero exit/timeout/interruption is **not** reported
  as success; no blind retry of ambiguous effects. `continue`/Cancel use
  the existing durable Actions lifecycle and versioned grants.
- For raw local storage questions, the separate read-only `system.status`
  tool should be used without executing a terminal command.

## Security boundary

- The native process is invoked with a validated **/usr/bin argv vector**;
  arguments are not concatenated into a shell. User-authored `bash -lc`
  can run complex scripts *inside the same sandbox* only after exact approval.
- `sudo`, `su`, `doas`, `pkexec`, `mount`, `umount`, `setcap`,
  `chown`, `chmod` and direct `bwrap` are denied as the first executable.
  These guards are not a substitute for the OS namespace; a shell may invoke
  other binaries, still confined by its isolation and existing service UID.
- The terminal uses an unprivileged Bubblewrap namespace with network/PID/IPC
  isolation, empty private HOME, /usr read-only, /sys read-only, private /tmp,
  minimal /dev and /proc; no bearer credentials or source browser sessions.
  It inherits none of the mail/Google/model environment secrets.
- Only **narrow** already-granted roots may be mounted. Even if files have
  a broad `/home/okal` grant, the terminal refuses to bind that ancestor or
  a Core-state ancestor; hidden directory ancestors are excluded. Commands
  cannot see the entire owner's home from that grant.
- Existing `system.command` named profiles retain their separate semantics.
  External network use belongs to the explicitly granted, isolated browser
  adapters. No unrestricted desktop shell, root, hardware, account or provider
  authorization is inferred from this terminal permission.
- Commands can modify explicitly writable narrow roots; read commands can
  reveal data inside granted roots. Carefully inspect the approval preview
  and do not grant folders containing secrets. Approval expires and policy
  revocation invalidates queued runs.

## Verification and limits

Run full Core Python/Node/governance CI, then focused:

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p 'test_chat_terminal.py' -v
node --test apps/core/tests/test_computer_ui.cjs
```

Tests use synthetic policy/paths and mocked native execution only. They verify
no execution without approval, `--unshare-all`, bounded argv, no broad home
mount, and privilege/read-only denials. They do **not** prove installed
Bubblewrap works inside the actual hardened `okal-core.service`. Post-deploy
owner-host acceptance must use safe read-only commands first, compare with
the native system, test revocation and verify failure paths before any file
mutations. No owner state, OAuth or Production code is changed by this PR.

For truly unrestricted native terminal/interactive commands, a distinct
owner-session capability with a separate privilege, session and review design
would be required. It must not be silently implemented by weakening the Core
service sandbox. Cognitive Memory V2 #128 remains open.
