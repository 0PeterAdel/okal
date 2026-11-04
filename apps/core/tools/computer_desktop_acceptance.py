"""Opt-in native launch/focus acceptance using a disposable desktop entry, no config edits."""

from pathlib import Path
import json, os, subprocess, tempfile, time, uuid
from okal_core.store import Store
from okal_core.intelligence import Intelligence
from okal_core.computer.engine import Engine
from okal_core.computer.contracts import Plan

with tempfile.TemporaryDirectory(prefix="okal-desktop-test-") as temp:
    root = Path(temp) / "workspace"
    root.mkdir()
    data = Path(temp) / "desktop-data"
    (data / "applications").mkdir(parents=True)
    marker = root / "launch-observed.txt"
    # A disposable desktop entry proves actual gio/desktop dispatch without
    # registering anything in the owner's application directories.
    (data / "applications" / "okal-acceptance.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=OKAL acceptance\nExec=/usr/bin/touch "
        + str(marker)
        + "\n"
    )
    os.environ["XDG_DATA_DIRS"] = str(data) + ":/usr/share"
    store = Store(Path(temp) / "state")
    con = Intelligence(store).create()["id"]
    e = Engine(store)
    e.configure(
        {
            "mode": "assisted",
            "tools": ["desktop.launch", "desktop.focus", "desktop.windows"],
            "roots": [{"root": str(root), "write": True}],
            "applications": ["okal-acceptance.desktop"],
        },
        1,
    )
    active = json.loads(
        subprocess.check_output(["/usr/bin/hyprctl", "-j", "activewindow"])
    )["address"]
    plan = Plan(
        understanding="Verify owner desktop launch and focus",
        steps=[
            {
                "tool": "desktop.launch",
                "arguments": {"name": "okal-acceptance.desktop"},
            },
            {"tool": "desktop.focus", "arguments": {"address": active}},
        ],
    )
    run = e.propose(con, uuid.uuid4().hex, "Synthetic desktop acceptance", plan)
    run = e.execute(run["id"], run["approval_digest"])
    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.05)
    print(
        json.dumps(
            {
                "status": run["status"],
                "desktop_launch_native_marker": marker.exists(),
                "focus_verified": run["steps"][1]["status"] == "verified",
                "errors": [r["error"] for r in run["steps"]],
            }
        )
    )
    assert run["status"] == "succeeded" and marker.exists()
