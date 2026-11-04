"""Every installation must serve the same Git-tracked 1254px logo."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
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

    def test_repo_brand_is_full_resolution_webp_on_fresh_clone(self):
        """Production cannot silently regress to the 9 KB thumbnail."""
        response = self.client.get("/assets/okal-identity")
        self.assertEqual(response.status_code, 200)
        self.assertIn("image/webp", response.headers["content-type"])
        self.assertGreater(len(response.content), 200_000)
        self.assertEqual(response.content[:4], b"RIFF")
        self.assertEqual(response.content[8:16], b"WEBPVP8X")
        self.assertEqual(int.from_bytes(response.content[24:27], "little") + 1, 1254)
        self.assertEqual(int.from_bytes(response.content[27:30], "little") + 1, 1254)
        self.assertEqual(hashlib.sha256(response.content).hexdigest(),
                         "43d864616984749a29bbe636d5e312fcf0ad65ecc6b84c1ca2127eb47cfd7d24")
        # The global secure-response middleware enforces no-store instead.
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertEqual(response.headers["content-security-policy"][:16],
                         "default-src 'non")

    def test_direct_repo_brand_asset_is_high_quality(self):
        response = self.client.get("/assets/okal-master-hq.webp")
        self.assertEqual(response.status_code, 200)
        self.assertIn("image/webp", response.headers["content-type"])
        self.assertGreater(len(response.content), 200_000)
        self.assertEqual(response.content[8:16], b"WEBPVP8X")
        self.assertEqual(int.from_bytes(response.content[24:27], "little") + 1, 1254)

    def test_html_uses_repo_asset_directly_with_cache_revision(self):
        from okal_core.api import STATIC
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('src="/assets/okal-master-hq.webp?brand=1254-v2"'), 2)

    def test_existing_private_logo_cannot_replace_repo_asset(self):
        """Existing machine-specific files must not override Git content."""
        brand = self.store.directory / "brand"
        brand.mkdir(mode=0o700)
        logo = brand / "okal-approved-master.png"
        logo.write_bytes(b"not-a-logo" * 3000)
        logo.chmod(0o600)
        direct = self.client.get("/assets/okal-master-hq.webp")
        alias = self.client.get("/assets/okal-identity")
        self.assertEqual(direct.status_code, 200)
        self.assertEqual(alias.status_code, 200)
        self.assertEqual(direct.content, alias.content)
        self.assertEqual(hashlib.sha256(alias.content).hexdigest(),
                         "43d864616984749a29bbe636d5e312fcf0ad65ecc6b84c1ca2127eb47cfd7d24")
        self.assertEqual(alias.headers["content-type"].split(";")[0], "image/webp")


if __name__ == "__main__":
    unittest.main()
