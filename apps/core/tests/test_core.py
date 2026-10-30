import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient
from pydantic import ValidationError

from okal_core.api import create_app
from okal_core.models import SummaryInput
from okal_core.store import Conflict, InvalidCursor, Store


def item(number=1, **changes):
    values = dict(
        workflow="demo",
        account_ref="private-account-reference",
        occurrence=f"occurrence-{number}",
        title=f"Demo {number}",
        body="Not real email",
        data_kind="fixture",
    )
    values.update(changes)
    return SummaryInput(**values)


class CoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / "state"
        self.now = 1800000000
        self.store = Store(self.directory, clock=lambda: self.now)
        self.device = self.store.issue_device("test browser")
        self.headers = {"Authorization": "Bearer " + self.device["token"]}
        self.client = TestClient(
            create_app(self.store),
            base_url="http://127.0.0.1:8766",
            client=("127.0.0.1", 12345),
        )
        self.addCleanup(self.client.close)

    def test_private_modes(self):
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)

    def test_refuse_shared_directory_and_symlinks(self):
        bad = Path(self.tmp.name) / "shared"
        bad.mkdir(mode=0o755)
        with self.assertRaises(ValueError):
            Store(bad)
        link = Path(self.tmp.name) / "link"
        link.symlink_to(self.directory)
        with self.assertRaises(ValueError):
            Store(link)
        other = Path(self.tmp.name) / "other"
        other.mkdir(mode=0o700)
        (other / "core.sqlite3").symlink_to(self.store.path)
        with self.assertRaises(OSError):
            Store(other)

    def test_token_never_persisted_or_listed(self):
        self.assertNotIn(self.device["token"].encode(), self.store.path.read_bytes())
        listed = self.store.list_devices()
        self.assertEqual(listed[0]["scope"], "inbox:read")
        self.assertNotIn("token", listed[0])
        self.assertNotIn("verifier", listed[0])

    def test_token_expiry_and_revocation(self):
        self.assertTrue(self.store.authenticate(self.device["token"]))
        self.now = self.device["expires_at"]
        self.assertFalse(self.store.authenticate(self.device["token"]))
        self.now -= 1
        self.assertTrue(self.store.revoke_device(self.device["id"]))
        self.assertFalse(Store(self.directory).authenticate(self.device["token"]))
        self.assertFalse(self.store.revoke_device("unknown"))

    def test_invalid_token_and_device_inputs(self):
        for token in ("", "a" * 10000, "中文", "x" * 43):
            self.assertFalse(self.store.authenticate(token))
        for days in (0, 91, True, 1.5):
            with self.assertRaises(ValueError):
                self.store.issue_device("browser", days)

    def test_atomic_idempotent_persistence(self):
        run_id = self.store.record_success(item())
        reopened = Store(self.directory)
        self.assertEqual(reopened.record_success(item()), run_id)
        self.assertEqual(len(reopened.list_summaries()["items"]), 1)
        self.assertEqual(reopened.get_run(run_id)["status"], "succeeded")
        self.assertNotIn("account_ref", reopened.get_run(run_id))

    def test_conflicting_replay_preserves_original(self):
        self.store.record_success(item())
        with self.assertRaises(Conflict):
            self.store.record_success(item(body="Changed"))
        self.assertEqual(
            self.store.list_summaries()["items"][0]["body"], "Not real email"
        )

    def test_concurrent_replay(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            ids = list(pool.map(lambda _: self.store.record_success(item()), range(12)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(self.store.list_summaries()["items"]), 1)

    def test_transaction_rolls_back_incomplete_run(self):
        with self.store.connect() as db, db:
            db.execute(
                "CREATE TRIGGER fail_summary BEFORE INSERT ON summaries "
                "BEGIN SELECT RAISE(ABORT, 'test interruption'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_success(item())
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)

    def test_cursor_stable_across_insert_and_restart(self):
        for n in range(5):
            self.store.record_success(item(n))
        first = self.store.list_summaries(2)
        self.store.record_success(item(99))
        reopened = Store(self.directory)
        second = reopened.list_summaries(2, first["next_cursor"])
        third = reopened.list_summaries(2, second["next_cursor"])
        ids = [x["id"] for page in (first, second, third) for x in page["items"]]
        self.assertEqual(ids, [5, 4, 3, 2, 1])
        self.assertIsNone(third["next_cursor"])
        self.assertEqual(reopened.list_summaries()["items"][0]["id"], 6)

    def test_cursor_and_limit_validation(self):
        for raw in (
            None,
            [],
            {"v": 1, "b": True, "s": 1},
            {"v": 1, "b": -1, "s": 0},
            {"v": 1, "b": 1, "s": 2**64},
            {"v": 2, "b": 1, "s": 1},
        ):
            cursor = (
                base64.urlsafe_b64encode(json.dumps(raw).encode()).decode().rstrip("=")
            )
            with self.assertRaises(InvalidCursor):
                self.store.list_summaries(cursor=cursor)
        for cursor in ("!", "a", "a" * 161):
            with self.assertRaises(InvalidCursor):
                self.store.list_summaries(cursor=cursor)
        for limit in (0, 101, True):
            with self.assertRaises(ValueError):
                self.store.list_summaries(limit)

    def test_model_bounds_and_unknown_fields(self):
        for changes in (
            {"body": ""},
            {"title": "a" * 201},
            {"body": "a" * 12001},
            {"workflow": "shell"},
            {"data_kind": "verified"},
            {"command": "id"},
        ):
            with self.assertRaises(ValidationError):
                item(**changes)

    def test_sql_and_html_are_data(self):
        payload = "<img src=x onerror=alert(1)> '); DROP TABLE runs; --"
        self.store.record_success(item(title=payload, body=payload))
        self.assertEqual(self.store.list_summaries()["items"][0]["body"], payload)

    def test_future_schema_rejected(self):
        with self.store.connect() as db:
            db.execute("PRAGMA user_version=99")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            Store(self.directory)

    def test_backup_refuses_overwrite_and_restores(self):
        run_id = self.store.record_success(item())
        backup = Path(self.tmp.name) / "backup.sqlite3"
        self.store.backup(backup)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            self.store.backup(backup)
        restored = Path(self.tmp.name) / "restored"
        restored.mkdir(mode=0o700)
        shutil.copy2(backup, restored / "core.sqlite3")
        self.assertEqual(Store(restored).get_run(run_id)["status"], "succeeded")

    def test_health_minimal_and_security_headers(self):
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.json(), {"status": "ok", "schema_version": 1})
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn(
            "frame-ancestors 'none'", response.headers["content-security-policy"]
        )
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_all_private_routes_require_auth(self):
        for path in (
            "/api/v1/summaries",
            "/api/v1/capabilities",
            "/api/v1/runs/missing",
            "/api/v1/requests",
            "/api/v1/unknown",
        ):
            self.assertEqual(self.client.get(path).status_code, 401)
        response = self.client.get("/api/v1/summaries?limit=bad")
        self.assertEqual(response.status_code, 401)  # before request validation

    def test_header_only_auth_and_duplicates(self):
        self.client.cookies.set("token", self.device["token"])
        self.assertEqual(self.client.get("/api/v1/summaries").status_code, 401)
        self.client.cookies.clear()
        self.assertEqual(
            self.client.get(
                "/api/v1/summaries?token=" + self.device["token"]
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/summaries?token=ignored", headers=self.headers
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/summaries",
                headers=[
                    ("Authorization", self.headers["Authorization"]),
                    ("Authorization", self.headers["Authorization"]),
                ],
            ).status_code,
            401,
        )

    def test_auth_read_and_redacted_run(self):
        run_id = self.store.record_success(item())
        response = self.client.get("/api/v1/summaries", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["data_kind"], "fixture")
        run = self.client.get("/api/v1/runs/" + run_id, headers=self.headers)
        self.assertEqual(run.status_code, 200)
        self.assertNotIn("private-account-reference", run.text)
        self.assertNotIn("digest", run.text)
        self.assertEqual(
            self.client.get("/api/v1/runs/missing", headers=self.headers).status_code,
            404,
        )

    def test_revocation_applies_to_live_api(self):
        self.store.revoke_device(self.device["id"])
        self.assertEqual(
            self.client.get("/api/v1/summaries", headers=self.headers).status_code, 401
        )

    def test_no_writes_or_remote_capabilities(self):
        caps = self.client.get("/api/v1/capabilities", headers=self.headers).json()
        self.assertEqual(caps["providers"], [])
        for key in ("external_writes", "remote_pairing", "scheduler", "voice"):
            self.assertFalse(caps[key])
        self.assertEqual(
            self.client.post(
                "/api/v1/summaries", headers=self.headers, json={}
            ).status_code,
            405,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/requests", headers=self.headers, json={}
            ).status_code,
            404,
        )

    def test_host_origin_and_nonloopback_denied(self):
        for extra in (
            {"Host": "attacker.test"},
            {"Origin": "https://attacker.test"},
            {"Origin": "null"},
            {"Sec-Fetch-Site": "cross-site"},
        ):
            self.assertEqual(
                self.client.get(
                    "/api/v1/summaries", headers=self.headers | extra
                ).status_code,
                403,
            )
        remote = TestClient(
            create_app(self.store),
            base_url="http://127.0.0.1:8766",
            client=("192.168.1.20", 12345),
        )
        with remote:
            self.assertEqual(
                remote.get(
                    "/api/v1/health", headers={"X-Forwarded-For": "127.0.0.1"}
                ).status_code,
                403,
            )

    def test_bounded_queries_and_disabled_docs(self):
        self.assertEqual(
            self.client.get(
                "/api/v1/summaries?limit=101", headers=self.headers
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/summaries?cursor=broken", headers=self.headers
            ).status_code,
            400,
        )
        for path in ("/docs", "/openapi.json", "/redoc", "/core.sqlite3"):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_static_shell_has_no_storage_or_unsafe_html(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        code = self.client.get("/app.js").text
        for forbidden in (
            "innerHTML",
            "localStorage",
            "sessionStorage",
            "serviceWorker",
            "eval(",
        ):
            self.assertNotIn(forbidden, code)
        self.assertIn("textContent", code)

    def test_cli_restart_demo_and_revoke(self):
        command = [
            sys.executable,
            "-m",
            "okal_core",
            "--state-dir",
            str(self.directory),
        ]
        for _ in range(2):
            subprocess.run(command + ["demo"], check=True, capture_output=True)
        self.assertEqual(len(self.store.list_summaries()["items"]), 2)
        issued = subprocess.run(
            command + ["device-add", "cli-test"],
            check=True,
            capture_output=True,
            text=True,
        )
        device = json.loads(issued.stdout)
        live_clock_store = Store(self.directory)
        self.assertTrue(live_clock_store.authenticate(device["token"]))
        subprocess.run(
            command + ["device-revoke", device["id"]], check=True, capture_output=True
        )
        self.assertFalse(live_clock_store.authenticate(device["token"]))
        result = subprocess.run(
            command + ["serve", "--host", "0.0.0.0"], capture_output=True
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
