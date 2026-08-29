# Sandboxing and Execution Isolation

## Objective

Execute untrusted or high-variance workloads without granting them the host,
operator identity, memory database, secret store, or control-plane network.

## Sandbox profiles

| Profile | Intended work | Network | Filesystem |
|---|---|---|---|
| `pure-compute` | Parsing, transforms, evaluation | Denied | Read inputs, write artifacts |
| `network-readonly` | Research and API reads | Allowlisted GET-like destinations | Task workspace |
| `connector-write` | Approved external mutation | Exact connector proxy | Task workspace |
| `code-test` | Build and test repository | Dependency allowlist | Isolated checkout |
| `browser` | Web interaction | Browser proxy and destination policy | Download/upload workspace |
| `desktop-vm` | GUI computer use | Policy proxy | Ephemeral VM disk |
| `gpu-worker` | Local model, OCR, TTS, media | Provider-specific | Model cache and artifacts |

## Initial provider

Rootless containers with dropped capabilities, read-only base images, non-root
UIDs, seccomp/AppArmor where available, explicit mounts, CPU/RAM/PID/time limits,
and controlled egress. The provider interface permits later gVisor, Firecracker,
or Cua VM backends.

## Prohibited shortcuts

- Mounting the Docker socket into agent containers.
- Mounting the operator home directory.
- Sharing host SSH/GPG/browser profiles by default.
- Running workers as root.
- Giving general internet access when an allowlist is sufficient.
- Using environment variables containing broad long-lived secrets.
- Trusting a container boundary as the only control for R3 operations.

## Workspace lifecycle

Each execution gets an immutable input view, writable scratch/artifact paths,
quota, expiry, and cleanup state. Material artifacts move to the content-addressed
store only after validation. Cleanup is recorded and retried; forensic retention
is a policy decision.

## Network enforcement

Egress uses a policy-aware proxy where practical. URLs are normalized and
validated after DNS resolution and redirects. Loopback, link-local, private,
metadata, userinfo, alternate encoding, and redirect bypasses are denied unless
explicitly required by a local service profile.

## Execution measurement

Receipts include image/runtime digest, kernel/platform profile, command or
entrypoint, exit state, stdout/stderr hashes, wall time, CPU, peak RAM, GPU lease,
network destinations, artifact hashes, and termination reason.

## Cancellation and cleanup

Cancellation first revokes connector/network grants, then requests graceful
stop, then enforces termination after a bounded interval. A killed process is not
reported as a natural successful exit.

## Validation

CI and pre-release tests cover path traversal, symlink escape, process fork
bombs, resource limits, denied network, redirect/encoding SSRF, secret access,
malicious archives, cancellation, orphan cleanup, and evidence accuracy.
