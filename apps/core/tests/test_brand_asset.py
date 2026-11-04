"""Brand route uses validated owner PNG or committed full-resolution WebP."""
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

    def test_repo_fallback_is_full_resolution_webp_on_fresh_clone(self):
        """Production cannot silently regress to the 9 KB thumbnail."""
        response = self.client.get("/assets/okal-identity")
        self.assertEqual(response.status_code, 200)
        self.assertIn("image/webp", response.headers["content-type"])
        self.assertGreater(len(response.content), 200_000)
        self.assertEqual(response.content[:4], b"RIFF")
        self.assertEqual(response.content[8:16], b"WEBPVP8X")
        self.assertEqual(int.from_bytes(response.content[24:27], "little") + 1, 1254)
        self.assertEqual(int.from_bytes(response.content[27:30], "little") + 1, 1254)
        self.assertIn("no-cache", response.headers["cache-control"])
        self.assertEqual(response.headers["content-security-policy"][:16],
                         "default-src 'non")

    def test_direct_repo_brand_asset_is_high_quality(self):
        response = self.client.get("/assets/okal-master-hq.webp")
        self.assertEqual(response.status_code, 200)
        self.assertIn("image/webp", response.headers["content-type"])
        self.assertGreater(len(response.content), 200_000)
        self.assertEqual(response.content[8:16], b"WEBPVP8X")
        self.assertEqual(int.from_bytes(response.content[24:27], "little") + 1, 1254)

    def test_html_uses_identity_endpoint_with_cache_revision(self):
        from okal_core.api import STATIC
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('src="/assets/okal-identity?brand=1254-v1"'), 2)

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
