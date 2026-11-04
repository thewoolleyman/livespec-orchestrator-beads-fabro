# Independent implementation re-review (Fable, round 2) — `lan_ssh_fallback` at `d362168f`

Reviewed: `git -C /home/ubuntu/.worktrees/livespec-dev-tooling/lan-ssh-fallback diff
1ae298ae d362168f` plus a full read of the revised `tasks/server.yml`,
`tasks/verify.yml`, `lan-ssh-fallback.yml`, `defaults/main.yml`, `HOST_VARS.md`
and every template, against the round-1 review
(`ssh-impl-review-fable.md`). Same rules as before: nothing on any host,
repository or ledger changed; no ansible against hosts. Local checks run:
`ansible-playbook --syntax-check` and `--list-hosts -e
lan_ssh_fallback_only=hp-xubuntu` (no host contact), `ansible-lint`
(production profile, clean), `/usr/sbin/sshd -G` on the control node against
the new address-bound drop-in, a Jinja2 render of the templates with
`trim_blocks=True`, and `ansible localhost -m debug` evaluations of every new
expression (the one-host gate, the proven-hosts and alias sets for the full
and one-host cases on vps and on a home-lab host, the `needs_activation`
listener comparison for the empty / port-22 / converged cases, and the
cordoned-node regex). The `.ansible/` cache directory my own lint run created
in the worktree was removed; `git status` is clean.

Verdict: every round-1 finding is closed, and the fixes introduce no
regression that would fail a converge on a correct host or reach Tailscale,
`/etc/ssh/ssh_host_*`, routes, interfaces or k3s. One ordering hazard remains
that will bite within weeks, not today, and a few comments were left stale by
the binding change.

## BLOCKER

None.

## Round-1 findings, disposition

- **B1 (own drop-in refused)** — closed. `tasks/server.yml:135` now rejects
  `[lan_ssh_fallback_dropin, lan_ssh_fallback_auth_dropin]`.
- **B2 (`--limit`)** — closed. Plays stay on groups; `-e
  lan_ssh_fallback_only=<host>` is validated at `lan-ssh-fallback.yml:39-43`
  and gates the `include_role` at `:48`. Measured: with `-e
  lan_ssh_fallback_only=hp-xubuntu`, `--list-hosts` still shows 3/1/3/4/4
  hosts for the five plays, so plays 1-2 set every hostvar the templates index.
  Evaluated: unset → `'' in [''] + home_lab` true and runs on every host;
  `hp-xubuntu` → runs on hp only; `vps` → refused by the assert. Operator
  precedence (`| default('')` binds before `in`, `+` binds before `in`) is
  what the author intended; verified by evaluation, not by reading.
- **S1/S4 (BindToDevice vs ARP flux; boot ENODEV)** — closed by returning to
  address binding. `templates/00-lan-fallback.conf.j2:10` renders
  `ListenAddress 192.168.1.4:22022` (rendered and checked); `sshd -G` against
  that exact drop-in prints `listenaddress 192.168.1.4:22022` and nothing
  else, which is what `tasks/server.yml:360-362` asserts. The Ubuntu generator
  (`listen_addr_is_default`) treats any non-`0.0.0.0`/`::` address as custom,
  so `ssh.socket`'s `Listen=` becomes exactly `192.168.1.4:22022 (Stream)`,
  which `:474-481` and `tasks/verify.yml:104-111` assert. The socket drop-in
  and `lan_ssh_fallback_socket_dropin` are gone from code and defaults; the
  `FreeBind=yes` the packaged unit carries covers a lease absent at boot.
- **S2 (`nc -w 30` idle kill)** — closed: `templates/ssh_config.j2:26` is
  `nc %h %p`.
- **S3 (first drift red)** — closed: `tasks/verify.yml:80-114` gates the
  listener read and assert on the role's drop-in existing, and the `when` list
  short-circuits on `inventory_hostname in groups['home_lab']` before touching
  the registered `stat` on vps.
- **S5 (docs)** — closed in `HOST_VARS.md` (variables table, preseed scope,
  `--limit`, rollback meaning).
- **N1 (listener flap)** — closed by `lan_ssh_fallback_needs_activation`
  (`tasks/server.yml:198-209`): evaluated as false for a converged host
  (`192.168.1.4:22022 (Stream)` and unchanged drop-ins), true for an empty
  `Listen` (hp before install), for the packaged `0.0.0.0:22 / [::]:22`, for
  a changed drop-in, and for a present off switch — so an abandoned apply's
  off switch is recovered by the next apply. Hold/inert/activate are all
  gated on it; the install block is still gated on `pinned_present`.
- **N2** — closed (`tasks/server.yml:407-417` rescue message). **N5** —
  closed: evaluated alias set on vps for the full run is the nine aliases the
  rendered config carries (three `-lan`, six `-lan-via-`), and for
  `lan_ssh_fallback_only=hp-xubuntu` it is `hp-xubuntu-lan`,
  `hp-xubuntu-lan-via-gmktec-xubuntu`, `hp-xubuntu-lan-via-poweredge-xubuntu`
  — the jumps need only Tailscale SSH, so a one-host first apply is provable.
  On hp itself the set is empty, on poweredge it is the two `-lan` peers.
  **N6** — closed (`\sReady(\s|,)` accepts a cordoned node; `~/.ssh` ensured
  at `tasks/keys.yml:47-53`).

## SHOULD-FIX

### S1. The exact version pin will fall behind the archive on the next openssh security update, and when it does the role touches the off switch BEFORE the fence refuses

Not a regression — round 1 had the same order — but `needs_activation` now
makes the consequence sharper, so it is worth fixing while the file is open.
Sequence on a converged host after unattended-upgrades (enabled on all three
hosts, `20auto-upgrades`) has moved openssh to the next security release:

1. `tasks/server.yml:104-107` — `pinned_present` is false (installed ≠ pin).
2. `:198-212` — `needs_activation` is therefore true and **the off switch is
   created** while the socket keeps serving.
3. `:276-281` — `apt-get -s install openssh-server=1:10.2p1-2ubuntu3.8 ...`
   fails: the pinned version is no longer in the lists (`E: Version ... was
   not found`), or is present and reads as a downgrade the apt module (which
   passes `-y` without `--allow-downgrades`) would refuse. The `block` has an
   `always` but no `rescue`, so the play stops here with no message.
4. The host is left converged-but-armed: the off switch sits on disk, and the
   next reboot or the next openssh upgrade's preinst/postinst pair leaves
   `ssh.socket` condition-skipped — the fallback goes dark on the next event,
   on every home-lab host the apply reached, with nothing in the output
   saying so.

Under `--check` the same simulation runs (`check_mode: false`) and the drift
report goes red every day after that update, which is probably the first
anyone would hear of it — but the apply path is the one that arms the switch.

Fix, in order of preference: (a) move the fence (`:239-308`, simulation and
refusal) ahead of `Hold OpenSSH off` so a refused transaction never touches
the switch; or (b) make `pinned_present` accept an installed version that is
**newer** than the pin (`dpkg --compare-versions` per package, or
`version(...)` tests) so a security update that unattended-upgrades already
applied does not count as drift, and keep the exact pin only as a floor; or
(c) at least give the install block a `rescue` that removes the switch it
created when nothing was installed. (a) is a pure reorder and is sufficient;
(b) is what makes the role survivable as a standing gitops role.

## NOTE

### N1. Comments and host_vars text still describe device binding

Left behind by the S1/S4 change; none affects behaviour.

- `ansible/inventory/host_vars/{poweredge,hp,gmktec}-xubuntu.yml`
  (`:14`, `:126`, `:14`): "OpenSSH binds the WIRED interface by device
  (BindToDevice), so a DHCP lease change cannot strand the listener" — now
  the opposite is true (an address-bound listener with `FreeBind` silently
  binds a departed lease; the per-run interface check at
  `tasks/server.yml:69-86` is what catches it). These files say they are
  generated from `HOST_VARS.md`, whose YAML block carries no such comment, so
  the next regeneration will drop it anyway; until then it misleads.
- `tasks/server.yml:3` "LAN addresses"; `:76-79` "the listener is bound by
  device and survives a lease change".
- `HOST_VARS.md:162` "bound to the interface".

### N2. Confirmed-correct points for the revision

- `sshd` accepts `Port 22022` before `ListenAddress addr:22022` (the
  explicit port makes the ordering moot anyway); `-G` output verified
  locally.
- `tasks/verify.yml:8-25`: `product`, `map('join', ...)`, the backreference
  `^(.*)-lan-via-\1$` through YAML plain-scalar and Jinja string escaping,
  `regex_replace('$', '-lan')` (appends exactly once), and `ternary` with an
  eagerly evaluated unused branch all evaluate correctly; both set_facts are
  check-mode safe.
- `lan-ssh-fallback.yml:48` attaches the `when` to every task of the
  included role, including the `delegate_to: localhost` keyscan, so a
  non-targeted host does nothing in play 3 under `lan_ssh_fallback_only`.
- `gather_facts: false` on play 5 is fine: `verify.yml` uses only magic vars
  and registered results.
- The poweredge flow is unchanged in substance: first run upgrades 3.6 → 3.8
  inside the fence (preinst stops both units, postinst's socket restart is
  condition-skipped), inert checks pass with nothing on 22022, activation
  releases and restarts, `ssh.service` is restarted because a PID was
  recorded. On the hp/gmktec fresh-install flow nothing changed except the
  address-bound `ListenAddress`.
- The rescue at `:520-544` remains reachable only from the activation block,
  as documented; the inert block's new rescue (`:407-417`) only reports.
- `ansible-lint` passes; syntax check passes; the worktree is clean.

REVIEW-COMPLETE: NO-BLOCKERS
