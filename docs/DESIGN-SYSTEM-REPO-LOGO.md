# OKAL Design System — Git-tracked master logo

The primary OKAL logo on this branch is the exact approved
`1254×1254` WebP committed at:

`apps/core/src/okal_core/static/assets/okal-master-hq.webp`

**The owner must add and push the binary once from their Omarchy machine.**
The branch intentionally has no substitute graphic or automatic external
download. A fresh clone of this branch, once the asset is committed,
contains the logo and works offline with no owner home-directory copy.

The web application references only:
`/assets/okal-master-hq.webp?v=1254-design-v1`
for both sidebar and Chat hero. FastAPI serves the file from the checkout
via `STATIC / "assets" / "okal-master-hq.webp"`. The old
`/assets/okal-identity` route remains a backward-compatible alias to the
**same Git file**. It does not check `~/Downloads`,
`~/.local/state/okal-core/brand`, or any private PNG.

## Owner setup

Use the sibling Git worktree to avoid switching the running Production
checkout away from `main`. A single-branch fetch may update only `FETCH_HEAD`;
explicitly create the tracking ref first with:

    git -C ~/Projects/Okal fetch origin \
      '+refs/heads/feat/okal-design-system:refs/remotes/origin/feat/okal-design-system'

Then create
`~/Projects/.okal-design-work` as a separate worktree of that same repo.
Copy `~/Downloads/okal-master-hq.webp` into the path above, verify that
it is WebP VP8X and 1254 by 1254, `git add`, commit using conventional
commits, and `git push` to the feature branch.

Do not commit the private original PNG, user keys, runtime state,
temporary virtual environments, or experimental folders.

## Acceptance

After committing the asset, on the design worktree run:

    bash scripts/preview-design-logo.sh

It creates a temporary source snapshot and Python environment, verifies
that the logo is **in Git** before serving, runs Python brand/API/UI tests
and opens the page on loopback port 8767. The running Production service
on 8766 and its database are untouched. Test in Firefox with
Ctrl+Shift+R if the image is cached.

The logo asset and design branch should only be merged to `main` after
owner visual approval and successful CI. This work is independent of
older PR #114; do not merge both variants without reconciling them.
