# OKAL Idle Resource Benchmark (offline-only)

Issue #90. This developer/owner tool measures the process that user-systemd
reports as `okal-core.service MainPID`, not the machine as a whole. It never
reads Gmail messages, OAuth credentials, local SQLite, prompts or network data.
There are **no network requests, Ollama calls or external writes**.

## Run on owner Omarchy (after pulling merged main)

```bash
cd "$HOME/Projects/okal-production"
python3 scripts/benchmark-okal-idle.py --samples 12 --interval 5
```

Wait until sync completes before sampling an **idle** baseline. Run another
sample during a known manual sync or approved AI task to compare. The
script prints aggregate JSON for process CPU average/peak (100% = one CPU
core), RSS memory peak, elapsed time, sample count and process restarts.

For a private on-disk result:

```bash
python3 scripts/benchmark-okal-idle.py --samples 12 --interval 5 \
  --out "$HOME/okal-idle-measurement.json"
```

The output file is created using restrictive 0600 permissions and never
overwritten. Do not publicly share raw process metadata if your environment
has privacy constraints.

## Limitations

- No claim about the owner's real CPU/memory is made until an actual
  60-second Omarchy run is supplied.
- This samples only systemd's reported **MainPID**. If the service spawns
  children or Ollama GPU processes, their CPU/RAM/VRAM are **not** included.
  For GPU use run `nvidia-smi` manually and do not submit unrelated process
  names or credentials.
- Sampling while idle does NOT prove Gmail pushed in real time or that the
  Google Calendar 3-hour service policy was deployed.
- If systemd service stopped, the JSON reports unavailable samples and
  null CPU/RAM rather than inventing zeros.
- No new daemons, systemd timers or auto-start tasks introduced.

## Tests

```bash
PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests \
  -p test_idle_benchmark.py -v
```

Check the same benchmark twice, first idle, then during one explicit
operation, before deciding whether an idle CPU/memory optimization is
worth the added complexity.
