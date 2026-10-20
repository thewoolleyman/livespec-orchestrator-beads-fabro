# GitOps deployment: this repository's own deploy surface

Read this BEFORE any deployment, Ansible, GitOps, host-provisioning, `kubectl`,
or ssh-to-a-fleet-host action in this repository.

The fleet-canonical rules are in livespec `.ai/gitops-deployment-discipline.md`
— six of them — and they bind here unchanged. Read that file for all six and for
the failure each one answers. This file carries only this repository's own LAYER
MAP: which committed artifact deploys which file onto a fleet host, and from
where. It is this repository's slice of livespec work-item `livespec-tf27wm`
(child C7 of livespec plan `gitops-deployment-instructions-and-enforcement`,
epic `livespec-okypgg`).

## The two rules to carry into every host action here

**A live fleet host is never changed by hand.** A deploy is a change to git
followed by the committed apply. A needed hand change is a gap in the
automation to fix — "this has to be done by hand on the host" names that gap,
and closing it is the response. It is never a task to hand the maintainer, and
never licence for an improvised privileged command. Three of the four
installers below sit in exactly that state today, and each is recorded as a gap
rather than as a procedure to repeat.

**ssh to a fleet host is for READ-ONLY verification only** — reading a unit's
status, a file's content, a process list. It is never how a change is made. The
Driver's fleet-host mutation guard enforces the mechanical half of this: when it
denies you, the denial is correct, and the remedy is to find or write the
committed path, never a command shape the guard fails to recognise.

## The layer map — every in-repository installer, and what runs it

| Installer | What it installs | What runs it on a fleet host |
| --- | --- | --- |
| `bd-guard/install.sh` | the `bd` lifecycle guard at `/usr/local/bin/bd` | NOTHING — hand-run; a gap |
| `dev-tooling/install-ci-fabro.sh` | a pinned `fabro` inside the CI runner | the committed CI workflow; no fleet host |
| `orchestrator-image/services/reconcile-runs/install.sh` | the `reconcile-runs` root system timer | NOTHING — hand-run; a gap |
| `orchestrator-image/services/work-supply/install.sh` | the `work-supply@` root system timer, per tenant | NOTHING — hand-run; a gap |

Measured 2026-10-20: no role or play in `livespec-dev-tooling` `ansible/` — the
tree that provisions the legacy Ubuntu fleet, `vps` and `hp-xubuntu` included —
names `bd-guard`, `reconcile-runs` or `work-supply`. So for those three there is
no apply path and, per rule 5, no drift report can exist either: a host no
playbook covers is invisible to both `just ansible-apply` and
`just ansible-drift`, and an empty report about such a host means nothing.

### `bd-guard/install.sh` — nothing deploys it

Installs this repository's tracked `bd-guard.sh` as `/usr/local/bin/bd` and
relocates the real beads binary to `/usr/local/bin/bd-real`, which is the policy
boundary AGENTS.md §"Beads runtime prerequisites" requires every `bd` call to
resolve through. `rollback.sh` reverses it.

Its own header says it is "a HOST MUTATION and is deliberately NOT executed by
the test suite or CI", and its README that "a maintainer runs them explicitly" as
`sudo bd-guard/install.sh` from a checkout on the host. That is the gap: the
installer is idempotent and recreatable, so it is ready to be APPLIED by
something, and nothing applies it.

### `dev-tooling/install-ci-fabro.sh` — the committed CI workflow runs it

This one deploys to no fleet host at all. `.github/workflows/ci.yml` runs
`just install-ci-fabro`, which runs the script, which installs the pinned,
sha256-verified upstream `fabro` v0.254.0 musl release at `/usr/local/bin/fabro`
so `check-fabro-graph-validity` can resolve it. The target is the EPHEMERAL CI
runner, rebuilt per job, not a machine whose state anyone converges — so there is
no host here to drift, and rules 2 through 5 have no surface to bind to.

The committed workflow is the mechanism, which means a change to WHEN or HOW this
runs lands in `.github/workflows/ci.yml`. A factory branch never creates or
updates a file under `.github/workflows/`: restore it to master's content,
publish the rest, and report the dropped diff for maintainer-side landing
(`.ai/git-pr-and-release-mechanics.md`).

### `orchestrator-image/services/reconcile-runs/install.sh` — nothing deploys it

Writes the committed `reconcile-runs.service` and `reconcile-runs.timer` text
into `/etc/systemd/system` (overridable via `UNIT_DIR`) and runs `systemctl
daemon-reload` plus `enable --now`, so the installed artifact is a ROOT system
timer. It reconciles every declared factory's non-terminal run inventory against
the ledger on the interval the timer carries, which is what closes the window a
drained dispatch queue leaves open.

Its README states it outright: "Installing it on a host is a separate operator
action; nothing in this repository installs it" — `sudo ./install.sh --repo
/data/projects/livespec-orchestrator-beads-fabro`. The unit TEXT is committed, so
rule 3's layer already exists in git; what is missing is the applier.

### `orchestrator-image/services/work-supply/install.sh` — nothing deploys it

Same shape, one timer INSTANCE per tenant repository: it writes the committed
`work-supply@.service` and `work-supply@.timer` into `/etc/systemd/system` and
enables `work-supply@<instance>.timer`. Each firing starts one ordinary
unattended drain pass, governed by every admission condition unchanged.

Its README carries the identical sentence — nothing in this repository installs
it — and the invocation is `sudo ./install.sh --repo <tenant> --interval 30min`,
once per tenant. The per-tenant instancing is part of the gap: the set of tenants
a host supplies is desired state nothing declares.

## What is NOT this repository's deploy surface

The host Fabro server this repository dispatches runs to is owned elsewhere: its
canonical unit and installer live in `thewoolleyman/fabro-hosts` at
`services/fabro-server/`, and `livespec-dev-tooling` `ansible/fabro-hosts.yml`
is the play that applies them to `hp-xubuntu` and `vps`. Do not change the
factory's unit, its environment file, or its pinned binary from here — a change
made only to a copy that nothing applies has changed nothing on any host, however
correct it is (rule 3). The pinned `fabro` build and the rollback commands are
documented in `orchestrator-image/README.md`; rolling one out is still a change
to the owning repository followed by that play.

## Closing one of the three gaps

The fix is not to run the installer again. It is to move the install into the
layer that APPLIES — a role in `livespec-dev-tooling` `ansible/`, reached by the
play that already targets the host (`dev-host.yml` for `vps`, `fabro-hosts.yml`
for the factory pair) — rendering from the unit text this repository already
commits, so the two repositories keep one source each rather than two copies of
one file. Then retire the shell installer per rule 4: delete it and cite its
pre-deletion commit, because two layers that both look like the installer for the
same file will be edited in the wrong order.

Until a gap is closed, verification of those three is per-service and local, not
a drift report:

```bash
systemctl list-timers reconcile-runs.timer --no-pager
journalctl -u reconcile-runs.service -n 50 --no-pager
```

A green repository is never proof that a host matches it.
