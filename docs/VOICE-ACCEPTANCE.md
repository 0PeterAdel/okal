# Speech recognition acceptance on the owner's Omarchy laptop

This is a **new** 40-command suite (15 Egyptian Arabic, 10 English, 15 mixed).
The existing baseline, holdout and vocabulary recordings have already informed
model and prompt choices, so they cannot establish an independent 70% gate.
Do not add these new reference phrases to model prompts, hotwords or fine-tuning
data before the first review. The audio, transcripts and reviews remain private.

## One recording session

From `~/Projects/okal`, fetch the current acceptance branch and check out its
remote commit for this evaluation:

```bash
git fetch origin feat/voice-acceptance
git switch --detach origin/feat/voice-acceptance
```

This works even when an older local `feat/voice-acceptance` branch exists and
has diverged after a squash merge. It leaves that local branch and the private,
untracked audio untouched. Do not pull or reset the old local branch to run the
evaluation.

Then record any missing clips (existing clips are kept):

```bash
bash scripts/record-voice-lab.sh voice-lab-acceptance-audio acceptance
```

For each prompt: press Enter to start, speak naturally (including the displayed
English terms), then Enter to stop. After the first clip, listen to the
playback. The recorder rejects silent and very short clips; if the mic changes,
stop and check `wpctl status`. A separate directory prevents overwriting the
old holdout files. Recording takes human input; there is no remote audio upload.

## Run cached models against the same 40 WAVs

```bash
src="${XDG_CACHE_HOME:-$HOME/.cache}/okal/audio.cpp-source"
OKAL_AUDIOCPP_SERVER="$src/build-okal-cuda/bin/audiocpp_server" \
  bash scripts/run-voice-acceptance.sh
```

This checks that every clip, the locally built audio.cpp binary and the
converted Whisper model exist before starting. `HF_HUB_OFFLINE=1` and the
QwenCleo lab's cache-only model lookup avoid a new weight download. The run
generates QwenCleo auto/context (live candidates), two language-forced
diagnostics, and the currently cached Egyptian Whisper in dual mode. It does
not change `voice.env`, restart the service or promote a model. It preserves
existing review files; use a fresh output directory for another run.

If a cached runtime/model is missing, stop and inspect the paths. Do not run
any `--download-*` or setup command merely to complete this acceptance pass.

## Review command meaning, not word overlap

The output directory contains three `*-review.json` files, one for each live
candidate. Every row contains the reference, recognized transcript, and three
specific checks: action/intent, target, and critical details (quantity,
negation, order, etc.). For each row set four **JSON booleans**:

- `intent_ok`: the spoken action is preserved (opening is not closing).
- `target_ok`: the correct file, app, person or setting is preserved.
- `details_ok`: quantity, negation, order and other requested limits are right.
- `unsafe_action`: true if the transcript would trigger a different or
  prohibited action; otherwise false.

Mark all three checks true and `unsafe_action` false only when the command
could safely be routed with the correct meaning. A failed or empty
transcription fails even if booleans were accidentally marked true. A person's
review is essential here: normalized WER and automatic critical-term matching
do not determine the intended action. For uncertain cases, mark the relevant
check false and explain in `notes`. You may send the **three result JSON files
only** for assisted review; WAV files remain on your machine.

Once all 40 cases in each review have booleans filled:

```bash
python3 scripts/review-voice-acceptance.py score voice-lab-acceptance-results/*-review.json
```

The threshold is at least **11/15 Arabic, 7/10 English, and 11/15 mixed**,
independently. Failed recognition counts as a failure. Scoring rejects missing
cases, edited rubrics and incomplete reviews. Any unsafe action flip blocks the
gate even if the percentage passes. The result is evidence about
transcript comprehension on this one speaker and microphone, **not** proof of
end-to-end task execution: the current voice slice only classifies routes.
PR #10 is merged as an experimental, classification-only voice slice.
Do not treat it as action-ready until this acceptance gate passes and the
action layer is separately implemented and reviewed. No new STT model should be downloaded based on old 12-clip WERs.

The UI/audio experience ideas from [Mark-LV](https://github.com/FatihMakes/Mark-LV)
and [Friday](https://github.com/alimaandev/Friday), and skill/trace contracts
from [OpenJarvis](https://github.com/open-jarvis/OpenJarvis), are later,
independent tasks. This acceptance change copies none of their code or assets.
