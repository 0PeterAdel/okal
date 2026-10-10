import io
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

from okal_voice import tts_worker


class TtsWorkerTests(unittest.TestCase):
    def test_serve_loads_cached_asmaa_once_and_renders_two_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = [Path(tmp) / "one.wav", Path(tmp) / "two.wav"]
            lines = "".join(json.dumps({"text": text, "output": str(path)}, ensure_ascii=False) + "\n"
                            for text, path in zip(("مساء الخير", "أنا معاك"), outputs))
            engine = mock.Mock()
            engine.synthesize.side_effect = lambda text, **kwargs: Path(kwargs["output"]).write_bytes(b"RIFF")
            module = ModuleType("voicetut_tts")
            module.VoiceTutTTS = mock.Mock()
            module.VoiceTutTTS.from_pretrained.return_value = engine
            result = io.StringIO()
            with mock.patch.dict("sys.modules", {"voicetut_tts": module}), \
                 mock.patch.object(tts_worker, "check_cache", return_value=(Path(tmp), [])), \
                 mock.patch("sys.stdin", io.StringIO(lines)), mock.patch("sys.stdout", result):
                self.assertEqual(tts_worker.main(["--speaker", "Asmaa", "--serve"]), 0)
            self.assertEqual(module.VoiceTutTTS.from_pretrained.call_count, 1)
            self.assertEqual(engine.synthesize.call_count, 2)
            self.assertTrue(all(path.read_bytes() == b"RIFF" for path in outputs))
            self.assertEqual(result.getvalue().count('OKAL_TTS {"ok": true}'), 2)


if __name__ == "__main__":
    unittest.main()
