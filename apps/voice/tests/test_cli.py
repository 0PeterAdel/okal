"""Readiness checks for the installed voice profile."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from okal_voice.cli import doctor, load_voice_environment
from okal_voice.config import VoiceConfig


class VoiceCliTests(unittest.TestCase):
    def test_environment_file_is_data_and_shell_can_override(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"OKAL_STT_DEVICE": "cpu"}, clear=True):
            path = Path(tmp) / "voice.env"
            path.write_text('OKAL_STT_MODEL_DIR="/some model/path"\nOKAL_STT_DEVICE=cuda\nIGNORED=x\n', encoding="utf-8")
            load_voice_environment(path)
            self.assertEqual(os.environ["OKAL_STT_DEVICE"], "cpu")
            self.assertEqual(os.environ["OKAL_STT_MODEL_DIR"], "/some model/path")
            self.assertNotIn("IGNORED", os.environ)

    def test_faster_whisper_doctor_checks_active_model_not_whisper_cpp(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp)
            (model / "model.bin").write_bytes(b"x")
            (model / "config.json").write_text("{}", encoding="utf-8")
            config = VoiceConfig(stt_model_dir=model, stt_device="cpu", silma_enabled=False)
            with patch("okal_voice.cli.urlopen", side_effect=OSError("offline")):
                _, checks = doctor(config)
            names = {item["name"] for item in checks}
            self.assertIn("STT model", names)
            self.assertNotIn("Whisper model", names)
            self.assertNotIn("whisper.cpp", names)
            self.assertTrue(next(item["ok"] for item in checks if item["name"] == "STT model"))
            (model / "model.bin").unlink()
            with patch("okal_voice.cli.urlopen", side_effect=OSError("offline")):
                _, checks = doctor(config)
            self.assertFalse(next(item["ok"] for item in checks if item["name"] == "STT model"))


if __name__ == "__main__":
    unittest.main()
