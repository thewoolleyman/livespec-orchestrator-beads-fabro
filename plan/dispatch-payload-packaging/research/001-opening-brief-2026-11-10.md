## The maintainer's statement of what done means

Yes, do that recommendation. Ensure the correct solution is included in the plan. But is gmktec factory placement the right place, or just another catch-all plan?

## Definition of Done assertions derived from that statement

- A dispatch of the implement-work-item workflow from any fleet member materializes a workflow.toml that carries no helper program source.
- Every file of a dispatch's materialized workflow package measures under Fabro's 524,288-byte per-file cap by at least the margin the size gate enforces, for every member of the fleet array in livespec's .livespec-fleet-manifest.jsonc.
- This repository's CI renders every fleet member's materialized workflow package on every pull request and master push, and fails the run naming the member and file when any file exceeds the size gate's threshold.
- A dispatched sandbox checks the digest of every delivered helper payload against the digest the Dispatcher recorded, and a run whose payload digest mismatches is refused before dod_gate with a failure cause naming the mismatched payload.
- Once the replacement packaging is live, the Dispatcher's rendered run configuration carries no gzip+base64-packed helper payload.
- A dispatch on the setup-command-node workflow of the run.prepare migration (bd-ib-dpsiwz) delivers its helper programs through this plan's packaging, with no second payload path.
- The plan epic records the model-visible goal size and dod_gate judgement subject size, measured with token-spend-analysis before and after the packaging change.

# 001 — Opening brief and problem statement (2026-11-10)

Plan opened by legacy-coordinator-agent on the maintainer's direction. The brief file
it was given lived under a temporary scratchpad, so it is copied here verbatim and into
the plan's first scope event.

## Brief (verbatim)

```text
You are the seat for a NEW maintainer-driven plan, dispatch-payload-packaging, in this repository (livespec-orchestrator-beads-fabro). legacy-coordinator-agent opened you on the maintainer's direction (2026-11-10 ~20:5xZ, verbatim: "Yes, do that recommendation. Ensure the correct solution is included in the plan. But is gmktec factory placement the right place, or just another catch-all plan?"). Create the plan with /livespec-orchestrator-beads-fabro:plan dispatch-payload-packaging (new plan; record the maintainer's words above as its first scope event).

PROBLEM: about 400-500 KB of orchestrator helper programs are inlined into every dispatch's materialized workflow.toml, which overflows Fabro's 512 KiB per-file cap (the f0b6/v0.312.3 stop-the-line: 61 of 61 queued items over the threshold, and the orchestrator's own dispatches about 6.6 KB under the cap). The interim fix, bd-ib-p5e32s (gzip+base64 of every embed), stays with gmktec-factory-placement as a stopgap, with byte-exact round-trip checks required. THREE items from three owners change this same surface: p5e32s (compression), bd-ib-jrawlp (ship the helpers as separate workflow-package files) and bd-ib-dpsiwz (fabro-currency's run.prepare migration, which moves the payload env into the run config).

DEFINITION OF DONE (draft; refine it, keep the intent):
- No helper program is inlined into a dispatch's workflow.toml. Every materialized per-file size is under Fabro's cap with a measured margin, checked in CI fleet-wide (adopt bd-ib-pwkhqz).
- The payload reaches the sandbox byte-verified (a digest check), and a mismatch refuses the run with a named cause.
- The gzip+base64 compression of p5e32s is retired once the real packaging is live.
- dpsiwz's run.prepare migration and this plan's packaging are reconciled onto ONE design, with fabro-currency.
- The model-visible goal and judgement subject sizes are measured before and after, with token-spend-analysis, so token cost is known, not assumed.

ADOPT as children: bd-ib-jrawlp and bd-ib-pwkhqz (both parentless today). Do NOT take p5e32s; it finishes with gmktec-factory-placement.

DIRECTION IS THE MAINTAINER'S (coordinator-duties section 9): prepare 2-3 lettered options (for example A: separate package files, jrawlp; B: everything through run.prepare, dpsiwz; C: keep compression permanently), with measured costs, risks to factory correctness, and your recommendation. Send them to legacy-coordinator-agent by SendMessage in a form the maintainer can answer cold. Do not start implementation before the maintainer picks. Name this seat to the maintainer as workspace livespec-orchestrator-beads-fabro, tab dispatch-payload-packaging.

Rules: read .ai/coordinator-duties.md section 5 on hand-landing; use worktrees; never pass --no-verify; open PRs as --draft until graded. Run the plan's /loop once the plan exists.
```

## Derivation note

The Definition of Done assertions above are SESSION-DERIVED from the coordinator's draft
Definition of Done in the brief (the maintainer's own words are the statement). They keep
the draft's intent; assertion 6 restates "reconciled onto ONE design" as an observable
dispatch, and assertion 7 restates "token cost is known, not assumed" as a recorded
before/after measurement. They are expected to be re-worded by a carrier-map scope event
once the maintainer chooses a direction from the lettered options (research note 002).

## Owners of the shared surface

- bd-ib-p5e32s — gzip+base64 packing of every prepare payload (gmktec-factory-placement,
  livespec-dev-tooling-me5aqz). Stopgap; NOT a child of this plan.
- bd-ib-jrawlp — ship helpers as separate workflow-package files. Adopted by this plan.
- bd-ib-pwkhqz — fleet-wide materialized-size gate in CI. Adopted by this plan.
- bd-ib-dpsiwz — run.prepare to command-node migration (fabro-currency, bd-ib-6tcjfx).
  Stays with fabro-currency; this plan reconciles the design with it.
