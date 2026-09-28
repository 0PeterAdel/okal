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
while IFS=$'\t' read -r case_id phrase; do
  printf '\n[%s] Say exactly:\n%s\nPress Enter to record, then Enter to stop.\n' "$case_id" "$phrase"
  read -r
  pw-record --rate 16000 --channels 1 "$OUT_DIR/$case_id.wav" &
  recorder_pid=$!
  read -r
  kill -INT "$recorder_pid" 2>/dev/null || true
  wait "$recorder_pid" 2>/dev/null || true
  recorder_pid=""
  duration="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT_DIR/$case_id.wav")"
  if [[ -z "$duration" ]] || ! awk -v seconds="$duration" 'BEGIN { exit !(seconds >= 0.25) }'; then
    rm -f -- "$OUT_DIR/$case_id.wav"
    printf 'Recording too short or invalid: %s. Please rerun the recorder.\n' "$case_id" >&2
    exit 1
  fi
  printf 'Saved %s.wav\n' "$case_id"
done <<< "$case_lines"

printf '\nVoice Lab recordings are in %s\n' "$OUT_DIR"
