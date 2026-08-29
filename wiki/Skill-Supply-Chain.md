# Skill Supply Chain

## Goal

Allow Okal to learn new procedures without treating Markdown, scripts, or
community popularity as trusted code.

## Intake pipeline

```mermaid
flowchart LR
    D["Discover"] --> P["Pin source"]
    P --> L["License and SBOM"]
    L --> S["Static and semantic scan"]
    S --> C["Conformance tests"]
    C --> E["Task evaluations"]
    E --> A["Operator approval"]
    A --> R["Sign and promote"]
```

## Required controls

### Source pinning

Resolve repository, exact commit, subdirectory, included resources, recursive
dependencies, and content digest. Branch names and mutable release aliases are
not executable identities.

### License and SBOM

Generate an SBOM with Syft or an equivalent tool, record model/dataset licenses
separately, and block incompatible or unknown license terms from the core.

### Security scanning

SkillSpector is the mandatory skill-specific scanner. It is combined with secret
scanning, dependency vulnerability scanning, executable/script inspection,
network destination extraction, and manual review for high-risk capabilities.
No single scanner proves safety.

### Conformance

Test schema, error handling, timeout, cancellation, permission denial, empty
outputs, malformed tool calls, secret redaction, network denial, and artifact
binding in a quarantined sandbox.

### Evaluation

Compare against no-skill and current-skill baselines on public and private cases.
Measure task success, unsafe behavior, cost, latency, resource use, and regression.

### Promotion

Approval covers an exact version and permission manifest. Promotion signs the
manifest, evaluation report, SBOM, and artifact digest. Updates repeat intake.

## Skill content rules

- Instructions cannot redefine kernel policy or authority.
- Referenced scripts and assets are part of the scanned artifact.
- Dynamic network downloads during execution are forbidden unless declared.
- Skills request capabilities through manifest references, not arbitrary shell.
- Sensitive examples and expected answers do not enter production prompts.
- Skills are loaded on demand; the full catalog is never injected into context.

## Candidate self-improvement

Okal may derive a candidate skill from successful traces. The candidate is
written to a development workspace, never the active registry. It must pass the
same intake and outperform the baseline across multiple seeds without increasing
safety violations. Promotion is a release action with rollback.

## Revocation

Critical findings immediately set the version to `revoked`, stop new dispatch,
identify affected tasks and memory, and produce an incident report. Historical
receipts preserve the version reference.

## Initial sources

Matt Pocock's engineering skills, gstack, and the Anthropic Cybersecurity Skills
community project are evaluation sources, not wholesale dependencies. Only
skills that fill a defined use case and pass intake enter the active registry.
