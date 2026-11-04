"""Git-tracked OKAL master logo: no machine-specific fallback or override."""

import hashlib
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from okal_core.api import STATIC, create_app
from okal_core.store import Store


class BrandAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "state")
        self.client = TestClient(
            create_app(self.store),
            base_url="http://127.0.0.1:8766",
            client=("127.0.0.1", 1234),
        )
        self.addCleanup(self.client.close)

    def test_master_is_checked_into_repo_at_original_resolution(self):
        path = STATIC / "assets" / "okal-master-hq.webp"
        self.assertTrue(path.is_file(), "Copy and commit okal-master-hq.webp to Git")
        raw = path.read_bytes()
        self.assertGreater(len(raw), 200_000)
        self.assertFalse((STATIC / "assets" / "okal-master.webp").exists(),
                         "Remove obsolete 9 KB thumbnail from Git")
        self.assertEqual(raw[0:4], b"RIFF")
        self.assertEqual(raw[8:16], b"WEBPVP8X")
        self.assertEqual(int.from_bytes(raw[24:27], "little") + 1, 1254)
        self.assertEqual(int.from_bytes(raw[27:30], "little") + 1, 1254)

    def test_browser_image_urls_are_routable_and_return_exact_git_bytes(self):
        """Catch HTML URL query strings that middleware would reject with 400."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.text
        img_urls = re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', html)
        self.assertEqual(img_urls, ["/assets/okal-master-hq.webp"] * 2)
        source_bytes = (STATIC / "assets" / "okal-master-hq.webp").read_bytes()
        for url in img_urls:
            with self.subTest(url=url):
                image_response = self.client.get(
                    url,
                    headers={
                        "accept": "image/avif,image/webp,image/*;q=0.8",
                        "referer": "http://127.0.0.1:8766/",
                        "sec-fetch-dest": "image",
                        "sec-fetch-mode": "no-cors",
                        "sec-fetch-site": "same-origin",
                    },
                )
                self.assertEqual(image_response.status_code, 200,
                                 image_response.text[:200] if image_response.status_code != 200 else "")
                self.assertEqual(image_response.headers["content-type"].split(";")[0],
                                 "image/webp")
                self.assertEqual(image_response.content, source_bytes)

    def test_query_parameters_are_not_needed_for_same_origin_brand_images(self):
        """Global query policy must not be bypassed to load static images."""
        self.assertEqual(
            self.client.get("/assets/okal-master-hq.webp?v=1254-design-v1").status_code,
            400,
        )
        self.assertIn("no-store",
                      self.client.get("/assets/okal-master-hq.webp").headers["cache-control"])

    def test_repo_master_route_serves_same_bytes_as_git_file(self):
        file_bytes = (STATIC / "assets" / "okal-master-hq.webp").read_bytes()
        for url in ("/assets/okal-master-hq.webp", "/assets/okal-identity",
                    "/assets/okal-master.webp"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn("image/webp", response.headers["content-type"])
                self.assertEqual(
                    hashlib.sha256(response.content).digest(),
                    hashlib.sha256(file_bytes).digest(),
                )

    def test_old_private_logo_never_overrides_git_image(self):
        brand = self.store.directory / "brand"
        brand.mkdir(mode=0o700)
        stale_override = brand / "okal-approved-master.png"
        stale_override.write_bytes(b"private-should-not-display" * 1000)
        stale_override.chmod(0o600)
        master = self.client.get("/assets/okal-master-hq.webp")
        alias = self.client.get("/assets/okal-identity")
        self.assertEqual(master.content, alias.content)
        self.assertEqual(alias.headers["content-type"].split(";")[0], "image/webp")


if __name__ == "__main__":
    unittest.main()
