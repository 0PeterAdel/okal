"""Brand route uses only a validated owner PNG or bundled WebP fallback."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import struct
import unittest

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.store import Store


class BrandAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "state")
        self.client = TestClient(create_app(self.store),
                                 base_url="http://127.0.0.1:8766",
                                 client=("127.0.0.1", 1234))
        self.addCleanup(self.client.close)

    def test_fallback_remains_webp_when_no_high_res_master(self):
        response = self.client.get("/assets/okal-identity")
        self.assertEqual(response.status_code, 200)
        self.assertIn("image/webp", response.headers["content-type"])
        self.assertEqual(response.content[:4], b"RIFF")
        self.assertEqual(response.headers["content-security-policy"][:16],
                         "default-src 'non")

    def test_private_owner_png_overrides_bundled_webp(self):
        brand = self.store.directory / "brand"
        brand.mkdir(mode=0o700)
        logo = brand / "okal-approved-master.png"
        header = (
            b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
            + struct.pack(">II", 1254, 1254)
        )
        logo.write_bytes(header + b"\x00" * 11000)
        logo.chmod(0o600)
        response = self.client.get("/assets/okal-identity")
        self.assertEqual(response.status_code, 200)
        self.assertIn("image/png", response.headers["content-type"])
        self.assertEqual(response.content[:8], b"\x89PNG\r\n\x1a\n")

    def test_insecure_owner_asset_rejected_to_fallback(self):
        brand = self.store.directory / "brand"
        brand.mkdir(mode=0o700)
        logo = brand / "okal-approved-master.png"
        logo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00"*11000)
        logo.chmod(0o644)
        response = self.client.get("/assets/okal-identity")
        self.assertIn("image/webp", response.headers["content-type"])


if __name__ == "__main__":
    unittest.main()
