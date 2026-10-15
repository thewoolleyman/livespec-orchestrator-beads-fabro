# Independent review: `lan_ssh_fallback` dpkg-lock wait (pgrep -> fuser)

Reviewer: Fable 5.1, read-only. Worktree reviewed:
`/home/ubuntu/.worktrees/livespec-dev-tooling/fix/lan-ssh-fallback-dpkg-lock-wait`
(branch `fix/lan-ssh-fallback-dpkg-lock-wait`, one modified file:
`ansible/roles/lan_ssh_fallback/tasks/server.yml`). The whole role, its
templates, `HOST_VARS.md` and `ansible/lan-ssh-fallback.yml` were read. No
remote host was touched; every measurement below was taken on the control node
(vps: apt 3.1.6, psmisc 23.7-2ubuntu1, openssh-server 1:10.0p1-5ubuntu5.4,
unattended-upgrades 2.12ubuntu4, ansible-core 2.21.4) or by reading local
sources of the same packages the targets run.

## Verdict in one paragraph

The fix is correct, complete for its purpose, and fail-safe in both failure
directions. The load-bearing part of the change is `become: true`, not the
switch from `pgrep` to `fuser`: measured here, a non-root `fuser` on a file
whose fcntl lock is held by a root process exits 1 (invisible) while the same
call as root exits 0, so a root-less `fuser` loop would have false-cleared
instantly on every run. The change carries `become: true`, so that trap is
closed. Nothing in the change can alter host state in a drift run or under
`become`. I found no blocker in the rest of the role; the remaining findings
are hardening recommendations, ranked below.

## 1. Is the fix correct and complete?

### What the new command is, exactly

The folded YAML renders to one line (parsed with PyYAML; bash `-n` clean):

```
for i in $(seq 1 120); do fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock >/dev/null 2>&1 || exit 0; sleep 5; done; exit 1
```

All four continuation lines sit at the same indentation, so no "more-indented"
literal newline sneaks in. The dropped `set -o pipefail` was only needed for the
old pipe and nothing now pipes.

### Why the old task could never clear (confirming the diagnosis)

`pgrep -x` matches the full 15-byte `comm`. `unattended-upgrade-shutdown
--wait-for-signal` is a permanent resident on every Ubuntu host with
`unattended-upgrades` (it holds a logind delay inhibitor; measured: its source
takes no apt or dpkg lock while idle) and its comm truncates to
`unattended-upgr`, identical to a real run. The old wait therefore matched a
process that never exits and burned its full 600 s on every host. The new wait
asks the question the install actually cares about (is a lock held), not a
proxy for it.

### Can it false-clear?

The instrument is fd-based: `fuser` reports a process that has the file open.
apt, dpkg and python-apt open a lock file and keep the fd open exactly as long
as the fcntl lock is held (on a failed lock they close it at once), so "fd open"
and "lock held" coincide for every package-manager path that matters:

- `unattended-upgrade` (both the `apt-daily-upgrade` run and the `apt-daily`
  `--download-only` run) calls `apt_pkg.pkgsystem_lock()` immediately after its
  startup checks (`/usr/bin/unattended-upgrade` line 2658) and holds
  `lock-frontend` for the whole run; `pkgsystem_unlock_inner` /
  `lock_inner` (lines 818, 827) only release the inner `/var/lib/dpkg/lock`
  while dpkg runs, and dpkg itself holds that file. So there is no gap between
  unattended-upgrade phases, including MinimalSteps package-by-package runs.
- `apt-get -d dist-upgrade` holds `lock-frontend` while downloading, and the
  `archives/lock` during fetch.
- `apt-get update` holds `/var/lib/apt/lists/lock`.

Residual false-clear windows, both real and both small:

1. The few seconds between a package-manager process starting and its lock
   call (python imports, cache load).
2. Between phases of `/usr/lib/apt/apt.systemd.daily` (after `apt-get update`
   releases `lists/lock` and before the download step takes
   `lock-frontend`). The script itself holds `/var/lib/apt/daily_lock` on fd 3
   for its entire run (lines 325-327; the child is re-exec'd with `3>&-` but
   the parent keeps it). Adding `/var/lib/apt/daily_lock` to the `fuser`
   list closes this window for free. Recommended; not required.

Do these windows matter given what follows? Read the sequence: the timers are
already stopped (so no NEW apt-daily / apt-daily-upgrade job can start; an
in-flight one continues), then the wait, then `apt-get -s install
--no-install-recommends --no-remove` which runs WITHOUT `become`, i.e. as the
connection user. Measured locally: non-root `apt-get -s` works (rc 0, prints
the "NOTE: This is only a simulation!" banner, which matches neither `^Inst `
nor `^Remv `) and takes no lock at all, so a false-clear cannot make the
simulation collide with anything. The install then goes through the `apt`
module with `lock_timeout: 600`, which the module passes as
`-o DPkg::Lock::Timeout=600`, so the real transaction waits on the kernel's
lock regardless of what the wait concluded. The worst case of a false-clear is
therefore: an upgrade that was starting up slips in between the simulation and
the install. Consequences, enumerated:

- It upgrades unrelated packages: the real transaction is resolved afresh by
  apt and would not need to remove anything because of that, but see finding
  3.2 below, because the real transaction does not carry `--no-remove`.
- It upgrades openssh on poweredge to exactly the pin: the install becomes a
  no-op; fine.
- It upgrades openssh past the pin: `apt-get -y install pkg=older` refuses
  ("Packages were downgraded and -y was used without --allow-downgrades"),
  the block fails, `always` restarts the timers, the play stops; the off
  switch is in place so OpenSSH stays down on poweredge; a re-run sees
  `pinned_present` (the check is `ge`) and proceeds to verify and activate.
  Access is never at risk: nothing here touches Tailscale.
- It outlasts the 600 s lock timeout: the install task fails cleanly before
  installing anything. Same recovery.

So a false-clear degrades to a clean refusal, never to an unsupervised change.

### Can it false-block forever?

Nothing on an Ubuntu desktop or server holds those four files open
permanently. `unattended-upgrade-shutdown` does not (measured above).
`packagekitd` (aptcc), `aptdaemon`, `update-manager` and the Pro client's
`esm-cache` take locks only inside a transaction. A GUI package manager left
open (synaptic holds the dpkg lock while its window is up) is the one
plausible long holder; it is not permanent, and the loop is bounded at 600 s.
Container processes (hp runs docker and k3s) cannot match: `fuser` compares
device and inode, and a container's `/var/lib/dpkg/lock-frontend` is a
different inode on an overlay. Measured: `fuser` over all four files with
~1,200 processes on the control node takes 0.35 s, so the loop period stays
about 5 s even on hp's larger process table.

If the wait does exhaust its 600 s, the task exits 1, the block's `always`
restarts the apt timers and cancels the restore unit, and the play stops before
the simulation and install. On hp and gmktec that leaves two drop-ins and an off
switch for a package that is not installed, harmless. On poweredge it leaves the
off switch beside a running port-22 sshd, which `HOST_VARS.md` "Rollback"
documents (its next unattended openssh upgrade would leave OpenSSH stopped).
Tailscale SSH is untouched in every case. The failure direction is the safe
one: refuse before the install.

### One thing the exit status cannot tell you

`fuser` returns 1 both for "no process holds any listed file" and for a fatal
error of its own (per its man page and source), and the shell returns 127 if
the binary is missing; `|| exit 0` treats all of these as "clear". Measured
locally. psmisc 23.7 is measured present on all three hosts and is a
`standard`-priority package, so this is a robustness note, not a defect: a
`command -v fuser >/dev/null || exit 2` guard in front of the loop costs one
line and makes a missing instrument a refusal instead of a silent pass.

I also checked the alternative instruments so nobody re-derives them:
`flock -n` is BLIND to apt's locks (measured: `flock -n` succeeded on a file
whose fcntl lock a root process held), because apt and dpkg use POSIX fcntl
record locks, not BSD flock. The kernel's own answer is `fcntl(F_GETLK)`
(measured: it reports the holder's pid without taking the lock), which would be
the one strictly faithful instrument; `fuser`'s fd-based reading is equivalent
in practice because every holder keeps the fd open for the lock's lifetime.
`fuser` is the right choice.

## 2. Check mode, drift runs, and `become`

- `check_mode: false` means the wait runs for real under `just ansible-drift`.
  That is intended (the drift report must see past it) and it is read-only:
  `fuser` without `-k`, `-i` or `-m` only reads `/proc`. The only trace
  `become` leaves is a sudo journal line.
- In a drift run on an unconverged host the install block is entered because
  `pinned_present` is false. Inside it, the two `ansible.builtin.command`
  tasks without `check_mode: false` ("Clear a restore unit", "Arm a host-side
  restore") are SKIPPED in check mode (the command module skips unless
  `creates`/`removes` is given; confirmed from `ansible-doc`), the
  `systemd_service` stops and starts are no-ops, `debconf` is a no-op, the
  wait, the simulation and `dpkg-query` run (all read-only), the assertion
  evaluates, and the `apt` install is a no-op. Net host change in a drift run:
  none. This is the same as before the change; the fix only makes the drift
  run finish in seconds rather than 600 s.
- Because the timers are NOT actually stopped in a drift run, the wait may
  contend with a live timer-triggered job; bounded, and correct.
- `become: true` on the wait introduces no new requirement: every other task
  in the block already escalates through the same sudo path.

## 3. Other defects in the role, ranked by severity

None is a blocker. Severity is judged by the maintainer's own bar (the hosts
must never lose access).

### 3.1 Medium: no mechanical proof that the live connection is Tailscale SSH

The role's safety argument is that the play rides Tailscale SSH, so moving
OpenSSH off port 22 cannot cut the control node off. The preflight keyscan
cannot discriminate this on poweredge: Tailscale SSH presents
`/etc/ssh/ssh_host_*_key` when they exist, so OpenSSH on port 22 and Tailscale
SSH on port 22 of the tailnet address present the SAME fingerprint, and the
"unchanged host key" assertion passes either way. If, on some future host or
after some future `tailscale set --ssh=false`, the connection were in fact
OpenSSH, the activation block would move the listener to LAN:22022 and the
rescue would then STOP OpenSSH entirely (the rollback stops `ssh.socket` and
`ssh.service` and restores the off switch), converting a partial loss into a
total one. Today this is covered by evidence, not mechanism: `HOST_VARS.md`
records that poweredge's OpenSSH had no login in the 30 days before the role,
and hp and gmktec have no OpenSSH at all. Recommended preflight, cheap and
precise: assert that the task's own process ancestry contains `tailscaled`
and no `sshd` (Tailscale SSH sessions are children of a `tailscaled be-child`
process; with `become` the chain is tailscaled, sh, sudo, python, bash), e.g.
a shell task that walks `/proc/<pid>/stat` from `$$` to pid 1 and refuses on
any `sshd`. This belongs with the existing "Nothing has been changed" refusals.

### 3.2 Medium-low: the real install transaction does not carry `--no-remove`

The simulation runs `apt-get -s install --no-install-recommends --no-remove`
and the assertion refuses any `Remv` line, but the `apt` module's actual
command is `apt-get -y ... install` with no `--no-remove` (module source line
~802). The refusal therefore exists only in the simulation; the stopped timers
and the fixed wait make the window between simulation and install small, but
the window exists (see the false-clear analysis above). The module exposes
exactly this flag as `fail_on_autoremove: true` ("Corresponds to the
`--no-remove` option for apt"). One line on the install task carries the
simulation's guarantee into the transaction that matters, independent of any
wait.

### 3.3 Low: add `/var/lib/apt/daily_lock` to the `fuser` list

Closes the between-phases window in `apt.systemd.daily` described in section
1. Zero cost; the parent script holds that fd for its whole run.

### 3.4 Low: guard the instrument

`command -v fuser >/dev/null || exit 2` before the loop, so a missing or
non-executable `fuser` refuses rather than clearing (section 1, exit status
note).

### 3.5 Low: the install block has no `rescue`

The inert-verification block's rescue explains the off switch to the operator;
a failure inside the install block (lock wait exhausted, simulation refused,
archive moved, lock timeout) falls out with only the task error. On poweredge
that is the one case where the off switch has a sharp edge (the next unattended
openssh upgrade leaves OpenSSH stopped). `HOST_VARS.md` documents the manual
remedy; a `rescue` that repeats the inert block's message would put it in
front of the operator at the moment it applies.

### 3.6 Informational, verified rather than found

- The central host-key claim holds for the packaged postinst: the
  openssh-server postinst on this control node (1:10.0p1) decides which keys to
  create from `/usr/sbin/sshd -G` (`get_config_option`, line 17), runs
  `create_sshdconfig` BEFORE `create_keys`, and the packaged
  `/usr/share/openssh/sshd_config` carries `Include /etc/ssh/sshd_config.d/*.conf`
  (line 24), so the drop-in's `HostKey` is the only one `sshd -G` lists and no
  `/etc/ssh/ssh_host_*` file is generated. If `sshd -G` failed, `hostkeys`
  would be empty and `create_key` would create nothing: the fail direction is
  also safe. The role's post-install assertion catches the case where this
  ever changes.
- `ssh.service` and `ssh.socket` both carry
  `ConditionPathExists=!/etc/ssh/sshd_not_to_be_run`, and `ssh.service` has
  `KillMode=process`, so a package-triggered restart under the off switch
  stops OpenSSH and cannot start it, and existing sessions survive restarts.
- The preseed `openssh-server/password-authentication` is honoured by
  `create_sshdconfig` (postinst line 70), writing `PasswordAuthentication no`
  into the main file on a fresh install.
- Every wait in the role is bounded: `ssh-keyscan -T 10`, the 600 s lock loop,
  `DPkg::Lock::Timeout=600`, `ConnectTimeout=15` plus `BatchMode=yes` on
  every verify login, `DEBIAN_FRONTEND=noninteractive` with
  `--force-confdef/--force-confold` from the apt module (no conffile prompt).
- The role touches no firewall, interface, route, sysctl or Tailscale state,
  and the `must_stay_running` units (tailscaled, k3s, docker, fabro-server,
  llama-server per host) are never restarted. A host firewall that blocked
  22022 would fail the verify play without changing access; the role does not
  check for one.
- `systemd-run --unit=<name>` refuses if a previous transient unit of that
  name is in `failed` state; "Clear a restore unit" only stops it. A
  `systemctl reset-failed <unit>.service` alongside the stop would make the
  re-arm robust. Failure mode is a clean block failure before any install.

## Scope statement

Searched: the complete role (`defaults`, `handlers`, five task files, five
templates, `HOST_VARS.md`), the playbook, and the diff. Instruments and their
positive controls: `fuser` exit codes measured with a lock held and not held,
as root and as non-root; `flock` blindness measured against the same held
lock; `F_GETLK` measured to see the holder; non-root `apt-get -s` measured to
succeed without a lock; the local sources of `unattended-upgrade`,
`unattended-upgrade-shutdown`, `apt.systemd.daily`, the openssh-server
postinst, `ssh.service`/`ssh.socket`, and the ansible `apt` and `command`
modules read for the claims attributed to them. Not measured: the target hosts
themselves (out of scope for this review); their package versions are taken
from the briefing.

REVIEW-COMPLETE: NO-BLOCKERS

---

# Follow-up review: uncommitted changes on top of e32b7a48

Diff reviewed: `git diff HEAD` in the same worktree (one file,
`tasks/server.yml`): the ancestry preflight and its assert, the `command -v
fuser` guard plus `/var/lib/apt/daily_lock` in the wait, and
`fail_on_autoremove: true` on the install. Same rules: nothing run remotely;
measurements on the control node only.

## The ancestry preflight

Rendered command (PyYAML, bash `-n` clean, no `become`):

```
p=$$; while [ "$p" -gt 1 ]; do cat /proc/$p/comm; p=$(awk '/^PPid:/ {print $2}' /proc/$p/status); done
```

### Could it false-refuse on hp, gmktec or poweredge?

- **`$$` inside the shell module.** The module runs `/bin/bash -c '<cmd>'`,
  so `$$` is that bash's pid and the first line printed is `bash` (measured:
  running the same text through `bash -c` printed `bash zsh claude zsh
  herdr`; running it as a script file printed the script's name instead, which
  is why the module form, not a script, is the right one). The loop is not a
  single simple command, so bash does not exec-optimise it away.
- **Chain under Ansible, with or without pipelining or ControlPersist.** The
  remote side of every Ansible task is `sh -c '... python3 ...'` spawned by the
  session; pipelining only changes whether the module arrives on stdin, and
  ControlPersist multiplexes on the CLIENT only. For Tailscale SSH each session
  is a fresh incubator forked by the daemon, so the daemon (`tailscaled`, pid
  1604 on hp) is an ancestor of every task whatever the incubator later execs
  (`login`, `su` or the command itself; exec never changes parentage). The
  coordinator's `ps --forest` on hp shows both the per-session and the daemon
  `tailscaled`, so `'tailscaled' in stdout_lines` is satisfied at least once
  and in practice twice. Under `become` the chain would gain `sudo` and still
  contain `tailscaled`; the task does not use `become`, which is the simpler
  and correct choice.
- **Comm truncation.** `tailscaled` is 10 bytes and `sshd-session` 12, both
  under the 15-byte limit (measured by truncating each name to 15; only
  `unattended-upgrade-shutdown` truncates, to `unattended-upgr`). The
  `'tailscaled' in` test is an exact element match on `stdout_lines`, which
  strips the newline `cat /proc/<pid>/comm` prints. The comm comes from the
  exec'd basename, so a symlinked combined binary or a snap wrapper still
  reads `tailscaled` as long as the path exec'd is named that; the apt
  package's `/usr/sbin/tailscaled` is a plain binary.
- **Reading root-owned ancestors as the non-root connection user.** Measured:
  as `ubuntu`, under root-owned `sudo` and `su` ancestors, the snippet printed
  `su sudo zsh claude zsh herdr`, and `/proc/1/comm` and `/proc/1/status` read
  fine. `comm` and `status` are world-readable unless `/proc` is mounted with
  `hidepid=1|2`; the control node's `/proc` is
  `rw,nosuid,nodev,noexec,relatime` (no hidepid). The coordinator's `ps
  --forest` on hp was taken over Tailscale SSH and showed root-owned
  `tailscaled` ancestors; if that `ps` ran as the login user rather than under
  sudo it also rules out hidepid on hp. gmktec and poweredge are assumed to
  match; a hidepid mount there would produce a refusal, not a wrong pass.
- **A broken chain fails the read, it does not pass a short list.** Measured:
  when `/proc/<pid>/status` cannot be read, awk prints nothing, `[ "" -gt 1 ]`
  errors and ends the loop, and the while loop's exit status is awk's (2), so
  the shell task itself fails with rc 2 before the assert runs. Either way the
  direction is a refusal.
- **The Jinja tests.** `select('match', '^sshd')` is Ansible's `match` test
  (`re.match`), so the anchor is redundant but harmless; on OpenSSH 10's split
  daemon it catches `sshd`, `sshd-session` and `sshd-auth`. In a Tailscale
  SSH session none of the ancestors begin with `sshd`, so the second condition
  holds. `check_mode: false` on the read and an unconditional assert mean a
  drift run over OpenSSH refuses too, which is correct and read-only.
- **Placement.** It sits after the must-stay-running assert and before the
  interface read, so everything ahead of it is still read-only and the
  fail_msg's "Nothing has been changed" is true.

I found no false-refuse on a host reached over Tailscale SSH from vps.

### Could it pass wrongly?

A wrong pass needs `tailscaled` as an ancestor AND no ancestor whose comm
starts with `sshd` AND a connection that moving or stopping OpenSSH could cut.
An OpenSSH connection always carries an `sshd*` ancestor: with Ubuntu's
`Accept=no` socket the session is a child of `sshd-session` under the listener
`sshd`; with a per-connection socket it would be an `sshd-session` directly
under systemd; an sshd started by hand from a Tailscale SSH shell with `-D`
would put `tailscaled` in the chain but also `sshd`, and the second condition
refuses. A `connection: local` run on a home-lab host from a Tailscale SSH
shell would pass, and that connection cannot be cut by OpenSSH. A non-OpenSSH
server (dropbear) would lack `tailscaled` and refuse. I found no wrong pass.

## The hardened wait

Rendered (bash `-n` clean, `become: true`):

```
command -v fuser >/dev/null || exit 2; for i in $(seq 1 120); do fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock /var/lib/apt/daily_lock >/dev/null 2>&1 || exit 0; sleep 5; done; exit 1
```

`exit 2` on a missing `fuser` fails the task (refusal direction); `/usr/bin`
is on sudo's `secure_path`, so the guard resolves psmisc's binary under
`become`. `/var/lib/apt/daily_lock` is held on fd 3 by the parent
`apt.systemd.daily` for its whole run and by nothing else (the child is
re-exec'd with `3>&-`); if the file does not yet exist, `fuser` reports it and
ignores it (measured earlier, rc 1 with a missing file and no holder). This
closes the between-phases window from section 1. No false-block: nothing holds
`daily_lock` outside a daily run.

## `fail_on_autoremove: true`

The module turns it into `--no-remove` on the `apt-get -y ... install` line
(module source lines 784 and 802), which is the same flag the simulation
asserts under. apt-get is the backend here (not aptitude), so the flag is not
ignored. A transaction that would remove anything now fails inside apt with
"Packages need to be removed but remove is disabled" before dpkg runs, which is
the refusal the simulation promised, carried into the real transaction.

## Residual notes (no action required)

- The hidepid assumption on gmktec and poweredge is the one thing this review
  could not measure; its failure mode is a refusal.
- ansible-lint's `risky-shell-pipe` does not apply: neither new command pipes.

REVIEW-COMPLETE: NO-BLOCKERS
