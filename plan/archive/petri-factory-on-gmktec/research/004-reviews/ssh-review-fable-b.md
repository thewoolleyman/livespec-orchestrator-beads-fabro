# Adversarial review B — `ssh-fallback-design.md` (direct LAN OpenSSH fallback)

Reviewer: independent, read-only, no part in the design. Date 2026-10-15.
Brief: assume the plan locks the maintainer out of a home-lab machine while
they are travelling with Tailscale SSH as their only access, and find how.

Method. Every host claim below was re-measured over
`ssh cwoolley@<host>.perch-rudd.ts.net '<read-only cmd>'` (cat, ls, ip,
systemctl is-*/cat/status, `sudo -n iptables -S`, `sudo -n ss -ltnp`, dpkg,
apt-cache, ssh-keygen -lf, `tailscale status --self --json`), plus
`ssh-keyscan` and two `ssh -W 127.0.0.1:1` channel probes from the control
node (they open a `direct-tcpip` channel to a closed loopback port; nothing is
reached and nothing changes). Sources read at the exact versions running on
the hosts: tailscale v1.102.2 `ssh/tailssh/{tailssh,hostkeys}.go`, Ubuntu
openssh `1:10.2p1-2ubuntu3.x` `debian/patches/sshd-socket-generator.patch`
and `systemd-socket-activation.patch` plus the dep8 test, the installed
`openssh-server.{preinst,postinst,config,prerm}` on poweredge, systemd v259
`src/core/socket.c`, `unit-dependency-atom.c` and `man/systemd.unit.xml`.
I did not read `ssh-review-fable-a.md`. Nothing on any host, repository or
ledger was changed.

Verdict first: I found NO path by which the design, executed as written,
changes what Tailscale SSH presents, breaks tailscaled, MagicDNS, routes,
interfaces, k3s, or the maintainer's current access. The findings below are
about verification gaps, durability of the fallback, and consumers the design
missed. None is a blocker.

## Ranked findings

### BLOCKER

None.

### SHOULD-FIX

**S1. The host-key verification must scan all three key types and must be a
login, not only a keyscan.** Tailscale SSH serves rsa, ecdsa and ed25519
(`hostkeys.go:32 keyTypes`), selects each type independently
(`hostkeys.go:59-86`: a type found under `/etc/ssh` is used, every other type
comes from `/var/lib/tailscale/ssh`), and re-reads the files on EVERY new
connection (`tailssh.go:516` `getHostKeys` inside `newConn`). Clients on this
fleet pin types other than ed25519: hp's `~cwoolley/.ssh/known_hosts` carries
hashed `ecdsa-sha2-nistp256` and `ssh-rsa` lines beside ed25519 ones
(`cat ~/.ssh/known_hosts | cut -c1-110` on hp). A role that records and
re-checks only "the fingerprint" (one type) can pass while a single stray
`/etc/ssh/ssh_host_rsa_key` has changed the RSA key hp presents to
RSA-pinning clients. Record and compare `ssh-keyscan -t rsa,ecdsa,ed25519`
for every host at step 1, 5, 6 and 7. Add one positive control after step 6:
a `BatchMode=yes` login over the tailnet from the control node (the Ansible
connection itself is one; say so explicitly so the proof is recorded).

**S2. The boot path is never exercised, and the generator's failure mode
silently reverts the socket to port 22.** `sshd-socket-generator` parses the
live config with sshd's own parser and writes
`/run/systemd/generator/ssh.socket.d/addresses.conf` as `ListenStream=`
(reset) followed by one `ListenStream=<addr>:<port>` per resolved
`ListenAddress` (generator source lines 167-170, 172-229). If the config does
not parse, `parse_server_config` is fatal, the generator exits non-zero, the
override is removed (lines 247-254) and ssh.socket falls back to the base
unit's `0.0.0.0:22` and `[::]:22` (`/usr/lib/systemd/system/ssh.socket` on
poweredge) while `ExecStartPre=/usr/sbin/sshd -t` fails the service. That is
a systemd-held port-22 listener with no sshd behind it — not a Tailscale
problem (Tailscale SSH is answered by netstack on `tailscale0` before the
kernel socket), but it breaks the design's "never port 22" invariant on the
next daemon-reload or boot, and nothing in the design re-checks after apply.
Add to the role's verification AND its drift report: `sshd -t` passes, the
generator override exists and equals the expected `ListenStream=` set, and
`systemctl show ssh.socket -p Listen` equals the LAN:22022 set. Then prove
the boot path once on the least critical host (a reboot through the
sanctioned path, when the maintainer chooses), because FreeBind, the
generator-at-boot and `ssh.service` (enabled in `multi-user.target.wants`
with `Requires=ssh.socket` via `ssh.service.requires/`) are only ever
combined at boot.

**S3. poweredge has a PENDING unattended security upgrade of openssh-server
(installed 1:10.2p1-2ubuntu3.6, candidate 3.8 from resolute-security;
`APT::Periodic::Unattended-Upgrade "1"`, `apt-daily*.timer` enabled and
active on all three hosts).** The 3.x preinst runs `deb-systemd-invoke stop
ssh.socket` and `stop ssh.service` on upgrade, and the postinst runs
`systemctl daemon-reload` then `deb-systemd-invoke restart ssh.socket`
(installed postinst, final block). So apt WILL restart poweredge's OpenSSH on
its own schedule: before the play (harmless), during the play if the fence is
not yet up, or after a rollback that left the drop-in in place (the restart
is condition-skipped only while `sshd_not_to_be_run` exists). Either upgrade
poweredge's openssh-server to 3.8 inside the same fence (then all three hosts
run one version and the unattended restart has already happened under
supervision), or state that the first unattended run after the play
restarts the listener and that the rollback keeps the off-switch in place.
The 3.7/3.8 changelog entries are CVE patches only; no maintscript change,
so the postinst read on poweredge is the one that will run.

**S4. A real consumer of poweredge's port 22 is dropped silently: the
MacBook key.** `~cwoolley/.ssh/authorized_keys` on poweredge holds three
keys — `ubuntu@vp…`, and two `cwoolley@…` keys (the design names them hp and
"a MacBook"). The design's `AuthorizedKeysFile
/etc/ssh/lan-fallback/authorized_keys/%u` stops OpenSSH consulting
`~/.ssh/authorized_keys` at all, and the rendered file carries only the three
hosts' cwoolley keys plus vps's ubuntu key. The MacBook is the one physical
client the maintainer will have on the LAN when they are home, i.e. the
client the fallback is for when the tailnet is down. Either render the
MacBook key into the file or state the exclusion. Related, unmeasurable from
here: `tailscale status` shows poweredge's public endpoint `73.231.243.71`
behind an upstream `10.0.0.168`; if the home router forwards WAN port 22 to
192.168.1.200, that path dies with the move (probably desirable, must be
known).

**S5. Listen only on the wired addresses, and pin them to what k3s already
pins.** Measured: the wired addresses are `valid_lft forever` on all three;
gmktec's Wi-Fi `wlp195s0` 192.168.1.66 is `dynamic … valid_lft 6829sec`
(`ip addr show wlp195s0`). The k3s units already hard-code the wired
addresses (`--server https://192.168.1.200:6443`, `--node-ip 192.168.1.4`,
`--node-ip 192.168.1.156`; flannel `vxlan … local 192.168.1.200 dev eno1`,
`local 192.168.1.4 dev enp11s0`, `local 192.168.1.156 dev eno1`), so the
fallback is exactly as durable as the cluster if it binds the same
addresses, and no more durable if it adds a lease-bound Wi-Fi one. A
preflight assertion that host_vars LAN address == live `ip -br addr` ==
the k3s unit's `--node-ip` (agents) / `--server` (poweredge) turns an
address drift into a refusal instead of a dead listener. (Design question 4
is answered below; this is the actionable half of it.)

**S6. `restart ssh.socket` depends on a link the preflight does not assert.**
systemd refuses to start a socket whose service is active
(`socket.c` v259:2634-2637, `"Socket service %s already active, refusing."`,
EBUSY). The restart works only because `ssh.service` carries
`Requires=ssh.socket` through `/etc/systemd/system/ssh.service.requires/
ssh.socket` (present on poweredge), and systemd.unit documents that a
Requires= dependent "will be stopped (or restarted) if one of the other
units is explicitly stopped (or restarted)". If that symlink is ever absent
(it is created by `deb-systemd-helper enable ssh.socket` from the socket's
`RequiredBy=ssh.service`), the restart fails EBUSY and the OLD sshd keeps
port 22 — and the design's step-6 `ss` check would catch it only if it is
written as an equality against the expected listener set, not as "no :22".
Assert the link in preflight, or run `systemctl restart ssh.socket
ssh.service` explicitly, and write the `ss` check as an exact set.

### NOTE

**N1. The design's central claim holds, and the exact mechanism is sharper
than stated.** `getSystemHostKeys` (`hostkeys.go:140-155`) reads only the
fixed paths `/etc/ssh/ssh_host_{rsa,ecdsa,ed25519}_key`, only when
tailscaled runs as root, and never consults sshd_config. Measured: keyscan
from the control node gives poweredge `SHA256:v3I/O4FRyavIf0kN40Tpb639hEW+X6
yGES1j/rNlqfc` == `/etc/ssh/ssh_host_ed25519_key.pub`, gmktec
`SHA256:vUCMIho6aIRyyY7exW2Is9Yz3h0/aX81uNgZ53103cQ` == its `/etc/ssh` key,
hp `SHA256:YEq8NepgBNWE+WKJ4VVuy6ZUXNsySXjVFBYLNvYjJdQ` with no `/etc/ssh`
keys and `/var/lib/tailscale/ssh/ssh_host_*` dated 2026-08-15. Because the
read is per connection, a key file appearing on hp takes effect on the next
connection with no restart; equally, the design's explicit `HostKey` cannot
influence it.

**N2. `sshd-keygen.service` is the one residual key generator on hp.** It
runs `ssh-keygen -A` (ALL default types into `/etc/ssh`, sshd_config
ignored), is enabled by the postinst, and is `WantedBy=ssh.socket`, so every
`systemctl restart ssh.socket` pulls it in. It is gated by
`ConditionFirstBoot=yes`, which systemd 259 documents as false "after the
manager has finished the startup phase", and the postinst's
`deb-systemd-invoke start sshd-keygen.service` is condition-skipped. The
residual is a future first boot (machine-id wiped, factory reset, or
`systemd.condition_first_boot=yes` on the kernel line): on hp that would
generate `/etc/ssh` keys and change every Tailscale SSH pin for hp. Record it
in the role's README; masking the unit on hp is a unit-state change and the
maintainer's call. cloud-init is installed on all three but disabled
(`/etc/cloud/cloud-init.disabled`, unit `not-found`), so its ssh module is
not a path.

**N3. The postinst cannot create `/etc/ssh/ssh_host_*` under this design, and
no trigger file exists.** `create_keys` generates only the paths
`sshd -G | sed -n 's/^hostkey //Ip'` lists; `fill_default_server_options`
adds the three defaults only when no `HostKey` is configured; the drop-in is
included first (`Include /etc/ssh/sshd_config.d/*.conf` is line 24 of
`/usr/share/openssh/sshd_config`, before `#HostKey` at 40-42, and the live
poweredge `sshd_config` starts with the same Include). `openssh-server.config`
(debconf) only greps `PermitRootLogin`/`PasswordAuthentication`. There is no
`openssh-server.triggers` in `/var/lib/dpkg/info/`. Ubuntu's sshd, when
systemd passes fds, uses them and skips its own `ListenAddress` binds
(`systemd-socket-activation.patch` sshd.c hunk, lines 245-260 of the
`+` text), so sshd never opens port 22 on its own either.

**N4. systemd's own `systemd-ssh-generator` adds a second sshd entry point
the design does not mention.** On poweredge `sshd-unix-local.socket` is
active (`ListenStream=/run/ssh-unix-local/socket`, `Accept=yes`) and spawns
`sshd@.service` = `/usr/sbin/sshd -i … -o "AuthorizedKeysFile
${CREDENTIALS_DIRECTORY}/ssh.ephemeral-authorized_keys-all
.ssh/authorized_keys"`. The same units will appear on hp and gmktec once
`/usr/sbin/sshd` exists and daemon-reload runs. It is AF_UNIX only (no vsock
device on bare metal), reachable as `ssh .host` locally, reads the drop-in's
`HostKey` but overrides `AuthorizedKeysFile` from the command line. Not a
network listener and not a Tailscale concern; the role's "exactly these
units/listeners" assertions and drift report must expect it.

**N5. No consumer reaches OpenSSH today, and the design is right about why.**
Every automated ssh toward the home lab names the tailnet short name or
FQDN: `refresh-node-status-kubeconfig` lines 85-88 (`ssh -o BatchMode=yes …
poweredge-xubuntu "sudo cat …"`), `refresh-gates-kubeconfig` lines 68-71
(same shape from vps as `ubuntu` via `sudo -u`), vps `~ubuntu/.ssh/config`
(`Host poweredge-xubuntu` / `Host gmktec-xubuntu`, `User cwoolley`),
`ansible/ansible.cfg` (`host_key_checking = False`) with
`ansible/inventory/legacy.yml` (`ansible_user: cwoolley`, no `ansible_port`,
no `ansible_host`), and `/etc/hosts` on all three carries only
`127.0.1.1 <self>`. Keyscan banners on port 22 of all three tailnet names
are `SSH-2.0-Tailscale`. Nothing in livespec-dev-tooling references
`ProxyJump`, `22022`, a LAN address, or a per-user `ssh_config` toward
these hosts (grep over the whole tree). Two consequences the design should
record: (a) `node_status_credential` pins poweredge's
`/etc/ssh/ssh_host_ed25519_key.pub` as "the host key every OpenSSH in this
pool offers" (`defaults/main.yml:71-77`) — after the move that file is the
key Tailscale SSH offers and NOT the key OpenSSH offers, so the comment
becomes wrong while the pin stays right; and (b) a future "remove the unused
OpenSSH host keys on poweredge/gmktec" cleanup would break every tailnet pin
for those hosts. Say so where the next reader will look.

**N6. ProxyJump through Tailscale SSH works on this tailnet, measured.**
tailssh registers `direct-tcpip` (`tailssh.go:501-502`) gated by
`c.finalAction.AllowLocalPortForwarding` and the `TS_SSH_DISABLE_FORWARDING`
knob (`tailssh.go:56, 546-552`); `/etc/default/tailscaled` carries
`FLAGS=""`. From the control node, `ssh -o BatchMode=yes -W 127.0.0.1:1
cwoolley@<host>.perch-rudd.ts.net` returned `channel 0: open failed: connect
failed: dial tcp 127.0.0.1:1: connect: connection refused` on ALL THREE
hosts — the channel opened and tailscaled dialled from the host's own stack
(a policy refusal reads `administratively prohibited`). So form 1 is live
today for vps→{poweredge,hp,gmktec}. Render the jump as
`ProxyJump cwoolley@<host>.perch-rudd.ts.net` with the user explicit: the
vps `~/.ssh/config` stanzas match the short names only, and user config is
read before `/etc/ssh/ssh_config.d/`. Form 2 (nested ssh) is a correct
fallback and the only one if the ACL ever moves to `check` mode.

**N7. `daemon-reload` and `restart ssh.socket` on poweredge cannot touch
k3s.** `daemon-reload` re-runs generators and re-reads unit files; it
enqueues no job. `k3s.service` is `Type=notify`, `KillMode=process`,
`Delegate=yes`, `Restart=always`; its listeners (`*:6443`, `*:10250`,
`127.0.0.1:6444`…) and flannel's vxlan (`local 192.168.1.200 dev eno1`,
UDP 8472) never involve port 22 or sshd. `ssh.service` is `KillMode=process`,
so the restart replaces only the listener process. The INPUT chains measured
on poweredge and hp (`ts-input`, `KUBE-ROUTER-INPUT`, `KUBE-NODEPORTS`,
`KUBE-PROXY-FIREWALL`, `KUBE-EXTERNAL-SERVICES`, `KUBE-FIREWALL`) match
tailnet sources, cluster IPs, node-port ranges, pod sources and loopback
spoofing only; none can match LAN→LAN:22022, and INPUT policy is ACCEPT.

**N8. The apt fence inherited from the Docker design has one host-side gap.**
The timers are restarted by the controller's `always` block; if the control
node loses the host mid-play (the play itself rides Tailscale SSH), the
block cannot run and `apt-daily.timer`/`apt-daily-upgrade.timer` stay
stopped until reboot — security updates silently paused. A host-side
restore (`systemd-run --on-active=<n>m systemctl start apt-daily.timer
apt-daily-upgrade.timer`, armed before the stop and cancelled on success) is
cheap. An interrupted dpkg on hp/gmktec leaves openssh-client/-server
half-configured with the off-switch present, so nothing listens; the k3s
refresh keeps working because dpkg replaces `/usr/bin/ssh` by rename; a later
`dpkg --configure -a` re-runs the postinst, still inert. Recoverable over
Tailscale SSH, which the transaction never touches.

**N9. Rollback semantics should be stated.** On poweredge the rollback
(`touch sshd_not_to_be_run`, stop both units) leaves OpenSSH OFF, not
restored to port 22, and leaves the drop-in on disk; both are acceptable
(nothing uses OpenSSH today, and the off-switch also neutralises S3's
unattended restart) but the design says "nothing else to restore", which
reads as "restored".

**N10. Verification shape.** Step 6's `ss -ltn` must run as root to show
owners and must be an equality against the expected listener set (LAN
addresses × 22022, no `:22`, no tailnet address), not a negative grep —
otherwise S6's EBUSY case and S2's generator case both pass. Step 7's
`is-active` for `k3s`/`k3s-agent` proves the unit, not the cluster; add a
`kubectl get nodes` read on poweredge showing all three `Ready` after the
poweredge steps (the fleet hook's own allowed example). The rendered
known_hosts must use `[192.168.1.x]:22022` (non-22 port form) — the design
already says so; keep `HashKnownHosts` out of that file so it stays
diffable.

**N11. Minor.** `StrictModes` walks the `AuthorizedKeysFile` path to `/`
checking owner root/user and no group/world write; root-owned 0755 dirs and
a 0644 file pass. `AllowTcpForwarding yes` on the LAN sshd is not needed by
either vps form; harmless. The `00-` ordering argument against a cloud-init
drop-in is moot (cloud-init disabled) but costs nothing. The role's
generated `~cwoolley/.ssh/id_ed25519` on poweredge is a new per-user file;
`node_status_credential`/`gates_kubeconfig` do not run on poweredge, so no
consumer reads it.

## Answers to the design's questions

**1. Does Tailscale SSH select its host keys only from the fixed
`/etc/ssh/ssh_host_{rsa,ecdsa,ed25519}_key` paths, then its own store?**
Yes. `getHostKeys` (`hostkeys.go:36-42`) calls `getSystemHostKeys` only when
euid is 0, and that function (`:140-155`) iterates the three fixed filenames,
skipping any that are missing, empty or unparsable; `getTailscaleHostKeys`
(`:59-86`) then fills each missing TYPE from `<varRoot>/ssh/ssh_host_<type>_
key`, generating it if absent. sshd_config is never read. The selection runs
inside `newConn` (`tailssh.go:516`), i.e. on every incoming connection, so
the presented key follows the filesystem immediately in both directions. An
sshd `HostKey` directive pointing elsewhere therefore cannot change what
Tailscale SSH presents; only the appearance or removal of those exact files
can. The measured fingerprints (N1) confirm the per-host state the design
tabulates. One refinement to the design's wording: selection is per type,
so a partial set under `/etc/ssh` changes only the matching types (S1).

**2. Can anything in the 3.8 postinst, its triggers or the generator still
create `/etc/ssh/ssh_host_*` keys or open a port-22 listener?** Not under
this design. `create_keys` creates only paths that `sshd -G` lists as
`HostKey`; with the drop-in included first, that is only the lan-fallback
key, and the design generates it beforehand so even that path is a no-op.
`sshd-keygen.service` (`ssh-keygen -A`) is the only unconditional generator
and is gated by `ConditionFirstBoot=yes` (N2). No `triggers` file exists;
`openssh-server.config` only reads two debconf options. The generator uses
sshd's own parser, so `ListenAddress 192.168.1.x:22022` is handled exactly
as sshd handles it (the dep8 test covers `ListenAddress` with and without
`Port`), and `fill_default_server_options` adds `0.0.0.0`/`::` only when no
`ListenAddress` is configured, so no port-22 entry is emitted. Its one bad
path is a config that fails to parse: the override is then removed and the
BASE unit's port-22 listeners return at the next daemon-reload or boot (S2).
Ubuntu's sshd never binds port 22 itself when fds are passed (N3), and with
`sshd_not_to_be_run` present every unit start in the postinst is
condition-skipped, so during steps 2-5 nothing can listen.

**3. Is any step able to disturb tailscaled, the tailnet path, k3s, or the
hosts' networking?** No step writes a route, address, interface, sysctl,
firewall rule, resolver setting or Tailscale state, and I could not
construct one that does so indirectly. Tailscale SSH is served by netstack
on `tailscale0`, so a kernel socket on port 22 appearing or disappearing is
invisible to it (poweredge has had both coexisting since August).
`daemon-reload` enqueues no jobs; `restart ssh.socket` propagates only to
`ssh.service` via `Requires=` (S6) and replaces one listener process
(`KillMode=process`). The apt transaction installs/upgrades
openssh-{client,sftp-server,server} only (`apt-cache depends` on hp shows
every other dependency already satisfied; recommends off); `needrestart` is
not installed on any host (`dpkg -l needrestart` → `un`), so no unrelated
service restart rides the transaction. The iptables INPUT chains cannot
match the new traffic (N7). The two things that can go wrong are
OpenSSH-local (S2's bad-config revert, S3's unattended restart) and
process-local (N8's stranded timers). The play's own transport is Tailscale
SSH, so a tailscaled failure strands the play rather than the play causing
one.

**4. Is binding to the LAN addresses with FreeBind correct and robust, given
two interfaces on the same /24 on hp and gmktec?** Correct, with one
simplification recommended. `FreeBind=yes` is in the base `ssh.socket` and
the generator's override sets only `ListenStream=`, so it is preserved; a
bind to an address not yet present succeeds and receives once the address
is configured. The addresses are numeric, so the generator needs no DNS at
early boot. On hp and gmktec `arp_ignore=0`, `arp_announce=0` and
`rp_filter=2` (loose) are measured: a connection to the wired address may be
answered by the Wi-Fi NIC's ARP reply and replies leave by the metric-100
wired route whichever interface received the SYN — asymmetric at layer 2,
correct at layer 3, and the kernel's weak host model accepts it. It is
robust for the wired addresses, which are `valid_lft forever` and are the
same addresses k3s pins. It is only as robust as a DHCP lease for gmktec's
Wi-Fi address (`valid_lft 6829sec`); listing it buys nothing the wired
listener does not and invites a stale listener and a stale known_hosts
line, so bind the wired addresses only and assert them against the k3s units
in preflight (S5).

**5. Anything missing.** In priority order: the all-types host-key scan and a
login control (S1); a boot proof and a drift check for the generator output
(S2); the pending openssh-server 3.8 security upgrade on poweredge and its
unattended restart (S3); the MacBook key and any router port-forward to
poweredge:22 (S4); wired-only listeners pinned to the k3s addresses (S5);
the `Requires` link assertion and an exact-set `ss` check (S6); the
`sshd-unix-local.socket` units the role must expect (N4); the
`node_status_credential` comment that becomes wrong and the "do not delete
poweredge's unused OpenSSH host keys" hazard (N5); explicit
`cwoolley@<fqdn>` in the rendered `ProxyJump` (N6); a host-side timer
restore (N8); and a stated rollback meaning (N9). None of these changes the
design's shape; they close the gaps between what it asserts and what its
checks can prove.

REVIEW-COMPLETE: NO-BLOCKERS
