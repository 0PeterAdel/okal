# Local Voice on Omarchy

This first slice provides an offline voice entry point without granting a model
authority to execute capabilities. Press `SUPER + SHIFT + O` once to capture and
again to transcribe and route. The Omarchy overlay is visual-only and click-through.

## Local pipeline

```text
PipeWire capture
  → faster-whisper / CTranslate2 (Egyptian Arabic + English code-switching)
  → strict Ollama route (qwen3:0.6b, classification only)
  → SILMA TTS v1 (authorized local reference voice)
  → Piper / espeak-ng fallback
                                      ↓
                         classification-only route event
```

No cloud fallback exists. Ollama's HTTP interface is accepted only on loopback.
This slice cannot run tools, shell commands, desktop actions, GitHub writes, or
approvals. A future Control Kernel will consume the route event under policy.

## Selected local profile

| Concern | Current choice | Reason |
|---|---|---|
| Capture | PipeWire `pw-record` | Native to Omarchy; process absence proves idle capture is off |
| STT | `faster-whisper` + Egyptian/code-switching Whisper | Optimized for Egyptian Arabic mixed with English; CUDA FP16 by default |
| STT fallback | whisper.cpp `large-v3-turbo-q5_0` | Existing portable fallback while the specialized model is prepared |
| Router | Ollama `qwen3:0.6b`, non-thinking | Tiny local classifier; strict JSON; no tools |
| TTS | SILMA TTS v1 | 150M bilingual Arabic/English local model; voice cloning requires consent |
| TTS fallback | Piper → `espeak-ng` | Local fallback chain; lower quality is explicit |
| UI | Omarchy Shell panel | Native themed overlay; no input interception |

SILMA TTS v1 is an open 150M Arabic/English model. Its code is MIT and its
weights are Apache-2.0. It uses a short reference recording for voice cloning;
Okal requires the user to supply an authorized recording and its exact transcript.
We do not ship a real person's voice or a celebrity imitation.

The overlay is an original Okal implementation whose visual interaction is
informed by the MIT-licensed `wombatoperator/omarchy-voice` orb. Its required
copyright and license notice is preserved in `THIRD_PARTY_NOTICES.md`.

The reference hardware is an i7-14650HX, 16 GB RAM, and RTX 4060 Mobile 8 GB.
Voice has priority over background GPU work. Latency and peak RAM/VRAM are release
evidence to measure on that machine; they are not inferred from model size.

## Python compatibility

The local voice environment supports **CPython 3.12 or 3.13**. Python 3.14 is
intentionally rejected for the current SILMA dependency chain: SILMA TTS 1.0.5
depends on `nemo_text_processing==1.1.0`, and that release requires the older
`pynini==2.1.6.post1` line. That Pynini release has Linux wheels through Python
3.13, but not Python 3.14. Using Python 3.14 therefore makes pip fall back to a
source build and fail when OpenFst headers such as `fst/util.h` are unavailable.

## Install the new local stack

From the repository root:

```bash
bash scripts/setup-local-voice-stack.sh
```

The setup creates an isolated `.venv-okal-voice` with Python 3.12 or 3.13 and
installs the optional local STT, TTS, and benchmark dependencies. It does not
configure a hosted API. If your system is managed by mise and neither supported
Python is installed, use:

```bash
mise install python@3.13
mise use -g python@3.13
bash scripts/setup-local-voice-stack.sh
```

For the specialized Whisper model, the preferred deployment is a CTranslate2
model directory:

```bash
bash scripts/convert-egyptian-whisper-to-ct2.sh
export OKAL_STT_MODEL_DIR="$HOME/.local/share/okal/models/whisper/egyptian-code-switching-ct2"
export OKAL_STT_DEVICE=cuda
export OKAL_STT_COMPUTE_TYPE=float16
```

For lower VRAM pressure, use:

```bash
export OKAL_STT_COMPUTE_TYPE=int8_float16
```

The existing whisper.cpp provider remains available with:

```bash
export OKAL_STT_BACKEND=whisper.cpp
```

## SILMA voice setup

SILMA's local package is optional and must be installed in the isolated voice
environment. The voice is intentionally reference-based so we can choose a
pleasant, consistent voice without redistributing somebody else's voice.

Record a short clean reference in a quiet room, with permission from the speaker,
then configure:

```bash
export OKAL_SILMA_ENABLED=1
export OKAL_SILMA_REF_AUDIO="$HOME/.local/share/okal/voice/ref.wav"
export OKAL_SILMA_REF_TEXT='exact words spoken in the reference recording'
```

If SILMA is unavailable, Okal falls back to a reviewed Piper voice when configured,
then `espeak-ng`. A fallback is reported as such; it is not counted as the target
voice-quality result.

## Voice Lab

The Voice Lab deliberately uses 12 short utterances covering Egyptian Arabic,
English, and code-switching. It does not fabricate quality numbers: you provide
recordings named after the cases and the lab records actual transcription,
language, latency, and WER when `jiwer` is installed.

```bash
mkdir -p voice-lab-audio
# Record these exact filenames with the same person who will use Okal:
# ar_01.wav ... ar_05.wav, en_01.wav ... en_03.wav, mix_01.wav ... mix_04.wav

source .venv-okal-voice/bin/activate
okal-voice-lab voice-lab-audio --output voice-lab-results.json
```

The 12 references are embedded in `apps/voice/src/okal_voice/voice_lab.py`.
A missing recording is reported as a missing case rather than a zero-quality score.
The benchmark is the release gate for choosing the primary STT backend.

## Development

Requirements: Python 3.12 or 3.13, Bash, and standard-library `unittest`.

```bash
make check
PYTHONPATH=apps/voice/src python3 -m okal_voice.cli voice doctor
```

The unit tests use fake providers and never record audio, call a model, or access
the network. Real model and hardware evidence belongs to the Voice Lab and the
Omarchy acceptance run.

## Omarchy setup

Install native prerequisites appropriate for the current Omarchy release:
PipeWire tools, CMake/build tools, CUDA toolkit, Ollama, and `ffmpeg`.
Then:

```bash
bash scripts/setup-local-voice-stack.sh
ollama pull qwen3:0.6b
okal voice doctor
```

The existing installer still handles the native user service, orb, binding,
and rollback. No root service, secret, paid account, or external API is needed.

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
