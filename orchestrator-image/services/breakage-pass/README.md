# `breakage-pass` host timer

This is the host timer for the scheduled-workflow breakage pass. GitHub Actions
runners cannot reach the repository's Dolt tenant, so the host reads the latest
completed watched workflow run and files failed jobs through the normal capture
seam. It runs every 30 minutes; each command verdict is retained in the systemd
journal.

Install it on the dev host (not in a Fabro sandbox):

```bash
sudo ./install.sh --repo /data/projects/livespec-orchestrator-beads-fabro
```

The installer refuses an unavailable environment wrapper, preventing a timer
that would lack `BEADS_DOLT_PASSWORD`. Verify the installed schedule with:

```bash
systemctl list-timers breakage-pass.timer --no-pager
journalctl -u breakage-pass.service -n 50 --no-pager
```
