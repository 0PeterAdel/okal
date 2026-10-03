"""The TTS trial must not start another multi-gigabyte download."""

import io
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from okal_voice.tts_lab import check_cache, download_missing, main


class TtsCacheTests(unittest.TestCase):
    def test_missing_cache_stops_before_importing_model(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"HF_HUB_CACHE": tmp}):
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(["--cache-status", "--speaker", "Asmaa"])
            self.assertEqual(result, 2)
            self.assertIn("No download started", output.getvalue())
            self.assertIn("model.safetensors", output.getvalue())
            self.assertIn("Higgs audio tokenizer", output.getvalue())

    def test_complete_cached_components_pass_without_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"HF_HUB_CACHE": tmp}):
            revision = "a" * 40

            def cached(repo, files):
                root = Path(tmp) / ("models--" + repo.replace("/", "--"))
                (root / "refs").mkdir(parents=True)
                (root / "refs/main").write_text(revision, encoding="utf-8")
                snapshot = root / "snapshots" / revision
                for name, size in files.items():
                    path = snapshot / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("wb") as file:
                        file.truncate(size)

            cached("mohammedaly22/VoiceTut-TTS", {
                "config.json": 1, "model.safetensors": 2_450_000_000,
                "tokenizer.json": 1, "reference_speakers/references.json": 1,
                "reference_speakers/Asmaa_clean.wav": 1,
            })
            cached("eustlb/higgs-audio-v2-tokenizer", {
                "config.json": 1, "model.safetensors": 806_000_000,
                "preprocessor_config.json": 1,
            })
            snapshot, missing = check_cache(("Asmaa",))
            self.assertFalse(missing)
            self.assertEqual(snapshot.name, revision)
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(["--cache-status", "--speaker", "Asmaa"])
            self.assertEqual(result, 0)
            self.assertIn("No download started", output.getvalue())

    def test_download_uses_pinned_cache_and_only_inference_files(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"HF_HUB_CACHE": tmp}):
            revision = "a" * 40
            root = Path(tmp) / "models--mohammedaly22--VoiceTut-TTS"
            (root / "refs").mkdir(parents=True)
            (root / "refs/main").write_text(revision, encoding="utf-8")
            calls = []

            def download(repo, name, *, revision):
                calls.append((repo, name, revision))
                repo_root = Path(tmp) / ("models--" + repo.replace("/", "--"))
                (repo_root / "refs").mkdir(parents=True, exist_ok=True)
                (repo_root / "refs/main").write_text("b" * 40 if repo != "mohammedaly22/VoiceTut-TTS" else revision, encoding="utf-8")
                path = repo_root / "snapshots" / ("b" * 40 if repo != "mohammedaly22/VoiceTut-TTS" else revision) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("wb") as file:
                    file.truncate(2_450_000_000 if repo == "mohammedaly22/VoiceTut-TTS" and name == "model.safetensors" else 806_000_000 if name == "model.safetensors" else 1)
                return str(path)

            with patch.dict(sys.modules, {"huggingface_hub": types.SimpleNamespace(hf_hub_download=download)}):
                with redirect_stdout(io.StringIO()):
                    download_missing(("Asmaa",))
                    download_missing(("Asmaa",))
            names = [name for _, name, _ in calls]
            self.assertNotIn("optimizer.bin", names)
            self.assertEqual(names.count("model.safetensors"), 2)
            self.assertEqual(len(calls), len(set((repo, name) for repo, name, _ in calls)))
            self.assertTrue(all(rev == revision for repo, _, rev in calls if repo == "mohammedaly22/VoiceTut-TTS"))
            self.assertTrue(all(rev in ("main", "b" * 40) for repo, _, rev in calls if repo != "mohammedaly22/VoiceTut-TTS"))


if __name__ == "__main__":
    unittest.main()
