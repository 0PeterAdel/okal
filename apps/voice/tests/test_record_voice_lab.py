import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/record-voice-lab.sh"


class RecorderTests(unittest.TestCase):
    def test_prompts_use_terminal_input_instead_of_case_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            binaries.mkdir()
            for name, body in {
                "python3": "printf '%s\\n' \"$*\" > \"$CASE_ARGS\"\nprintf 'ar_01\\tاختبار التسجيل\\n'\n",
                "pw-record": "printf 'WAV' > \"${@: -1}\"\n",
                "ffprobe": "printf '1.0\\n'\n",
                "ffmpeg": "printf '[Parsed_volumedetect_0] max_volume: -12.0 dB\\n' >&2\n",
                "pw-play": ":\n",
            }.items():
                path = binaries / name
                path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
                path.chmod(0o755)

            audio = root / "recordings/ar_01.wav"
            env = dict(os.environ, PATH=f"{binaries}:{os.environ['PATH']}", CASE_ARGS=str(root / "case-args"))
            process = subprocess.Popen(
                ["bash", str(SCRIPT), str(audio.parent), "holdout"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            try:
                assert process.stdin is not None
                process.stdin.write("\n")
                process.stdin.flush()
                deadline = time.monotonic() + 3
                while not any(path.stat().st_size for path in audio.parent.glob(".ar_01.*.wav")) and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(any(path.stat().st_size for path in audio.parent.glob(".ar_01.*.wav")), "recorder did not wait for the first Enter")
                output, errors = process.communicate(input="\n\n", timeout=5)
                self.assertEqual(process.returncode, 0, errors)
                self.assertIn("Saved ar_01.wav", output)
                self.assertTrue(audio.is_file())
                self.assertIn("--suite holdout --list-cases", (root / "case-args").read_text())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_silent_clip_is_retried_without_replacing_previous_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            binaries.mkdir()
            volume_count = root / "volume-count"
            for name, body in {
                "python3": "printf 'ar_01\\tاختبار التسجيل\\n'\n",
                "pw-record": "printf 'WAV' > \"${@: -1}\"\n",
                "ffprobe": "printf '1.0\\n'\n",
                "pw-play": ":\n",
                "ffmpeg": (
                    'count=0; [[ ! -f "$VOLUME_COUNT" ]] || read -r count < "$VOLUME_COUNT"\n'
                    'count=$((count + 1)); printf "%s\\n" "$count" > "$VOLUME_COUNT"\n'
                    'if [[ "$count" == 1 ]]; then peak=-inf; else peak=-12.0; fi\n'
                    'printf "max_volume: %s dB\\n" "$peak" >&2\n'
                ),
            }.items():
                path = binaries / name
                path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
                path.chmod(0o755)

            audio = root / "recordings/ar_01.wav"
            audio.parent.mkdir()
            audio.write_bytes(b"old")
            env = dict(os.environ, PATH=f"{binaries}:{os.environ['PATH']}", VOLUME_COUNT=str(volume_count))
            process = subprocess.Popen(
                ["bash", str(SCRIPT), str(audio.parent)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=env,
            )
            try:
                assert process.stdin is not None
                for attempt in (1, 2):
                    process.stdin.write("\n")
                    process.stdin.flush()
                    deadline = time.monotonic() + 3
                    while not any(path.stat().st_size for path in audio.parent.glob(".ar_01.*.wav")) and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(any(path.stat().st_size for path in audio.parent.glob(".ar_01.*.wav")))
                    self.assertEqual(audio.read_bytes(), b"old")
                    process.stdin.write("\n")
                    process.stdin.flush()
                    if attempt == 1:
                        deadline = time.monotonic() + 3
                        while not volume_count.exists() and process.poll() is None and time.monotonic() < deadline:
                            time.sleep(0.01)
                        self.assertEqual(volume_count.read_text().strip(), "1")
                        deadline = time.monotonic() + 3
                        while list(audio.parent.glob(".ar_01.*.wav")) and process.poll() is None and time.monotonic() < deadline:
                            time.sleep(0.01)
                output, errors = process.communicate(input="\n", timeout=5)
                self.assertEqual(process.returncode, 0, errors)
                self.assertIn("Silent or very quiet recording", errors)
                self.assertIn("Saved ar_01.wav", output)
                self.assertEqual(audio.read_bytes(), b"WAV")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()


if __name__ == "__main__":
    unittest.main()
