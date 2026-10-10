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

The small `qwen3:0.6b` model classifies intent; its short reply is not a
full conversational assistant. For an optional conversational trial,
`OKAL_CONVERSATION_MODEL` sends only `conversation` routes to a separate
larger local Ollama model. Task, dictation, clarify, and blocked routes are
never sent to it. Both Ollama requests use `keep_alive=0` so their GPU memory
can be released before speech synthesis. The trial has no tool access.

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
before starting Python. It imports the Voice Lab from the checked-out source,
so a `git pull` does not require reinstalling the package to use new lab flags.
It checks the libraries first and does not alter system CUDA or driver
configuration.

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

## Voice quality trial: Egyptian speech and warmer conversation

SILMA or `espeak-ng` speech is insufficient evidence for a pleasant assistant
voice. `VoiceTut-TTS` is a 0.6B Egyptian Arabic / English code-switching model
with built-in voices; its authors report about 2.93 GB peak VRAM on a T4 in
FP16. That is a published figure, not a measurement on the reference RTX 4060.
An isolated environment avoids changing the existing STT and SILMA packages.

```bash
bash scripts/run-tts-voice-lab.sh --setup
bash scripts/run-tts-voice-lab.sh
```

The first command downloads dependencies; the second uses cached model files
and writes private WAVs plus a timing/VRAM manifest in
`voice-lab-tts/`. Listen to each speaker's greeting, practical response, and
Arabic/English sentence. Check pronunciation, Egyptian accent, warmth, natural
pauses, code-switching, delay, and whether the exact words were spoken. Run
`bash scripts/run-tts-voice-lab.sh --list-speakers` or use
`--speaker Asmaa --speaker Mohamed` to narrow the trial. This does not
silently replace the service voice. A chosen voice needs a target-machine
listening decision and a separate service adapter.

### Recover a stopped VoiceTut download without spending more data

The initial lab accidentally requested the entire Hugging Face model repository,
including `optimizer.bin` (a 4.9 GB training artifact). The inference checkpoint
is `model.safetensors` (2.45 GB). OmniVoice also needs a separate Higgs audio
tokenizer checkpoint (806 MB). The lab now checks both existing caches before
loading and forces Hub offline mode; it cannot start a network download.

After pulling the update, inspect the local cache for one voice first:

```bash
bash scripts/run-tts-voice-lab.sh --cache-status --speaker Asmaa
```

If the check passes, run only that speaker and listen. Other speakers may need
small reference clips which the cache check reports before any model load:

```bash
bash scripts/run-tts-voice-lab.sh --speaker Asmaa &&
pw-play voice-lab-tts/asmaa-greeting.wav
```

If the check lists `model.safetensors` or the Higgs audio tokenizer, stop here.
The old 4.21 GB transfer does not prove those files completed, and no offline
command can reconstruct absent weights. Do not delete the Hugging Face cache or
rerun the original lab: it could spend more data. The incomplete optimizer file
is irrelevant for inference and is deliberately ignored. When you have access
to a local copy of the missing checkpoint later, it can be reused without
reinstalling the voice environment or rerecording anything.

When bandwidth is available, fetch just the inference files for one speaker:

```bash
bash scripts/run-tts-voice-lab.sh --download-missing --speaker Asmaa
```

The command selects the old VoiceTut revision already recorded in the local
cache, downloads individual files into the same Hugging Face cache, disables
the Xet transfer path that failed here, and skips completed files. It never
requests `optimizer.bin`, random training states, or every speaker clip. The
remaining large inference files can require about 2.45 GB for VoiceTut and
806 MB for the separate audio tokenizer, plus small files. This is a rough
file-size budget, not a promise about actual network traffic or recovery of
the earlier failed Xet transfer.

If connectivity or the data allowance runs out, stop the command with Ctrl+C
and later run **the same command**. Keep the same machine, Hugging Face cache,
and virtual environment; the regular transfer path retains `.incomplete`
blobs for resume when supported by the server. Do not pass `--setup`, clear
the cache, use `hf cache prune`, or change `HF_HOME`/`HF_HUB_CACHE` in between.
Some bytes from the earlier Xet reconstruction failure may be unrecoverable;
we cannot guarantee zero repeated traffic. `--cache-status --speaker Asmaa`
always remains safe to run without an internet connection. Only after it
passes should you synthesize and play the sample.

### Try the approved Asmaa voice in the local service

After listening to the Asmaa samples, enable the voice explicitly. The service
uses the existing separate `.venv-okal-tts-lab` and model cache, with Hub
offline mode forced for every synthesis. It never downloads at runtime.
Typing bare `OKAL_VOICETUT_...=...` assignments into a shell does not persist
them for the user service; `okal voice doctor` still shows the old provider.
From the checkout root, run this repeatable command instead:

```bash
git pull --ff-only
bash scripts/enable-voicetut-voice.sh
okal voice say 'مساء الخير يا بيتر'
```

The enable command checks the cached Asmaa files without network access,
installs current service code, writes these settings once into the owner-only
`~/.config/okal/voice.env`, restarts the user service, and runs `okal voice
doctor`. Verify `PASS Local TTS: VoiceTut` and `PASS VoiceTut cache: Asmaa`.
The equivalent manual settings, using the actual absolute checkout path, are:

```ini
OKAL_VOICETUT_ENABLED=1
OKAL_VOICETUT_SPEAKER=Asmaa
OKAL_VOICETUT_PYTHON=/home/okal/Projects/okal/.venv-okal-tts-lab/bin/python
```

Only Asmaa's reference clip is cached by the one-speaker download command.
If the opt-in voice fails, the response text remains visible and the service
reports a TTS error instead of unexpectedly substituting `espeak-ng`.
The first request after service restart loads Asmaa's weights into the isolated
renderer. The process stays loaded for later requests and is stopped with the
service. This saves repeated loading time but keeps roughly the lab's 2 GB of
GPU memory in use while idle. The router receives an explicit Egyptian Arabic
instruction; if it still answers an Arabic-only greeting in English, the
service replaces that text with a short Egyptian Arabic greeting before speech.
`okal voice say 'مساء الخير يا بيتر'` now speaks those exact words without routing
them through Ollama. It accepts the request asynchronously: the initial JSON
response reports `speaking`, then the orb shows the same text while Asmaa speaks.
Use `okal voice ask 'مساء الخير يا بيتر'` for a conversational reply. Repeat
`say` once to check the warm renderer. No model download is needed.
To revert
without deleting any downloaded files, set `OKAL_VOICETUT_ENABLED=0` and
restart `okal-voice.service`.

If setup stopped at `torchaudio` with Python 3.13, pull the updated script
and rerun `--setup`. The old CUDA 12.1 index had a compatible `torch` wheel
but no matching `torchaudio` wheel. The lab now installs the matching
2.9.1 CUDA 12.6 pair in its separate environment. It preserves that
environment across retries; the earlier CUDA 12.1 download cannot satisfy
this pair. Chain the sample generation and playback with `&&` so a failed
download does not attempt to play a nonexistent WAV.

The response text can also sound cold even with good audio: the default tiny
router only classifies. To try fuller Egyptian replies in conversation, install
the local `command-r7b-arabic` Ollama model (about 5.1 GB on disk) and add
`OKAL_CONVERSATION_MODEL=command-r7b-arabic` to
`~/.config/okal/voice.env`:

```bash
ollama pull command-r7b-arabic
systemctl --user restart okal-voice.service
okal voice doctor
okal voice ask 'مساء الخير، عامل إيه؟'
```

Edit the environment file before the restart. The model is opt-in because an
8 GB GPU must also accommodate STT, context, and TTS. Watch `nvidia-smi`,
latency, and any fallback to CPU while testing. The response model never
receives tool access, and the route log stays classification-only. It may
still misread a request or produce inaccurate text; review actual replies
before promoting it.

## Voice Lab

The Voice Lab deliberately uses 12 short utterances covering Egyptian Arabic,
English, and code-switching. It does not fabricate quality numbers: the guided
recorder shows each exact phrase, and the lab records actual transcription,
language, latency, and WER when `jiwer` is installed. Keep the WAV recordings
private; the default recording directory and result file are Git-ignored.

Before recording, use `wpctl status` to confirm the starred entry under Audio
Sources is the microphone, not a monitor or disconnected input. Use
`wpctl set-default SOURCE_ID` if it is wrong, and
`wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 0` if the source is muted. The recorder
rejects clips shorter than 0.25 seconds and clips with a peak at or below
-55 dBFS, then retries the same phrase. It keeps the previous WAV until a new
clip passes these checks. A level check cannot prove the words are audible, so
the recorder plays the first saved clip and waits for your confirmation before
continuing with the other phrases.

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

If English recordings are transcribed as Arabic, compare automatic language
detection with a diagnostic run on the *same* WAV files:

```bash
bash scripts/run-voice-lab.sh voice-lab-audio --output voice-lab-results.json
bash scripts/run-voice-lab.sh voice-lab-audio --language-hints --output voice-lab-hints.json
```

The second run passes `ar` or `en` to faster-whisper for cases whose spoken
language is known. Mixed cases stay automatic. Compare each transcript and WER
between the two private JSON reports, especially `en_02`, `en_03`, and `ar_03`.
Language hints use the benchmark's answer key, so their scores are diagnostic
only; they are not a production or release score. If they improve the result,
production still needs a way to infer language without knowing the words.
Plain WER also counts punctuation, Arabic spelling variants, and spaces as
errors; inspect the words and whether the requested action survived.

### Optional technical vocabulary hints

`faster-whisper` accepts short `hotwords` hints when decoding. To try a small
list of product terms without retraining or changing the default behavior,
set `OKAL_STT_HOTWORDS`. The list is passed to both decodes in experimental
`dual` mode. It is a decoding hint, not a guaranteed vocabulary constraint:
check whether it introduces words the speaker never said, and keep the old
report for comparison. The private lab report records the chosen hints.

```bash
export OKAL_STT_HOTWORDS='README, commits, pull request, git status, VS Code, GitHub, Wi-Fi'
OKAL_STT_LANGUAGE_MODE=dual \
bash scripts/run-voice-lab.sh voice-lab-holdout-audio --suite holdout \
  --output voice-lab-holdout-hotwords.json
unset OKAL_STT_HOTWORDS
```

These phrases overlap recordings we have already inspected, so an improvement
on the existing holdout is diagnostic only. For a credible release comparison,
use the separate `vocabulary` suite: it fixes 12 new phrases in advance,
including Arabic commands and sentences without any listed technical terms.
Record once, then compare the same WAVs with the hints unset and set. Ideally
ask another speaker to record the same suite in their own private directory.

```bash
bash scripts/record-voice-lab.sh voice-lab-vocabulary-audio vocabulary
OKAL_STT_LANGUAGE_MODE=dual \
bash scripts/run-voice-lab.sh voice-lab-vocabulary-audio --suite vocabulary \
  --output voice-lab-vocabulary-control.json
OKAL_STT_LANGUAGE_MODE=dual \
OKAL_STT_HOTWORDS='README, commits, pull request, git status, VS Code, GitHub, Wi-Fi' \
bash scripts/run-voice-lab.sh voice-lab-vocabulary-audio --suite vocabulary \
  --output voice-lab-vocabulary-hotwords.json
```

Evaluate critical terms (`README` versus `ريدمي`, `commits` versus `comments`,
complete `pull request`) and Arabic verbs as well as raw WER and latency. Check
the sentences without listed terms for words the speaker did not say. The
phrases are new, but a recording by the original speaker is not a new-speaker
validation. Do not silently replace command words after transcription.
Actual fine-tuning is a separate step requiring many labeled audio clips and
their exact transcripts; a text-only word list cannot update model weights.

To investigate a selector that does not know the spoken language beforehand,
run both Arabic and English candidate decodes on every clip:

```bash
bash scripts/run-voice-lab.sh voice-lab-audio --language-probes --output voice-lab-probes.json
```

The owner-only report preserves the automatic result and adds its Arabic/English
language probabilities plus the text, raw WER, latency, and mean segment log
probability of each forced candidate. These are diagnostic scores, not a proven
way to choose a transcript; compare all 12 cases before changing production.
This mode performs three decodes per clip and does not use the reference to
select a candidate or change what the voice service does.

To trial the candidate rule in the actual STT adapter, set
`OKAL_STT_LANGUAGE_MODE=dual` for one lab run. The default `auto` mode is
unchanged. Dual mode runs the English decoder only when automatic detection
selects Arabic, then picks English if its mean segment log probability is
higher. It does not read the benchmark reference. A failed English candidate
keeps the automatic transcript. This rule is experimental: the 12 cases used
to derive it are not independent validation, and it adds decoding time for
Arabic and mixed speech. Do not treat a good result on these same recordings
as a release gate or enable it by default before measuring new speakers and
phrases.

```bash
OKAL_STT_LANGUAGE_MODE=dual \
bash scripts/run-voice-lab.sh voice-lab-audio --output voice-lab-dual.json
```

For an independent check after choosing a rule, record the separate holdout
suite. Its phrases and WAV directory differ from the baseline; read each prompt
exactly and listen to the first clip. Run `auto` and `dual` on the same new WAVs
to compare recognition and the cost of an extra decode. Keep these recordings
and JSON reports private; their paths are Git-ignored.

```bash
bash scripts/record-voice-lab.sh voice-lab-holdout-audio holdout
bash scripts/run-voice-lab.sh voice-lab-holdout-audio --suite holdout --output voice-lab-holdout-auto.json
OKAL_STT_LANGUAGE_MODE=dual \
bash scripts/run-voice-lab.sh voice-lab-holdout-audio --suite holdout --output voice-lab-holdout-dual.json
```

To compare the general `large-v3-turbo` CTranslate2 model, download it into
the normal Hugging Face cache before running the lab. Large-file network
failures can leave an incomplete cached snapshot; rerun this download after
connectivity returns. Do not delete the cache or the completed Egyptian model.
The longer download timeout can help with a slow connection. The lab checks
the model once before the batch, so a failed download does not retry for every
recording.

```bash
HF_HUB_DISABLE_XET=1 HF_HUB_DOWNLOAD_TIMEOUT=120 \
.venv-okal-voice/bin/python - <<'PY'
from pathlib import Path
from huggingface_hub import snapshot_download

path = Path(snapshot_download(
    "dropbox-dash/faster-whisper-large-v3-turbo",
    allow_patterns=["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"],
))
for name in ("model.bin", "config.json", "preprocessor_config.json", "tokenizer.json"):
    if not (path / name).is_file() or not (path / name).stat().st_size:
        raise SystemExit(f"Incomplete model: {name}")
print(f"Ready CTranslate2 model: {path}")
PY

env -u OKAL_STT_MODEL_DIR \
  HF_HUB_OFFLINE=1 OKAL_STT_MODEL=dropbox-dash/faster-whisper-large-v3-turbo \
  OKAL_STT_LANGUAGE_MODE=auto OKAL_STT_DEVICE=cuda OKAL_STT_COMPUTE_TYPE=int8_float16 \
  bash scripts/run-voice-lab.sh voice-lab-holdout-audio --suite holdout \
    --output voice-lab-generic-turbo.json
```

## Next-generation STT tournament

The current faster-whisper backend remains the production default until measured
evidence selects a replacement. Two newer local candidates are available only
through explicit backends:

- `cohere`: `CohereLabs/cohere-transcribe-arabic-07-2026`, a 2B Arabic/English
  ASR model specialized for Arabic dialects and code-switching. It needs a
  pre-selected `ar` or `en` language, so the lab records both an Arabic-matrix
  deployment run and a diagnostic language-hinted run.
- `qwencleo`: `mohammedaly22/QwenCleo-ASR`, a Qwen3-ASR 1.7B fine-tune for
  Egyptian Arabic and Arabic/English code-switching. Its production candidate
  run uses automatic language selection; a second Arabic-matrix run measures
  the checkpoint author's recommended hint for Egyptian/code-switched speech.

These candidates intentionally use separate virtual environments. The Qwen ASR
package pins a Transformers 4.x release while Cohere Transcribe Arabic requires
Transformers 5.4 or newer. Keeping them isolated avoids replacing dependencies
inside `.venv-okal-voice`.

Set them up without modifying system Python, CUDA, or the existing voice venv:

```bash
bash scripts/setup-stt-tournament.sh
```

Cohere's Hugging Face repository is gated. Accept its access conditions in your
own Hugging Face account and authenticate locally with `hf auth login`. Never
put an access token in a committed command, source file, or benchmark report.

Run all candidate passes against the same existing recordings:

```bash
bash scripts/run-stt-tournament.sh voice-lab-holdout-audio holdout
```

The command writes owner-only JSON reports under `voice-lab-tournament/` and
prints an Arabic/English/mixed comparison table. When the existing Okal voice
environment is present, it first reruns the current Seif medium code-switched
faster-whisper model as a control with the new metrics. It then runs QwenCleo
with automatic language selection, QwenCleo with Arabic as the matrix language,
Cohere with Arabic as the matrix language, and a diagnostic Cohere pass that
uses the benchmark's known Arabic/English labels for pure-language clips. The
diagnostic pass is not a production or release score.

Voice Lab continues to report raw WER, and also reports normalized WER,
normalized CER, recall of command/technical terms present in each reference,
median latency, and PyTorch peak reserved GPU memory when the backend uses
PyTorch. Normalization removes case, punctuation, Arabic diacritics, tatweel,
and common Alef/Yeh spelling variation; the raw transcript is always preserved.
The memory number is an in-process PyTorch measurement, not whole-GPU telemetry,
so it is useful for relative candidate pressure but does not replace
`nvidia-smi`.

The tournament does not silently promote a winner. A candidate still needs
new-speaker and natural-command evidence plus end-to-end voice acceptance before
changing the default backend.

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

The installer copies the app and creates the native user service, orb, and
binding. It uses the isolated `.venv-okal-voice` Python and its CUDA 12 libraries.
Keep the checkout and virtual environment at the same path while the service is
installed. Service settings are saved in `~/.config/okal/voice.env` (mode
`0600`), which direct `okal voice doctor` checks also read. Existing settings
survive reinstall. Edit `OKAL_STT_MODEL_DIR` there if you choose another local
CTranslate2 model, then run `systemctl --user restart okal-voice.service`.
The installer defaults to the converted Egyptian model and experimental dual
decoding; it does not download any model. The fallback `espeak-ng` permits an
initial audible test before configuring SILMA.

For a first hardware smoke test, check `systemctl --user status
okal-voice.service`, then run `okal voice say 'مساء الخير'`. The orb should show
the exact supplied words and the local TTS should speak. Use
`okal voice ask 'مساء الخير'` to test a routed reply. Press `SUPER + SHIFT + O`,
speak a short command, and press it again. Check `okal voice status` for the
phase and displayed reply; inspect `journalctl --user -u okal-voice.service -n 80`
if a stage fails. The router classifies tasks but never executes them. Try
`okal voice cancel` while recording and verify the mic capture stops.

To use SILMA, record an authorized 5–10 second reference into
`~/.local/share/okal/voice/ref.wav` and add `OKAL_SILMA_REF_AUDIO` (absolute
path) and `OKAL_SILMA_REF_TEXT` (the exact spoken words) to
`~/.config/okal/voice.env`; restart the service. `okal voice doctor` reports
the active TTS provider. A fallback result is not SILMA quality evidence.

No root service, secret, paid account, or external API is needed.

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

## QwenCleo Q8 speech recognition trial

This optional [QwenCleo-ASR GGUF](https://huggingface.co/mohammedaly22/QwenCleo-ASR-GGUF) trial uses the [audio.cpp server](https://github.com/0xShug0/audio.cpp/blob/main/app/server/README.md) on loopback. The author describes the model as trained for Egyptian Arabic and code switching; this is a candidate, not an observed improvement on Okal's recordings. The Q8 file is about 2.31 GiB, plus an official audio.cpp v0.9.0 CUDA archive of about 214 MB. Nothing changes the installed service or downloads automatically. The Ubuntu CUDA prebuilt has not yet been tested on the target Omarchy host; if its system libraries fail on Arch, stop and report the server log rather than downloading another model.

From the repository root, check the cache without network access:

```bash
bash scripts/prepare-qwencleo-gguf.sh --cache-status
```

When bandwidth permits, fetch each missing artifact with resumable commands. Keep the same Hugging Face cache and archive location between retries; rerunning skips verified files:

```bash
bash scripts/prepare-qwencleo-gguf.sh --download-model
bash scripts/prepare-qwencleo-gguf.sh --download-runtime
bash scripts/prepare-qwencleo-gguf.sh --cache-status
```

The GGUF is pinned to a revision, and the runtime archive is checked against the release SHA-256 before extraction. Then run the already recorded holdout suite:

```bash
bash scripts/run-qwencleo-gguf-lab.sh voice-lab-holdout-audio holdout voice-lab-qwencleo-gguf
```

The run starts a temporary CUDA server at `127.0.0.1:18080`, writes `qwencleo-auto.json`, `qwencleo-context.json`, `qwencleo-ar.json`, and `qwencleo-hints.json`, prints individual transcripts and normalized WER/critical term recall, and stops the server on exit. The first clip includes cold model load time; compare later clip latency separately. The auto and context reports use language selection available to a live assistant. The context pass differs only by a fixed optional software-terms system prompt sent via the server's `prompt` field; it may improve a technical term or introduce a false one, so compare every affected command and the Arabic control clips. `OKAL_AUDIOCPP_PROMPT` remains empty by default and is limited to 1024 characters. The Arabic report forces Arabic for every clip, including English, and the hints report supplies the reference language for English clips as a diagnostic; a real assistant does not know that label. Compare both against `voice-lab-holdout-dual.json` and inspect terms such as `README`, `commits`, `pull request`, and the action verbs. Do not switch the live backend based on the author's published scores or a single WER average.

### QwenCleo with tied embeddings on audio.cpp

The QwenCleo GGUF has no `thinker.lm_head.weight`: its output projection shares
`thinker.model.embed_tokens.weight`. The v0.9.0 prebuilt server requests the
missing tensor and returns HTTP 500. The upstream audio.cpp source at commit
`2721dc03a4349b62af0dfd264d3ca47b94273e46` contains the tied-embedding
loader fix. The downloaded 2.31 GiB GGUF is valid for this path and stays in
the Hugging Face cache; do not download it again or edit its bytes.

First check for build tools without fetching anything:

```bash
command -v cmake
command -v nvcc
command -v c++
```

If `nvcc` is absent, stop here; the Python CUDA runtime libraries do not
include the CUDA compiler. When a CUDA toolkit and build tools are already
installed and source bandwidth is available, build a Qwen3 ASR-only server
from the fixed upstream source. This fetches source and may fetch build
dependencies, but it does not fetch model weights:

```bash
src="${XDG_CACHE_HOME:-$HOME/.cache}/okal/audio.cpp-source"
mkdir -p "$src"
if ! git -C "$src" rev-parse --git-dir >/dev/null 2>&1; then git -C "$src" init; fi
if ! git -C "$src" remote get-url origin >/dev/null 2>&1; then
  git -C "$src" remote add origin https://github.com/0xShug0/audio.cpp.git
fi
git -C "$src" fetch --depth 1 --filter=blob:none origin 2721dc03a4349b62af0dfd264d3ca47b94273e46
git -C "$src" checkout --detach FETCH_HEAD
cmake -S "$src" -B "$src/build-okal-cuda" -DENGINE_ENABLE_CUDA=ON \
  -DCUDAToolkit_ROOT=/opt/cuda -DCMAKE_CUDA_COMPILER=/opt/cuda/bin/nvcc \
  -DCMAKE_CUDA_ARCHITECTURES=89 -DAUDIOCPP_MODEL_SET=custom \
  -DAUDIOCPP_MODELS=qwen3_asr
cmake --build "$src/build-okal-cuda" --parallel 4 --target audiocpp_server
OKAL_AUDIOCPP_SERVER="$src/build-okal-cuda/bin/audiocpp_server" \\
  bash scripts/run-qwencleo-gguf-lab.sh voice-lab-holdout-audio holdout voice-lab-qwencleo-gguf
```

The fetch can be retried in the same directory if the connection drops; it
only requests the pinned source commit. The configure step explicitly uses the
CUDA toolkit already installed at `/opt/cuda` on Omarchy. Keep the v0.9.0 executable and the live Okal service untouched. Check
the individual transcripts and command terms before considering any backend
change.

## Review a transcript before routing

The microphone normally routes recognized text immediately. To pause after
transcription, add `OKAL_VOICE_REVIEW_TRANSCRIPT=1` to
`~/.config/okal/voice.env` and restart the user service. The orb then shows
the recognized text. Press `SUPER + SHIFT + O` again, or run
`okal voice confirm`, to submit it. Use `okal voice correct 'corrected text'`
to replace it, or `okal voice cancel` to discard it. This reviews text only;
the router remains classification-only and does not execute desktop actions.

Try the same review flow without a microphone (the flag is not required):

```bash
okal voice preview 'افتح البرواز'
okal voice status
okal voice correct 'افتح المتصفح'
```

`preview` creates a pending sample but does not route it until confirmation
or correction. `correct` requires a pending transcript; an empty correction
is rejected. The current orb is click-through, so corrections use the CLI.

On the owner's 12 recorded holdout commands, QwenCleo Q8 with automatic language selection finished 12/12: Arabic normalized WER 0.283, English 0.074, mixed 0.496; median latencies were around 0.37–0.50 seconds on this run. Forcing Arabic gave the same Arabic and mixed transcripts and slightly different English text. The reference-language hints pass improved `commits` in one English command, but those labels are unavailable to a live assistant. The fixed-context holdout run completed 12/12 on the same recordings. Compared with auto without context, mean normalized WER improved from 0.283 to 0.258 (Arabic), 0.074 to 0.037 (English), and 0.496 to 0.393 (mixed); mean critical-term recall rose from 0.625 to 0.875, 0.833 to 1.0, and 0.458 to 0.646 respectively. The context recovered `commits` in English and `pull request` in mixed speech, but `اقفل` still became `اكلم`, `README` remained unrecognized in a mixed clip, and `الاجتماع تأجل` changed to the less faithful `الاجتماعات أجل`. The context candidate is therefore useful for an optional live transcription trial, not a reliable action trigger. Preserve the default STT and keep PR #10 in Draft until new natural-command recordings and an end-to-end review show that verbs and targets are preserved.

`OKAL_STT_BACKEND=audiocpp` and `OKAL_AUDIOCPP_ENDPOINT` exist only for an explicitly started local server. The default installed STT and the selected VoiceTut Asmaa voice stay as configured.
