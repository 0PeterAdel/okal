import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okal_voice.contracts import VoicePhase, VoiceSnapshot
from okal_voice.runtime import StateStore, runtime_dir


class RuntimeTests(unittest.TestCase):
    def test_refuses_tmp_fallback(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            runtime_dir()

    def test_files_and_directory_are_owner_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "voice"
            store = StateStore(root)
            store.publish(VoiceSnapshot.new(VoicePhase.IDLE))
            store.write_level(0.5)
            store.append_route({"route": "conversation"})
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            for path in (store.state_path, store.level_path, store.route_path):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_missing_state_is_idle(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = StateStore(Path(temporary) / "voice")
            self.assertEqual(store.read().phase, VoicePhase.IDLE)


if __name__ == "__main__":
    unittest.main()
