"""Bounded subprocesses, process-group cancellation, no shell interpolation."""

import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


def run(argv, check, timeout=20, input_data=None, desktop=False):
    environment = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
    }
    if desktop:
        for name in (
            "HOME",
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "XDG_RUNTIME_DIR",
            "DBUS_SESSION_BUS_ADDRESS",
            "HYPRLAND_INSTANCE_SIGNATURE",
            "XDG_DATA_DIRS",
        ):
            if name in os.environ:
                environment[name] = os.environ[name]
    with (
        tempfile.TemporaryFile() as output,
        tempfile.TemporaryFile() as error,
        tempfile.TemporaryFile() as source,
    ):
        if input_data is not None:
            source.write(input_data)
            source.seek(0)
        process = subprocess.Popen(
            argv,
            stdin=source,
            stdout=output,
            stderr=error,
            env=environment,
            start_new_session=True,
        )
        started = time.monotonic()
        try:
            while process.poll() is None:
                check()
                if time.monotonic() - started > timeout:
                    raise TimeoutError("process_timeout")
                if (
                    os.fstat(output.fileno()).st_size + os.fstat(error.fileno()).st_size
                    > 262144
                ):
                    raise ValueError("process_output_limit")
                time.sleep(0.03)
            check()
            output.seek(0)
            error.seek(0)
            result = output.read(131073)
            if len(result) > 131072:
                raise ValueError("process_output_limit")
            if process.returncode != 0:
                # Native stderr can contain secrets or personal paths. The
                # receipt reports a bounded error code instead of echoing it.
                raise ValueError("native_process_failed_" + str(process.returncode))
            return result
        finally:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
