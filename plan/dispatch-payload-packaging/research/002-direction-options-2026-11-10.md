# 002 — Direction options for dispatch payload packaging (2026-11-10)

Prepared for the maintainer's direction choice (coordinator-duties section 9). Nothing is
implemented until the maintainer picks. Goal served: keep every dispatch under Fabro's
hard per-file cap with margin, without putting helper bytes in front of the model and
without adding a Fabro fork carry (the fabro-currency goal "carry only what the factory
needs").

## Measurements (this host, 2026-11-10)

Materialized `$TMPDIR/fabro-workflow-<hex>/workflow.toml` sizes, from the dispatch
directories left on vmi3006760.contaboserver.net:

| Date | Bytes |
| --- | --- |
| 2026-11-02 | 467,910 |
| 2026-11-06 | 473,925 |
| 2026-11-08 | 487,669 |
| 2026-11-10 (livespec-dev-tooling-wacdfl, the stop-the-line) | 524,343 |
| 2026-11-10 20:21Z (livespec-dev-tooling-ev4hgk) | 518,117 |

The file grew about 50 KB in 8 days, roughly 6 KB a day. The cap is 524,288 bytes, and the
gate threshold is 471,859 bytes (90%).

Breakdown of the 518,117-byte file:

- 409,951 B of `LIVESPEC_PREPARE_PAYLOAD*` env values across 55 `[[run.prepare.steps]]`.
  - 191,888 B is the gh-refresh bundle, already tar.gz+base64.
  - 204,651 B is plain helper source (the largest are `livespec-carry-forward-decision.py`
    at 41.8 KB, `livespec-commit-runner.py` at 39.0 KB and `_dispatcher_proof_attachment.py`
    at 49.6 KB in three parts).
  - 13,412 B is per-dispatch data (the dod_gate subject and the pull-request body).
- 30,727 B of step scripts, plus the committed base of about 40.5 KB.
- The dispatch's `workflow.fabro` is ALSO 310,593 B, 59% of its own 512 KiB cap.

Packing all the plain helpers as one gzip+base64 blob gives 74,940 B, so the toml would be
about 388 KB. Removing every static helper gives about 122 KB.

A sparse, blobless, depth-1 fetch of this repository's helper sources at a pinned commit
took 1.1 s to clone plus 2.2 s to check out on this host. That has not been measured
inside a sandbox.

## Engine facts

These were read on carrier `carrier-v0.408.0-nightly.0-20261108` (85071c828, Petri
ac0b9fb3) and serving `bbe693847`. The full evidence is in
`003-fabro-engine-delivery-findings-2026-11-10.md`.

1. Workflow-package files are NEVER written into the sandbox.
   - The packager collects only files the workflow references: `goal`/`prompt`/`output_schema` `@file`, imports, child workflows, a Dockerfile and template includes (`fabro-dot/src/lib.rs:252-259`, verified by this session).
   - `script=` is never scanned. Files must be UTF-8.
   - No code materializes package files into the sandbox. The only file delivery is the `[run.clone]` repository checkout.
   - The caps (512 KiB per file including workflow.fabro, 2 MiB per version, 512 files) are `pub const` values, checked on both client and server, with no setting to raise them.
2. Command nodes take no literal per-node `env`. A script runs as one `bash -c` argument (the kernel caps one argument at 128 KiB). Under the default `compact` fidelity, every completed command node's FULL script is pasted into the prompt of every later agent node, ACP included.
3. Literal `[environments.<id>.env]` values reach EVERY process in the sandbox: command nodes, ACP agent processes, their tool subprocesses and the container env.
   - They are never rendered into a model prompt.
   - They are persisted twice per run (the `run.created` run spec and the stored graph blob).
   - About 400 KB of environment rides on every exec, against the shared argv+env ARG_MAX (about 2 MiB).
   - Draft PR #4844 (bd-ib-dpsiwz) moves the payloads into this table.
4. On resume onto a re-acquired sandbox, `run_prepare_<N>` command nodes re-run, and they see the environment table.

## Options

### A — Ship each helper as its own workflow-package file (bd-ib-jrawlp as filed)

- What it takes: the engine has NO path that delivers a package file into the sandbox. A
  needs a Fabro fork change: collect declared extra files, materialize them into the
  sandbox before setup, and support non-UTF-8 content or base64 text. The change lands on
  both client and server, and it is carried on every carrier rebase.
- Cost: a new permanent fork carry against fabro-currency's "carry only what the factory
  needs". The 2 MiB version cap and the 512 KiB per-file cap still apply, per file.
- Risk to factory correctness: medium. A new engine path runs on the critical setup
  route, and is unproven on resume.

### B — Everything through command nodes (literal reading of the run.prepare migration, bd-ib-dpsiwz)

- Put the helper bytes in the `run_prepare_<N>` node scripts in workflow.fabro.
- Cost and risk: rejected on measurement.
  - workflow.fabro is already 310 KB, so about 400 KB more overflows it at once.
  - Any one script over 128 KiB fails execve.
  - Every script is re-sent to every later agent node's prompt. The precedent measurement in `plan/factory-context-per-turn-reduction` research note 003 found 358,046 script characters, about 241,400 tokens, 71% of the first-request floor.
- dpsiwz's draft (PR #4844) already avoids this by hoisting payloads into the environment table, which is option C's carrier.

### C — Keep gzip+base64 in env values permanently (bd-ib-p5e32s, plus dpsiwz's environment-table hoist)

- Cost: none beyond what is landing now.
- Headroom: about 388 KB against the 471,859-byte gate, about 84 KB. The compressible
  growth is about 6 KB a day raw, roughly 2-3 KB a day packed, so the gate is reached in
  about 4-6 weeks unless growth slows. The next stop-the-line is a matter of when, not if.
- Risk to factory correctness:
  - About 150-390 KB of environment on every sandbox exec, including agent tool calls,
    counted against ARG_MAX.
  - The payload is duplicated into two stored run records per run.
  - An agent running `env` sees the payload in its tool output. That is model-visible
    through an agent's own action.

### D — Pinned, digest-verified fetch of the helpers from the dispatching build's own commit (RECOMMENDED)

How it works:

- The Dispatcher writes a small manifest into workflow.toml: the orchestrator repository,
  the exact commit of the installed plugin build, and one sha256 per helper path. That is
  a few KB.
- One `run_prepare_<N>` node does a sparse, blobless, depth-1 fetch of that commit and
  verifies every digest. On any mismatch, unreachable commit or missing path, it fails
  the run with a named cause.
- Because the node carries the `run_prepare_` prefix, it re-runs on resume.
- This is the same mechanism shape as the pinned run-from clones that landed today
  (cfa81a6b5, Scenario 336).
- Per-dispatch data (dod_gate subject and pull-request body, about 13 KB) stays inline,
  as do the small decoders.

What it achieves:

- workflow.toml falls to about 122 KB plus the manifest. The ceiling stops tracking
  helper growth.
- No helper bytes in any prompt, the environment or the run records.
- No fork carry.
- It works identically on `run.prepare` (serving) and command nodes (C408), so it
  composes with dpsiwz rather than competing with it.

Cost:

- One new setup node plus a manifest renderer in the Dispatcher.
- A sandbox needs egress to github.com, which it already has for the `[run.clone]`
  target and the sibling clones.
- About 3 s of setup per dispatch (host-measured).

Risks to factory correctness:

1. A dispatch from an unpushed local build cannot be fetched. It must refuse before
   claim, naming the commit; a fallback to C for local builds is a design choice to make.
2. Some helpers may be assembled by the Dispatcher rather than copied verbatim. Those
   must be reproduced in-sandbox, or published as a release asset with the same digest
   check.
3. GitHub availability becomes a setup dependency. It already is one for the clone.

### Recommendation

D, with C as the stopgap until D is live.

- p5e32s finishes with gmktec-factory-placement as planned.
- dpsiwz lands as drafted on fabro-currency's deadline: the environment-table hoist
  keeps it off the model.
- This plan then replaces the hoisted payload with D's manifest and fetch node, and
  retires the gzip+base64 packing.
- bd-ib-jrawlp is re-cut to D's design.
- bd-ib-pwkhqz (the CI size gate) stays as filed, extended to measure workflow.fabro too.

## On the maintainer's question "is gmktec factory placement the right place?"

No. Packaging is a dispatch-design topic shared by three owners, not a placement concern.
This plan (dispatch-payload-packaging, bd-ib-x5ypbf) owns it. gmktec-factory-placement
keeps only the p5e32s stopgap, and fabro-currency keeps only the dpsiwz migration.
