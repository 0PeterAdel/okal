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

No bulk-deletion script is included. The owner-reported local archive is recorded
below; no remote archive tags have been verified. Remote deletion is pending
these gates. Closing PRs is reversible while their branches are preserved.
Keep private backup locations in the owner's local records, not public uploads.

For example, after local preflight, inspect the retained voice branch:

```bash
git fetch origin feat/voice-acceptance
git log -1 --oneline origin/feat/voice-acceptance
```

## Runtime migration is separate

Do not run old voice/agent installers to install the new center. Inventory exact
enabled services and Hermes cron entries before replacing them; record restore
steps. Never disable all services sharing a name prefix. Only stop a replaced
schedule after its replacement passes and the owner consents. An explicit owner
decision to pause a feature without replacement is separate from a successful
migration; record that distinction and preserve its restore command.

The installation PR must provide idempotent install/upgrade/uninstall,
backup/restore and boot tests. No home-directory cleanup, token deletion,
browser-profile migration or model-cache removal is performed by this reset.

## Owner checkpoint: 2026-10-30

Evidence source: terminal output supplied by the owner. This session cannot
inspect the laptop directly; these are reported results, not independent device
verification. No private audio, browser profiles or account tokens were uploaded.

| Item | Reported state | Consequence |
|---|---|---|
| Git history | Complete bundle verified with `git bundle verify` | Committed history preserved locally |
| Worktree tips | Nine tags under `archive/20261029-221730/` | Detached tips retained; tags are local |
| Working trees | No tracked modifications reported across nine worktrees | Not permission to delete ignored/untracked files |
| Voice experiments | Audio, results, environments and build files remain locally | Separate private-file backup still required |
| Freelance environment | Main checkout links to the environment inside `okal-freelance-pilot` | Keep both paths unchanged for now |
| `okal-voice.service` | `inactive`, `dead`, `disabled` | Voice deliberately paused, not replaced by the new core |
| `voxtype.service` | Active in the earlier inventory; not targeted | Leave the independent dictation service alone |
| New core/mobile/Gmail | Not implemented or deployed by this reset | No startup or account functionality claimed |

The Git bundle does not contain untracked/ignored files or installed service
configuration. Do not interpret a clean `git status` as a complete backup.
Do not move the freelance worktree: the symlink and virtualenv executable paths
may depend on its current location. Local files remain untouched until an
explicit protected backup and dependency check are complete.

The owner paused only the exact voice unit with:

```bash
systemctl --user disable --now okal-voice.service
```

To restore the old voice service later, after verifying its original paths and
configuration still exist:

```bash
systemctl --user enable --now okal-voice.service
```

### Next gate

1. Review proposed ADR-013 and resolve the applicable human-review policy before
   merging PR #37. Passing automation is not human approval.
2. Begin R1 from reviewed `main`, using one implementation task and PR. Deliver
   only the authenticated durable inbox, mobile-readable shell and service
   lifecycle; keep real account connections and external writes out of R1.
3. Prove the R1 lifecycle on the owner laptop, then add the read-only Gmail digest
   in R2. Do not open parallel voice/social/freelance implementation tracks.
4. Treat branch/worktree deletion as separate maintenance, not a prerequisite
   for the first useful workflow. Retained archives do not run agents or services.

## Review limitations

The external ShiftCore handbook URL was unavailable during review. Repository
AGENTS, CONTRIBUTING and GOVERNANCE were read and remain unchanged. No merge or
policy exception is performed. The Solo Maintainer review date in GOVERNANCE
needs maintainer attention; this reset does not silently renew it.
