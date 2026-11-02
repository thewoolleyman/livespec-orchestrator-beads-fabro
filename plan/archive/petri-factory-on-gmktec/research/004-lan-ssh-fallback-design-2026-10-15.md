# Direct LAN OpenSSH fallback between poweredge, hp and gmktec — design

Date: 2026-10-15. Plan `petri-factory-on-gmktec` (epic `bd-ib-fyozyd`). This is
the plan's FIRST step, by the maintainer's instruction of 2026-10-15:

> "The three machines, PowerEdge, HP, and GMKTech, are all in my home lab on the
> same local subnet. [...] In order to provide a fail-safe fallback, each of
> these machines should be able to reach each other via direct SSH without
> involving [Tailscale] and should be running an open SSH server accordingly.
> But do not touch any of the tailscale [SSH] agent config. Leave it exactly as
> is. [...] continue to do it with the absolute utmost care to avoid breaking
> networking on any of the machines or losing access."
> "And be aware that the VPS is actually a VPS in the cloud so it is not on the
> same subnet. Anything that it drives would have to hop through an SSH tunnel
> on one of the other machines."
> "And make sure you run the open SSH servers in a way that does not conflict
> with Tailscale at all. Run it at a non-standard port and do anything else you
> have to do to avoid conflicting with the Tailscale SSH."

(Bracketed words are the session's reading of voice-dictation: "Telnet" and
"tailscale essence agent" as Tailscale and Tailscale SSH.)

## Measured state (2026-10-15, read-only)

| | poweredge-xubuntu | hp-xubuntu | gmktec-xubuntu |
| --- | --- | --- | --- |
| LAN addresses | eno1 192.168.1.200 | enp11s0 192.168.1.4, wlp10s0 192.168.1.54 | eno1 192.168.1.156, wlp195s0 192.168.1.66 |
| openssh-server | installed 1:10.2p1-2ubuntu3.6, `ssh.socket` active on 0.0.0.0:22 and [::]:22, no sshd_config.d drop-ins, no OpenSSH login in the last 30 days of journal | not installed (client 3.6) | not installed (client 3.6) |
| archive candidate | — | 1:10.2p1-2ubuntu3.8 | 1:10.2p1-2ubuntu3.8 |
| tailnet port 22 banner | `SSH-2.0-Tailscale` | `SSH-2.0-Tailscale` | `SSH-2.0-Tailscale` |
| host key Tailscale SSH presents | equals `/etc/ssh/ssh_host_ed25519_key` | from `/var/lib/tailscale/ssh/` (no `/etc/ssh/ssh_host_*`) | equals `/etc/ssh/ssh_host_ed25519_key` (created 2026-08-17) |
| cwoolley key | none | `id_ed25519` | `id_ed25519` |
| cwoolley authorized_keys | vps ubuntu key, a MacBook key, hp key | none file | empty |
| ufw | `ENABLED=no` | `ENABLED=no` | `ENABLED=no` |
| iptables INPUT policy | ACCEPT | ACCEPT | ACCEPT |
| port 22022 | free | free | free |

Every peer short name (`poweredge-xubuntu`, `hp-xubuntu`, ...) resolves through
MagicDNS to the tailnet address, so all current host-to-host SSH (including the
k3s agents' node-status credential refresh, which runs `ssh poweredge-xubuntu`)
rides Tailscale SSH on port 22 and never reaches an OpenSSH daemon. The control
node `vps` is a cloud host, not on the LAN; it reaches the three only over the
tailnet.

From poweredge's installed `openssh-server.postinst`: `create_keys` generates
`/etc/ssh/ssh_host_{rsa,ecdsa,ed25519}_key` ONLY for paths that `sshd -G`
lists as `HostKey`; `sshd-keygen.service` has `ConditionFirstBoot=yes`; the
packaged `ssh.socket` carries `ConditionPathExists=!/etc/ssh/sshd_not_to_be_run`
and `FreeBind=yes`; `sshd-socket-generator` derives the socket's listen
addresses from `sshd -G` on every daemon-reload; the postinst restarts
`ssh.socket` after a daemon-reload when the socket is enabled.

## The conflict this design must avoid, found by measurement

Tailscale SSH presents the system's `/etc/ssh/ssh_host_*_key` host keys when
they exist, and its own keys under `/var/lib/tailscale/ssh/` otherwise. hp has
no `/etc/ssh` host keys. A default openssh-server install on hp would generate
them, and Tailscale SSH on hp would then present a DIFFERENT host key on the
tailnet: every `known_hosts` pin for hp's tailnet name (on vps, poweredge,
gmktec and anywhere else) would fail with "host identification has changed",
and every `BatchMode` ssh to hp would stop. That is a Tailscale-visible change
made without touching Tailscale's configuration, and it is excluded.

## Design

A new gitops role `lan_ssh_fallback` in livespec-dev-tooling, a host group
`home_lab` (the three hosts; membership in the inventory, LAN addresses in
host_vars), and a play in a new playbook targeting that group plus a client-
only play for `dev_hosts`. No machine name appears in the role or playbook.

**OpenSSH's identity and listeners are wholly separate from Tailscale SSH's:**

- Port `22022` on LAN addresses only, never port 22 and never the tailnet
  address. `/etc/ssh/sshd_config.d/00-lan-fallback.conf`:

  ```
  ListenAddress 192.168.1.156:22022   # one line per host_vars LAN address
  ListenAddress 192.168.1.66:22022
  HostKey /etc/ssh/lan-fallback/ssh_host_ed25519_key
  AuthorizedKeysFile /etc/ssh/lan-fallback/authorized_keys/%u
  PasswordAuthentication no
  KbdInteractiveAuthentication no
  PermitRootLogin no
  AllowUsers cwoolley
  PubkeyAuthentication yes
  AllowTcpForwarding yes
  X11Forwarding no
  ```

  `00-` sorts before any cloud-init drop-in, and sshd takes the first value per
  keyword. The packaged `ssh.socket` already sets `FreeBind=yes`, so a Wi-Fi
  address that is absent at a boot does not stop the socket from binding the
  wired one.
- Because the drop-in names an explicit `HostKey`, `sshd -G` lists ONLY that
  key, so the postinst generates NONE of `/etc/ssh/ssh_host_*_key`. The role
  generates `/etc/ssh/lan-fallback/ssh_host_ed25519_key` itself beforehand, if
  absent, and never replaces it. On poweredge and gmktec the existing
  `/etc/ssh/ssh_host_*` keys are left in place untouched (Tailscale SSH presents
  them); OpenSSH simply stops using them.
- Authorized keys live in a root-owned, gitops-rendered file
  `/etc/ssh/lan-fallback/authorized_keys/cwoolley` (mode 0644): the cwoolley
  public key of each of the three hosts plus vps's `ubuntu` key. Nobody's
  `~/.ssh/authorized_keys` is touched.
- poweredge, which has no cwoolley key, gets one generated by the role
  (`ssh-keygen` as cwoolley, only if absent, never replaced). The private keys
  never leave their hosts; the role only reads the `.pub` files.

**Order on a host without openssh-server (hp, gmktec) — inert until proven:**

1. Preflight (read-only, refuse on failure): `tailscaled` active; the host's
   tailnet SSH presents the same host-key fingerprint the role recorded at the
   start of the run (`ssh-keyscan` from the control node); INPUT policy and
   ufw state as recorded above; port 22022 free; no `/etc/ssh/sshd_config.d`
   file other than this role's.
2. `touch /etc/ssh/sshd_not_to_be_run` (the package's own off switch).
3. Generate the dedicated host key; write the drop-in and the authorized-keys
   file.
4. Install `openssh-server` (and the `openssh-client` and
   `openssh-sftp-server` it requires at the same version) with recommends off
   and `--no-remove`, under the same apt fence as the Docker design (stop
   `apt-daily*.timer`, wait for no apt/dpkg process, simulate and refuse any
   other `Inst`, `Remv` or upgrade beyond these three, restart the timers in an
   `always` block). With the off switch present, the postinst's socket restart
   is condition-skipped: nothing listens.
5. Verify, still inert: `sshd -t` passes; `sshd -G` lists exactly the
   dedicated `HostKey`, the LAN `ListenAddress`es, the auth settings above;
   `/etc/ssh/ssh_host_*` on hp still do not exist, and on the others still hash
   to the recorded values; the tailnet SSH host-key fingerprint from the
   control node is unchanged.
6. Remove `/etc/ssh/sshd_not_to_be_run`, `systemctl daemon-reload` (re-runs
   `sshd-socket-generator`), `systemctl restart ssh.socket`; the socket listens
   only on the LAN addresses at 22022 (`ss -ltn` shows no `:22` socket owned by
   systemd/sshd and none on the tailnet address).
7. Verify end to end: from each other home-lab host, `ssh -p 22022
   cwoolley@<lan-ip> true` with `StrictHostKeyChecking=yes` against the
   gitops-rendered known_hosts; from vps, the jump path below; and once more
   the tailnet SSH host-key fingerprint is unchanged and `tailscaled`,
   `k3s-agent`/`k3s` and the LLM service are active.

**On poweredge (OpenSSH already running on port 22):** steps 1, 3 and 5-7, with
the drop-in moving OpenSSH from 0.0.0.0:22 and [::]:22 to the LAN address at
22022. Nothing reaches poweredge's OpenSSH today (all traffic to its port 22
over the tailnet is answered by Tailscale SSH; no OpenSSH login in 30 days).
The `systemctl restart ssh.socket` cannot affect Tailscale SSH, which is
served by tailscaled's own network stack.

**Rollback** (any verification failure after step 6): `touch
/etc/ssh/sshd_not_to_be_run`, `systemctl stop ssh.socket ssh.service`. No
firewall, interface, route, sysctl or Tailscale state is changed at any step,
so there is nothing else to restore; the dead-man timer of the Docker design is
not needed here.

**Client side.** `/etc/ssh/ssh_config.d/50-lan-fallback.conf` on each home-lab
host and on vps, rendered from the inventory: `Host <name>-lan` aliases with
`HostName <wired LAN address>`, `Port 22022`, `User cwoolley`,
`UserKnownHostsFile /etc/ssh/lan-fallback/known_hosts` (rendered from each
host's dedicated host public key, entries `[192.168.1.x]:22022`), and
`StrictHostKeyChecking yes`. On vps every alias also carries `ProxyJump` via
a different home-lab host's TAILNET name (Tailscale SSH on the jump host
forwards the TCP stream), with a documented second form for when Tailscale SSH
port forwarding is refused: `ssh <jump-host> ssh <target>-lan` (nested ssh with
the jump host's own key). Both forms are tested at step 7.

## What the fallback does and does not cover

It covers: any one host whose tailnet path is broken, as long as one other
home-lab host is reachable from vps over the tailnet and both are on the LAN.
It does not cover: all three tailnet paths broken at once (vps has no route to
the LAN), or a host whose LAN interface is down.

## Questions for the reviewers

1. Does Tailscale SSH select its host keys only from the fixed
   `/etc/ssh/ssh_host_{rsa,ecdsa,ed25519}_key` paths (then its own store), so
   that an sshd `HostKey` directive pointing elsewhere cannot change what
   Tailscale SSH presents? (tailscale source: `ssh/tailssh`.)
2. Can anything in the openssh-server 1:10.2p1-2ubuntu3.8 postinst, its
   triggers or `sshd-socket-generator` still create `/etc/ssh/ssh_host_*` keys
   or open a port-22 listener under this design?
3. Is any step able to disturb tailscaled, the tailnet path, k3s, or the hosts'
   networking?
4. Is binding to the LAN addresses (with FreeBind) correct and robust, given
   two interfaces on the same /24 on hp and gmktec?
5. Anything missing.
