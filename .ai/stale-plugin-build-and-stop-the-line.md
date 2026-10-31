# Stale plugin builds and stopping the line for breakages

Moved word for word from `AGENTS.md` §"Beads runtime prerequisites" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

**A long-lived session dispatches through the plugin build it STARTED with, not
the build its repository resolves — and the failure reads as a factory outage.**
A Claude Code session binds `CLAUDE_PLUGIN_ROOT` once, at start. `claude plugin
update` and the SessionStart hook move the registered install underneath it,
and nothing re-points the running session except a restart or a human-typed
`/reload-plugins` (`bd-ib-97v4`: the update remedy cannot move a running
session). Measured 2026-09-06: the `overseerd` session, started 2026-09-03,
dispatched `overseer-qt3wvu.1` through cache build `d709f27ac3c1` (v0.124.1,
2026-08-31) — the one installed build that templates the sandbox prepare steps
(`39526e5c`) but predates the host-side substitution fix (`79066c79`,
`bd-ib-8atx`, released v0.124.3 on 2026-09-04) — while livespec-overseer's
registered install was already v0.129.1. The run died at setup command index 1
on a literal template opener, exit 127, and the session recorded "the whole
livespec-overseer lane is down" on the ledger; hp had completed four
livespec-overseer runs that same day. The discriminator is the SUDO JOURNAL,
which records the full `drive.py` / `dispatcher.py` path and therefore NAMES
the build (journal timestamps are local, +02:00 against a run's UTC):

```bash
journalctl --since "<t1>" --until "<t2>" -o short-iso _COMM=sudo | grep -E 'drive.py|dispatcher.py'
git merge-base --is-ancestor <fix-sha> <cache-hash> && echo fixed || echo NOT-fixed
```

The dispatcher now journals a `dispatcher-registered-install-lag` warning when
the executing build is older than the target repository's registered install
(`_dispatcher_registered_install_currency.py`). It is surfaced, never enforced,
per the ratified currency contract, so READ the dispatcher stderr the `drive`
result carries before concluding anything about the factory. The remedy brings
the SESSION onto the current build and dispatches on the NORMAL path: restart
the session, or issue a human-typed `/reload-plugins` — either rebinds it
afresh (confirm the rebind by lease ownership per
`.ai/plugin-cache-lease-and-rebind.md`, not by the reload's confirmation line).
"Human-typed" means typed at the session's own prompt, so a session in a herdr
pane does this ITSELF and never asks the maintainer to; follow that file's
detached-waiter form exactly, because typing into your own pane mid-turn
stalls the session.
Do NOT keep your own work moving by invoking the registered build's
`scripts/bin/` entry point by explicit path, or otherwise routing a live
session around the stale build: that normalizes the outage and validates only
your private path, never the one every other session dispatches through —
§"Stop the line for breakages" below governs. To REFUSE a known-broken build
range outright before it can execute, commit a `dispatcher.minimum_release`
floor in the target repository's `.livespec.jsonc` through the ordinary release
path. Second-order trap, same incident: the failure write-up quoted the literal
opener into the item's own comment, which is exactly the poisoning case above —
file such a failure with the U+27E6 / U+27E7 substitution, never verbatim.

**Stop the line for breakages.** When shared factory or fleet tooling is
BROKEN — a bad model/adapter config, a stale-but-fixable plugin build a session
dispatches through, a mint/credential outage, or a gate wedged by a defect —
HALT, fix the root cause or notify its owner and WAIT for the fix, and resume
only on the NORMAL path once the fix rolls out through the ordinary channel
(release → `ensure-plugins` → reload → normal dispatch). Never pin a build,
re-route to another factory, or otherwise route around a breakage to keep your
own work moving: a broken-window workaround normalizes the outage, hides it from
a real fix, and validates only your private path, not the one every other
session and fleet member uses. A transient — a rate-limit window that resets, an
intermittent ENOSPC — is waited out and retried on the normal path; a permanent
tool limitation is designed within — neither is a bypass. The stale-build trap
above is the canonical instance: rebind the session (restart or
`/reload-plugins`) rather than invoke a fixed build by explicit path to sidestep
the stale one. Fleet source: the livespec `agent-disciplines.md` discipline
§"A factory or tooling BREAKAGE stops the line" (maintainer ruling 2026-09-10).
