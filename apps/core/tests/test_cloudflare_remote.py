"""Signed Cloudflare Access JWTs are required IN ADDITION to OKAL read key."""
import base64
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric import rsa,padding
from cryptography.hazmat.primitives import hashes
from fastapi.testclient import TestClient

from okal_core.cloudflare_access import AccessGate
from okal_core.api import create_app
from okal_core.store import Store

REMOTE="assistant.example.com"
TEAM="okal-private"
AUD="a"*64
EMAIL="owner@example.com"
ENV={"OKAL_REMOTE_HOST":REMOTE,"OKAL_CF_ACCESS_TEAM":TEAM,
     "OKAL_CF_ACCESS_AUD":AUD,"OKAL_CF_ACCESS_EMAIL":EMAIL}


def b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class AccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=cls.key.public_key().public_numbers()
        cls.jwk={"kid":"owner-test-key","kty":"RSA","alg":"RS256",
                 "n":b64(public.n.to_bytes((public.n.bit_length()+7)//8,"big")),
                 "e":b64(public.e.to_bytes(3,"big"))}
        cls.now=1793660000

    def jwt(self, **overrides):
        claims={"type":"app","iss":"https://"+TEAM+".cloudflareaccess.com",
                "aud":[AUD],"email":EMAIL,"sub":"verified-human-owner",
                "iat":self.now-60,"nbf":self.now-60,"exp":self.now+1800}
        claims.update(overrides)
        h=b64(json.dumps({"alg":"RS256","kid":"owner-test-key"}).encode())
        b=b64(json.dumps(claims).encode())
        data=(h+"."+b).encode()
        sig=self.key.sign(data,padding.PKCS1v15(),hashes.SHA256())
        return h+"."+b+"."+b64(sig)

    def gate(self):
        return AccessGate(REMOTE,TEAM,AUD,EMAIL,keys=[self.jwk],now=lambda:self.now)

    def test_remote_off_by_default_and_reject_incomplete_config(self):
        self.assertIsNone(AccessGate.from_environment({}))
        with self.assertRaises(ValueError):
            AccessGate.from_environment({"OKAL_REMOTE_HOST":REMOTE})
        for name in ("127.0.0.1","okal","example.local","malicious name"):
            with self.assertRaises(ValueError):
                AccessGate(name,TEAM,AUD,EMAIL)
        with self.assertRaises(ValueError):
            AccessGate(REMOTE,TEAM,AUD,"owner@example.com\nPASSWORD=1")

    def test_signed_owner_jwt_and_exact_audience_issuer_email(self):
        gate=self.gate()
        self.assertTrue(gate.authorize(self.jwt()))
        for token in (
            None,"attacker",self.jwt(exp=self.now-1),
            self.jwt(aud=["other"]),
            self.jwt(iss="https://other.cloudflareaccess.com"),
            self.jwt(email="attacker@example.com"),
            self.jwt(type="org"),
            self.jwt(sub=""),
            self.jwt(nbf=self.now+200),
            self.jwt(iat=self.now+200),
        ):
            with self.subTest(token=str(token)[:35]):
                self.assertFalse(gate.authorize(token))
        token=self.jwt()
        a,b,c=token.split(".")
        self.assertFalse(gate.authorize(a+"."+b+"."+c[:-5]+"abcde"))
        self.assertFalse(gate.authorize(self.jwt().replace("RS256","none")))

    def test_api_remote_host_requires_signed_access_plus_owner_read_key(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/"state",clock=lambda:self.now)
            with patch.dict("os.environ",ENV):
                with patch("okal_core.cloudflare_access.AccessGate._fetch_keys",
                           return_value=[self.jwk]):
                    with TestClient(create_app(store),
                         base_url="https://"+REMOTE,
                         client=("127.0.0.1",1234)) as client:
                        self.assertEqual(client.get("/api/v1/health").status_code,403)
                        headers={"Cf-Access-Jwt-Assertion":self.jwt()}
                        self.assertEqual(client.get("/api/v1/health",
                                          headers=headers).status_code,200)
                        self.assertEqual(client.get("/api/v1/mail/triage",
                                          headers=headers).status_code,401)
                        self.assertEqual(client.post("/api/v1/mail/oauth/start",
                                          json={},headers={
                                              **headers,"Origin":"https://"+REMOTE,
                                              "Sec-Fetch-Site":"same-origin",
                                          }).status_code,409)
                        self.assertEqual(client.get("/api/v1/health",headers={
                            **headers,"Origin":"https://attacker.example",
                        }).status_code,403)
                    # Defense against accidental tunnel httpHostHeader=okal:
                    # access cannot bypass the configured read-key mode.
                    with TestClient(create_app(store),
                        base_url="https://okal",
                        client=("127.0.0.1",1234)) as local:
                        self.assertEqual(local.get("/api/v1/mail/triage").status_code,401)

    def test_service_has_no_autostart_and_no_token_in_process_arguments(self):
        root=Path(__file__).resolve().parents[3]
        service=(root/"deploy/okal-remote.service").read_text()
        control=(root/"scripts/okal-remote.py").read_text()
        self.assertIn("--token-file %h/.config/okal/remote.token",service)
        self.assertNotIn("[Install]",service)
        self.assertIn("OKAL_REQUIRE_READ_KEY=1",control)
        self.assertIn("not_authenticated()",control)
        self.assertIn("remote.token",control)
        self.assertNotIn("curl -k",control)


if __name__=="__main__":
    unittest.main()
