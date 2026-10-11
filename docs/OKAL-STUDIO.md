# Okal Studio

Okal Studio is a local, Arabic-first workspace for the existing voice service. It opens in the default browser, shows the voice phase, accepts typed questions and microphone toggles, and displays text, charts, image galleries, or plans in an adaptive canvas. The home screen includes clearly labeled design previews so the interface can be explored before any agent integration.

## Run it

From the repository root:

```bash
bash scripts/run-okal-studio.sh
```

The page opens at `http://127.0.0.1:8765`. To use another port or keep the browser closed:

```bash
bash scripts/run-okal-studio.sh --port 8766 --no-open
```

Python's standard library is sufficient. No model or package download is required. Start the existing service separately with `systemctl --user start okal-voice.service` if you want to use the microphone and typed requests. With no service running, the interface and the three design previews remain usable.

The typed request calls the existing `ask` route. Voice input calls the existing `toggle` route. The assistant's returned text is shown in the conversation and canvas when the voice session finishes. Today this route can converse and classify intent; it does **not** execute desktop commands, publish posts, submit proposals, or grant an agent new authority. The agent section is a preview of future connections. The canvas does not claim generated charts or images that the current voice service cannot produce.

## Publish real content to the canvas

A local producer can atomically write UTF-8 JSON to `$XDG_RUNTIME_DIR/okal/studio/canvas.json`. The server polls and validates that file, then updates the open interface. This is a display contract, not a command channel. The schema is `okal.studio.canvas.v1`. Every item has `schema_version`, `kind`, `title`, `subtitle`, and `source`.

| `kind` | Additional fields | Limit |
| --- | --- | --- |
| `text` | `body`, optional `highlights` string array | 8,000 characters, 6 highlights |
| `chart` | `series` of `{ "label": string, "value": number }`, optional `unit` | 12 values between 0 and 100 |
| `gallery` | `images` of `{ "src": string, "alt": string, "caption": string }` | 8 local images |
| `steps` | `steps` of `{ "title": string, "detail": string, "state": "done" | "active" | "waiting" }` | 8 steps |

Example, using actual measured data supplied by the publisher:

```json
{
  "schema_version": "okal.studio.canvas.v1",
  "kind": "chart",
  "title": "استهلاك المساحة",
  "subtitle": "نسب استخدمها ناشر محلي بعد قياس الأقراص",
  "source": "فحص الأقراص المحلي",
  "unit": "%",
  "series": [
    { "label": "النظام", "value": 54 },
    { "label": "البيانات", "value": 31 }
  ]
}
```

To try the schema without inventing a measurement, copy the example and change its labels to say "معاينة" or use one of the built-in previews. A real producer should write a temporary file in the same directory and rename it to `canvas.json` only after all bytes have been written:

```python
import json, os
from pathlib import Path

folder = Path(os.environ["XDG_RUNTIME_DIR"]) / "okal" / "studio"
folder.mkdir(mode=0o700, parents=True, exist_ok=True)
target = folder / "canvas.json"
temporary = folder / "canvas.json.tmp"
temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
temporary.chmod(0o600)
temporary.replace(target)
```

The server also accepts image paths under `/media/` with `.png`, `.jpg`, `.jpeg`, or `.webp` extensions. Put those files in `~/.local/share/okal/studio/media/`. Only direct regular files of up to 12 MB are served; URLs, arbitrary paths, SVG uploads, and HTML are not accepted. The three bundled SVG images are original illustration previews under `/assets/`.

## Boundaries and next integration

The server binds only to `127.0.0.1`, checks `Host` and `Origin`, uses a session CSRF token for POST, sets a restrictive Content Security Policy, and forwards only `ask`, `toggle`, and `cancel` to the owner's UNIX voice socket. Canvas content is reduced to a small typed schema and inserted as text nodes. It accepts no browser supplied shell command or arbitrary file path. The local canvas file is still untrusted display data; a future adapter must attach verified source and action status before calling a result "completed".

The interface borrows the idea of a dynamic voice HUD and cards from [Mark-LV](https://github.com/FatihMakes/Mark-LV), but uses new code, artwork, and layout. Mark-LV's noncommercial license is not imported into Okal.
