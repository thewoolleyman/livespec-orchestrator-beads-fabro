# Independent review (Fable A) — `ssh-fallback-design.md`

Reviewed: `tmp/petri-gmktec-review/ssh-fallback-design.md` (2026-10-15), against
`/data/projects/livespec-dev-tooling/ansible/roles/ssh_hardening/`,
`/data/projects/livespec-dev-tooling/ansible/inventory/legacy.yml`, read-only
host state on poweredge-xubuntu, hp-xubuntu and gmktec-xubuntu, and upstream
sources: tailscale v1.102.2 (the version all three hosts run), Ubuntu
openssh `1:10.2p1-2ubuntu3.x` packaging (poweredge's installed maintainer
scripts plus the `ubuntu/resolute-devel` patch tree), OpenSSH `V_10_2_P1`,
and systemd v259 (the version installed, `259.5-0ubuntu3.4`).

Nothing on any host was changed. Every remote command was one of: `cat`,
`ls`, `head -c`, `systemctl is-active|is-enabled|cat`, `ip -br addr`,
`ip route`, `sudo -n ss -ltnp`, `sudo -n iptables -S`, `dpkg -l`,
`apt-cache policy|depends|show`, `tailscale status --self --json`, `cut` over
public-key files.

## Findings, ranked

### BLOCKER

None. Every mechanism the design relies on checks out against source, and no
step can reach tailscaled, the tailnet path, k3s or host networking. The
items below are correctness and robustness gaps in the design itself, not
hazards to the hosts.

### SHOULD-FIX

**S1. The pinned LAN addresses are all DHCP leases; a lease change silently
kills the fallback (and FreeBind hides it).**
Evidence: `ip route` on each host — poweredge `default via 192.168.1.1 dev
eno1 proto dhcp src 192.168.1.200`; hp `default ... dev enp11s0 proto dhcp
src 192.168.1.4` and `... dev wlp10s0 proto dhcp src 192.168.1.54`; gmktec
`default ... dev eno1 proto dhcp src 192.168.1.156` and `... dev wlp195s0
proto dhcp src 192.168.1.66`. The netplan files are root-only, so whether
the router holds reservations could not be read from the hosts. The design
binds `ListenAddress 192.168.1.x:22022` and renders the same literals into
every client alias and `known_hosts` entry. With `FreeBind=yes` the socket
binds a lease that no longer exists without any error, and the daemon never
logs anything: the fallback simply stops answering, and the first time
anyone learns is when Tailscale is already down — the one moment it exists
for. Fix options, in order of preference: (a) confirm or create router DHCP
reservations for the three wired addresses and record that in the design;
(b) make the server binding address-independent — a
`/etc/systemd/system/ssh.socket.d/` drop-in with `BindToDevice=<wired
interface>` (SO_BINDTODEVICE excludes `tailscale0` at the kernel, so
`Port 22022` with no `ListenAddress` would still never touch the tailnet
address; the generator then emits `ListenStream=0.0.0.0:22022` /
`[::]:22022`, which with `BindToDevice` reach only the wired NIC) — and
keep the client-side pins as the one place a lease change has to be
re-rendered; (c) at minimum, add a verify-time assertion that each
`ListenAddress` literal is currently assigned (`ip -br addr`) and a note in
the role's HOST_VARS.md that the addresses are leases.

**S2. The failure direction of the generator is toward a port-22,
all-addresses, password-capable listener; add one line of defence that does
not depend on the drop-in surviving.**
Evidence: `sshd-socket-generator.patch` (ubuntu/resolute-devel) —
`parse_sshd_config_options()` calls `parse_server_config()`, which `fatal()`s
on a malformed directive, so the generator exits non-zero, writes no
`addresses.conf`, and the packaged unit's `ListenStream=0.0.0.0:22` /
`[::]:22` (poweredge `/usr/lib/systemd/system/ssh.socket`) is what the next
socket start binds; and `if (num_listen_streams <= 0 || !have_custom_config)
... r = -ENODATA` — a missing drop-in yields the same packaged default. The
fresh `/etc/ssh/sshd_config` the postinst installs from
`/usr/share/openssh/sshd_config` carries `#PasswordAuthentication yes`
(commented, i.e. default yes) — read on poweredge. So the combined failure
of "drop-in lost or broken" is OpenSSH on port 22 on every address including
the LAN with password authentication on, and the design's step-5 gate only
protects the first apply. The cheap fix: preseed debconf before install
(`openssh-server/password-authentication false`), which makes the postinst's
`create_sshdconfig` write `PasswordAuthentication no` into the main file
(poweredge `/var/lib/dpkg/info/openssh-server.postinst`, `create_sshdconfig`:
`if [ "$password_authentication" != true ]; then sed -i
's/^#PasswordAuthentication .*/PasswordAuthentication no/'`). On poweredge,
where the main file already exists, the role should instead assert the main
file's `PasswordAuthentication` state or carry it in a second, independent
drop-in. Note that on the tailnet address this failure is invisible anyway
(tailscaled intercepts port 22 — see Q1), which is exactly why it would not
be noticed.

**S3. On poweredge `ssh.service` is enabled directly and holds the port-22
file descriptors; make the step-6 restart explicit and verify the daemon
PID changed.**
Evidence: `systemctl is-enabled ssh.service` → `enabled`
(`/etc/systemd/system/multi-user.target.wants/ssh.service` exists, created
2026-08-12 16:53, alongside `ssh.service.requires/ssh.socket`), and `ss
-ltnp` shows `0.0.0.0:22 users:(("sshd",pid=2455,fd=3),("systemd",pid=1,
fd=348))` — the running `sshd` owns a dup of the listening socket. The
design's step 6 is `systemctl restart ssh.socket` only. I checked systemd
v259 `src/core/transaction.c:1112-1121`: a RESTART of a unit propagates as
`JOB_TRY_RESTART` over `UNIT_ATOM_PROPAGATE_STOP`, and
`unit-dependency-atom.c:43` gives `UNIT_REQUIRED_BY` that atom, so the
socket restart WILL try-restart the active `ssh.service`, and `Before=
sockets.target ssh.service` orders the new socket first. So the step works
as written on this systemd — but it works by a propagation rule the design
never states, and if it did not, the old `sshd` would keep serving port 22
from its inherited fds while the new socket on 22022 accepted connections
into a backlog nobody drains. Write `systemctl restart ssh.socket
ssh.service` (the rollback line already names both), and add to step 6's
verification that `ss -ltnp` shows no `sshd` process on `:22` AND that the
`sshd` main PID differs from the one recorded at step 1.

**S4. The `AuthorizedKeysFile` override on poweredge drops the MacBook key
that is in `~cwoolley/.ssh/authorized_keys` today.**
Evidence: poweredge `cut -d" " -f1,3- ~/.ssh/authorized_keys` → `ssh-ed25519
ubuntu@vps.perch-rudd.ts.net`, `ssh-ed25519 cwoolley@macbook-2026-06-24`,
`ssh-ed25519 cwoolley@hp-xubuntu`. The design's rendered file holds "the
cwoolley public key of each of the three hosts plus vps's ubuntu key", and
`AuthorizedKeysFile /etc/ssh/lan-fallback/authorized_keys/%u` replaces the
default (`.ssh/authorized_keys` is no longer read). The maintainer's laptop
on the home LAN therefore loses its only non-Tailscale door to poweredge,
which is the opposite of a fallback. Either include that key in the
rendered set (it is a public key already on the host), or write
`AuthorizedKeysFile /etc/ssh/lan-fallback/authorized_keys/%u
.ssh/authorized_keys` (sshd accepts several, space-separated). Also note the
design says poweredge "has no cwoolley key" — it has no `id_ed25519` (true,
`ls ~/.ssh` shows only `authorized_keys` and `known_hosts`), but it does
have authorized keys, and the table row "cwoolley authorized_keys: vps
ubuntu key, a MacBook key, hp key" already records them without drawing
this consequence.

**S5. The Tailscale host-key invariant is per key TYPE and re-read on every
connection; verify all three types, not "the fingerprint".**
Evidence: tailscale v1.102.2 `ssh/tailssh/hostkeys.go:140-156`
`getSystemHostKeys` reads exactly `/etc/ssh/ssh_host_{rsa,ecdsa,ed25519}_key`
and `getTailscaleHostKeys` (lines 59-91) substitutes a Tailscale-generated
key only for each type that is MISSING; `tailssh.go:516` calls
`getHostKeys(...)` inside `newConn`, i.e. per incoming connection, with no
cache. So a stray `/etc/ssh/ssh_host_rsa_key` appearing on hp would change
ONLY the RSA key Tailscale SSH presents, on the very next connection, and
an `ssh-keyscan` compared on one line (ed25519, the one clients negotiate
first) would report "unchanged". `ssh-keyscan` fetches rsa, ecdsa and
ed25519 by default; compare all three lines at steps 1, 5 and 7. gmktec
carries all three system keys (`ls -la /etc/ssh`: rsa/ecdsa/ed25519 dated
Aug 17 00:26) and poweredge all three (Aug 12 14:49); hp none.

### NOTE

**N1. Installing openssh-server adds a listener the design does not mention,
and neither the off switch nor the rollback covers it: systemd's own
`sshd-unix-local.socket`.**
Evidence: systemd v259 `src/ssh-generator/ssh-generator.c:464`
`find_executable("sshd", ...)` and lines 265-282 generate
`sshd-unix-local.socket` on `/run/ssh-unix-local/socket` whenever an `sshd`
binary exists; on poweredge it is live: `systemctl is-enabled
sshd-unix-local.socket` → `generated`, `is-active` → `active`,
`/run/ssh-unix-local/socket` mode `srw-rw-rw-`. The generated
`sshd-unix-local@.service` is a symlink to the package's `sshd@.service`
(`ExecStart=-/usr/sbin/sshd -i $SSHD_OPTS -o "AuthorizedKeysFile
${CREDENTIALS_DIRECTORY}/ssh.ephemeral-authorized_keys-all
.ssh/authorized_keys"`), so through THIS door `~/.ssh/authorized_keys` is
honoured (command-line `-o` wins over the drop-in). It is AF_UNIX only —
unreachable from the LAN or the tailnet, and `ss -ltn` (TCP) never shows
it — and the generator ignores `/etc/ssh/sshd_not_to_be_run`. On hp and
gmktec it will be generated at the postinst's `daemon-reload` and started at
the next boot. Not a conflict with anything; document it, and extend the
"nothing listens" wording in steps 4-5 to "no TCP listener".

**N2. Question 2 is answered NO by the maintainer scripts, with one
ordering fact worth recording.** The postinst runs `create_sshdconfig`
BEFORE `create_keys` (poweredge postinst, the `configure` branch), so by the
time `sshd -G` is consulted the fresh `/etc/ssh/sshd_config` already carries
`Include /etc/ssh/sshd_config.d/*.conf` as its first directive and the
role's `HostKey` is in effect. `servconf.c:305` (V_10_2_P1) adds the three
default `HostKey` paths only when `num_host_key_files == 0`, so `sshd -G`
lists the dedicated key alone and `create_key`'s `grep -x "$file"` matches
none of the three. `sshd -G` dumps at `sshd.c:1576`, before any host key is
loaded, so a missing default key cannot fail it. `sshd-keygen.service`
(`ExecStart=ssh-keygen -A`, which WOULD create all three keys regardless of
config) is gated by `ConditionFirstBoot=yes`; `/run/systemd/first-boot` is
absent on all three hosts, so the postinst's `deb-systemd-invoke start
sshd-keygen.service` is a condition no-op. `cloud-init` is disabled on hp and
gmktec (`/etc/cloud/cloud-init.disabled`). There is no `openssh-server.triggers`
file. The two residual ways to get system keys are a future `/etc/machine-id`
reset (first boot fires `ssh-keygen -A`) and a human running `ssh-keygen -A`;
both are outside this design but belong in the role's comments.

**N3. The socket generator's address-family edge.** The generator skips an
address whose family differs from `AddressFamily` and, with only IPv4
`ListenAddress` lines and the default `AddressFamily any`, emits
`ListenStream=` (reset) followed by one `ListenStream=192.168.1.x:22022` per
line (`write_systemd_socket_file`). The packaged `BindIPv6Only=ipv6-only` and
`FreeBind=yes` survive, so the override is exactly what the design expects.
Also: sshd under socket activation uses the passed fds and never binds its
own `ListenAddress` (`systemd-socket-activation.patch`, `server_listen`:
`if (systemd_num_listen_fds > 0) ... else listen_on_addrs`), so the socket
unit is the single source of truth for what is bound — a stale `addresses.conf`
is impossible because the generator runs on every `daemon-reload` and boot.

**N4. `sshd -t` as root requires `/run/sshd`; it exists on all three hosts
today, so step 5 is fine, but the reason is not what the design says.**
`sshd.c:1736-1740` (V_10_2_P1) fatals `Missing privilege separation
directory` under `-t` when `need_chroot` (uid 0). `/run/sshd` is created at
boot by `openssh-client`'s tmpfiles entry `d /run/sshd 0755`
(`/usr/lib/tmpfiles.d/openssh-client.conf` on hp), not by the server package
(`/usr/lib/tmpfiles.d/openssh-server.conf` is only `x /tmp/sshauth.*`). Note
it so a future reader does not drop the client package's tmpfiles.

**N5. The apt step must pin all three packages to `1:10.2p1-2ubuntu3.8`.**
`apt-cache policy` on hp and gmktec: candidate `3.8` from resolute-security;
`3.7` is `phased 75%` in resolute-updates. `openssh-server` hard-Depends on
`openssh-client (= <same>)` AND `openssh-sftp-server` (Depends, not
Recommends, on Ubuntu — `apt-cache show`), so the audited `Inst` set is
exactly `openssh-sftp-server`, `openssh-server`, and the `openssh-client`
upgrade `3.6 → 3.8`; every other Depends is already installed (`dpkg -l` for
ucf, libwrap0, procps, libpam-*, libpam-systemd, debconf, sysvinit-utils,
libaudit1, libkrb5-3, libcom-err2, libgssapi-krb5-2, systemd: all `ii`).
Recommends (`ncurses-term`, `xauth`, `ssh-import-id`) are correctly excluded
by `--no-install-recommends`. `needrestart` is not installed on any host, so
no apt hook can restart services. `unattended-upgrades` IS enabled and active
on both hosts (`20auto-upgrades`), so every future openssh upgrade will
`stop ssh.socket`/`ssh.service` in preinst and `restart ssh.socket` in
postinst — the fallback flaps for the duration, and `create_keys` re-runs
under whatever `HostKey` is then in effect (another reason for S2).

**N6. The `node_status_credential` role is a second consumer of the
poweredge invariant and a free positive control for step 7.**
`roles/node_status_credential/defaults/main.yml:76` reads
`/etc/ssh/ssh_host_ed25519_key.pub` on the SERVER and installs it as the
agents' `known_hosts` entry for `poweredge-xubuntu`, because Tailscale SSH on
poweredge presents exactly that key (hostkeys.go, above). The design keeps
that key untouched, so nothing changes — but step 7 should include one
`refresh-node-status-kubeconfig`-style `ssh -o BatchMode=yes
poweredge-xubuntu true` as `cwoolley` from hp and gmktec, since that is the
production path the invariant protects.

**N7. Question 5: the ProxyJump form depends on a control-plane flag, so
keep the nested form as the documented default rather than the fallback.**
`tailssh.go:492` `LocalPortForwardingCallback: c.mayForwardLocalPortTo` and
`:547` `if c.finalAction != nil && c.finalAction.AllowLocalPortForwarding`
— `direct-tcpip` (what `ProxyJump`/`-J` opens) is allowed only when the
control plane sets that bit on the matched action. The tailnet policy
(`/data/projects/tailscale-admin/policy.hujson`) has a single `accept` rule
with no port-forwarding key, so the bit's value is whatever Tailscale's
control sets by default; the OSS tree cannot tell. The nested form `ssh
<jump> ssh <target>-lan` needs nothing from the control plane and the
design already puts the aliases and keys on every home-lab host, so it is
the more robust primary. Either way the step-7 test settles it empirically;
record which form passed. Also, for the nested form, the vps-side command
must pass `-o BatchMode=yes` through to the inner `ssh` (quote the inner
command), or an interactive prompt on the jump host turns the fallback into
a hang.

**N8. The `-lan` client config should pin `IdentitiesOnly yes` and the
identity file.** vps's `ubuntu` has only `id_ed25519`; the home-lab hosts'
`cwoolley` have only `id_ed25519` — fine today — but with
`StrictHostKeyChecking yes` and a dedicated `UserKnownHostsFile`, the one
remaining way for the alias to fail silently is the client offering an
unexpected key first after someone adds one. Cheap to pin now.

**N9. Question 4 confirmations.** `rp_filter` is `2` (loose) on hp and
gmktec (`/proc/sys/net/ipv4/conf/{all,default}/rp_filter`), `arp_ignore` and
`arp_announce` are `0`, `ip_nonlocal_bind` is `0` (irrelevant — `FreeBind`
is the per-socket `IP_FREEBIND`, which is what the socket unit sets). With
two addresses on one /24, a peer may ARP-learn the Wi-Fi address against the
wired MAC ("ARP flux"); traffic still lands on the host and the kernel
listener is address-, not device-bound, so it is served; replies leave by
the metric-100 wired route regardless of which address they carry, which
loose rp_filter tolerates. Correct and robust as designed — subject to S1.

**N10. Minor wording.** The design says the `00-` prefix sorts "before any
cloud-init drop-in"; there is none on these hosts (cloud-init disabled; the
directory does not exist on hp/gmktec and is empty on poweredge). The role
must create `/etc/ssh/sshd_config.d` (root 0755) at step 3 on hp/gmktec;
dpkg adopts the existing directory at unpack. The table's "archive
candidate —" for poweredge should read `3.8` (same pockets), which matters
because unattended-upgrades will take poweredge to `3.8` on its own.

## Answers to the design's questions

**1. Tailscale host-key selection.** Yes — the selection is a fixed set of
three absolute paths and nothing else. `ssh/tailssh/hostkeys.go` at
v1.102.2 (the version on all three hosts, `tailscale status --self --json`
→ `1.102.2-t6cac91817-g6ff0ddc72`) hard-codes `"/etc/ssh/ssh_host_" + typ +
"_key"` for `rsa`, `ecdsa`, `ed25519`, read only when `os.Geteuid() == 0`,
and falls back per type to `<varRoot>/ssh/ssh_host_<typ>_key`. It never
opens `/etc/ssh/sshd_config`, never runs `sshd -G`, and no file in
`ssh/tailssh/` references `/etc/ssh` other than that line (grep over
tailssh.go, session.go, user.go, incubator.go, listen.go, accept_env.go,
hostkeys.go). `AcceptEnv` for Tailscale SSH comes from the ACL rule
(`tailssh.go:1279` returns `r.AcceptEnv`), not from `sshd_config`, so
installing a `sshd_config` on hp/gmktec changes nothing Tailscale reads. An
sshd `HostKey` pointing at `/etc/ssh/lan-fallback/...` therefore cannot
affect what Tailscale SSH presents. Two caveats: the read is per connection
(`tailssh.go:516`), so any later appearance of one of the three paths takes
effect immediately, and it is per key type (S5). Port 22022 is never
intercepted by tailscaled: `ipn/ipnlocal/local.go` builds the intercept list
from `22` (when SSH is on), the web-client port and `serve` ports only.

**2. Postinst, triggers, generator, keygen.** No. `create_keys` creates a
key only for a path that `sshd -G` lists as `HostKey` and that does not yet
exist; with the role's explicit `HostKey`, `fill_default_server_options`
adds no defaults (`servconf.c:305`), so the listed set is the dedicated key
alone. The main config is installed by `create_sshdconfig` BEFORE
`create_keys`, so the Include is honoured on first install. There is no
triggers file. `sshd-keygen.service` is `ConditionFirstBoot=yes` and the
flag file is absent. `sshd-socket-generator` only translates the parsed
`ListenAddress` set into `ListenStream=` lines and never writes keys. The
only port-22 listener path is the generator's fallback to the packaged unit
when the drop-in is absent or unparsable (S2) — on first apply that is
caught by step 5's `sshd -t`, but it is the design's standing failure
direction thereafter. The postinst's own `restart ssh.socket` is a condition
no-op while `/etc/ssh/sshd_not_to_be_run` exists, and on a fresh install
`ssh.service` is NOT enabled (`deb-systemd-helper debian-installed
ssh.service` is false on first install), so only the socket is ever enabled
on hp/gmktec. One listener the design does not list does appear: systemd's
AF_UNIX `sshd-unix-local.socket` (N1), local-only.

**3. Disturbing tailscaled, the tailnet, k3s, networking.** No step can.
The system-wide side effects of the install are `systemd-sysusers`,
`systemd-tmpfiles --create openssh-server.conf` (`x /tmp/sshauth.*`), two
`systemctl daemon-reload`s, `deb-systemd-helper enable` symlinks, and the
condition-skipped socket start; `openssh-client` is upgraded in place (no
running process is touched; k3s's `refresh-node-status-kubeconfig` spawns a
fresh `ssh` per run). No sysctl, route, interface, firewall (`-P INPUT
ACCEPT` on all three, ufw off) or Tailscale state is written. `ssh.service`
has `KillMode=process`, so a restart on poweredge would not kill sessions
even if any existed (none do: all host-to-host SSH rides Tailscale SSH, and
the ansible control connection is Tailscale SSH too). `needrestart` is not
installed, so apt cannot restart anything else. The only things that could
have gone wrong are the two the design already fences (unattended-upgrades
racing the apt step; a poisoned `/etc/ssh/ssh_host_*`), plus S3 on
poweredge, which systemd's restart propagation happens to cover.

**4. LAN binding with FreeBind on two-interface hosts.** Correct as a
binding model (N9): `IP_FREEBIND` lets the socket bind the Wi-Fi lease when
it is absent at boot, loose `rp_filter` tolerates the asymmetric
address/interface pairing, and the listener is address-bound rather than
device-bound so ARP flux does not matter. The real weakness is not the two
interfaces but that every address involved is a DHCP lease (S1): FreeBind
makes a lease change silent on the server side, and the client-side literals
go stale at the same time.

**5. The vps jump path.** Sound in shape — vps has only tailnet reach, so
every route is through a home-lab host, and the design's two forms (ProxyJump
over Tailscale SSH's `direct-tcpip`; nested `ssh jump ssh target-lan`) cover
the two states of the control-plane forwarding bit. I would invert the
default (N7): the nested form is the one that depends on nothing the policy
file cannot show, and the step-7 test should record which form actually
passed. The ACL is a single `accept` rule from `autogroup:member` to
`autogroup:self` for `cwoolley`/`ubuntu`, so neither hop will meet a `check`
re-authentication prompt in BatchMode. The jump path also inherits S4: the
vps `ubuntu` key is in the rendered set, so that leg is fine.

**6. Missing.** S1 (lease pinning), S2 (fail-safe direction), S4 (the
MacBook key), S5 (three-type fingerprint compare), the AF_UNIX listener
(N1), the k3s positive control (N6), `IdentitiesOnly` (N8), and the
poweredge `ssh.service` enablement fact (S3), which the measured-state table
should record alongside "`ssh.socket` active".

REVIEW-COMPLETE: NO-BLOCKERS
