import json
import tempfile
import unittest
from pathlib import Path

from okal_voice.model_conversion import preprocessor_config


class ModelConversionTests(unittest.TestCase):
    def test_extracts_nested_feature_config_for_128_mel_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = {"feature_size": 128, "sampling_rate": 16000, "n_fft": 400}
            (root / "processor_config.json").write_text(
                json.dumps({"feature_extractor": feature}), encoding="utf-8"
            )
            (root / "config.json").write_text(json.dumps({"num_mel_bins": 128}), encoding="utf-8")
            self.assertEqual(preprocessor_config(str(root)), feature)

            (root / "config.json").write_text(json.dumps({"num_mel_bins": 80}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                preprocessor_config(str(root))


if __name__ == "__main__":
    unittest.main()
