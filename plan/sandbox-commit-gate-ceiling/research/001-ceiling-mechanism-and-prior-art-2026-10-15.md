## The maintainer's statement of what done means

Go ahead and work the tool call ceiling bug too.

## Definition of Done assertions derived from that statement

- On hp, a factory implement-stage agent's git commit whose repository commit hook runs longer than one agent tool call completes with the hook's own verdict.
- On hp, a commit completed that way carries every trailer the repository commit hook wrote, and the run publishes it without a human finishing the commit by hand.
- A factory sandbox commit leg that ends without a hook verdict is reported to the agent as having no verdict, and the agent does not treat it as a commit.

## Why this plan exists

The maintainer ruled at about 23:4xZ on 2026-10-14, in the
`gitops-fleet-capacity-monitoring` driver session: "Go ahead and work the
tool call ceiling bug too." The defect is work item `bd-ib-sufca7`: a
factory implement-stage agent can finish a verified Red-Green-Replay change
and still lose it, because the commit that records the Green half fires the
repository's pre-commit aggregate, and that aggregate outlasts one agent
tool call.

## The instance, measured

Run `01M4XWYERJEZ15GNMGHV66CSBY` on hp (item `bd-ib-5guqmt`, dispatch
`45bcb87b7f8442c18b6631b33678e24c`), read on 2026-10-15 through
`fabro dump --server https://hp-xubuntu.perch-rudd.ts.net:32276`.

- The implement stage ran from 19:09:12Z to 21:54:57Z (2h45m) against a
  node timeout of `14400s`, so the stage limit was NOT what stopped it.
- Earlier Red commits took 105 to 179 seconds each, and earlier Green
  amends took 465 s and 565 s; all completed.
- The last two `git commit --amend --no-edit` tool calls ended `failed`
  after `elapsed_ms` 1202366 and 1203117: both at about 20 minutes. The
  agent's own final message says "SIGTERMed at 14 and 20 minutes"; the
  event record contradicts the 14, so the agent's account is not evidence
  of two different limits.
- The run ended at `needs_human` with the staged tree preserved, and the
  owner session finished it by hand on the host through the detached
  runner, where the same amend took 41 minutes with hooks on.

Run `01M4TZQKSKWFWAZZ3QX6ZM3D8N` (item `bd-ib-mnuo5n`, 2026-10-13, recorded
in `bd-ib-6p7kkd`) failed its Green amend at 1202 s too. Three of three
over-limit commits ended at the same 1200-second mark.

## Where the 1200-second limit comes from

The overlay the Dispatcher materializes for every dispatch
(`commands/_dispatcher_overlay.py`, from `bd-ib-k627ja`) sets
`BASH_MAX_TIMEOUT_MS=3600000`. But this repository's committed
`.claude/settings.json` carries an `env` block with
`BASH_MAX_TIMEOUT_MS=1200000`, and the sandbox clone carries that file. The
dev-tooling runner's own header (`dev-tooling/gate-run.sh`) names the same
file as the 20-minute cap on the host side. So the probable source is the
committed project settings overriding the overlay. That is an inference:
the export does not carry the tool call's own `timeout` argument, so the
agent choosing 1200000 itself has not been excluded. The design below does
not depend on which it is.

Raising the cap is NOT the fix. The host measured 41 minutes for the same
amend under load, a fleet repository's cap is that repository's own
setting, and any fixed ceiling is outrun by a slower enough host. The
defect is that a commit's outcome depends on one tool call's patience.

## Prior art (ledger scan with `--status all`)

- `bd-ib-6p7kkd` (pending-approval): reap and NAME an over-limit implement
  commit hook. Gated on `bd-ib-svw54x` (blocked, needs-human), because no
  ACP or app-server interface exposes the tool-call limit or the moment it
  fires. Even after both land, this instance is reaped, named and lost.
- `bd-ib-xi63mq` (active): the `publish_draft` command-node half of
  Scenario 177. Not the agent's own commit legs.
- `bd-ib-k627ja` (closed): raised sandbox shell timeouts and disabled
  auto-backgrounding. The 1200 s kills above happened after it landed.
- `contracts.md` "Repository hooks that outlive a limit" and Scenario 177
  specify reaping and naming; neither specifies that the commit completes.
  That is why this plan routes a spec proposal before dispatch.

## Mechanism the host already uses

`livespec-dev-tooling`'s worktree-discipline pack ships `gate-run.sh`
(`just gate-start` / `gate-wait` / `gate-status`): the gate command runs in
its own detached session that outlives the tool call, and its run
directory is the evidence (`exit_code` is written only on real completion;
a signal death or a vanished process reads `DIED_WITHOUT_VERDICT`, never
PASSED). The same command runs with the same hooks; only the waiting moves.

The sandbox has no sanctioned equivalent. Two things stand in the way:

1. The pack is gitignored and package-installed, and it belongs to the
   dev-tooling fleet tooling; the implement workflow is the orchestrator
   plugin's own, dispatched against any adopter repository, so it cannot
   assume a target repository carries that pack.
2. Every factory prompt says "NEVER background a tool call", "do not start
   a poller ... or a loop that waits for a condition". A detached commit
   followed by re-issued bounded waits is outside that wording, even
   though the rule's purpose (nothing left running when the turn ends) is
   compatible with it.

## Direction

Give the sandbox agent a plugin-shipped detached commit leg: start the
`git commit` (Red commit, Green amend, or any later commit that fires the
hook aggregate) in its own session; wait in bounded foreground calls that
can be re-issued across tool calls; read the verdict, exit status and
resulting commit from durable files the commit process itself writes; and
treat no verdict as no commit. The prompts gain one sanctioned exception
to the backgrounding rule, scoped to that leg, with the existing
end-of-turn obligation kept: the detached commit must reach a verdict (or
be stopped) before the final message. Hooks, `--no-verify`,
`LIVESPEC_CHECK_SKIP` and every severity knob are untouched.

This lands in `livespec-orchestrator-beads-fabro` and is factory-eligible.
It is complementary to `bd-ib-6p7kkd`: with completion in place the
over-limit case should stop arising for commit legs, while reap-and-name
remains the backstop for anything not routed through the leg.

## Side finding

The committed `.claude/settings.json` 1200000 ms cap silently defeats the
overlay's 3600000 ms in this repository's sandboxes. It is recorded here
because it is the measured source of this instance; it is not this plan's
fix and is reported to the driver rather than folded in.
