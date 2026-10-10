#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SUITE="${2:-baseline}"
case "$SUITE" in
  baseline) default_dir="$ROOT_DIR/voice-lab-audio" ;;
  holdout) default_dir="$ROOT_DIR/voice-lab-holdout-audio" ;;
  vocabulary) default_dir="$ROOT_DIR/voice-lab-vocabulary-audio" ;;
  *) echo "Unknown Voice Lab suite: $SUITE (expected baseline, holdout, or vocabulary)" >&2; exit 2 ;;
esac
OUT_DIR="${1:-$default_dir}"
umask 077
command -v pw-record >/dev/null || { echo "pw-record is required" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe is required to check recording duration" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg is required to check microphone level" >&2; exit 1; }
mkdir -p "$OUT_DIR"

recorder_pid=""
candidate_path=""
cleanup() {
  if [[ -n "$recorder_pid" ]]; then
    kill -INT "$recorder_pid" 2>/dev/null || true
    wait "$recorder_pid" 2>/dev/null || true
  fi
  if [[ -n "$candidate_path" ]]; then
    rm -f -- "$candidate_path"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

case_lines="$(PYTHONPATH="$ROOT_DIR/apps/voice/src" python3 -m okal_voice.voice_lab --suite "$SUITE" --list-cases)"
while IFS=$'\t' read -r case_id phrase <&3; do
  audio_path="$OUT_DIR/$case_id.wav"
  while :; do
    printf '\n[%s] Say exactly:\n%s\nPress Enter to record, then Enter to stop.\n' "$case_id" "$phrase"
    read -r
    candidate_path="$(mktemp "$OUT_DIR/.${case_id}.XXXXXX.wav")"
    pw-record --rate 16000 --channels 1 "$candidate_path" &
    recorder_pid=$!
    read -r
    kill -INT "$recorder_pid" 2>/dev/null || true
    wait "$recorder_pid" 2>/dev/null || true
    recorder_pid=""
    if [[ ! -s "$candidate_path" ]]; then
      printf 'pw-record did not create audio. Check the microphone with wpctl status, then retry.\n' >&2
    elif ! duration="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$candidate_path" 2>/dev/null)"; then
      printf 'Recording is not a valid WAV; retry %s.\n' "$case_id" >&2
    elif [[ -z "$duration" ]] || ! awk -v seconds="$duration" 'BEGIN { exit !(seconds >= 0.25) }'; then
      printf 'Recording too short; retry %s.\n' "$case_id" >&2
    elif ! volume_output="$(ffmpeg -hide_banner -nostats -i "$candidate_path" -af volumedetect -f null - 2>&1)"; then
      printf 'Could not measure microphone level; retry %s.\n' "$case_id" >&2
    else
      peak_db="$(sed -n 's/.*max_volume: \([^ ]*\) dB.*/\1/p' <<< "$volume_output" | tail -n 1)"
      if [[ -z "$peak_db" || "$peak_db" == "-inf" ]] || ! awk -v peak="$peak_db" 'BEGIN { exit !(peak + 0 > -55) }'; then
        printf 'Silent or very quiet recording (peak %s dB). Check the selected input and mute with wpctl status; retry %s.\n' "${peak_db:-unknown}" "$case_id" >&2
      else
        mv -f -- "$candidate_path" "$audio_path"
        candidate_path=""
        printf 'Saved %s.wav (peak %s dB)\n' "$case_id" "$peak_db"
        break
      fi
    fi
    rm -f -- "$candidate_path"
    candidate_path=""
  done
  if [[ "$case_id" == "ar_01" ]] && command -v pw-play >/dev/null 2>&1; then
    printf 'Playing back the first clip. Listen for your words.\n'
    pw-play "$audio_path"
    printf 'If your words are clear, press Enter to continue. Otherwise press Ctrl+C and check the microphone.\n'
    read -r
  fi
done 3<<< "$case_lines"

printf '\nVoice Lab recordings are in %s\n' "$OUT_DIR"
