# Chat Action receipts — readable source-grounded UX

Workstream B of [#140](https://github.com/0PeterAdel/okal/issues/140).

## Behavior

- A verified computer Action may contain more evidence than the assistant's
  short text bubble. The bubble expands to a usable maximum width on desktop,
  while remaining fluid on small screens.
- Local storage evidence displays the actual block-device count, device names,
  sizes and mounted free space. Technical tool arguments/receipts remain
  available in collapsed disclosure controls.
- Public browser cards show only observed source titles, bounded excerpts and
  safe HTTPS links. Terminal cards show exact approved argv and verified stdout.
  No result is fabricated by the model or changed in the browser.
- The control area groups actual actions rather than presenting giant buttons
  in a single vertical column. Focus outlines and accessible roles remain.
- **Recovery is only displayed when a receipt contains supported reversible
  operations.** Successful read-only disk, browser and information requests
  never show a misleading Recover button.

## Verification

```bash
node --test apps/core/tests/test_computer_ui.cjs
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests
```

On the owner's approved deployment, verify desktop and mobile width, keyboard
focus, an actual `system.status` receipt, one public browser receipt, and
that read-only cards have no recovery affordance. Reversible file operations
must retain their explicitly confirmed recovery capability.

No backend permissions, database schema, Ollama configuration or Production
service changes are performed by this UI-only code PR. The screenshot and
GitHub CI do not establish owner-host browser rendering acceptance.
