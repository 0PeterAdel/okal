"""Optional Cloudflare Access gate for named, owner-controlled remote hosts.

Remote is DISABLED if no explicit config is supplied. Every request using
the remote hostname MUST carry a signed, unexpired, owner-scoped Access JWT.
A Tunnel alone is never an authorization boundary.
"""
import base64
import json
import os
import re
import ssl
import threading
import time
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

_HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_TEAM = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_AUD = re.compile(r"^[A-Za-z0-9]{16,128}$")
_KID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_B64 = re.compile(r"^[A-Za-z0-9_-]+$")


def _decode(encoded, max_chars):
    if (not isinstance(encoded,str) or not 1<=len(encoded)<=max_chars or
            not _B64.fullmatch(encoded)):
        raise ValueError("invalid_base64url")
    return base64.urlsafe_b64decode(encoded + "="*((-len(encoded))%4))


def _json(data):
    return json.loads(data.decode("utf-8"))


class AccessGate:
    """Validates account signing key, exact app AUD and *owner* email."""

    def __init__(self, hostname, team, audience, email, *, keys=None, now=None):
        if (not isinstance(hostname,str) or not _HOST.fullmatch(hostname)
                or hostname.endswith((".localhost",".local",".internal"))
                or not isinstance(team,str) or not _TEAM.fullmatch(team)
                or not isinstance(audience,str) or not _AUD.fullmatch(audience)
                or not isinstance(email,str) or
                not re.fullmatch(r"[^@\s]{1,100}@[^@\s]{1,150}",email)):
            raise ValueError("invalid_cloudflare_access_configuration")
        self.hostname=hostname
        self.issuer=f"https://{team}.cloudflareaccess.com"
        self.audience=audience
        self.email=email.casefold()
        self._keys=keys
        self._fetched_at=0.0
        self._lock=threading.Lock()
        self._now=now or time.time

    @classmethod
    def from_environment(cls, env=None, **kwargs):
        env = os.environ if env is None else env
        fields=[env.get(name,"") for name in (
            "OKAL_REMOTE_HOST","OKAL_CF_ACCESS_TEAM",
            "OKAL_CF_ACCESS_AUD","OKAL_CF_ACCESS_EMAIL")]
        if not any(fields):
            return None
        if not all(fields):
            raise ValueError("incomplete_cloudflare_access_configuration")
        return cls(*fields,**kwargs)

    def _fetch_keys(self):
        # TLS-verified fixed Cloudflare Access team cert endpoint; no redirects
        # to arbitrary host or environment-defined proxies.
        url=self.issuer+"/cdn-cgi/access/certs"
        opener=build_opener(ProxyHandler({}),HTTPSHandler(
            context=ssl.create_default_context()))
        response=opener.open(Request(url,headers={
            "Accept":"application/json","User-Agent":"OKAL-Local-Access-Gate"
        }),timeout=4)
        with response:
            if response.url!=url or response.status!=200:
                raise ValueError("invalid_cloudflare_certs_endpoint")
            raw=response.read(65537)
        if len(raw)>65536:
            raise ValueError("cloudflare_key_response_too_large")
        decoded=_json(raw)
        keys=decoded.get("keys")
        if not isinstance(keys,list) or not 1<=len(keys)<=20:
            raise ValueError("invalid_cloudflare_signing_keys")
        return keys

    def _signing_key(self, kid):
        if self._keys is not None:
            records=self._keys
        else:
            # Cache only valid JWKS for 15 minutes, fail closed if unavailable.
            with self._lock:
                if self._keys is None or (self._now()-self._fetched_at)>900:
                    self._keys=self._fetch_keys()
                    self._fetched_at=self._now()
                records=self._keys
        matches=[item for item in records if isinstance(item,dict)
                 and item.get("kid")==kid and item.get("kty")=="RSA"
                 and item.get("alg","RS256")=="RS256"]
        if len(matches)!=1:
            # One key rotation retry is safe and bounded.
            if self._fetched_at and records is self._keys:
                with self._lock:
                    self._keys=self._fetch_keys()
                    self._fetched_at=self._now()
                return self._signing_key(kid)
            raise ValueError("unknown_cloudflare_signing_key")
        return matches[0]

    def authorize(self, token):
        try:
            if (not isinstance(token,str) or not 50<=len(token)<=8192
                    or token.count(".")!=2):
                return False
            head,body,signature=token.split(".")
            header=_json(_decode(head,2048))
            payload=_json(_decode(body,6144))
            if (not isinstance(header,dict) or header.get("alg")!="RS256"
                    or not _KID.fullmatch(header.get("kid",""))
                    or not isinstance(payload,dict)):
                return False
            key=self._signing_key(header["kid"])
            n=int.from_bytes(_decode(key["n"],1024),"big")
            e=int.from_bytes(_decode(key["e"],32),"big")
            if n.bit_length()<2048 or e not in (65537,3):
                return False
            from cryptography.hazmat.primitives.asymmetric import padding,rsa
            from cryptography.hazmat.primitives import hashes
            pub=rsa.RSAPublicNumbers(e,n).public_key()
            pub.verify(_decode(signature,1024),
                       (head+"."+body).encode("ascii"),
                       padding.PKCS1v15(),hashes.SHA256())
            now=self._now()
            exp=payload.get("exp")
            issued=payload.get("iat")
            nbf=payload.get("nbf",issued)
            aud=payload.get("aud")
            return (
                payload.get("type")=="app"
                and payload.get("iss")==self.issuer
                and isinstance(aud,list) and self.audience in aud
                and type(exp) in (int,float) and now<exp<=now+86400*8
                and type(issued) in (int,float) and 0<=issued<=now+60
                and type(nbf) in (int,float) and 0<=nbf<=now+60
                and isinstance(payload.get("sub"),str)
                and len(payload["sub"])>0
                and isinstance(payload.get("email"),str)
                and payload["email"].casefold()==self.email
            )
        except Exception:
            # Signature, key fetch, malformed JWT or transient Cloudflare outage:
            # never authenticate by fallback, cookie or a forwarded header.
            return False
