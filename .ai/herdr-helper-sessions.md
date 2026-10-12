# Helper sessions in herdr: open as a split, close when consumed

A session sometimes needs a SEPARATELY STARTED agent to do one bounded job — an
independent critique of a proposal, a host-proof replay that must come from a different
session identity, a second opinion on an escalation. In herdr that helper is a PANE the
driving session opens, drives, reads, and closes. Three rules, each from a measured miss on
2026-10-10.

1. **Open it as a split of your own pane in the CURRENT tab, never as a new tab.** The
   maintainer coordinates sessions by tab, and a helper belongs visually under the session
   that owns it:

   ```bash
   new=$(herdr pane split <my-pane-id> --direction down --ratio 0.5 --cwd <repo> \
         | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["pane_id"])')
   ```

   `herdr tab create` makes a peer of the maintainer's own tabs; a helper opened that way
   was reported as "I do not see a pane" and had to be closed and redone.

2. **Launch the agent by typing ONE quoted command line into the split's shell.**
   `herdr pane run <pane> codex -m <model> "<prompt>"` word-splits the prompt into separate
   arguments, so `codex` prints its usage and never starts, while the pane's status stays
   `unknown` and looks merely slow. Use:

   ```bash
   herdr pane send-text "$new" "codex -m <model> 'Read tmp/<brief>.md in this repository and do exactly what it says.'"
   herdr pane send-keys "$new" enter
   herdr agent wait "$new" --timeout <ms>      # matches idle, done or blocked; always bound it
   ```

   Keep the prompt free of apostrophes (they break the single-quoted argument) and put the
   real instructions in a brief file under the gitignored `tmp/`, with the output path named
   in the brief so the result is a file, not a screen.

3. **Close the pane in the same turn you consume its output.** `herdr pane close "$new"`,
   then `herdr pane list` to confirm the tab holds only your pane. A helper pane left open
   after its file is read is the same slobbery as a worktree left behind after its pull
   request merged; the maintainer's words were "Clean up after yourself."

Do not type into a BUSY agent pane, and never into your own pane mid-turn. `send-text`
appends to the pane's input box, but a `send-keys enter` sent while the agent is working
does not submit it, so successive sends pile up on one line. Measured 2026-10-12: a
`/reload-plugins` and a follow-up prompt became the single command
`/reload-plugins <follow-up>`, and nothing ran until a human pressed Enter. Every herdr
call exited 0. Wait for the pane to go idle (`herdr agent wait <pane> --until idle --until
done`) and submit prompts with `herdr agent prompt`. For your own pane, run that wait in a
detached waiter and end your turn; the recipe is in `.ai/plugin-cache-lease-and-rebind.md`.
