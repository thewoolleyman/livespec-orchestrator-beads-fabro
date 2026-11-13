# 028 — Plan Proof of Done readiness, 2026-11-13

Written by claude:fabro-currency session 2032fcbc at about 10:15Z on 2026-11-13. It maps each of the plan's nine
Definition of Done assertions to the evidence that exists today and to what the plan's own Proof of Done still has to
capture. Read it before taking the plan record.

## Where the plan stands

- The latest carrier-map scope event is from 2026-11-07T20:29:13Z (session 1040a2). Its carriers are:
  - 1: bd-ib-qx45e6, bd-ib-iud52v
  - 2, 3 and 7: bd-ib-iud52v
  - 4: bd-ib-iud52v, bd-ib-xdmkhf
  - 5: bd-ib-4ipmub, bd-ib-iud52v
  - 6: bd-ib-sxcnj7
  - 8: bd-ib-j9x
  - 9: bd-ib-6vhgqg, bd-ib-iud52v
- Every carrier is closed except **bd-ib-qx45e6**. qx45e6 waits on bd-ib-dpsiwz, which waits on the first sample of the
  sandbox-loss drill (livespec-dev-tooling-5wybjq). 5wybjq is recovering: its seeded relaunch passed implement, janitor
  and review, and failed only at proof_verify, on an Anthropic "Authentication required" credential error.
- A closed carrier does not discharge a plan assertion. Only the plan's own Proof of Done does: a `verified` record
  covering every non-human-attested assertion, posted after the latest `captured` record and after the 11-07
  carrier-map event, through `dispatcher.py post-plan-record`. A different session must replay what the capturing
  session captured.
- Every plan assertion is `host_captured` by default. None is declared `human_attested`.
- The release the record must name: assertions about the orchestrator are judged against this repository's release
  tags. The record must run against released artifacts installed through their normal path.

## Per-assertion status

| # | Assertion (short) | Evidence today | Still owed for the plan record |
| --- | --- | --- | --- |
| 1 | Serving gmktec base is an exact upstream tag within 30 days; the integration commit is on origin/factory-integration | All four gmktec instances serve `fabro 0.408.0-nightly.0 (d22808f)`, sha256 f3259547...057cf015 (qx45e6 read-backs, 11-12). Base tag v0.408.0-nightly.0 was published 2026-11-05T10:49:59Z, so the window runs to about **2026-12-05**. factory-integration merge 93081e09d has parents 8b82e99bb and d22808f8e. | Capture `--version` on the serving instance, the tag's publication date, and `git merge-base --is-ancestor d22808f8e origin/factory-integration`. Do it while still inside the window. |
| 2 | One Codex-adapter ImplementWorkItem dispatch on gmktec runs implement, janitor, review and pr, and its PR merges | No 0.408-era Codex-adapter run has been identified by this seat. | Find or run one. Which nodes run Codex is set by `dispatcher.acp_nodes`, an operator dial, so read the run's own adapter labels rather than the committed config. |
| 3 | A needs-human exit terminates the run, and the item is routed to blocked | Run 01M79N4E3YZX (petri :32276, d22808f) reached needs_human at 06:47Z on 11-13, ended `failed`, and livespec-dev-tooling-5wybjq went `blocked`, `blocked-reason:needs-human`. Run 01M7A2P35VZH (candidate :32278) did the same at 09:51Z. | Capture one such run's stage list and the item's ledger state together. |
| 4 | A cancelled dispatch is reported as cancelled, not as an implementation failure | No 0.408-era cancel observed by this seat. bd-ib-xdmkhf (closed 10-20) carried the behaviour. | One cancel on gmktec, on a named consenting run, and the Dispatcher's journal outcome. |
| 5 | `fabro inspect` and `fabro dump` of a gmktec run contain no resolved credential value | bd-ib-4ipmub closed 10-18. bd-ib-6tcjfx.1 (held under ruling R129) records an earlier raw-payload dump from a 0.382 client. | Run both against a disposable run, never a live canary, per R129. Scan the output by value-comparison counts only, and never print it. The dev host's PATH client is now 0.408 (d22808f), which decodes Kubernetes runs. |
| 6 | The orchestrator image bakes the serving binary digest, and the runbook names the tag and patch set | PR #5097 merged (04cd1b7c9): the image `livespec-orchestrator:fabro-v0.408-d22808f8e` (ID sha256:f854d8db...) has `/usr/local/bin/fabro` reading sha256 f3259547...057cf015. The README instance table (PR #5020) names all four instances and the carried patch set. | Capture both from a released orchestrator build. The image must be rebuilt or re-read from the release, not from the local bake. |
| 7 | The legacy 0.254 instance on hp is stopped before 2026-11-14T00:00Z, with its binary and storage kept read-only | Measured read-only by this seat at about 10:10Z on 11-13 (ssh root@hp-xubuntu). `fabro-server`, `fabro-server-candidate` and `fabro-server-mi-homelab` units are all `disabled`. `fabro-server` is `inactive`/`dead`, and no process is named `fabro`. `/home/cwoolley/.fabro`, `bin` and `storage` are `dr-xr-xr-x`, the binary is `-r-xr-xr-x`, `fabro 0.254.0 (8869e88 2026-10-16)`, sha256 199407ce...a22421. | Capture the same reads in the plan record. The deadline clause is met as of 11-13; the capture only has to show it still holds. |
| 8 | A dispatch to a factory serving a base older than 30 days is refused before claim, naming the base, its date, the newest release and the route | bd-ib-j9x closed 10-11. On 11-12 the gate's verdict read "base v0.408.0-nightly.0 is 6 calendar days behind v0.414.0-nightly.0", which admitted. A gap was recorded on qx45e6: an ordinary admit journals nothing. | A REFUSAL is needed, not an admit. Exercise it against a factory or fixture whose base is out of the window, and capture the refusal text. |
| 9 | One dispatch produces a `run_turn` record in Honeycomb `fabro` with the work-item id, the clear adapter command and a command digest, and no environment value; a concurrent legacy run does not match | bd-ib-6vhgqg closed 10-18. Not re-measured on 0.408 by this seat. | Query the Honeycomb `fabro` dataset for one named 0.408 dispatch. There is no legacy instance left serving, so the "concurrent legacy run" leg needs a ruling on how it is shown. |

## Order that keeps the clocks safe

1. Assertion 7 is already met. Assertion 1's window closes around 2026-12-05.
2. After qx45e6 closes, take the plan capture in one session, against released builds.
3. Have a separately started session replay it and post `verified`.
4. Then commission the independent completeness reviewer, and run the archive gates.
