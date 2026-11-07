"""Owner-directed disk questions use verified read-only tools, not AI guesses."""
from pathlib import Path
import tempfile
import unittest
import uuid

from okal_core.computer.chat import DEVICE_STATUS, propose_for_chat
from okal_core.computer.engine import Engine
from okal_core.computer.system_status import disk_status
from okal_core.intelligence import Intelligence
from okal_core.store import Store


class ChatDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = Store(Path(temporary.name) / "state")
        self.conversation_id = Intelligence(self.store).create()["id"]
        self.engine = Engine(self.store)

    def configure(self, tools):
        record = self.engine.policy()
        return self.engine.configure({
            "mode": "read_only",
            "tools": tools,
            "roots": [],
            "browser_origins": [],
            "commands": {},
            "applications": [],
            "accounts": [],
        }, record["revision"])

    def test_explicit_arabic_english_and_command_queries_route(self):
        for query in (
            "عندي كام هارد متوصل بالجهاز؟",
            "وريني مساحة الهارد",
            "كم عدد الأقراص عندي؟",
            "How many hard drives are connected?",
            "Show disk space on my device",
            "df -h",
            "lsblk",
        ):
            with self.subTest(query=query):
                self.assertIsNotNone(DEVICE_STATUS.search(query))
        for query in ("How large is Jupiter?", "مساحة المثلث كام؟", "Hello OKAL"):
            with self.subTest(query=query):
                self.assertIsNone(DEVICE_STATUS.search(query))

    def test_default_deny_is_precise_about_missing_tool(self):
        result = propose_for_chat(
            self.store, self.conversation_id, uuid.uuid4().hex,
            "عندي كام هارد؟",
        )
        self.assertEqual(result["source"], "action_permission_policy")
        self.assertNotIn("action_run", result)
        self.assertIn("system.status", result["answer"])

    def test_enabled_diagnostic_proposes_without_model_or_shell(self):
        self.configure(["system.status"])
        request_id = uuid.uuid4().hex
        result = propose_for_chat(
            self.store, self.conversation_id, request_id,
            "عندي كام هارد متوصل؟",
        )
        self.assertEqual(result["source"], "proposed_action_plan")
        run = self.engine.get(result["action_run"])
        self.assertEqual(run["plan"]["steps"], [
            {"tool": "system.status", "arguments": {}},
        ])
        self.assertEqual(run["status"], "ready")
        finished = self.engine.execute(run["id"])
        self.assertEqual(finished["status"], "succeeded")
        record = self.engine.get(run["id"])["steps"][0]["result"]
        self.assertTrue(record["verified"])
        self.assertIsInstance(record["evidence"]["block_devices"], list)
        self.assertIsInstance(record["evidence"]["mounted_space"], list)

    def test_block_devices_are_not_partitions_and_mounts_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            block = root / "sys"
            block.mkdir()
            for name, sectors, removable in (
                ("sda", 2000, 0), ("sdb", 3000, 1),
                ("loop0", 6000, 0), ("sda1", 400, 0),
            ):
                entry = block / name
                entry.mkdir()
                (entry / "size").write_text(str(sectors))
                (entry / "removable").write_text(str(removable))
            (block / "sda1" / "partition").write_text("1")
            mounts = root / "mounts"
            mounts.write_text(
                "1 2 8:1 / / rw - ext4 /dev/sda1 rw\n"
                "3 2 0:1 / /home/okal/.local/state/okal-core rw - ext4 /dev/sda1 rw\n"
            )
            status = disk_status(block, mounts)
            self.assertEqual(status["block_device_count"], 2)
            self.assertEqual([v["name"] for v in status["block_devices"]], ["sda", "sdb"])
            self.assertEqual(status["block_devices"][0]["size_bytes"], 1024000)
            self.assertEqual(status["block_devices"][1]["removable"], True)
            self.assertEqual([v["mountpoint"] for v in status["mounted_space"]], ["/"])
            self.assertFalse(status["inventory_limited"])


if __name__ == "__main__":
    unittest.main()
