#!/usr/bin/env python3
"""Owner-controlled Cloudflare Tunnel: configure, token, on, off, status.

OFF by default. Never creates Cloudflare DNS, policies, billed resources or
running tunnels during configuration. Requires signed Access JWT + local
browser read-key when explicitly enabled.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib import error, request

ROOT=Path(__file__).resolve().parents[1]
DIR=Path.home()/".config"/"okal"
ENV=DIR/"remote.env"
TOKEN=DIR/"remote.token"
USERUNIT=Path.home()/".config/systemd/user/okal-remote.service"
DROPIN=Path.home()/".config/systemd/user/okal-core.service.d/remote.conf"
UNIT=ROOT/"deploy/okal-remote.service"
OVERRIDE=("[Service]\nEnvironment=OKAL_REQUIRE_READ_KEY=1\n"
          "EnvironmentFile=%h/.config/okal/remote.env\n")


def run(*args):
    r=subprocess.run(args,check=False,capture_output=True,text=True,timeout=15)
    if r.returncode:
        raise RuntimeError("local_systemd_action_failed")


def active(name):
    try:
        r=subprocess.run(["systemctl","--user","is-active","--quiet",name],
                         check=False,stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,timeout=4)
        return r.returncode==0
    except (OSError,subprocess.TimeoutExpired):
        return False


def private_write(path, data):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    # No symlink following, no accidental over-write of unrelated data.
    if path.is_symlink():
        raise ValueError("unsafe_remote_config_symlink")
    tmp=path.with_name(path.name+".new")
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    fd=os.open(tmp,flags,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            stream.write(data)
        os.replace(tmp,path)
        os.chmod(path,0o600)
    finally:
        if tmp.exists(): tmp.unlink()


def parse_env():
    if not ENV.is_file() or ENV.is_symlink():
        raise ValueError("remote_config_missing")
    values={}
    for line in ENV.read_text().splitlines():
        if "=" not in line: raise ValueError("invalid_remote_env")
        key,val=line.split("=",1)
        if key not in ("OKAL_REMOTE_HOST","OKAL_CF_ACCESS_TEAM",
                       "OKAL_CF_ACCESS_AUD","OKAL_CF_ACCESS_EMAIL") or key in values:
            raise ValueError("invalid_remote_env")
        values[key]=val
    if len(values)!=4:
        raise ValueError("incomplete_remote_env")
    sys.path.insert(0,str(ROOT/"apps/core/src"))
    from okal_core.cloudflare_access import AccessGate
    result=AccessGate.from_environment(values)
    if result is None:
        raise ValueError("remote_not_configured")
    return result


def not_authenticated():
    # Local backend must reject a remote Host without Access JWT; and
    # reject private local reads without a paired owner read-key.
    import http.client
    gate=parse_env()
    for host,path,want in (
        (gate.hostname,"/api/v1/health",403),
        ("okal","/api/v1/mail/triage",401),
    ):
        connection=http.client.HTTPConnection("127.0.0.1",8766,timeout=4)
        try:
            connection.request("GET",path,headers={"Host":host})
            response=connection.getresponse()
            response.read(4096)
            if response.status!=want:
                raise RuntimeError("unsafe_core_authentication_policy")
        finally:
            connection.close()


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="action",required=True)
    c=sub.add_parser("configure")
    c.add_argument("--hostname",required=True)
    c.add_argument("--team",required=True)
    c.add_argument("--aud",required=True)
    c.add_argument("--email",required=True)
    sub.add_parser("token")
    c=sub.add_parser("on")
    c.add_argument("--confirm-access-policy",action="store_true",required=True)
    sub.add_parser("off")
    sub.add_parser("status")
    sub.add_parser("ui-key")
    a=p.parse_args()
    if a.action=="ui-key":
        sys.path.insert(0,str(ROOT/"apps/core/src"))
        from okal_core.remote_control import issue_control_key
        if not sys.stdout.isatty():
            raise ValueError("remote_control_key_requires_private_terminal")
        key=issue_control_key()
        print("One-day Remote Settings control key (shown only now):")
        print(key)
        print("Enter this key in OKAL local Settings. Never paste it in chat.")
        return
    if a.action=="status":
        try: cfg=parse_env()
        except ValueError: cfg=None
        started=active("okal-remote.service")
        print(json.dumps({
            "configured":cfg is not None,
            "tunnel_running":started,
            "external_url_if_configured":"https://"+cfg.hostname+"/" if cfg else None,
            "public_reachability_verified":False,
            "remote_auto_start":False,
            "access_jwt_required":True,
            "read_key_required_when_running":True,
        },indent=2))
        return
    if a.action=="configure":
        if active("okal-remote.service"):
            raise ValueError("remote_must_be_stopped_before_reconfiguration")
        sys.path.insert(0,str(ROOT/"apps/core/src"))
        from okal_core.cloudflare_access import AccessGate
        cfg=AccessGate(a.hostname,a.team,a.aud,a.email)
        values={
            "OKAL_REMOTE_HOST":cfg.hostname,
            "OKAL_CF_ACCESS_TEAM":a.team,
            "OKAL_CF_ACCESS_AUD":cfg.audience,
            "OKAL_CF_ACCESS_EMAIL":cfg.email,
        }
        private_write(ENV,"".join(k+"="+v+"\n" for k,v in values.items()))
        if USERUNIT.exists() and USERUNIT.read_text()!=UNIT.read_text():
            raise ValueError("existing_remote_service_modified")
        USERUNIT.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if not USERUNIT.exists():
            private_write(USERUNIT,UNIT.read_text())
        run("systemctl","--user","daemon-reload")
        print("Remote prepared; tunnel still OFF. Install a verified Access policy and token.")
        return
    if a.action=="token":
        if active("okal-remote.service"):
            raise ValueError("stop_remote_before_token_rotation")
        parse_env()
        if not sys.stdin.isatty():
            raise ValueError("token_requires_private_interactive_tty")
        token=getpass.getpass("Cloudflare Tunnel token (hidden): ").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.=-]{50,8192}",token):
            raise ValueError("invalid_tunnel_token")
        private_write(TOKEN,token+"\n")
        print("Tunnel token stored privately; remote still OFF.")
        return
    if a.action=="on":
        if not a.confirm_access_policy:
            raise ValueError("cloudflare_access_policy_confirmation_required")
        cfg=parse_env()
        if not (TOKEN.is_file() and not TOKEN.is_symlink() and
                TOKEN.stat().st_mode & 0o077 == 0):
            raise ValueError("private_cloudflare_token_missing")
        if not shutil.which("cloudflared"):
            raise ValueError("cloudflared_not_installed")
        if not USERUNIT.is_file() or USERUNIT.read_text()!=UNIT.read_text():
            raise ValueError("remote_service_not_installed")
        if DROPIN.exists() and DROPIN.read_text()!=OVERRIDE:
            raise ValueError("existing_core_override_modified")
        if active("okal-remote.service"):
            print("Remote already started; no action.")
            return
        private_write(DROPIN,OVERRIDE)
        try:
            run("systemctl","--user","daemon-reload")
            run("systemctl","--user","restart","okal-core.service")
            not_authenticated()
            run("systemctl","--user","start","okal-remote.service")
        except Exception:
            subprocess.run(["systemctl","--user","stop","okal-remote.service"],
                           check=False,stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            if DROPIN.is_file() and DROPIN.read_text()==OVERRIDE:
                DROPIN.unlink()
            subprocess.run(["systemctl","--user","daemon-reload"],check=False)
            subprocess.run(["systemctl","--user","restart","okal-core.service"],
                           check=False)
            raise
        print(json.dumps({
            "tunnel_running":active("okal-remote.service"),
            "configured_external_url":"https://"+cfg.hostname+"/",
            "remote_reachability_verified":False,
            "auth":"Cloudflare Access owner JWT AND OKAL read-key pairing",
        },indent=2))
        return
    if a.action=="off":
        run("systemctl","--user","stop","okal-remote.service")
        if DROPIN.is_file():
            if DROPIN.read_text()!=OVERRIDE:
                raise ValueError("remote_core_override_manually_modified")
            DROPIN.unlink()
            run("systemctl","--user","daemon-reload")
            run("systemctl","--user","restart","okal-core.service")
        print("Remote OFF. Local HTTPS remains available. Tunnel token not erased.")


if __name__=="__main__":
    try:
        if len(sys.argv)>1 and sys.argv[1] in ("on","off"):
            # Serialize operator CLI and UI actions in the same private lock.
            import fcntl
            DIR.mkdir(mode=0o700,parents=True,exist_ok=True)
            fd=os.open(DIR/"remote-action.lock",
                       os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,"rb") as stream:
                fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                main()
        else:
            main()
    except BlockingIOError:
        print("OKAL remote: another remote transition is running",file=sys.stderr)
        raise SystemExit(1)
    except (ValueError,OSError,RuntimeError,subprocess.TimeoutExpired) as exc:
        print("OKAL remote: safe stop — "+str(exc),file=sys.stderr)
        raise SystemExit(1)
