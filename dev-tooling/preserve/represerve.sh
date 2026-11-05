#!/usr/bin/env bash
# usage: represerve.sh <UTC HH:MM> <FULL_RUN_ID> <alias-ref>   (alias e.g. bd-ib-<item>-<RUN12>; HH:MM in the past = now)
# Runs preserve_runs.sh at the given time, then mirrors its SHA to the alias ref under the same rule:
# never move an alias ref to a tip that does not contain its old value (write a SHA-suffixed sibling).
S=$(dirname "$0"); R=https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro
t=$(date -u -d "$(date -u +%F)T$1:00Z" +%s); now=$(date +%s); [ $t -gt $now ] && sleep $((t-now))
row=$(bash "$S/preserve_runs.sh" "$2" 2>>"${TMPDIR:-/tmp}/represerve_$2.err" | tail -1); echo "$row"
sha=$(printf '%s' "$row" | cut -f4); v=$(printf '%s' "$row" | cut -f6); r3=$(printf '%s' "$row" | cut -f3); [ -n "$r3" ] && [ "$r3" != - ] && R=$r3
if [ "${v%%+*}" = VERIFIED ]; then
  # Same working directory preserve_runs.sh used (PRESERVE_WORK, else its default).
  D=${PRESERVE_WORK:-${XDG_STATE_HOME:-$HOME/.local/state}/livespec-preserve}/$2.git; ref=refs/heads/preserve/$3
  old=$(git ls-remote $R "$ref" | cut -f1)
  if [ -n "$old" ] && [ "$old" != "$sha" ] && ! git -C "$D" merge-base --is-ancestor "$old" "$sha" 2>/dev/null; then
    ref=$ref-${sha:0:12}
  fi
  for pa in 1 2 3 4 5; do git -C "$D" push -q $R "+${sha}:${ref}" 2>$D.alias.err && break; sleep $((pa * 7 + RANDOM % 7)); done; grep -v '^remote:' $D.alias.err
  for _ in 1 2 3 4 5; do got=$(git ls-remote $R "$ref"); [ "${got%%[[:space:]]*}" = "$sha" ] && break; sleep 3; done
  echo "$got"
fi
