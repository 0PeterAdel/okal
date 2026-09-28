#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT_DIR/voice-lab-audio}"
umask 077
command -v pw-record >/dev/null || { echo "pw-record is required" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe is required to check recording duration" >&2; exit 1; }
mkdir -p "$OUT_DIR"

recorder_pid=""
cleanup() {
  if [[ -n "$recorder_pid" ]]; then
    kill -INT "$recorder_pid" 2>/dev/null || true
    wait "$recorder_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

case_lines="$(PYTHONPATH="$ROOT_DIR/apps/voice/src" python3 -m okal_voice.voice_lab --list-cases)"
while IFS=$'\t' read -r case_id phrase <&3; do
  printf '\n[%s] Say exactly:\n%s\nPress Enter to record, then Enter to stop.\n' "$case_id" "$phrase"
  read -r
  audio_path="$OUT_DIR/$case_id.wav"
  pw-record --rate 16000 --channels 1 "$audio_path" &
  recorder_pid=$!
  read -r
  kill -INT "$recorder_pid" 2>/dev/null || true
  wait "$recorder_pid" 2>/dev/null || true
  recorder_pid=""
  if [[ ! -s "$audio_path" ]]; then
    printf 'pw-record did not create %s. Check PipeWire/microphone access and leave time between Enter presses.\n' "$audio_path" >&2
    exit 1
  fi
  if ! duration="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$audio_path" 2>/dev/null)"; then
    printf 'Recording is not a valid WAV: %s\n' "$audio_path" >&2
    exit 1
  fi
  if [[ -z "$duration" ]] || ! awk -v seconds="$duration" 'BEGIN { exit !(seconds >= 0.25) }'; then
    rm -f -- "$audio_path"
    printf 'Recording too short or invalid: %s. Please rerun the recorder.\n' "$case_id" >&2
    exit 1
  fi
  printf 'Saved %s.wav\n' "$case_id"
done 3<<< "$case_lines"

printf '\nVoice Lab recordings are in %s\n' "$OUT_DIR"
