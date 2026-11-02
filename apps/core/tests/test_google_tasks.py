"""Google Tasks must remain separately authorized, date-only and read-only."""
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from okal_core.store import Store
from okal_core.google_tasks import (
    GoogleTasksError, cached, status, sync, _scheduled_date,
    private_credentials,
)
from okal_core.api import create_app


class FakeRequest:
    def __init__(self, owner, name):
        self.owner, self.name = owner, name

    def list(self, **kw):
        self.owner.calls.append((self.name,kw))
        return self

    def execute(self, num_retries=0):
        self.owner.retry_values.append(num_retries)
        value=self.owner.pages.pop(0)
        if isinstance(value,Exception):
            raise value
        return value


class FakeService:
    def __init__(self,*pages):
        self.pages=list(pages)
        self.calls=[]
        self.retry_values=[]
    def tasklists(self):
        return FakeRequest(self,"tasklists")
    def tasks(self):
        return FakeRequest(self,"tasks")


def item(task_id,due=None,status="needsAction",title="Private task"):
    row={"id":task_id,"title":title,"status":status,
         "updated":"2026-11-02T08:00:00.000Z"}
    if due is not None: row["due"]=due
    return row


class GoogleTasksTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        now=int(datetime(2026,11,2,8,tzinfo=ZoneInfo("Africa/Cairo")).timestamp())
        self.store=Store(Path(d.name)/"state",clock=lambda:now)

    def test_date_only_due_is_not_time_or_deadline(self):
        self.assertEqual(_scheduled_date("2026-11-03T00:00:00.000Z"),"2026-11-03")
        for invalid in ("tomorrow",False,"2026-99-99T00:00:00Z","2026-11-03"):
            with self.subTest(value=invalid),self.assertRaises(GoogleTasksError):
                _scheduled_date(invalid)

    def test_atomic_snapshot_and_idempotent_replay_without_provider_writes(self):
        service=FakeService(
            {"items":[{"id":"list-a"}],"nextPageToken":"NEXT-LISTS"},
            {"items":[{"id":"list-b"}]},
            {"items":[item("a",due="2026-11-03T00:00:00.000Z",
                            title="Meeting task")],
             "nextPageToken":"NEXT"},
            {"items":[item("b",status="completed")]},
            {"items":[item("c")]},
        )
        result=sync(self.store,service=service)
        self.assertEqual(result["list_count"],2)
        self.assertEqual(result["task_count"],3)
        self.assertFalse(result["provider_writes"])
        self.assertEqual([v for v in service.retry_values],[0]*5)
        self.assertTrue(all(method in {"tasklists","tasks"} for method,_ in service.calls))
        rows=cached(self.store)["items"]
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["scheduled_day"],"2026-11-03")
        self.assertFalse(rows[0]["has_exact_due_time"])
        self.assertFalse(rows[0]["is_deadline"])
        self.assertNotIn("notes",rows[0])
        result=sync(self.store,service=FakeService(
            {"items":[{"id":"list-a"}]},
            {"items":[item("a",due="2026-11-04T00:00:00Z")]}
        ))
        self.assertEqual(result["task_count"],1)
        self.assertEqual(len(cached(self.store)["items"]),1)
        self.assertEqual(cached(self.store)["items"][0]["scheduled_day"],"2026-11-04")
        self.assertEqual(status(self.store)["task_count"],1)

    def test_partial_provider_page_does_not_delete_prior_snapshot(self):
        sync(self.store,service=FakeService(
            {"items":[{"id":"list-a"}]},
            {"items":[item("old-id",due="2026-11-03T00:00:00Z")]}
        ))
        bad=FakeService({"items":[{"id":"list-a"}]},
             {"items":[item("new-id")],"nextPageToken":"PAGE2"},
             RuntimeError("provider secret access token"))
        with self.assertRaisesRegex(GoogleTasksError,"google_tasks_read_failed"):
            sync(self.store,service=bad)
        self.assertEqual(cached(self.store)["items"][0]["task_id"],"old-id")
        self.assertEqual(status(self.store)["task_count"],1)

    def test_provider_403_reports_safe_access_or_api_disabled_code(self):
        class HttpFailure(Exception):
            resp = type("Response", (), {"status": 403})()
        failure = FakeService({"items":[{"id":"list-a"}]}, HttpFailure(
            "DO NOT EXPOSE provider token and identity"
        ))
        with self.assertRaisesRegex(GoogleTasksError,
            "google_tasks_access_denied_or_api_disabled"):
            sync(self.store,service=failure)
        self.assertFalse(cached(self.store)["connected"])

    def test_invalid_duplicate_or_overbudget_rejects_snapshot(self):
        samples=[
            FakeService({"items":[{"id":"duplicate"},{"id":"duplicate"}]}),
            FakeService({"items":[{"id":"list-a"}]},
                        {"items":[item("same"),item("same")]}),
            FakeService({"items":[{"id":"list-a"}]},
                        {"items":[item("bad",due="invalid-due")]}),
            FakeService({"items":[{"id":"list-a"}]},
                        {"items":[{"title":"missing ID"}]}),
        ]
        for service in samples:
            with self.subTest(which=service.pages),self.assertRaises(GoogleTasksError):
                sync(self.store,service=service)
            self.assertEqual(cached(self.store)["items"],[])


    def test_recorded_sync_preserves_cache_and_exposes_safe_failure(self):
        from okal_core.google_tasks import sync_recorded
        sync(self.store,service=FakeService(
            {"items":[{"id":"list-a"}]},
            {"items":[item("saved")]}
        ))
        with patch("okal_core.google_tasks._service",
                   return_value=FakeService(
                       {"items":[{"id":"list-a"}]},
                       RuntimeError("SECRET provider failure"))):
            with self.assertRaisesRegex(GoogleTasksError,"google_tasks_read_failed"):
                sync_recorded(self.store)
        result=status(self.store)
        self.assertEqual(result["last_result"],"failed")
        self.assertEqual(result["last_error"],"google_tasks_read_failed")
        self.assertEqual(result["task_count"],1)
        self.assertNotIn("SECRET",str(result))
        self.assertEqual(cached(self.store)["items"][0]["task_id"],"saved")
        with patch("okal_core.google_tasks._service",
                   return_value=FakeService(
                       {"items":[{"id":"list-a"}]},
                       {"items":[item("fresh")]})):
            sync_recorded(self.store)
        self.assertEqual(status(self.store)["last_result"],"complete")
        self.assertIsNone(status(self.store)["last_error"])
        self.assertEqual(cached(self.store)["items"][0]["task_id"],"fresh")

    def test_sync_button_is_same_origin_local_only_and_requires_credentials(self):
        headers={"Origin":"http://127.0.0.1:8766",
                 "Sec-Fetch-Site":"same-origin"}
        with TestClient(create_app(self.store),
                base_url="http://127.0.0.1:8766",
                client=("127.0.0.1",12000)) as client:
            response=client.post("/api/v1/google-tasks/sync",json={},headers=headers)
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()["detail"],
                             "google_tasks_reauthorization_required")
            self.assertEqual(client.post("/api/v1/google-tasks/sync",
                                         json={},headers={
                   "Origin":"https://example.org",
                   "Sec-Fetch-Site":"cross-site",
                 }).status_code,403)

    def test_api_never_fetches_live_tasks_or_exposes_tokens(self):
        with patch("okal_core.google_tasks._service",side_effect=AssertionError(
            "NO PROVIDER CALL ON GET"
        )):
            with TestClient(create_app(self.store),
                    base_url="http://127.0.0.1:8766",
                    client=("127.0.0.1",12000)) as client:
                reply=client.get("/api/v1/google-tasks/status")
                self.assertEqual(reply.status_code,200)
                self.assertEqual(reply.json()["sync"]["authorization"],"not_connected")
                self.assertTrue(reply.json()["sync"]["read_only_scope"])
                got=client.get("/api/v1/google-tasks/cached")
                self.assertEqual(got.status_code,200)
                self.assertEqual(got.json()["items"],[])
                self.assertEqual(client.post(
                    "/api/v1/google-tasks/cached",json={}).status_code,401)
                self.assertEqual(client.get("/google-tasks-ui.js").status_code,200)
                self.assertEqual(client.get(
                    "/api/v1/google-tasks/oauth/callback?state=bad").status_code,400)

    def test_protected_mode_blocks_unauthorized_cache_reads_and_connect(self):
        with TestClient(create_app(self.store,require_read_key=True),
                base_url="http://127.0.0.1:8766",
                client=("127.0.0.1",1234)) as client:
            self.assertEqual(client.get("/api/v1/google-tasks/cached").status_code,401)
            self.assertEqual(client.get("/api/v1/google-tasks/status").status_code,401)
            self.assertEqual(client.post("/api/v1/google-tasks/oauth/start",
                                        json={},headers={
                                        "Origin":"http://127.0.0.1:8766"
                                        }).status_code,401)

    def test_oauth_is_separate_and_scoped_to_tasks_readonly(self):
        from okal_core.google_tasks_oauth import TasksOAuthWeb, SCOPES
        from okal_core.mail.private import write_private
        from okal_core.calendar_google import credential_file
        class Flow:
            redirect_uri=None
            credentials=type("Cred",(),{
                "granted_scopes":SCOPES,
                "scopes":SCOPES,
                "to_json":lambda self:__import__("json").dumps({
                    "scopes":SCOPES,"refresh_token":"PRIVATE_REFRESH_TOKEN"})
            })()
            def authorization_url(self,**kwargs):
                return ("https://accounts.google.com/o/oauth2/auth?test=1",
                        "S"*24)
            def fetch_token(self,**kwargs):
                return None
        flows=[]
        def builder(config,scopes,**kwargs):
            self.assertEqual(scopes,SCOPES)
            self.assertEqual(kwargs["autogenerate_code_verifier"],True)
            flows.append(Flow())
            return flows[-1]
        with patch("okal_core.google_tasks_oauth.gmail_desktop_client",
                   return_value={"installed":{"client_id":"example"}}):
            oauth=TasksOAuthWeb(self.store.clock,flow_builder=builder)
            entry=oauth.start(self.store,"127.0.0.1:8766")
            self.assertTrue(entry["authorization_url"].startswith(
                "https://accounts.google.com/"))
            self.assertIn("/api/v1/google-tasks/oauth/callback",flows[-1].redirect_uri)
            self.assertEqual(oauth.finish(self.store,"S"*24,"CODEVALID123")[
                "authorization"],"configured_not_verified")
            with self.assertRaisesRegex(ValueError,"expired_tasks_oauth_state"):
                oauth.finish(self.store,"S"*24,"CODEVALID123")
        self.assertTrue(private_credentials(self.store).exists())
        self.assertFalse(credential_file(self.store,"default").exists())
        self.assertFalse((self.store.directory/"mail"/"token.json").exists())


if __name__ == "__main__":
    unittest.main()
