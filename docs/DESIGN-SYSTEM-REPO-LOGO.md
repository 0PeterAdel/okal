# OKAL Design System — single Git-tracked logo

The only active OKAL logo is the owner's approved transparent
**1254 × 1254 WebP** committed at:

`apps/core/src/okal_core/static/assets/okal-master-hq.webp`

The file is **already committed and pushed to GitHub**. Any fresh clone of
this branch (and of `main` after an owner-approved merge) includes the
exact same artwork. No external image URL, local Downloads file, private
state override, or post-installation image copy is necessary.

## Frontend and backend source of truth

Both the Sidebar and Chat hero reference:

    /assets/okal-master-hq.webp

FastAPI serves the file from `STATIC / "assets" / "okal-master-hq.webp"`.
The legacy `/assets/okal-identity` and `/assets/okal-master.webp`
URLs return the **same high-resolution bytes**, not an old thumbnail.
**Do not append a cache-busting query string** to image URLs: the
FastAPI global request policy rejects unsupported query parameters with
HTTP 400. All local responses already set `Cache-Control: no-store`,
so `?v=...` is unnecessary. A regression test follows the exact
`<img src>` URLs from the rendered home page through the same-origin
HTTP middleware, and requires a 200 WebP response with bytes identical
to the Git-tracked logo.

The obsolete 9 KB `okal-master.webp` file was removed from Git.
The old private-logo installer and PR #113 logo preview are obsolete and
are removed from this feature branch. This does not delete or alter
anything in a user's home directory, private SQLite state, OAuth
credentials, or running Production instance.

## Verification and visual acceptance

On the feature branch worktree:

    git ls-files apps/core/src/okal_core/static/assets/
    bash scripts/preview-design-logo.sh

The preview starts only on local port 8767, using an isolated temporary
working directory, Python environment and SQLite database. It verifies
the Git-archived image dimensions and runs the logo route and HTML
contract tests before serving it. Production on 8766 is untouched.

In Firefox refresh with Ctrl+Shift+R to invalidate stale image caches.
Inspect the hero logo, Sidebar logo, and direct asset URL. Only merge
into `main` after review and all required CI checks pass.

The old PR #114 has overlapping changes and should not be merged
separately alongside the design branch.
