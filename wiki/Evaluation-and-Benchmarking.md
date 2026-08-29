# Evaluation and Benchmarking

Evaluation is a release control, not a demo activity. Every model, prompt, capability, routing rule, memory change, and skill version must prove that it improves the target behavior without unacceptable regressions.

## Evaluation layers

| Layer | Purpose | Typical method |
|---|---|---|
| Component | Validate one parser, adapter, policy, or tool | deterministic tests |
| Trajectory | Judge a plan and its sequence of actions | replay plus trace assertions |
| Outcome | Verify the final state in the native system | state inspection |
| Safety | Detect policy bypass, injection, exfiltration, or overreach | adversarial suite |
| Human | Measure usefulness and correction burden | blinded rubric |
| Operations | Measure latency, cost, reliability, and resources | controlled load test |

## Benchmark suites

1. **Assistant Core:** planning, clarification, scheduling, drafting, and structured extraction.
2. **Showcase Workflow:** GitHub/Jira work item, Arabic PDF evidence, code change, tests, review, and approval.
3. **Routing:** local/remote selection under quality, privacy, cost, and resource constraints.
4. **Memory:** correct recall, temporal updates, provenance, contradiction handling, and deletion.
5. **Documents:** Arabic/English OCR, layout recovery, tables, citations, and answer grounding.
6. **Voice:** wake/turn handling, Arabic recognition, interruption, tool-use latency, and TTS quality.
7. **Security:** prompt injection, malicious MCP server, poisoned skill, confused deputy, and secret access.
8. **Resource Pressure:** 16 GB RAM and 8 GB VRAM scenarios with concurrent voice, OCR, and generation.
9. **Resilience:** provider outage, worker crash, duplicate callback, network partition, and resume.

## Required metrics

| Area | Metrics |
|---|---|
| Outcome | governed success, native-state correctness, completion rate |
| Quality | rubric score, citation precision/recall, extraction F1 |
| Autonomy | steps per task, unnecessary actions, human interventions |
| Safety | policy violation rate, exploit success rate, unsafe-action recall |
| Memory | grounded recall, stale-memory rate, deletion completeness |
| Reliability | recovery rate, duplicate side effects, mean time to resume |
| Efficiency | p50/p95 latency, tokens, cost, CPU/RAM/VRAM time |
| Experience | voice turn latency, interruption success, user correction rate |

Each suite defines its own thresholds. A single aggregate score cannot conceal a critical safety or reliability failure.

## Dataset governance

- Maintain public, private, adversarial, and regression splits.
- Version prompts, fixtures, expected states, rubrics, and judge configuration.
- Preserve Arabic and English coverage; add dialectal Egyptian Arabic where appropriate.
- Strip secrets and personal data from recorded trajectories.
- Keep a sealed holdout set for release decisions.
- Record random seeds and dependency versions where reproducibility is possible.

## Model-based judging

Model judges may assess open-ended quality, but they cannot be the sole verifier for side effects, security properties, citations, or schema validity. Calibrate each judge against blinded human labels and monitor position, verbosity, and self-preference bias.

## Promotion policy

A candidate is promoted only when:

- all deterministic and security gates pass;
- critical suites show no regression;
- quality gains exceed the suite's minimum meaningful delta;
- latency, cost, and resources stay within budget;
- failures are inspected, classified, and linked to receipts;
- a rollback target and migration path exist.

Production rollout proceeds through shadow, canary, limited, and general stages. Automatic rollback is triggered by governed-success, security, or duplicate-side-effect thresholds.

## Baselines

Compare Okal against:

- the same task using one strong model with no tools;
- the same model with direct tools but no kernel controls;
- local-only and cloud-only routing;
- memory disabled versus each memory layer enabled;
- fixed runtime selection versus Okal's capability router.

This isolates which part of the architecture creates the improvement.

## Evaluation artifacts

Each run produces a signed manifest, configuration snapshot, dataset version, trace bundle, receipt set, metric report, failure clusters, and promotion decision. Reports are reproducible locally without access to production secrets.

## Acceptance criteria

- Every release candidate has a reproducible evaluation report.
- Critical safety tests have zero unwaived failures.
- Side-effect benchmarks verify native state rather than model claims.
- Routing benchmarks include constrained local hardware.
- Any waived regression has an owner, expiration, and linked risk entry.
