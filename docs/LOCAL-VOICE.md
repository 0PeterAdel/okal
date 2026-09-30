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
configure a hosted API.

`faster-whisper` currently passes `metadata_errors` to PyAV when opening audio.
PyAV 19 removed that argument, so the STT profile constrains `av<19`. If an
earlier setup installed PyAV 19, repair only that dependency with:

```bash
.venv-okal-voice/bin/python -m pip install 'av>=11,<19'
```

The converted CTranslate2 model and recorded WAV files do not need to be
downloaded or recorded again.

On the reference GPU, CTranslate2 requires CUDA 12 cuBLAS and cuDNN 9 even if
PyTorch installed CUDA 13 libraries. For an existing voice environment, install
the missing local runtime packages once:

```bash
.venv-okal-voice/bin/python -m pip install '.[cuda]'
```

The setup script includes these packages for new installations. Run the Voice
Lab through `scripts/run-voice-lab.sh`, which sets the CUDA 12 library paths
before starting Python. It checks the libraries first and does not alter system
CUDA or driver configuration.

If mise exposes an unconfigured `python3.13` shim, the setup installs Python
3.13 with mise and uses it only for this virtual environment. It does not
change your global Python setting. You can also install it beforehand with:

```bash
mise install python@3.13
bash scripts/setup-local-voice-stack.sh
```

For the STT benchmark alone, install the smaller STT/conversion profile first:

```bash
bash scripts/setup-local-voice-stack.sh --stt-only
bash scripts/convert-egyptian-whisper-to-ct2.sh
export OKAL_STT_MODEL_DIR="$HOME/.local/share/okal/models/whisper/egyptian-code-switching-ct2"
export OKAL_STT_DEVICE=cuda
export OKAL_STT_COMPUTE_TYPE=int8_float16
bash scripts/run-voice-lab.sh voice-lab-audio --output voice-lab-results.json
```

The model repository provides `processor_config.json` with a nested 128-bin
feature extractor instead of `preprocessor_config.json`. The converter writes
the required flat feature extractor configuration and checks it against the
model's mel-bin count before converting. A retry removes an empty output
directory left by setup and reuses a complete conversion. If an incomplete
directory contains files, inspect and move it aside before retrying; the
converter never deletes those files. This command uses Hugging Face's non-Xet
transfer path by default to avoid a large-file reconstruction failure observed
with this model. Set `HF_HUB_DISABLE_XET=0` before running it to try Xet again.
Wait for `Converted CTranslate2 model` before running the Voice Lab; a failed
download cannot produce meaningful transcripts.

For the specialized Whisper model, the preferred deployment is a CTranslate2
model directory:

```bash
bash scripts/convert-egyptian-whisper-to-ct2.sh
export OKAL_STT_MODEL_DIR="$HOME/.local/share/okal/models/whisper/egyptian-code-switching-ct2"
export OKAL_STT_DEVICE=cuda
export OKAL_STT_COMPUTE_TYPE=int8_float16
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
English, and code-switching. It does not fabricate quality numbers: the guided
recorder shows each exact phrase, and the lab records actual transcription,
language, latency, and WER when `jiwer` is installed. Keep the WAV recordings
private; the default recording directory and result file are Git-ignored.

```bash
bash scripts/record-voice-lab.sh

bash scripts/run-voice-lab.sh voice-lab-audio --output voice-lab-results.json
```

The 12 references are embedded in `apps/voice/src/okal_voice/voice_lab.py`.
A missing recording is reported as a missing case rather than a zero-quality score.
The command exits with status 2 until all 12 cases complete; group summaries
show Arabic, English, and mixed speech separately. Failed cases also print
their error and count, with details in the private JSON report.
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
