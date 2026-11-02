"""Remote Settings safety gates: separate key, local-only, no arbitrary commands."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from okal_core.api import create_app
from okal_core.store import Store
from okal_core import remote_control as remote


class RemoteSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.store=Store(self.root/"state")

    def test_control_key_is_private_and_expires_without_browser_storage(self):
        config=self.root/"config"
        with patch.object(remote,"CONFIG_DIR",config), patch.object(
            remote,"CONTROL_FILE",config/"key.json"
        ):
            with patch.object(remote.time,"time",return_value=1000):
                key=remote.issue_control_key()
                self.assertTrue(remote.authorize_control_key(key))
                self.assertFalse(remote.authorize_control_key("wrong"))
                self.assertFalse(remote.authorize_control_key(key[:-1]+"X"))
                self.assertEqual((config/"key.json").stat().st_mode & 0o077,0)
                self.assertNotIn(key,(config/"key.json").read_text())
            with patch.object(remote.time,"time",return_value=1000+86401):
                self.assertFalse(remote.authorize_control_key(key))
                self.assertFalse(remote.key_issued())

    def test_only_fixed_user_systemd_command_is_dispatched(self):
        status_payload=json.dumps({
            "configured":True,"tunnel_running":False,
            "external_url_if_configured":"https://okal.example.com/"
        })
        result_status=subprocess.CompletedProcess([],0,stdout=status_payload)
        result_action=subprocess.CompletedProcess([],0,stdout="")
        with patch.object(remote,"authorize_control_key",return_value=True):
            with patch.object(remote,"key_issued",return_value=True):
                with patch.object(remote.subprocess,"run",
                                  side_effect=[result_status,result_action]) as run:
                    result=remote.switch("on","TESTCONTROLKEY",True)
                self.assertEqual(result["state"],"accepted_not_confirmed")
                command=run.call_args_list[-1].args[0]
                self.assertEqual(command[:3],["systemd-run","--user","--collect"])
                self.assertEqual(command[-2:],["on","--confirm-access-policy"])
                self.assertTrue(str(remote.REMOTE_CLI) in command)
        with self.assertRaisesRegex(ValueError,"invalid_remote_action"):
            remote.switch("inject","TESTCONTROLKEY",False)

    def test_http_controls_reject_wrong_origin_and_missing_control_key(self):
        with TestClient(create_app(self.store), base_url="https://okal",
                client=("127.0.0.1",1234)) as client:
            with patch("okal_core.remote_control.status",return_value={
                "configured":False,"tunnel_running":False,
                "external_url_if_configured":None,
                "public_reachability_verified":False,
                "remote_auto_start":False,"owner_control_key_issued":False
            }):
                response=client.get("/api/v1/remote/status")
                self.assertEqual(response.status_code,200)
            payload={"action":"on","control_key":"bad","confirm_access_policy":True}
            self.assertEqual(client.post("/api/v1/remote/switch",json=payload,
                headers={"Origin":"https://attacker.example",
                         "Sec-Fetch-Site":"cross-site"}).status_code,403)
            with patch("okal_core.remote_control.switch",
                       side_effect=PermissionError("remote_owner_control_key_required")):
                response=client.post("/api/v1/remote/switch",json=payload,headers={
                    "Origin":"https://okal","Sec-Fetch-Site":"same-origin"
                })
            self.assertEqual(response.status_code,403)
            self.assertEqual(response.json()["detail"],
                             "remote_owner_control_key_required")

    def test_control_requires_https_okal_even_on_loopback(self):
        with TestClient(create_app(self.store),
                base_url="http://127.0.0.1:8766",
                client=("127.0.0.1",2222)) as client:
            response=client.post("/api/v1/remote/switch",json={
                "action":"off","control_key":"redacted",
                "confirm_access_policy":False
            },headers={"Origin":"http://127.0.0.1:8766",
                       "Sec-Fetch-Site":"same-origin"})
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()["detail"],
                             "remote_owner_local_https_only")


if __name__=="__main__":
    unittest.main()
