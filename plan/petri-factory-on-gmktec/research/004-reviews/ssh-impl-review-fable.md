# Independent implementation review (Fable) — `lan_ssh_fallback`

Reviewed: worktree `/home/ubuntu/.worktrees/livespec-dev-tooling/lan-ssh-fallback`,
branch `lan-ssh-fallback` (one commit, `1ae298ae`) against `origin/master`, read
through `git diff origin/master...HEAD`. Design and both design reviews in this
directory were read first. Nothing on any host, repository or ledger was
changed. Host reads were limited to `cat`, `ls`, `dpkg-query`, `apt-cache
policy`, `systemctl is-active|is-enabled|cat|show`, `ip -br addr|link`,
`ip route`, `sudo -n ss -ltnp`, `ssh-keygen -F`, and `ssh-keyscan` from the
control node. Local checks: `ansible-playbook --syntax-check` and
`--list-hosts` (no host contact), `ansible-inventory`, `ansible localhost -m
debug` over the role's filter expressions, a Jinja2 render of every template
with Ansible's `trim_blocks=True`, `ansible-lint` (production profile, clean),
`/usr/sbin/sshd -G` on the control node against the drop-in's directives, and
source reads of Ubuntu's `debian/patches/sshd-socket-generator.patch`
(`ubuntu/resolute-devel`), OpenSSH `V_10_2_P1` `sshd.c`, and the installed
`openssh-server.{preinst,postinst,config,prerm}` on poweredge.

Verdict first: nothing in this change can touch tailscaled, what Tailscale SSH
presents, `/etc/ssh/ssh_host_*`, routes, interfaces or k3s, and the inert-then-
activate order on all three hosts is sound. But the role is not idempotent and
its documented operator procedure fails on a correct host at its second command.
Those two are blockers; both are a few lines to fix. Below them, three findings
weaken the fallback itself (one intermittent refusal mode introduced by the
BindToDevice departure, a 30-second idle kill on the control-node path, and a
boot race), and the first drift report fails spuriously.

## BLOCKER

### B1. The role refuses its own second drop-in, so every run after the first is refused at preflight (and so is the documented procedure's third command)

`tasks/server.yml:121-139` lists `/etc/ssh/sshd_config.d/*.conf` and asserts
that the set minus `lan_ssh_fallback_dropin` is empty:

```
lan_ssh_fallback_other_dropins.files | map(attribute='path')
| reject('equalto', lan_ssh_fallback_dropin) | list | length == 0
```

`tasks/server.yml:174-181` writes a SECOND file the role owns,
`lan_ssh_fallback_auth_dropin` = `/etc/ssh/sshd_config.d/01-lan-fallback-auth.conf`
(`defaults/main.yml:44`). On any host that has been converged once, the next
run — `ansible-apply` or `ansible-drift`, which runs this task because `find`
and `assert` run under `--check` — fails with `Foreign sshd drop-ins:
/etc/ssh/sshd_config.d/01-lan-fallback-auth.conf`.

Consequences:
- `HOST_VARS.md:91-94` prescribes `--limit hp-xubuntu` first, then a full
  apply. The full apply's server play (`serial: 1`, `any_errors_fatal: true`)
  reaches hp — host order measured by `--list-hosts` is hp, poweredge, gmktec,
  so hp is the FIRST host of play 3 — is refused there, and the whole play
  stops before poweredge or gmktec are touched. The procedure cannot complete.
- "Re-running is the supported repair path" (`justfile:333`) is closed.
- `just ansible-drift` is red forever after the first converge, so the drift
  report that is supposed to catch a listener drifting back to port 22
  (`tasks/verify.yml:60-64`) never runs to that task.

Fix: reject both role-owned paths (`[lan_ssh_fallback_dropin,
lan_ssh_fallback_auth_dropin]`), e.g. `reject('in', [...])`. Nothing else
depends on this.

### B2. `--limit <host>` — the documented first step — fails mid-converge with an undefined hostvar; the playbook header's claim about it is false

`ansible/lan-ssh-fallback.yml:10-12` says "To change one host only, add
`--limit <host>` to both: every phase still reads the other hosts' public keys,
because the key phase targets the whole group." `--limit` is applied to every
play, not to the plays after the first. Measured, no host contact:

```
ansible-playbook --list-hosts --limit hp-xubuntu ansible/lan-ssh-fallback.yml
  play #1 (home_lab): hosts (1): hp-xubuntu
  play #2 (dev_hosts): hosts (0):
  play #3 (home_lab): hosts (1): hp-xubuntu
  ...
```

So under `--limit hp-xubuntu`, play 1 sets `lan_ssh_fallback_host_pubkey` /
`lan_ssh_fallback_user_pubkey` ONLY on hp, and play 2 runs on nobody, so
`lan_ssh_fallback_client_pubkey` is never set. Then:

- `tasks/server.yml:204-211` renders `templates/authorized_keys.j2`, whose
  lines 6-10 index `hostvars[host]['lan_ssh_fallback_user_pubkey']` for every
  `home_lab` host and `hostvars[host]['lan_ssh_fallback_client_pubkey']` for
  every `dev_hosts` host. Both are undefined for the excluded hosts, and the
  template task fails.
- `tasks/client.yml:14-21` (`known_hosts.j2:6`) fails the same way, and
  `tasks/verify.yml:7-28` would then try `ssh poweredge-xubuntu-lan` from hp
  against a poweredge that has no fallback yet.

The failure lands AFTER `tasks/server.yml:143-202` has touched the off switch
and written the three drop-ins. On hp/gmktec that is inert (no
`openssh-server`). On poweredge it is not inert in time: the preinst of the
pending unattended `1:10.2p1-2ubuntu3.8` security upgrade (`apt-cache policy`:
installed 3.6, candidate 3.8, `20auto-upgrades` on) stops `ssh.socket` and
`ssh.service`, and its postinst restart is condition-skipped by the off switch
(`ConditionPathExists=!/etc/ssh/sshd_not_to_be_run` on BOTH units, measured
with `systemctl cat`), so poweredge's OpenSSH would go down at the next apt
run and stay down. Not a lockout (Tailscale SSH is untouched; nothing uses that
daemon), but a converge that fails on a correct host and leaves a time bomb.

Fix: either delete the `--limit` advice from the header and `HOST_VARS.md:92`
and run the whole group (play 3 is already `serial: 1`, so "one host at a
time" is already true), or make plays 1-2 immune to `--limit` (for example by
gathering the keys with `delegate_to` over `groups['home_lab']` from one host,
or by `ansible_play_hosts`-independent `hosts: home_lab` with `run_once` loops).
The first is simpler and matches what the play already does.

## SHOULD-FIX

### S1. `BindToDevice=` turns the two-interface hosts' ARP flux into a refused connection — an intermittent "connection refused" on the fallback, including in the verify phase

The design bound by ADDRESS (`ListenAddress 192.168.1.x:22022`). Design review
A's N9 argued that ARP flux on hp and gmktec — two interfaces on one /24 with
`arp_ignore=0` — is harmless precisely because "the kernel listener is
address-, not device-bound, so it is served." The implementation changed that
premise (`templates/ssh-socket-dropin.conf.j2:7-8`, `BindToDevice={{
lan_ssh_fallback_interface }}`) without re-deriving the consequence.

Measured today: hp `enp11s0 192.168.1.4/24` AND `wlp10s0 192.168.1.54/24`, both
`UP`, `arp_ignore` = 0 on `all`, `enp11s0`, `wlp10s0`; gmktec `eno1
192.168.1.156/24` AND `wlp195s0 192.168.1.66/24`, both `UP`, `arp_ignore` = 0
on all three. With `arp_ignore=0` a Linux host answers an ARP request for ANY
of its addresses on ANY interface, so a peer asking "who has 192.168.1.4" gets
two replies, and the first to arrive (the kernel's 1-second ARP `locktime`
blocks the second) is cached. When that is the Wi-Fi MAC, the SYN arrives on
`wlp10s0`; a listener with `SO_BINDTODEVICE=enp11s0` is excluded from the
listener lookup for that packet (`inet_lhash2_lookup` / `compute_score`
compares `sk_bound_dev_if` against the ingress ifindex), so the kernel answers
RST and the client sees `Connection refused`. Under address binding the same
packet is accepted and the reply leaves by the metric-100 wired route.

Wired usually wins the race, so this will mostly work, and that is the problem:
a fallback that refuses "sometimes" is one that will be found broken when
Tailscale is down, and `tasks/verify.yml:7-28` (and the vps path through a
jump host) will fail intermittently for the same reason, with no rollback
reaching the server (phase 5 has none, by design).

Fix options, in order: (a) return to the design's address binding —
`ListenAddress {{ lan_ssh_fallback_address }}:{{ lan_ssh_fallback_port }}` in
`00-lan-fallback.conf.j2` (the generator turns it into
`ListenStream=192.168.1.x:22022`; `FreeBind=yes` survives), keep the socket
drop-in out, and keep the `tasks/server.yml:69-86` lease assertion, which
already covers the "lease changed" concern; the k3s units pin the same wired
addresses, so the fallback is exactly as durable as the cluster; (b) keep
BindToDevice and set `arp_ignore=1` on the wired and Wi-Fi interfaces — but
the role promises no sysctl change (`HOST_VARS.md`, rescue message), so that
is a separate decision; (c) at minimum, document the mode and make the verify
loop retry so a cached Wi-Fi ARP entry is reported as what it is rather than
as a role failure.

### S2. `nc -w 30` in the vps ProxyCommand is an IDLE timeout: every control-node fallback session dies after 30 idle seconds

`templates/ssh_config.j2:26`: `ProxyCommand ssh ... cwoolley@{{ jump }} nc -w
30 %h %p`. All three hosts and vps run netcat-openbsd (`/usr/bin/nc ->
nc.openbsd`, "OpenBSD netcat (Debian patchlevel 1.234-1)"), whose man page
says of `-w`: "Connections which cannot be established or are idle timeout
after timeout seconds. ... The default is no timeout." So an interactive `ssh
hp-xubuntu-lan` from vps is cut after 30 s without keystrokes; `nc` exits, ssh
reports the connection closed. The verify phase runs `true` and returns in
well under 30 s, so it proves nothing about this.

Fix: drop `-w` (the outer `ConnectTimeout=15` already bounds the dial; the
inner ssh has its own), or keep it and add `ServerAliveInterval 10` to the
`Host *-lan *-lan-via-*` block so traffic flows under the idle limit. Prefer
dropping it.

### S3. The first `just ansible-drift` fails at the verify phase on every host — exactly the spurious check-mode failure the brief asks about

`tasks/verify.yml:60-81` runs `systemctl show ssh.socket -p Listen -p
BindToDevice` with `check_mode: false` and then an `assert` with no
`ansible_check_mode` guard. Measured today: on hp and gmktec (no `ssh.socket`
unit) the command prints only `BindToDevice=` — no `Listen=` line at all — and
on poweredge it prints `Listen=0.0.0.0:22 (Stream)` / `Listen=[::]:22
(Stream)`. All three assertions therefore fail under `--check` before anything
has been converged (verified the expression against the bare string locally:
`search('BindToDevice=' ~ iface)` is `false`). The comment at :61-64 says the
task exists so the drift report can run it; on the first run it instead makes
the report red, and the operator procedure (`HOST_VARS.md:91`) says to read
that report before applying.

Fix: under `ansible_check_mode`, report rather than assert (a `debug` of the
stdout, or `failed_when: false` plus a `changed_when` that marks drift), and
keep the hard assert for the apply path. Note the related consequence of B1:
after converge the drift report never reaches this task at all.

### S4. `BindToDevice=` at boot: if `ssh.socket` starts before udev has renamed the NIC, the bind fails `ENODEV` and the socket stays failed with no retry

systemd's `socket_address_listen()` applies `BindToDevice=` with
`setsockopt(SO_BINDTODEVICE)`; the kernel resolves the name with
`dev_get_by_name` and returns `ENODEV` when `eno1`/`enp11s0` does not exist
yet. Socket units have no restart logic. The socket is ordered only by its
default dependencies (`After=sysinit.target`, before `sockets.target`);
`systemd-udev-trigger.service` is `Type=oneshot` and completes when events are
QUEUED, not when the net device has been renamed. The race is narrow on these
hosts (onboard PCI NICs) but real, and `HOST_VARS.md` already records that
"the boot path has not been exercised." On poweredge a failed `ssh.socket`
also fails `ssh.service` (`Requires=ssh.socket` via
`/etc/systemd/system/ssh.service.requires/`, measured). Neither affects
Tailscale SSH, k3s or networking; it affects only whether the fallback exists
after a reboot — the one time it is likely to be needed.

Fix (if BindToDevice is kept after S1): add to the socket drop-in

```
[Unit]
After=sys-subsystem-net-devices-{{ lan_ssh_fallback_interface }}.device
Wants=sys-subsystem-net-devices-{{ lan_ssh_fallback_interface }}.device
```

which is the standard device-bound-socket pattern. If S1 is resolved by
address binding, `FreeBind=yes` already covers the boot case and this finding
disappears.

### S5. Documentation and comments that no longer match the code

- `HOST_VARS.md` variables table: `lan_ssh_fallback_upgradable` is documented
  as `[openssh-client]`; `defaults/main.yml:72` is `[openssh-client,
  openssh-server, openssh-sftp-server]`. The table also says the packages are
  "installed only where `openssh-server` is absent"; the block at
  `tasks/server.yml:215-216` runs wherever the EXACT pinned set is not present,
  which includes poweredge (3.6 → 3.8 upgrade), and that is the intended
  design per `defaults/main.yml:55-60` and design review B's S3. The section
  header comment at `tasks/server.yml:213` ("only where openssh-server is
  absent") is wrong the same way.
- `ansible/lan-ssh-fallback.yml:10-12` and `HOST_VARS.md:92` — the `--limit`
  claim (B2).
- `HOST_VARS.md` "Three fail-safes": the debconf preseed is a no-op on
  poweredge. The package's `.config` script (read on poweredge) re-syncs
  `openssh-server/password-authentication` from the EXISTING
  `/etc/ssh/sshd_config` whenever that file exists, and poweredge's main file
  carries no `PasswordAuthentication` line, so it sets the value back to
  `true` before the postinst runs. The two drop-ins still hold
  `PasswordAuthentication no` (the role's `sshd -G` assert at
  `tasks/server.yml:350` proves the effective value), so this is a doc
  precision point: the third layer exists on fresh installs only, as the
  defaults comment already half-says.

## NOTE

### N1. Every converge restarts the listener

`tasks/server.yml:143-152` creates the off switch on every run (it does not
exist on a converged host), and `:399-429` unconditionally releases it and
restarts `ssh.socket` (and `ssh.service` where a PID was recorded). After B1
is fixed, each apply flaps the fallback listener for a second or so, and
`ansible-apply` is never "ok" for those tasks. Harmless today (nothing depends
on the daemon), but worth a `when` on the socket's current `Listen` /
`BindToDevice` matching the expected set.

### N2. The inert-verify block (`tasks/server.yml:324-392`) has no rescue, and the install fence can leave poweredge primed to go dark

A failure inside the inert block leaves the off switch present, the drop-ins
written and the packages installed. That is safe by construction (nothing
listens; Tailscale SSH untouched), but the fail message does not say so the
way the activation rescue's does (`:521-527`). Separately, a `Simulate`
refusal on poweredge (`:279-297`) leaves the off switch and drop-ins on disk
with sshd 3.6 still serving port 22; the next unattended 3.8 upgrade then
stops it (preinst) and cannot restart it (condition), so poweredge's OpenSSH
goes down unattended. Not a lockout, but the message should say that the off
switch must be removed by hand if the operator abandons the apply.

### N3. `/run/sshd` is created by systemd, not by either openssh package — so `sshd -t` at `tasks/server.yml:327-331` is safe on hp and gmktec

OpenSSH `V_10_2_P1` `sshd.c:1736-1740` fatals `Missing privilege separation
directory` for a root `-t` before the `test_flag` exit at `:1762`. The
directory exists on hp and gmktec today (`drwxr-xr-x root /run/sshd`, dated at
boot) because systemd ships `/usr/lib/tmpfiles.d/20-systemd-ssh-generator.conf`
with `d /run/sshd 0755` (read on hp). Design review A's N4 attributed it to
`openssh-client`'s tmpfiles; that file is only `x /tmp/ssh-*` on all three
hosts. Recording the real owner so nobody later "cleans up" the wrong one.

### N4. Things that check out, with the evidence, so they need not be re-derived

- `sshd -G` with exactly the drop-in's directives prints `port 22022`,
  `listenaddress [::]:22022`, `listenaddress 0.0.0.0:22022`, `hostkey
  /etc/ssh/lan-fallback/ssh_host_ed25519_key`, `authorizedkeysfile
  /etc/ssh/lan-fallback/authorized_keys/%u .ssh/authorized_keys`, `allowusers
  cwoolley`, and the four auth lines — every string `tasks/server.yml:345-355`
  asserts (run on the control node's OpenSSH 10.0p2; the dump format is
  unchanged in 10.2).
- The Ubuntu generator (`sshd-socket-generator.patch`, `listen_addr_is_default`)
  sets `have_custom_config` whenever the port is not 22, so with `Port 22022`
  and no `ListenAddress` it writes `ListenStream=` reset plus
  `ListenStream=[::]:22022` and `ListenStream=0.0.0.0:22022`; `BindIPv6Only`,
  `FreeBind` and the role's `BindToDevice` drop-in survive (different file
  names in different `.d` dirs merge).
- `systemctl show ssh.socket -p Listen [--value]` prints `0.0.0.0:22 (Stream)`
  per line (poweredge, measured), so `regex_findall('(\S+) \(Stream\)')` at
  `:458` and the three `search` patterns at `verify.yml:76-78` are correct;
  all evaluated locally against sample strings, including the
  `\\(`-in-plain-scalar escaping, `map(attribute=1)`, `select('in', ...)`,
  `reject('search', '\\sReady\\s')`, and the `not in` precedence at `:429`.
- Both `ssh.socket` and `ssh.service` carry
  `ConditionPathExists=!/etc/ssh/sshd_not_to_be_run` (measured), the 3.x
  preinst stops both units on upgrade, the postinst's final block restarts
  only `ssh.socket` (condition-skipped), `sshd-keygen.service` is
  `ConditionFirstBoot=yes` with `/run/systemd/first-boot` absent on all three,
  `create_keys` creates only `HostKey` paths from `sshd -G`, and
  `needrestart` is not installed anywhere. So the off switch really holds
  every TCP listener down through apt, and nothing in the transaction can
  create `/etc/ssh/ssh_host_*` or restart another unit.
- `ssh-keyscan -T 10 -t rsa,ecdsa,ed25519 <host> | ssh-keygen -lf - | awk ...`
  from the control node returns exactly three lines for each host (fingerprints
  match the measured-state table), so the `== 3` preflight at `:26-37` passes.
- Every `must_stay_running` unit is `active` today on all three hosts
  (including `fabro-server-candidate` on hp and `local-homelab-llama-server`
  on gmktec), and each declared address is on its declared interface.
- vps `~ubuntu/.ssh/known_hosts` has entries for the short names
  `poweredge-xubuntu`, `hp-xubuntu`, `gmktec-xubuntu` (`ssh-keygen -F`), so
  the BatchMode inner ssh of the ProxyCommand will not stall on an unknown
  host; `~ubuntu/.ssh/config` only adds `User cwoolley` for two of them, and
  the alias passes the user explicitly. `nc` is present on all three jumps.
  hp's and gmktec's `cwoolley` known_hosts pin `poweredge-xubuntu` (ed25519),
  so the tailnet positive control at `verify.yml:30-58` is runnable.
- Templates render as intended under `trim_blocks=True`: the blank line at
  `ssh_config.j2:24` correctly compensates for the stripped newline; known_hosts
  lines are `[192.168.1.x]:22022 ssh-ed25519 ...`; the `Host *-lan *-lan-via-*`
  block pins `IdentitiesOnly`, the identity, the known_hosts file and strict
  checking after the per-alias `HostName`/`ProxyCommand`.
- `ansible-lint` (production profile) passes on the playbook and role.
- Check-mode walk of `server.yml` on an unconverged host is clean: every
  `command`/`shell` that must run is `check_mode: false`; the `systemd-run`
  arming and the `systemctl stop` of the restore unit are correctly skipped;
  the inert and activation blocks are `when: not ansible_check_mode`; the slurp
  placeholders at `keys.yml:65-91` render.

### N5. The `-via-` alternate aliases are never exercised

`tasks/verify.yml:7-28` logs in through `<host>-lan` only, which on vps is the
first jump alphabetically (`gmktec-xubuntu-lan` via hp, `hp-xubuntu-lan` via
gmktec, `poweredge-xubuntu-lan` via gmktec). The `-via-poweredge-xubuntu`
forms are untested, and poweredge is the host with no Wi-Fi and the k3s
server. Looping over the rendered alias names would cover them.

### N6. Small robustness items

- `tasks/verify.yml:100`: a node at `Ready,SchedulingDisabled` (cordoned) does
  not match `\sReady\s` and fails the assert.
- `tasks/keys.yml:47-63` assumes `~cwoolley/.ssh` exists (it does on all three
  today); a `file: state=directory mode=0700` as the user would make the
  keygen self-sufficient.
- `tasks/server.yml:215` block runs the apt simulation without `become`;
  `apt-get -s` works unprivileged but prints the "only a simulation" notice
  on stderr; fine, just expected noise in the drift report.
- Verify-phase failures (play 5) do not roll back the servers, by design; the
  servers are in their correct state when that happens, so nothing to fix,
  but `HOST_VARS.md` "Rollback" could say that the automatic rollback covers
  the activation checks only.

REVIEW-COMPLETE: BLOCKERS
