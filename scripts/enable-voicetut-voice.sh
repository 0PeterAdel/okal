#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LAB_PYTHON="$ROOT/.venv-okal-tts-lab/bin/python"
VOICE_PYTHON="$ROOT/.venv-okal-voice/bin/python"
ENV_FILE="$HOME/.config/okal/voice.env"

if [[ ! -x "$LAB_PYTHON" || ! -x "$VOICE_PYTHON" ]]; then
  echo "Both existing VoiceTut and voice Python environments are required." >&2
  exit 1
fi

# This preflight never uses the network. A missing model must not enable TTS.
bash "$ROOT/scripts/run-tts-voice-lab.sh" --cache-status --speaker Asmaa
bash "$ROOT/scripts/install-local-voice.sh"

"$VOICE_PYTHON" - "$ENV_FILE" "$LAB_PYTHON" <<'PY'
import os
import sys
import tempfile
from pathlib import Path

path, interpreter = map(Path, sys.argv[1:])
values = {
    "OKAL_VOICETUT_ENABLED": "1",
    "OKAL_VOICETUT_SPEAKER": "Asmaa",
    "OKAL_VOICETUT_PYTHON": str(interpreter),
}
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
kept = [line for line in lines if line.split("=", 1)[0].strip().removeprefix("export ") not in values]
kept += [f"{key}={value}" for key, value in values.items()]
path.parent.mkdir(parents=True, exist_ok=True)
fd, temp_name = tempfile.mkstemp(prefix="voice.env.", dir=path.parent)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write("\n".join(kept) + "\n")
    os.replace(temp_name, path)
finally:
    if os.path.exists(temp_name):
        os.unlink(temp_name)
PY

systemctl --user restart okal-voice.service
"$HOME/.local/bin/okal" voice doctor
printf 'VoiceTut Asmaa enabled. Try: okal voice say '\''مساء الخير يا بيتر'\''\n'
