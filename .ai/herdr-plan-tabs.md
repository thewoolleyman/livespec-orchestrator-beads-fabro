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
  --dangerously-skip-permissions --model 'fable[1m]' --effort high -n <slug> \
  "/livespec-orchestrator-beads-fabro:plan <slug>"
```

The resume prompt rides the launch as Claude's trailing prompt argument. The 2026-10-10 run
typed it in afterwards with `herdr agent prompt <slug> ...`; that form is retired by the
2026-10-14 ruling in `.ai/herdr-helper-sessions.md`, because another session's pane is never
typed into, and later messages to the new session go through `SendMessage`. The
launch-argument form has not yet been re-measured through `herdr agent start`, so confirm
the session reached the plan picker before leaving it.

Measured 2026-10-20: `herdr agent start` returned
`{"error":{"code":"timeout","message":"timed out waiting for agent startup"}}` after its
240-second wait, but the plan session had started and was already working. A startup
timeout is therefore not a failed launch. Before concluding anything, read the pane with
`herdr pane read <pane-id> --lines 25`.

## Placing a tab: herdr CAN move tabs, through its socket API

**Do not tell the maintainer that herdr cannot move or place a tab.** Two sessions have
said so, and the maintainer had to correct it. The confusion has a specific cause:
- `herdr tab create` always APPENDS the new tab at the END of the workspace. It has no
  position option.
- The `herdr tab` command-line wrapper only offers `list`, `create`, `get`, `focus`,
  `rename` and `close`. It has no `move` subcommand.
- `herdr --skill` mentions `pane move` but never `tab move`.

The SOCKET API has a `tab.move` method, with params `{"tab_id": <id>, "insert_index": <n>}`.
`insert_index` is the 0-based position in the workspace's tab order, as `herdr tab list`
returns it. To place a new tab immediately to the RIGHT of your own:
- read your own position (`HERDR_TAB_ID`) in `herdr tab list --workspace "$HERDR_WORKSPACE_ID"`;
- move the new tab to that index plus one.

Measured 2026-10-20: `insert_index: 1` moved tab `w2H:tW` from the end to directly right of
`w2H:t2`, which was at index 0. The response is the reordered tab list.

```bash
python3 - <<'PY'
import json, os, socket
s = socket.socket(socket.AF_UNIX); s.connect(os.environ["HERDR_SOCKET_PATH"])
s.sendall((json.dumps({"id": "move-tab", "method": "tab.move",
    "params": {"tab_id": "<new-tab-id>", "insert_index": <your-index-plus-one>}}) + "\n").encode())
s.settimeout(10); buf = b""
while b"\n" not in buf:
    chunk = s.recv(65536)
    if not chunk: break
    buf += chunk
print(buf.decode())
PY
```

The general lesson: a command-line wrapper is not the whole API. Before reporting that herdr
"cannot" do something, check the full method list:

```bash
herdr api schema --json | grep -o '"tab\.[a-z_]*"' | sort -u
```

Swap `tab` for `pane`, `workspace` or `agent` to check those. The CLI's subcommand list is an
instrument that cannot show socket-only methods, so an absence there is not evidence.

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
