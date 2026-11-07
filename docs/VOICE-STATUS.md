# Voice — under development

**Status: experimental local voice lab; not released as an integrated
OKAL Chat feature.** This is a public product-status document, not a
promise that voice already works on fresh installs.

## Vision

A private, natural voice interface that understands Egyptian Arabic,
English and code-switching, remembers conversational context and can
offer the same clearly authorized computer actions as the text assistant.
The long-term voice experience should support a friendly daily briefing
and deliberate follow-up questions, without inventing executed actions.

## What exists in the repository

The experimental `apps/voice/` package and `scripts/*voice*.sh`
contain local audio capture/transcription, intent classification, local
speech-synthesis trials and quality benchmarks. The
[historical Local Voice guide](LOCAL-VOICE.md) documents experiments
including PipeWire, faster-whisper/Whisper, Ollama classification and
TTS options. That long guide also contains optional setup commands and
measurements from particular hardware; they are **not** a ready-to-use,
production Voice installation for every user.

The current Chat UI intentionally reports `voice_enabled: false`.
No Core setup command installs Voice, enables microphone capture, or
grants tools through spoken commands. A successful lab transcription or
route classification **does not** establish safe integration into
Chat, Memory or Actions.

## Still required before Voice release

- Explicit mic access and press-to-talk lifecycle with **off by default**
  capture and obvious recording status; no silent always-listening service.
- Reliable Arabic/English recognition and name fidelity on varied
  microphones, accents, noise conditions and hardware.
- A natural, consent-safe local TTS voice with explicit fallback and
  verified pronunciation/quality. Voice cloning requires authorization.
- Full integration with persistent Chat, Cognitive Memory and the
  governed Actions permission/approval flows. A spoken request cannot
  approve a destructive action by itself.
- Measured latency, VRAM/RAM use, suspend/restart recovery, cancellation,
  safe transcripts/retention and multi-device quality acceptance.
- User-friendly installation/update/removal procedures and clear model
  licenses/attributions.

## If you want to experiment

Only experienced contributors should follow
[Local Voice lab](LOCAL-VOICE.md) and its optional install scripts in a
**separate Python environment**. The repository root `pyproject.toml`
is for that lab, **not** the main Core. Models and native dependencies
may be large and GPU-dependent. Do not install the lab as a prerequisite
to launching the current text Chat.

**No install/enable command in the regular
[Getting started](GETTING-STARTED.md) guide starts voice.**

Development tracking and proposals belong in
[Issues](https://github.com/0PeterAdel/okal/issues). Use
[Feature status](FEATURE-STATUS.md) for other work in progress.
