#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-voice-lab-audio}"
mkdir -p "$OUT_DIR"

cases=(ar_01 ar_02 ar_03 ar_04 ar_05 en_01 en_02 en_03 mix_01 mix_02 mix_03 mix_04)
for case_id in "${cases[@]}"; do
  printf '\n[%s] Press Enter, speak naturally, then press Enter again.\n' "$case_id"
  read -r
  pw-record --rate 16000 --channels 1 "$OUT_DIR/$case_id.wav" &
  recorder_pid=$!
  read -r
  kill -INT "$recorder_pid" 2>/dev/null || true
  wait "$recorder_pid" 2>/dev/null || true
  printf 'Saved %s.wav\n' "$case_id"
done

printf '\nVoice Lab recordings are in %s\n' "$OUT_DIR"
