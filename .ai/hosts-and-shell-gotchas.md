# Hosts and shell gotchas: where this checkout runs and how to reach the factory

Facts about the machines this repository is operated from and the shell on
them, each of which has produced a confident wrong answer ("I cannot reach
hp", "fabro is not installed", "no such file"). Migrated from Claude Code
auto-memory notes on 2026-10-18 (plan `block-auto-memory-coverage`); dates are
those of the original measurement.

## The primary checkout runs ON the vps host

The `/data/projects/livespec-orchestrator-beads-fabro` primary checkout runs on
the `vps` host itself: `hostname` is `vmi3006760` (re-measured 2026-10-18) and
the tailscale `Self` node is `vps.perch-rudd.ts.net`. The other factory host,
`hp-xubuntu`, is the remote one. (vps is a retired factory per AGENTS.md
§"Host Fabro server", but it is still the machine this checkout runs on.)

`ssh root@vps` from here returns `Permission denied (publickey)`, as do
`thewoolleyman@`, `ubuntu@` and `cwoolley@`, which reads as missing access
rather than as a loopback. `tailscale status` lists the local node first, with
no connection descriptor, so its row looks exactly like an idle peer. Measured
2026-08-22 during the `factory-host-storage-reclamation` spike
(`bd-ib-bdcmok.1`). Measure and act on vps LOCALLY; ssh only to hp. A bare
`fabro ps` on this host queries the LOCAL server, so always pass `--server` for
the factory you mean.

## Reaching the hp factory host

`ssh root@hp-xubuntu.perch-rudd.ts.net` works, and so does
`ssh cwoolley@hp-xubuntu…` (BatchMode), which can also run `docker inspect` and
`docker cp` against sandbox containers (measured 2026-10-08 on the stopped
container of run `01M4CTSW4J48Y7H0MK7VZFF2ZD`). Other users are refused, and
the two refusals look different:

- `ubuntu@` gives `tailscale: failed to look up local user "ubuntu"`.
- `thewoolleyman@` and `chad@` give
  `tailscale: tailnet policy does not permit you to SSH as user "<name>"`.

Both close the connection immediately, so guessing the obvious username reads
as "hp is unreachable". Measured 2026-08-22; it cost three attempts.

The Fabro binary on hp is `/home/cwoolley/.fabro/bin/fabro`, NOT
`/root/.fabro/bin/fabro`, because the `fabro-server` service runs as
`cwoolley`. `ssh root@… '~/.fabro/bin/fabro --version'` therefore returns "No
such file or directory", which reads as "fabro is not installed". Use the
cwoolley path, or query the server over its API.

## `fabro system prune` exists; declarative retention does not

The pinned Fabro build exposes `fabro system prune` ("Delete old workflow
runs"), `fabro system df` and `fabro system info` under the `fabro system`
group (re-measured 2026-10-18 against `~/.fabro/bin/fabro system --help`).
`prune` is dry-run by default (`--yes` acts), takes `--older-than`, `--before`,
`--workflow`, `--label` and `--orphans`, and accepts `--server`, so one caller
prunes a remote factory without logging in to it. There is no declarative
retention or TTL configuration (checked 2026-08-22 against
`fabro settings --json`, every on-disk `~/.fabro/*.toml`,
`fabro server --help`, and the source at `v0.310.0-nightly`).

Ledger item `bd-ib-il35` records the opposite (that no prune or gc subcommand
exists and `fabro rm` by id is the only route). That scan missed it because
`fabro --help` lists the parent only as `system  System maintenance commands`,
a line containing none of "prune", "gc" or "retention". To answer "does this
CLI have subcommand X", expand each subcommand's own `--help`; never grep only
the top-level index. Never write a bespoke reaper for Fabro run state; schedule
`fabro system prune --server <factory>`. Size it first: the whole Fabro storage
layer measured about 430 MB on vps and 220 MB on hp (2026-08-22), and a 7-day
prune reclaimed about 104 MB, so it is a correctness concern, not a capacity
one.

## Interactive aliases break command substitution

In this host's interactive zsh, `ls` is aliased to `lsd --inode --long --all`,
`cat` to `bat`, and `grep` to `rg` (re-measured 2026-10-18). The `ls` alias
prints inode and permission columns even when piped, so `f=$(ls dir/*.md | head
-1)` captures a whole metadata row rather than a path, and the next command
fails with `can't read 30935546 .rw-rw-r-- …: No such file` (measured
2026-09-06). The `grep` alias returns nothing on files it judges binary (see
`.ai/factory-dispatch-preflight-and-triage.md` on `output.log`).

In scripts and command substitutions, use `find <dir> -maxdepth 1 -name
'*.md'`, a literal path, `command ls`, `/bin/cat` or `/usr/bin/grep`. Never
read the first token of an `ls` listing as a filename.
