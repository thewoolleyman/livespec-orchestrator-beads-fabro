# 004 — Option D implementation design for bd-ib-jrawlp (2026-11-11)

Written by claude:dispatch-payload-packaging when hand-landing bd-ib-jrawlp. The coordinator ruled the hand-land at about
11:05Z, after factory run 01M74SVXDEMF ended BLOCKED. The governing clause is spec v345, contracts.md §"Self-contained plugin
dispatch": "Helper programs are fetched in the sandbox from the dispatching build's own commit".

## Measurements, 2026-11-11, master 3825b0d35

What the size gate renders for this repository's implement-work-item overlay, representative case, with the gate's GitHub
App env set: 379,640 B in total, of which 285,276 B is step `env` values and 36,717 B is step scripts. The largest parts:

| Payload | Bytes | Kind |
|---|---|---|
| gh-refresh support archive, 4 chunks | 184,168 | gzip tarball of `_vendor` runtime modules, base64 |
| 18 packed helper programs (carry-forward 24,123; commit runner 18,311; proof grade 15,259; ...) | ~97,000 | gzip+base64 per helper |
| credential-use guard script, in the environment table | 17,387 | JSON string |
| proof-capture launcher and hooks, inline in a step script | ~6,400 | shell-quoted text |

The gate's measured worst case adds a 160,000 B dod_gate subject, which is per-dispatch data and stays inline.

Without the App env, gh-refresh does not render at all, and the overlay is 185,716 B. Any measurement script must set
`GITHUB_APP_ID` and `GITHUB_PRIVATE_KEY` the way `dev-tooling/checks/materialized_workflow_toml_size.py` does.

Forge operations timed from vmi3006760 against github.com:

- A reachability probe, `git fetch --depth=1 --filter=tree:0 --no-tags <repo> <sha>` into a scratch bare repository, took
  0.52 s. An unknown commit fails with `upload-pack: not our ref`. `git ls-remote <repo> <sha>` is NOT a reachability test,
  because ls-remote matches ref NAMES, so it fails for every commit. The factory draft used it.
- The sandbox fetch, a sparse no-cone checkout of `/.claude-plugin/scripts/` and `/.claude-plugin/.fabro/` followed by
  `fetch --depth=1 --filter=blob:none` and `checkout --detach FETCH_HEAD`, took 0.68 s to fetch and 1.84 s to check out.

## Decisions

1. **Build identity.** The commit is the installed build's `gitCommitSha` in `~/.claude/plugins/installed_plugins.json`:
   the entry whose `installPath` equals the executing payload root. Every cached install records it (checked for all 13
   project registrations). A root that is a git checkout falls back to `git rev-parse HEAD`. A root with neither yields no
   identity, and the dispatch is refused. The repository is `RELEASE_REPOSITORY_URL`. The factory draft read
   `git rev-parse` on the cache directory, which is not a checkout, so every real dispatch would have been refused.
2. **Reachability refusal.** A pre-dispatch-wall refusal runs before any claim is written, journaled with the commit. The
   probe is the 0.52 s commit-only fetch above, with a bounded timeout. Its runner is injectable, and an autouse test
   fixture stubs it as reachable in every test that does not test it. That answers the coordinator's 2026-11-11 finding
   that run 01M74SVXDEMF's Green hook ran for more than 2 h, because the overlay tests reached an unstubbed forge probe.
3. **Manifest.** One JSON env value, `LIVESPEC_DISPATCH_HELPER_MANIFEST`, carried by the fetch step. It holds
   `{repository, commit, helpers: [{name, path, mode, sha256}]}`. `path` is relative to the helper's named sandbox root,
   which the materializer resolves at run time exactly as today's steps do: the plugins root
   `${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}`, the gh-refresh root, and `/workspace/.livespec`.
4. **One fetch step, first among the Dispatcher steps.** Its script is short and inlines no helper source. It fetches as
   measured above, then runs the checkout's own materializer under `PYTHONPATH=<checkout>/.claude-plugin/scripts:<checkout>/.claude-plugin/scripts/_vendor`.
   Every failure exits non-zero with `LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH: <helper>: <reason>`: a commit that cannot
   be fetched, a source path missing at that commit, or a composed digest that differs. Because it is an ordinary step, the
   setup-node splice makes it a `run_prepare_<N>` node, so it re-runs on resume onto a re-acquired sandbox.
5. **One helper registry.** It names every Dispatcher-composed helper: its name, root, relative path, mode, and the
   composer that produces its bytes. The Dispatcher digests the registry's bytes, and the materializer writes and verifies
   the same registry's bytes. The gh-refresh bundle stops being an archive: its vendored files are copied from the checkout
   file by file, each one digested.
6. **The consuming steps stay and lose only their payload writes.** A step that runs the plugin-cache gate, unpacks gh,
   runs the run-from clones, and so on keeps its action lines. The `pack_payload` path remains only for per-dispatch data:
   the dod_gate subject and the pull-request body.
7. **No legacy inline branch.** The overlay always renders the fetch shape. The factory draft kept the inline shape
   whenever no source was passed, which would have left the size gate measuring the old shape and kept dead code alive.

## Factory draft reused

needs-human/3b503213 at 3a6a08261 is 5 files, +480/-4. Its manifest and materializer skeleton are reused. These parts are
replaced: the identity read (decision 1), the ls-remote probe (decision 2), the 11-helper coverage (decision 5), the
`assert`-based failure (it disappears under `python -O`), and the legacy branch (decision 7).
