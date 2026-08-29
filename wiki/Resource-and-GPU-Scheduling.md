# Resource and GPU Scheduling

## Resource correctness

Okal plans compute before dispatch. A task that causes OOM, starves voice,
thrashes swap, overheats the device, or exceeds cost/energy policy is not a valid
successful route.

## Resources

- CPU cores and scheduling priority;
- resident and committed RAM;
- GPU device, VRAM, compute mode, and model residency;
- disk space and I/O;
- network bandwidth and external rate limits;
- monetary and token budgets;
- thermal/power profile;
- latency deadline.

## Lease model

Workers request leases with minimum, preferred, and maximum resources. The
Resource Broker may queue, resize, unload another model, choose CPU, route to a
remote worker, or reject the request. Workers cannot allocate a second heavy
resource outside their lease.

## Priority classes

1. Safety, cancellation, and approval controls.
2. Active voice capture, STT, and TTS.
3. Interactive operator requests.
4. Consequential-action verification.
5. Scheduled/long-horizon work.
6. OCR batch, indexing, evaluation, and media generation.

## Reference laptop profile

Target hardware: Intel i7-14650HX, 16 GB RAM, RTX 4060 Mobile 8 GB, Linux/Wayland.

Initial policy:

- one GPU-heavy workload at a time;
- reserve VRAM headroom for the display/runtime;
- small quantized local text model for interactive use;
- unload or remote-route the text model before BF16 OCR/media workloads;
- never use swap capacity as proof that an interactive model fits;
- suspend background evaluation while voice is active;
- record actual peak RAM/VRAM and refine estimates.

Unlimited OCR is a 3B BF16 model, so raw weights alone are approximately 6 GB
before vision/runtime overhead. It must receive an exclusive or carefully
measured GPU profile on an 8 GB device.

## Model residency

The broker maintains a model cache with load cost, last use, predicted next use,
VRAM size, and eviction priority. Voice-critical models have higher residency
priority than batch generation.

## Remote execution

Remote workers advertise signed hardware/capability profiles and current health.
Routing remains constrained by privacy and cost. Remote success requires service
reachability plus bound native evidence; a queued request is not execution.

## Budgets and circuit breakers

Per-call, task, session, daily, and provider limits stop runaway loops. Repeated
OOM, timeout, or rate-limit failures degrade a route and open a circuit breaker.
Recovery requires health checks and controlled probing.

## Metrics

Queue wait, load time, time to first token/audio, peak RAM/VRAM, GPU utilization,
energy when measurable, cost, eviction count, OOM rate, throttling, and task
success per resource unit are recorded by hardware profile.
