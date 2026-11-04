# 006 — LAN SSH recovery paths, verified live (2026-10-16)

Reference for reaching poweredge-xubuntu, hp-xubuntu and gmktec-xubuntu when
Tailscale is broken. The maintainer asked for this to be recorded so it can be
used if needed. Every claim below was measured on 2026-10-16 between about
06:40Z and 06:55Z. Design background is in note 004. The role is
`ansible/roles/lan_ssh_fallback` in livespec-dev-tooling, item
`livespec-dev-tooling-4yrfjd` (closed).

## What is running on each host

| Host | LAN fallback listener | Tailscale SSH |
|---|---|---|
| poweredge-xubuntu | 192.168.1.200:22022 | unchanged, `tailscaled` active |
| hp-xubuntu | 192.168.1.4:22022 | unchanged, `tailscaled` active |
| gmktec-xubuntu | 192.168.1.156:22022 | unchanged, `tailscaled` active |

- The listener is OpenSSH on the wired LAN address only, at port 22022, with
  its own host key at `/etc/ssh/lan-fallback/ssh_host_ed25519_key`.
- Nothing listens on port 22 except Tailscale SSH.
- Authentication is by key only: passwords and root logins are refused, and
  the only user allowed is `cwoolley`.
- Trusted keys are in `/etc/ssh/lan-fallback/authorized_keys/cwoolley`
  (managed by the role): the three hosts' `cwoolley` keys and the VPS key
  `ubuntu@vps.perch-rudd.ts.net`. The server ALSO reads
  `~cwoolley/.ssh/authorized_keys`. On poweredge only, that file holds the
  MacBook key `cwoolley@macbook-2026-06-24`.
- On all three hosts `ssh.socket` is enabled, so the listener should return
  after a reboot, and the packaged socket uses `FreeBind`. This is INFERRED
  FROM CONFIGURATION, NOT TESTED: no host has rebooted since the fallback was
  installed on 2026-10-15. Last boots: poweredge 2026-10-12, hp and gmktec
  2026-09-16.

## Path 1 — host to host over the LAN (proven, all six directions)

On any of the three hosts, `ssh <other>-lan` reaches the other two. The aliases
are in `/etc/ssh/ssh_config.d/50-lan-fallback.conf`, with strict host-key
checking against the role's own known_hosts.

| From → to | Far side saw `SSH_CONNECTION` |
|---|---|
| poweredge → hp | 192.168.1.200 → 192.168.1.4:22022 |
| poweredge → gmktec | 192.168.1.200 → 192.168.1.156:22022 |
| hp → poweredge | 192.168.1.4 → 192.168.1.200:22022 |
| hp → gmktec | 192.168.1.4 → 192.168.1.156:22022 |
| gmktec → poweredge | 192.168.1.156 → 192.168.1.200:22022 |
| gmktec → hp | 192.168.1.156 → 192.168.1.4:22022 |

Every source and destination is a LAN address on port 22022, so none of these
connections used Tailscale.

Use this when ONE or TWO hosts have lost Tailscale: reach any host that still
has it, then hop over the LAN. For example, from the VPS:
`ssh cwoolley@hp-xubuntu`, then `ssh poweredge-xubuntu-lan`. The VPS has no
`-lan` aliases of its own, so this two-step form is the route.

## Path 2 — the VPS reaches all three with NO Tailscale anywhere (proven)

This is for the case where Tailscale is down on all three hosts, or the tailnet
itself is down. A machine on the home LAN opens an outbound SSH connection to
the VPS over the public internet, with reverse forwards back to each host's
LAN listener. Nothing is needed on the router. Remote Login on that machine is
NOT needed: it only relays traffic.

On the MacBook (or another LAN machine whose key the VPS trusts), with the
maintainer's `vps` SSH alias, which reaches the VPS's public address:

```bash
ssh -N \
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -R 127.0.0.1:22200:192.168.1.200:22022 \
  -R 127.0.0.1:22204:192.168.1.4:22022 \
  -R 127.0.0.1:22256:192.168.1.156:22022 \
  vps
```

It prints nothing while it runs. Ctrl-C closes the tunnel and the three ports.
The forwards bind only to the VPS's loopback address, never its public
address. Port map: 22200 is poweredge, 22204 is hp and 22256 is gmktec.

Then, on the VPS, as `ubuntu`, whose key all three hosts trust:

```bash
ssh -p 22200 cwoolley@127.0.0.1   # poweredge-xubuntu
ssh -p 22204 cwoolley@127.0.0.1   # hp-xubuntu
ssh -p 22256 cwoolley@127.0.0.1   # gmktec-xubuntu
```

The first connection asks about the host key. Each host's LAN host key is
`/etc/ssh/lan-fallback/ssh_host_ed25519_key.pub` on that host. The test below
pinned all three in a throwaway known_hosts file and used
`StrictHostKeyChecking=yes`.

Measured result, 2026-10-16 at about 06:55Z, with the maintainer running the
tunnel from the MacBook:

| VPS port | Logged in to | Far side saw `SSH_CONNECTION` |
|---|---|---|
| 22200 | poweredge-xubuntu | 192.168.1.57 → 192.168.1.200:22022 |
| 22204 | hp-xubuntu | 192.168.1.57 → 192.168.1.4:22022 |
| 22256 | gmktec-xubuntu | 192.168.1.57 → 192.168.1.156:22022 |

How this shows Tailscale was not involved:

- 192.168.1.57 is the MacBook's LAN address, so each connection reached the
  host over the home LAN.
- On the VPS, the tunnel's own connection arrived at the public SSH port
  (66.94.121.15:22) from the home public IP, 73.231.243.71, not from a 100.x
  tailnet address. So the `vps` alias crosses the public internet.
- No tailnet peer advertises a route for 192.168.1.0/24, so the MacBook's
  traffic to the hosts could not have been routed through Tailscale.

## Path 3 — straight from the MacBook

The MacBook's key is trusted only on poweredge, through
`~cwoolley/.ssh/authorized_keys`, so this works only where it is accepted:

- `ssh -p 22022 cwoolley@192.168.1.200` from the home LAN reaches poweredge,
  if `cwoolley@macbook-2026-06-24` is the key on that MacBook (not yet
  confirmed).
- From poweredge, `ssh hp-xubuntu-lan` and `ssh gmktec-xubuntu-lan` reach the
  other two.

If poweredge itself is the host that is down, use Path 2, or a keyboard and
monitor on the host.

## Known gaps, not acted on (maintainer: not needed now)

- The MacBook's key is not in the role's managed key list, so it cannot reach
  hp or gmktec directly.
- The role's `authorized_keys.j2` comment says `~/.ssh/authorized_keys` "is not
  read by this server", but the rendered `AuthorizedKeysFile` line does read it.
  The comment and the configuration disagree.
- The VPS has no rendered `-lan` aliases. Note 004 planned them, with a jump
  through another host's tailnet name, but they are absent from
  `~ubuntu/.ssh/config`.
- Surviving a reboot has not been tested on any host.
