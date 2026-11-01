"""Real process restart/resource smoke check using disposable local fixtures."""

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {
        "environment": "isolated Linux test host, not owner Omarchy laptop",
        "data": "fixtures only",
        "model_loaded": False,
        "owner_boot_verified": False,
    }
    with tempfile.TemporaryDirectory() as temp:
        command = [sys.executable, "-m", "okal_core", "--state-dir", temp]
        # TemporaryDirectory is already 0700; Store may use it directly.
        subprocess.run(command + ["demo"], check=True, capture_output=True)
        issued = json.loads(
            subprocess.check_output(command + ["device-add", "runtime-test"])
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        ids = []
        for iteration in range(2):
            started = time.monotonic()
            proc = subprocess.Popen(
                command + ["serve", "--port", str(port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            try:
                for _ in range(100):
                    if proc.poll() is not None:
                        raise RuntimeError(
                            "core process exited before health check: "
                            + proc.stderr.read().decode()
                        )
                    try:
                        with opener.open(
                            origin + "/api/v1/health", timeout=1
                        ) as response:
                            assert json.load(response)["status"] == "ok"
                        break
                    except OSError:
                        time.sleep(0.05)
                else:
                    raise RuntimeError("health check timed out")
                startup = round(time.monotonic() - started, 3)
                req = urllib.request.Request(
                    origin + "/api/v1/summaries",
                    headers={"Authorization": "Bearer " + issued["token"]},
                )
                with opener.open(req, timeout=2) as response:
                    ids.append([x["id"] for x in json.load(response)["items"]])
                if iteration == 0:
                    time.sleep(1)
                    report["startup_seconds"] = startup
            finally:
                proc.terminate()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    pid, status, usage = os.wait4(proc.pid, os.WNOHANG)
                    if pid:
                        proc.returncode = os.waitstatus_to_exitcode(status)
                        break
                    time.sleep(0.05)
                else:
                    proc.kill()
                    proc.wait()
                    raise RuntimeError("core did not shut down gracefully")
                logs = proc.stderr.read().decode()
                proc.stderr.close()
            # Uvicorn re-raises SIGTERM after graceful shutdown; systemd also
            # treats this signal as clean. Require the shutdown receipt, not just exit.
            if (
                proc.returncode not in (0, -signal.SIGTERM)
                or "Application shutdown complete" not in logs
            ):
                raise RuntimeError("core did not report graceful shutdown: " + logs)
            if iteration == 0:
                report["process_peak_rss_mib"] = round(usage.ru_maxrss / 1024, 2)
                report["process_cpu_seconds_during_smoke"] = round(
                    usage.ru_utime + usage.ru_stime, 3
                )
                report["idle_resources_separately_measured"] = False
        assert ids[0] == ids[1] and len(ids[0]) == 2
        report["restart_retains_summaries_and_token"] = True
        report["graceful_shutdown"] = True
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    print(output)


if __name__ == "__main__":
    main()
