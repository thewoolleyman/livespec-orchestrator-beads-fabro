# Plan sessions in herdr: one named tab per plan

The maintainer coordinates plan sessions as herdr TABS whose tab label, Claude
session name (the `-n` value) and plan slug are identical, grouped under a
workspace named for the topic (on 2026-10-10 the `fabro` workspace held
`fabro-currency`, `kubernetes-sandbox-backend`, `k3s-on-gmktec-for-vps-usage`,
`gitops-deployment-discipline` and `factory-worker-nodes-gitops`). `herdr agent
list` is then the live roster, and "name the owning session" in AGENTS.md
§"Working with the maintainer" resolves to that label. This is the tab-shaped
sibling of `.ai/herdr-helper-sessions.md`, which covers helper PANES; a plan
session is a peer of the maintainer's own tabs, so here `tab create` is right.

The recipe that worked on 2026-10-10, run from inside herdr (`HERDR_ENV=1`):

```bash
out=$(herdr tab create --workspace <ws-id> --cwd /data/projects/<repo> --label <slug> --no-focus)
pane=$(echo "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["root_pane"]["pane_id"])')
herdr agent start <slug> --kind claude --pane "$pane" --timeout 240000 -- \
  --dangerously-skip-permissions --model 'fable[1m]' --effort high -n <slug>
herdr agent prompt <slug> "/livespec-orchestrator-beads-fabro:plan <slug>"
```

Three rules from that run:

1. **A herdr agent name must match `[a-z][a-z0-9_-]{0,31}`**, so a plan slug
   longer than 32 characters cannot carry the matching session name. Choose
   the slug with that limit in mind (`factory-worker-nodes-gitops` was chosen
   over `factory-worker-nodes-under-gitops` for exactly this reason). The
   canonicalization in the plan operation truncates at 64, so it will not
   catch this for you.
2. **Kill the old tmux session for the same plan first**, after reading its
   pane tail (`tmux capture-pane -p -t <slug> -S -40`) so the move records
   what it displaced, and confirm the claude process is gone by PID before
   starting the tab. Both were measured necessary: the process outlived
   `tmux kill-session` by a few seconds.
3. **Do not `--wait` on the resume prompt.** A strict plan resume parks on the
   which-action picker for the maintainer, which herdr reports as `done` or
   `blocked`, so a wait returns nothing useful and a long one blocks the
   sending turn.
