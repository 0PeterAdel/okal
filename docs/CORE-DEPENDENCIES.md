# Core dependency intake (R1a)

Snapshot: 2026-10-30. Candidate adoption for #38, not a production-security
certification. Exact direct/transitive versions and distribution SHA-256 hashes
are in `apps/core/requirements.lock`; test additions have a separate lock.
Use `pip install --require-hashes`, not a floating install. No model weights,
external agent runtime, vendored upstream repository or paid API is added.

## Sources and licenses

Versions/license metadata were read from PyPI and installed distribution metadata.
Upstream API behavior was checked against official documentation/source; no
third-party copied implementation is used. Review the upstream LICENSE when
redistributing; the Okal MIT license does not replace dependency licenses.

| Distribution | Runtime version | Declared license |
|---|---|---|
| fastapi | 0.162.0 | MIT |
| pydantic | 2.14.2 | MIT |
| pydantic-core | 2.50.2 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| starlette | 1.10.0 | BSD-3-Clause |
| anyio | 4.15.1 | MIT |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| opentelemetry-api | 1.45.2 | Apache-2.0 |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |

Test-only additions: httpx 0.28.1 and httpcore 1.0.9 (BSD-3-Clause), certifi
2026.10.23 (MPL-2.0). They are not installed by the runtime lock. Starlette emits
an httpx deprecation warning; the locked compatibility path passed the tests.
Do not silently switch test clients without rerunning the boundary cases.

Official sources:

- [FastAPI](https://github.com/fastapi/fastapi) and [security guidance](https://fastapi.tiangolo.com/advanced/security/http-basic-auth/).
- [Pydantic](https://github.com/pydantic/pydantic).
- [Uvicorn](https://github.com/Kludex/uvicorn).
- [SQLite Python interface](https://docs.python.org/3/library/sqlite3.html).
- [PyPI version metadata](https://pypi.org/pypi/fastapi/0.162.0/json);
  equivalent version-specific metadata exists for every locked distribution.

## Security, destinations and replacement

`pip-audit` 2.9.0 checked every runtime pin against its advisory service and
reported no known vulnerabilities at this snapshot. This is time-bound and does
not establish absence of vulnerabilities. The generated
[CycloneDX SBOM](../apps/core/evidence/runtime-sbom.json) records the resolved
components. Hash lockfiles bind the downloaded artifacts; an SBOM alone does not.
Re-audit on updates and before release; the scanner is a development tool.

Install/resolution contacts PyPI/distribution hosting; advisory scans contact the
scanner's vulnerability service. Browser test setup downloads Playwright Chromium.
These operations use only public package metadata, not user mail or credentials.
Runtime serves loopback only and has no configured outbound provider or telemetry
exporter. The transitive OpenTelemetry API is not an installed SDK/exporter.
There are no external fonts, scripts, analytics or CDN dependencies in the UI.

Security review includes token-verifier storage, private files, SQL placeholders,
atomic writes, bounded queries, host/origin/client checks, no URL credentials,
no browser token persistence, and literal rendering of untrusted text. Local
same-user compromise and full transport/TLS/pairing are outside this first slice.

Replacement path: keep data operations behind Store and the v1 read contract;
an API-library replacement need not alter provider logic (none exists yet).
SQLite schema version is 1; newer versions are refused, never auto-downgraded.
Back up before upgrades. Tests prove same-version restore, not future migrations.

## Resources and acceptance

The [fixture smoke report](../apps/core/evidence/runtime-smoke.json) records actual
test-host startup, process peak RSS and total CPU during the smoke, graceful
shutdown and restart. No model/GPU workload is loaded. The host did not expose
child `/proc` metrics, so isolated idle RAM/CPU is not claimed. Measure that and
the full login/boot lifecycle on the owner Omarchy laptop before acceptance.
