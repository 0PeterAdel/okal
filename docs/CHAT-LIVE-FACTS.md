# Live public facts and conversational routing — OKAL

Issue #140. This code does not deploy to the owner's computer.

## Purpose

The screenshots showed a verified two-disk status receipt, followed by an
unrelated currency/weather question that inherited the earlier hard-drive
topic. Real-time public questions must be routed **before** general Ollama
generation, or explicitly clarified when essential location is missing.
A saved tool receipt or old MEMORY_CONTEXT must never substitute for current
weather or exchange rates.

## Behavior

- Egyptian Arabic `بروس كدا وشوف سعر الريال كام النهاردة` creates a
  `browser.search` plan for **SAR to EGP** as the explicitly disclosed default
  interpretation; if the owner says "مقابل الدولار", that requested pair wins.
- A weather/temperature request with an explicit city creates a bounded public
  `browser.search` plan using the owner's own city and requested day.
- Without a city, OKAL asks "في أنهي مدينة؟" **without external network I/O**.
  A short owner follow-up city is accepted only when the immediately preceding
  durable Chat response is the trusted `location_clarification` response.
  The Africa/Cairo timezone is **not** proof the user is in Cairo.
- Local CPU/GPU/hard-drive temperature, storage questions, normal science,
  memory and Gmail requests do **not** trigger a public weather search.
- New public search content still requires the exact owner
  `browser.search` grant, valid policy and the existing sandbox, networking,
  approval/receipt protections. Web content can never grant its own authority.
- Model generation emphasizes the latest question and avoids silently
  importing the previous disk topic into an unrelated answer. Misleading
  `external_writes_enabled:false` was removed from model input; this **does
  not** enable any external writes. Tool permissions are unchanged.
- Search receipts are public content, not verified financial advice or
  meteorological data. The current UI presents observed sources/excerpts;
  a later sourced answer-synthesis step must distinguish published data from
  search snippets and report verification failures honestly.

## Tests and owner acceptance

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p 'test_chat_live_intents.py' -v
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p 'test_chat_public_web.py' -v
node --test apps/core/tests/test_chat_ui.cjs
```

After reviewed release and verified online owner backup, enable only necessary
read grants in Actions and test these messages in a new conversation:

- `عندي كام هارد متوصل؟` — existing read-only verified device status.
- `بروس كدا وشوف سعر الريال كام النهاردة` — real public web plan, never
  repeated hard-drive explanation or made-up FX number.
- `بروس كدا وشوف درجة الحرارة كام النهارده` — ask which city.
- `أسيوط` — continue weather search from that explicit clarification.
- `درجة حرارة المعالج كام؟` — **not** a public weather request.
- Revoke `browser.search` and repeat; confirm precise permission denial,
  never model-fabricated price or temperature.

GitHub CI does not verify the owner's Chromium access, external Google site
consent/CAPTCHA, actual local Ollama output quality, or production provider
credentials. Do not re-run Schema 2 migration or overwrite live SQLite to
deploy this change. Issue #128 remains the production acceptance source.
