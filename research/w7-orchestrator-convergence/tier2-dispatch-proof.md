# W7 Tier-2 Containerized Dispatch Proof

This note is the runbook for `livespec-impl-beads-dn9`, the next W7
Beads/Fabro slice after the DinD spike (`livespec-impl-beads-o2f`) and the
production orchestrator image (`livespec-impl-beads-8bc`). The step-1 image
proved Tier 1: build, inner Docker daemon health, Fabro provisioning, web UI
reachability, and an ephemeral Dolt / `bd` round trip. Tier 2 proves one real
dispatcher invocation from inside that container.

## Proof Shape

Use `orchestrator-image/tier2-dispatch-proof.sh`. It starts the
`livespec-orchestrator:dev` image, lets the normal entrypoint provision the
inner Docker daemon and Fabro server, then runs:

```bash
python3 /workspace/livespec-impl-beads/.claude-plugin/scripts/bin/dispatcher.py \
  loop \
  --repo /workspace/livespec-impl-beads \
  --budget 1 \
  --mode shadow \
  --item <tiny-ready-item> \
  --no-close-on-merge \
  --journal /tmp/livespec-tier2-dispatch-journal.jsonl \
  --poll-attempts 3 \
  --poll-interval-seconds 10 \
  --json
```

The item is explicit and shadow-mode only. The script never selects from the
ready queue, never creates a work item, and passes `--no-close-on-merge` so the
proof cannot close the ledger item automatically. The operator must provide a
deliberately tiny, isolated, ready work item that is safe for a one-dispatch
probe.

## Running

Preflight only:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/tier2-dispatch-proof.sh --preflight
```

Build the image first if needed:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/tier2-dispatch-proof.sh --preflight --build-image
```

Run the proof:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/tier2-dispatch-proof.sh --run --item <tiny-ready-item>
```

The script requires these environment variable names to be present, normally
from the 1Password wrapper:

- `LIVESPEC_FAMILY_GITHUB_TOKEN`
- `ANTHROPIC_API_KEY_LIVESPEC_E2E`
- `CLAUDE_CODE_OAUTH_TOKEN`
- `BEADS_DOLT_PASSWORD_livespec_impl_beads`
- `HONEYCOMB_INGEST_KEY_LIVESPEC`

It reports only presence and byte counts for secret variables. It does not
print values.

## Evidence To Capture

Record the following in this file or in a successor note before closing
`livespec-impl-beads-dn9`:

- the exact item id used for the tiny ready-item proof;
- the script invocation;
- the inner Docker storage driver;
- confirmation that no host Docker socket was mounted;
- the dispatcher exit code;
- the redacted dispatcher journal tail;
- the inner `docker ps -a` summary after dispatch;
- whether cost/telemetry spans were token-observable, dollar-overlay-only, or
  still dark.

## Evidence So Far

2026-06-20 local time / 2026-06-19 UTC:

- `mise exec -- just w7-tier2-dispatch-proof -- --help` succeeded after the
  script was adjusted to tolerate the bare `--` that `just` forwards.
- `/data/projects/1password-env-wrapper/with-livespec-env.sh -- bash
  orchestrator-image/tier2-dispatch-proof.sh --preflight --build-image`
  succeeded:
  - all required secret env var names were present; the script printed only
    byte counts;
  - the script staged the host Fabro binary into the gitignored build context;
  - Docker built `livespec-orchestrator:dev`;
  - built image id:
    `sha256:913eeda6955aa58dff51b6950f34a7d2342e6928b4a8df6894243b8d234543a2`;
  - image size reported by Docker: `1064148333` bytes.
- A second preflight without `--build-image` succeeded and confirmed the image
  is present.

Remaining proof blocker: select or create a deliberately tiny, isolated, ready
work item that is safe for one shadow dispatch. Do not use `dn9` itself as the
dispatch target. The actual Tier-2 run is:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/tier2-dispatch-proof.sh --run --item <tiny-ready-item>
```

## Codex Runtime Classification

Tier 2 still runs the Beads/Fabro orchestrator, not a Codex driver. Codex
participation in this tier is therefore evidence classification:

- `livespec-impl-beads` has no Codex project adapter today; Codex support is
  contributor-workflow support through `AGENTS.md`, repo hooks, and stable
  CLI/script entry points.
- The core `livespec` checkout has verified Codex project-local adapters for
  `help`, `next`, and `doctor`; use those only where the proof touches core
  spec-side commands.
- Any Claude-only mechanics encountered by the run, especially Claude Code
  hooks or Fabro ACP behavior, must be named as Claude-driver-only or Codex
  replacement-required rather than silently inherited.

## Telemetry Rule

Tier-2 evidence remains token-first. Claude Code dollar estimates are a
provider-specific overlay. Codex/OpenAI evidence must not be inferred from
Claude Code cost spans; a future OpenAI extractor must map OpenAI token fields
explicitly.
