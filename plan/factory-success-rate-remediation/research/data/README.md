# Raw evidence corpus — failure-telemetry investigation (2026-07-23)

Collected during the 2026-07-23 factory-failure investigation (see
`../failure-telemetry-2026-07-23.md` for the analysis these files
support). Everything here is regenerable from live systems; it is
committed so the analysis stays auditable after run-history churn.

| File | What it is | How to regenerate |
|---|---|---|
| `failures.tsv` | One row per non-successful `implement-work-item` run: run id, repo, terminal mechanism, originating node | Derived from `fabro_all_runs.json` + per-run inspects |
| `fail_detail.tsv` | Same rows with the raw `failure_signature` / `conclusion.failure.detail` strings | Same |
| `fail_ids.txt` | The bare run-id list of the 55 non-successes | Same |
| `hctool.sh` | Honeycomb hosted-MCP JSON-RPC helper (`tools/call` wrapper). Reads `HONEYCOMB_MCP_API_KEY_LIVESPEC` from env — run under `with-livespec-env.sh`; contains NO secret | n/a (tool, not data) |
| `raw-archive.tar.gz` | `fabro_all_runs.json` (full 265-run census, `fabro --json ps -a`), `closed.json` (beads closed-item dump used for the merged-item lower bound), `insp/` (57 per-run `fabro --json inspect` outputs for the failures), `insp_sample.json`, `headers.txt`, `init-body.txt` (Honeycomb MCP handshake notes) | `FABRO_SERVER=http://127.0.0.1:32276 ~/.fabro/bin/fabro --json ps -a`; `fabro --json inspect <id>` per id in `fail_ids.txt`; `with-livespec-env.sh bd list --status closed --json` |

Census window: 2026-06-11 → 2026-07-23. The fabro server's durable
state is the authoritative source; Honeycomb (`fabro` dataset, team
`thewoolleyweb`, env `livespec`) only covers ~2026-07-17 onward at ~74%
run coverage — see the access notes in the parent analysis and ledger
item `bd-ib-elvxv2`.
