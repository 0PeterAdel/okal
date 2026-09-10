# Local Voice on Omarchy

This first slice provides an offline voice entry point without granting a model
authority to execute capabilities. Press `SUPER + SHIFT + O` once to capture and
again to transcribe and route. The Omarchy overlay is visual-only and click-through.

## Local pipeline

```text
PipeWire capture → whisper.cpp STT → strict Ollama route → local TTS
                                      ↓
                         classification-only route event
```

No cloud fallback exists. Ollama's HTTP interface is accepted only on loopback.
This slice cannot run tools, shell commands, desktop actions, GitHub writes, or
approvals. A future Control Kernel will consume the route event under policy.

## Selected local profile

| Concern | Initial choice | Reason |
|---|---|---|
| Capture | PipeWire `pw-record` | Native to Omarchy; process absence proves idle capture is off |
| STT | whisper.cpp `large-v3-turbo-q5_0` | Multilingual, quantized, strong Arabic/English, 547 MiB model |
| Router | Ollama `qwen3:0.6b`, non-thinking | Tiny multilingual classifier; strict JSON; no tools |
| TTS | Piper external process | Fast local neural TTS; voice weights reviewed separately |
| TTS fallback | `espeak-ng` | Very small and fast, but intentionally lower quality |
| UI | Omarchy Shell panel | Native themed overlay; no input interception |

The overlay is an original Okal implementation whose visual interaction is
informed by the MIT-licensed `wombatoperator/omarchy-voice` orb. Its required
copyright and license notice is preserved in `THIRD_PARTY_NOTICES.md`.

The reference hardware is an i7-14650HX, 16 GB RAM, and RTX 4060 Mobile 8 GB.
Voice has priority over background GPU work. Latency and peak RAM/VRAM remain
release evidence to measure on that machine; they are not inferred from model size.

## Development

Requirements: Python 3.12+, Bash, and standard-library `unittest`.

```bash
make check
PYTHONPATH=apps/voice/src python3 -m okal_voice.cli voice doctor
```

The tests use fake providers and never record audio, call a model, or access the
network.

## Omarchy setup

Install the native prerequisites appropriate for the current Omarchy release:
PipeWire tools, CMake/build tools, CUDA toolkit, Ollama, and either Piper or
`espeak-ng`. Then install the pinned STT provider:

```bash
bash scripts/setup-whisper-cpp.sh
ollama pull qwen3:0.6b
bash scripts/install-local-voice.sh
okal voice doctor
```

`setup-whisper-cpp.sh` checks out verified commit
`371b5a7561823ab2bb32142d2751e35e7534727b` (release v1.9.3) and verifies the
multilingual model's published SHA-1 before installation. Production release
intake will additionally record an artifact SHA-256 and SBOM.

The installer:

1. Copies the Python application under the user's XDG data directory.
2. Installs `~/.local/bin/okal`.
3. Installs and starts a hardened systemd user service.
4. Installs the `okal.voice` Omarchy Shell panel.
5. Backs up and extends `~/.config/hypr/bindings.lua`.

No root service, secret, paid account, or external API is needed.

## Commands

```bash
okal voice toggle
okal voice cancel
okal voice status
okal voice say "مساء الخير يا أوكال"
okal voice doctor
journalctl --user -u okal-voice -f
```

Typed `say` uses the same local router and TTS without activating the microphone.

## Piper voices

Piper supports Arabic (`ar_JO`) and English voices. Its engine is GPL-3.0 and
runs as an optional external process; it is not imported into the permissive
Okal core. Every voice has its own `MODEL_CARD` and may have different terms.
Do not redistribute a voice until its model card is reviewed and recorded.
After review, configure paths through the user service environment:

```ini
Environment=OKAL_PIPER_AR_MODEL=/absolute/path/to/ar_JO-voice.onnx
Environment=OKAL_PIPER_EN_MODEL=/absolute/path/to/en_US-voice.onnx
```

Without reviewed Piper weights, Okal uses local `espeak-ng` and keeps the text
visible if speech output is unavailable.

## Privacy and failure behavior

- No recorder process exists in `idle` or after cancellation.
- Continuous and wake-word recording are intentionally unavailable.
- Runtime directory mode is `0700`; state, route log, and socket are `0600`.
- Audio is a temporary owner-only WAV and is deleted after transcription.
- Empty audio and malformed router output fail closed.
- A failed TTS response does not replay routing and cannot replay an action.
- The overlay becomes inactive when state is stale or the daemon is absent.
- Route events say `classification-only`; they are not authorization evidence.

## Rollback

```bash
bash scripts/uninstall-local-voice.sh
```

The uninstaller stops the user service, removes the app and panel, and restores
the backed-up keybindings. Downloaded model files are preserved so rollback is
recoverable and does not destroy large user-owned artifacts.
