# Plugin cache leases and rebinding a running session

This note records how a Claude Code plugin cache build tracks the sessions bound
to it, what actually rebinds a running session onto a newer build, and the one
observation that reads as proof of rebinding while being nothing of the kind.

It exists because none of it is derivable from `AGENTS.md`. That file already
carries the CONSEQUENCE — the trap entry "A long-lived session dispatches through
the plugin build it STARTED with, not the build its repository resolves", and
`bd-ib-97v4`, which records that the update remedy cannot move a running session.
Neither says how to OBSERVE which build a session is bound to, and an operator
who cannot observe that cannot tell a genuine factory outage from a stale-build
session reporting one.

Everything below was measured on 2026-09-10 while working the `fix-plugin-install`
incident (plan epic `bd-ib-uy4lp7`).

## The `.in_use` lease directory is the binding instrument

Each plugin cache build directory carries an `.in_use` directory. It holds one
file per session that has bound that build, named by the holding process id and
containing that pid together with that process's start time.

That directory is the reference mechanism that makes a cache build safe or unsafe
to remove, and it is the instrument for the question an operator actually has:
**is any live session still bound to this build?** The pid plus start time is what
makes the answer trustworthy — a bare pid can be recycled onto an unrelated
process, and the recorded start time is what discriminates the original holder
from a later occupant of the same number.

Nothing else on disk answers that question. A registry entry records which build
is CURRENT, not which build any given session is USING, so a registry read is a
different question wearing the same words.

## A running session binds its plugin root once at session start

A running session binds its plugin root once, at session start. Neither a
registry update nor the SessionStart hook re-points a session that is already
running.

The consequence is the expensive part: a fleet-wide plugin update can leave live
sessions dispatching an OLDER build while every on-disk record looks correct. The
registry says the new build. The cache holds the new build. The update command
reported success. And the session in front of you is still executing the old one,
with nothing in its own output announcing the divergence. That is why the
`AGENTS.md` trap entry exists, and why a failure originating in a stale session
presents as a factory-wide outage.

## The supported in-place rebind is a human-typed plugin reload

A human-typed plugin reload is the supported in-place rebind, and it does
genuinely rebind — it is not merely a refresh of plugin definitions with the old
binding left in place.

That distinction was not assumed; it was established by LEASE OWNERSHIP. New
lease files appeared under the new build's `.in_use` directory immediately after
the reload. The other supported remedy remains restarting the session, which
binds afresh by construction.

"Human-typed" means typed at the session's own prompt, not typed by the
maintainer. A session running in a herdr pane can rebind itself, but NEVER by
typing into its own pane while its turn is still running. Measured 2026-10-12:
`send-text "/reload-plugins"`, `send-keys enter`, `send-text "<follow-up>"`,
`send-keys enter`, all sent mid-turn, left ONE line in the input box,
`/reload-plugins <follow-up>`. Neither Enter submitted anything; the two texts
were joined into one slash command whose follow-up became its arguments; and the
session then sat idle until the maintainer pressed Enter. Every herdr call exited
0, so nothing reported the failure.

The working form hands the keystrokes to a detached waiter that acts only once
the pane is idle, and it puts the slash command and the follow-up prompt in
separate submissions:

```bash
pane=$(herdr pane current | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
mise exec -- just gate-start -- sh -c "
  herdr agent wait $pane --until idle --until done --timeout 600000 &&
  herdr pane send-text $pane /reload-plugins && herdr pane send-keys $pane enter &&
  sleep 5 &&
  herdr agent prompt $pane 'Plugins reloaded; confirm the rebind by lease, then <next step>.'"
```

Resolve the pane with `herdr pane current`, as above, and never with
`$HERDR_PANE_ID`. That variable can carry a stale id that no herdr agent
command resolves. Measured 2026-10-14: in the `agent-session-stall-prevention`
session it read `w1:pF`, `herdr agent get w1:pF` returned `agent_not_found`, and
`herdr pane current` returned the real pane `w2H:p6`. A waiter armed with the
stale id polls normally and fails only at the wake, when nothing is left to
notice it. Before arming any self-wake, confirm the target with
`herdr agent get <pane>` and check that `terminal_title_stripped` is your
session name.

Then end the turn with no further tool calls; the waiter fires once the turn
ends. `herdr agent prompt` is the submit verb, and it refuses a blocked agent
instead of silently appending to its input. After resuming, read the pane
(`herdr pane read <pane> | tail`) to confirm the input box is empty, and confirm
the rebind by lease ownership as below. Never report a plugin reload as a task
only the maintainer can do. (Maintainer corrections, 2026-10-11 and 2026-10-12.)

## The trap: an update that failed reads as one that had nothing to do

Before a reload, make sure the update actually moved the registered install.
`claude plugin update` refreshes the marketplace from GitHub first. When that
fetch fails, the command still prints `already at the latest version (<old id>)`,
followed by a trailing `Warning: marketplace not refreshed`. It reads like
"nothing new was released", but it means "I could not look". The OLD build stays
registered, so a reload after it rebinds the stale build, and the lease you then
confirm belongs to the wrong build.

Measured 2026-10-14 by three sessions during the v0.196.15 rollout. In one case
the cause was a collision with another session's concurrent refresh: the HTTPS
clone found `~/.claude/plugins/marketplaces/<marketplace>..clone` already present
(it was gone seconds later), and the SSH fallback then failed on `publickey`.
The others saw transient GitHub fetch failures on both attempts. Running
`claude plugin marketplace update <marketplace>` again and then repeating the
plugin update succeeded each time.

The discriminator is the registered build id, not the command's message. After
the update, read this project's entry in `~/.claude/plugins/installed_plugins.json`
and confirm its build id equals the release you expect. Arm the reload only after
that; then confirm the rebind by lease, as below.

A second failure shape: the registered id matches the release, but the cache
copy is TRUNCATED. Measured 2026-10-16 on v0.201.8 (build `be31d5181296`):
`skills/` held 2 of 14 directories and there was no `cache-manifest.json`,
while `scripts/` was complete; the likely cause was many sessions reloading at
once around 07:54Z. After a reload onto such a copy the session's skill list
shrinks (38 to 26 in that instance). So before reloading, also compare the
cache's `skills/` with `git ls-tree <tag> .claude-plugin/skills` and check
that `cache-manifest.json` is present. During a fleet-wide rollout, rebind one
session at a time, at least 30 seconds apart, after the release owner has
verified the build (freeze-driver ruling R39). Migrated from an auto-memory
note on 2026-10-18.

## The trap: a stale lease file is not evidence of current binding

**The old lease file under the previous build is NOT removed on rebind.**

So a lease file's PRESENCE is not evidence of current binding. Only the NEW
build's lease directory discriminates, and checking a single directory yields a
confident wrong answer in either direction:

- Look only at the OLD build and find a lease for your pid: you conclude the
  session is still stale, and re-run a remedy that has already worked.
- Look only at the NEW build and find nothing yet: you conclude the reload did
  not take, and escalate a rebind that may simply not have happened yet.

Read BOTH directories, and treat the presence of a lease under the new build as
the positive signal. A leftover lease under the old build is expected debris, not
a finding.

The reload's own terminal confirmation line is likewise a PROXY and must not be
accepted as proof of rebinding. It reports that the command ran, which is a
different claim from "this session is now bound to the new build" — the same
shape as the catalogued "instrument that cannot return a hit" family in
`AGENTS.md`, one level on. The lease directory is the measurement; the
confirmation line is the announcement.

## There is no supported eviction verb for a stale cache build

There is no supported command that evicts a stale plugin cache build. The plugin
prune verb is not it: it removes auto-installed dependencies only, so reaching
for it to reclaim a superseded build is an instrument aimed at a different
population, and it will report success having done nothing to the build you meant.

Practically, that means a superseded build persists until something removes it,
and the `.in_use` directory is what tells you whether removing it is safe. Do not
improvise an eviction against a build whose lease directory you have not read.
