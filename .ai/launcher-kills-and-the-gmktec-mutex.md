# Killing a launcher can strand the gmktec launch mutex

Measured 2026-11-04. A dispatcher seat restarted a waiting launcher with
`kill -KILL` and the next launches stalled with a green fleet.

## What happened

The seat killed the first `hl-h2254o` launcher (`dispatch-dual-r681b.sh`) at
about 02:07Z, moments after it had taken the gmktec launch mutex. A SIGKILL
skips the launcher's `trap`, so neither the lock nor the ticket file was
released. `/run/user/1000/gmktec-launch-lock.d/holder` kept naming the dead pid
(`owner=... pid=3463725 item=hl-h2254o`).

The re-ticketed `hl-jfgwsi` and `hl-h2254o` then passed their launch-time
preflight at 02:16Z with the fleet green (13 of cap 16) and still sat in
"queue for the gmktec mutex". The launcher reaps a dead holder only when the
holder file is older than 900 s (`holder_dead()` in
`tmp/petri-canary/dispatch-dual-r681b.sh`), so the stall would have lasted
until about 02:22Z. The seat removed the stale holder by hand at about 02:17Z and
`hl-jfgwsi` took the mutex 20 seconds later.

A waiting ticket's owner asked why it was waiting on a fleet slot. The cause was
the seat's own stale lock, not capacity.

## What to do

- Prefer a plain `kill` (SIGTERM) when stopping a launcher or a
  `resume-capped.sh` ticket, so its trap releases the lock and its ticket file.
  Use SIGKILL only when it ignores SIGTERM.
- After ANY kill, read `/run/user/1000/gmktec-launch-lock.d/holder` and
  `ps -p <pid>`. If the named pid is dead, `rm -f` the holder file and `rmdir`
  the lock directory (what the launcher's own reaper does after 900 s), and
  `rm -f` the launcher's ticket file under
  `/run/user/1000/gmktec-launch-queue.d/`.
- Run each removal as its own top-level command. A `rm` inside a `bash -c`
  script is refused by the harness's removal safety check.
- When a head ticket has passed preflight on a green fleet and has been "queued
  for the gmktec mutex" for more than a minute, read the holder file BEFORE
  looking at capacity.
- zsh does not word-split an unquoted `$p` in `set -- $p`. Run launcher-start
  loops inside `bash -c`.
