# Repository Reset and Recovery

Snapshot: 2026-10-29. Tracking: [#36](https://github.com/0PeterAdel/okal/issues/36).
New scope: [Personal Assistant Plan](../wiki/Personal-Assistant-Plan.md).

## Preservation boundary

Old PRs may be closed as deferred/superseded, not as completed work. Their branches
remain until archive gates pass. Runtime files, dependencies, CI/security gates,
installed commands and existing history are not removed or rewritten.

Original main: `a1588a3be8007923d41109c1a7c5469520d21846`.
[Full branch snapshot](migration/2026-10-29-branches.json).
An inventory is not a backup; a recorded SHA alone does not justify deletion.

## Legacy disposition

| Branch | PR | Treatment |
|---|---|---|
| `feat/voice-acceptance` | #11 | Defer; retain evaluation |
| `feat/mostaql-proposal-pilot` | #22 | Defer until Khamsat acceptance |
| `feat/khamsat-request-scout` | #29 | Salvage read-only adapter |
| `feat/local-x-publisher` | #31 | Supersede standalone publisher |
| `feat/local-gmail-digest` | #33 | Salvage retrieval/tests; centralize scheduling |
| `feat/khamsat-autoreply` | #34 | Salvage review/receipts; remove Hermes coupling later |
| `feat/voice-stack-v2` | none | Preserve historical experiment |
| `test/social-evidence-dirty-source` | none | Preserve regression reproduction |

PR #34 targets #29's branch. Preserve both tips and review their ancestry before
cherry-picking. Closing a parent PR does not integrate its code. #29's observed
blocker was commit-message policy; this is not permission to bypass checks.

Issues #21/#28/#30/#32 can be closed as superseded/not-planned in their old
standalone form once linked to #36. Useful acceptance criteria remain in the
staged plan; closure is not evidence of live account testing.

## Owner-local preflight

The checkout is not mounted here. These commands inspect, without switching
branches or changing tracked files:

```bash
cd /home/okal/Projects/okal
git status --short --branch
git worktree list
git branch -vv
git log -5 --oneline
```

If HEAD is detached, preserve it on a named local branch before switching.
Preserve staged/unstaged/untracked files deliberately in every linked worktree.
Do not auto-stash, reset, clean or overwrite. Local-only commits are absent from
a remote snapshot; Git bundles do not back up untracked/working-tree files.
Do not publish credentials from custom local configuration.

## Archive-before-delete gates

1. Complete owner-local preflight and preserve local-only/private work.
2. Re-read each exact remote head; stop if it differs from the snapshot.
3. Create an archive tag for that exact head and verify the remote tag.
4. Create and verify an offline bundle of retained refs. Keep private runtime
   data in a separate protected backup, never in a public Git archive.
5. Verify no active PR/worktree depends on the branch; treat #34/#29 together.
6. Review the explicit deletion list, then delete only validated task branches.
   Never delete main or use broad branch-name globs.

No bulk-deletion script is included. Archive tags/bundles are not claimed to
exist. Remote deletion is pending these gates. Closing PRs is reversible while
their branches are preserved. Later record actual archive tags and bundle
locations beside the snapshot; restore from those verified refs.

For example, after local preflight, inspect the retained voice branch:

```bash
git fetch origin feat/voice-acceptance
git log -1 --oneline origin/feat/voice-acceptance
```

## Runtime migration is separate

Do not run old voice/agent installers to install the new center. Inventory exact
enabled services and Hermes cron entries before replacing them; record restore
steps. Never disable all services sharing a name prefix. Only stop a replaced
schedule after its replacement passes and the owner consents.

The installation PR must provide idempotent install/upgrade/uninstall,
backup/restore and boot tests. No home-directory cleanup, token deletion,
browser-profile migration or model-cache removal is performed by this reset.

## Review limitations

The external ShiftCore handbook URL was unavailable during review. Repository
AGENTS, CONTRIBUTING and GOVERNANCE were read and remain unchanged. No merge or
policy exception is performed. The Solo Maintainer review date in GOVERNANCE
needs maintainer attention; this reset does not silently renew it.
