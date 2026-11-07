# Natural live browsing and authoritative Memory inspection

Issue [#138](https://github.com/0PeterAdel/okal/issues/138).

## Owner-reported evidence

Owner-reported Production at `f7762b65` is alive, HTTP 200 and SQLite
`chat_schema=2` with quick and foreign-key checks OK. GitHub `main` was at
`17078fe` with fast-forward safety confirmed; **GitHub merges do not deploy
onto the owner's Omarchy computer**. No live Migration or owner account action
is performed by this PR.

Old screenshots show the model claiming OKAL has no terminal/browser tools and
mistaking a sampled `MEMORY_CONTEXT` for the actual saved-memory ledger.

## Behavior

- Explicit Egyptian Arabic live rate/price requests such as
  `بروس كدا وشوف سعر الريال كام النهاردة` enter the existing
  opt-in `browser.search` Action with exactly the owner's bounded query.
  Results are from actual browser receipts, not a model's cached knowledge.
  If not granted, OKAL explains the exact missing permission.
- An explicit owner request such as `اطبعلي كل محتويات الميموري عندك`
  returns a saved **pointer only** to an interactive live-memory view in Chat.
  That view loads `/api/v1/chat/memory-browse` with `status=current` on
  the actual authenticated owner browser, 50 records per page, with a
  refresh button and access to Memory Manager for corrections/forgetting.
  It displays key/content/scope/revision from the existing authoritative
  SQLite ledger using text-only DOM and the existing legacy-secret quarantine.
  Historical assistant responses never store a bulk memory dump, avoiding
  stale copies that survive an owner correction or deletion. A read failure
  is surfaced clearly, not replaced with simulated memories.
- The local language-model prompt now distinguishes its own lack of direct
  tool access from OKAL's independent governed Computer Actions. It does
  not infer current permissions from old memory snippets, historical replies
  or an `external_writes_enabled` field.

## Security and verification

- No automatic grant, external provider account authorization, terminal
  execution, browser credential reuse, new endpoint or SQLite migration.
- Web search is an opt-in **external** request; the query is disclosed to a
  search provider, and search-page snippets do not prove a currency quote's
  validity. Specific ambiguous currency conversions require sufficient units
  and supported source evidence, not an invented live number.
- Owner memory browser remains same-origin authenticated and paginated.
  Explicit forgetting and source versions continue under the existing
  memory-policy UI; this PR does not silently purge any owner memory.
- New tests cover colloquial FX routing and missing grant, live Memory
  inventory marker with no saved raw memory payload, and asynchronous UI
  pagination/quarantine. Full Core/Node/governance checks required.

Focused tests:

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p 'test_chat_public_web.py' -v
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p 'test_intelligence.py' -v
node --test apps/core/tests/test_chat_ui.cjs
```

## Owner-device acceptance (after reviewed code rollout)

With separately granted `system.status` and `browser.search`, ask the exact
three phrases from the owner's screenshots. Confirm disk results show
verified action receipts, live browsing shows a real source or honest error,
and Memory list shows real current records (including owner-selectable
correction/forget). Compare storage against `lsblk` / `df -h`; check that
ungranted tools do not execute. Verify persisted Chat responses do not contain
bulk copies of memory content. Do not run a second Memory migration on schema 2.
