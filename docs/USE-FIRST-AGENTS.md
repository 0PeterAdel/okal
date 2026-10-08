# Use-first agent stack (proposal, 2026-10-09)

## Goal and first acceptance

Get three useful local assistants running before extending the Okal kernel:
research with links, coding in an isolated checkout, and social content drafts.
The initial social agent **does not connect to a publishing account**. The
operator reviews every draft. A later Postiz adapter may schedule an approved
draft; neither a voice transcript nor an agent's claim is publication approval.

This is a proposed integration path, not a claim that the existing Okal voice
service executes tools. PRs #10 (voice), #11 (STT acceptance), and #12
(transcript review) are separate draft work. The recordings and their scoring
remain prerequisites before voice can request an action.

## Choice

| Component | Role now | Decision and cost |
|---|---|---|
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | ready-to-use local agent loop, three separate profiles, memory, CLI, optional scheduled jobs | Pilot as a **separate process**, MIT; connect to existing Ollama. No bundled fork. |
| [Okal voice draft](https://github.com/0PeterAdel/okal/pull/10) | future input/output adapter | Keep existing speech work. Route into an agent only after transcript acceptance, scoped capabilities, and action approval exist. |
| [Postiz](https://github.com/gitroomhq/postiz-app) | reviewed social scheduling and analytics | Optional **separate service** after draft flow. AGPL-3.0; self-hosting requires PostgreSQL/Redis/Temporal and social platform developer credentials. Its API supports draft-only creation. Do not embed code. |
| [Mixpost Lite](https://github.com/inovector/mixpost) | lighter social publisher | MIT, but the free Lite platform list is limited to Facebook Pages, X, and Mastodon; verify its API/MCP features for Lite before considering it in place of Postiz. |
| [Activepieces](https://github.com/activepieces/activepieces) | broad deterministic integrations | Later optional external automation worker; community edition MIT, enterprise features separate. Do not run another workflow server for the first three agents. |
| [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) | research, skill evaluation, reference agents | Evaluate specific workers later; avoid a second simultaneous agent control plane. |
| [OpenClaw](https://github.com/openclaw/openclaw), [Dify](https://github.com/langgenius/dify), [n8n](https://github.com/n8n-io/n8n) | alternative all-in-one/channel/workflow hosts | No core dependency in this pilot. Dify has a custom license; n8n is fair-code, not MIT. Revisit after a concrete missing feature. |

Hermes has a documented Ollama custom endpoint and independent per-profile
configuration/memory. The profile files in `agents/profiles/` are reusable
instructions, not an authorization mechanism or an imported skill catalog.

## Prepare the pilot

1. Run `ollama list`. Use a model already cached and verify one normal CLI
   chat first. For an existing Qwen3.5 9B installation, Hermes' custom
   provider points at `http://127.0.0.1:11434/v1` with model
   `qwen3.5:9b`. Check the current upstream
   [local Ollama guide](https://hermes-agent.nousresearch.com/docs/guides/local-ollama-setup)
   for installation and `hermes model` configuration. Do not download a
   second model for this pilot.
2. Install Hermes using its [official Linux installation guide](https://hermes-agent.nousresearch.com/docs/getting-started/installation),
   inspect its install script first, and test `hermes chat` with a harmless
   question. It is a separate app in `~/.hermes`, not a Python dependency of
   Okal. Avoid the subscription setup path; select the local custom endpoint.
3. From this repository run `bash scripts/setup-agent-profiles.sh --dry-run`
   and inspect the plan. Run `bash scripts/setup-agent-profiles.sh --apply` to
   create only absent `okal-research`, `okal-code`, and `okal-social` profiles
   and copy their `SOUL.md` templates. Existing profile identities and SOUL
   files are never overwritten.
4. Configure the same local model separately for each profile using
   `hermes -p okal-research model`, `hermes -p okal-code model`, and
   `hermes -p okal-social model`. Use `hermes -p <name> chat` to try them.
   Profiles are isolated, so do not use `--clone` to carry personal memory or
   tokens across roles.

Try the following requests without account credentials:

```text
okal-research: Summarize a local README and cite the file path and sections.
okal-code: Inspect a disposable checkout and propose one testable fix; show the diff.
okal-social: Draft two Egyptian Arabic posts about a project update; return drafts only.
```

The pilot passes when all three profiles answer, no social account is
connected, the code proposal is reviewable in an isolated checkout, and
stopping any agent does not stop Okal voice. Profile isolation is not an OS
sandbox: Hermes' local terminal tools still have the operator's filesystem
permissions. Use a disposable checkout for code; do not attach posting tools,
tokens, or a real browser session to the social profile in this pilot.

## Expand only after the first use

1. Social: connect a Postiz instance **on demand** to one test social channel,
   register the provider's official app/OAuth credentials privately, and
   create a `type: draft` item through its API. Human review in the Postiz UI
   precedes scheduling; check native post state afterward. Postiz is not
   needed to draft text today.
2. Research: add one read-only search/document connector, with source links.
3. Coding: give the code worker a disposable worktree, run tests, and ask for
   review before GitHub write. OpenHands can replace this worker if it wins a
   measured trial.
4. Voice: compare 40 fresh clips under the [acceptance protocol](https://github.com/0PeterAdel/okal/pull/11).
   Bind accepted text to a task; ask for explicit confirmation before any
   external write. Keep a keyboard/CLI path when speech is uncertain.
5. Okal kernel: add persisted tasks, scoped grants, approval, and native-state
   receipts between agent requests and tool execution, as required by ADR-001
   and ADR-004. Only then enable unattended recurring **read-only** monitoring.

## Exit and resource policy

All pilot profile data lives under `~/.hermes/profiles/okal-*/`. The setup
script never removes data; use Hermes' own profile export before removal.
No Docker services run by default. On the reference 16 GB RAM/8 GB VRAM
machine, use one large model/voice GPU workload at a time; defer full Postiz
and Activepieces stacks rather than keeping them running alongside Ollama.
If Hermes does not reliably use the selected local model's tools, compare an
OpenJarvis or OpenClaw pilot with the same three tasks before promoting any
dependency into Okal. A response alone is not proof that an action happened.

Sources checked 2026-10-09: [Hermes profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles),
[Hermes local Ollama](https://hermes-agent.nousresearch.com/docs/guides/local-ollama-setup),
[Postiz self-hosting](https://docs.postiz.com/self-host/configuration/reference),
[Postiz providers](https://docs.postiz.com/self-host/providers/overview),
[Postiz draft API](https://docs.postiz.com/public-api/posts/create),
[Mixpost Lite scope](https://mixpost.app/pricing),
[Activepieces Docker setup](https://github.com/activepieces/activepieces/blob/main/docs/install/options/docker-compose.mdx).
