"""In-sandbox Claude plugin-cache materialization gate and per-run build pin.

WHAT THIS DEFENDS AGAINST (bd-ib-dbqb, recurring as bd-ib-bb41.9). A Fabro
sandbox's Claude plugin registry can name an orchestrator plugin build whose
cache directory is INCOMPLETE or absent entirely. Measured 2026-09-07 inside
`fabro-run-01M1XFXWDFNEKFFMBDVNK8P9PQ`: `installed_plugins.json` named build
`59348141199a` at an `installPath` under `~/.claude/plugins/cache/`, and that
whole cache root did not exist. Nothing refused. The half-installed build
surfaced hours later as the worker's pre-push hook failing on a plugin root
"missing a scripts/bin directory", burning both 1800-second PR-node attempts
after a green janitor and an approved review.

WHY A PREPARE STEP AND NOT THE SESSION-START HOOK. A governed repo's
`.claude/settings.json` already runs `ensure-plugins` at SessionStart, whose
shared verifier reads the same `cache-manifest.json` `required_paths` this gate
reads. That leg cannot carry the guarantee inside a sandbox for two independent
reasons: a SessionStart hook's non-zero exit is ADVISORY, so a broken cache
proceeds into the run regardless; and the sandbox image ships no `claude` CLI
(only the `claude-agent-acp` adapter and the Claude Agent SDK it embeds), so the
verifier's own `claude plugin install` repair leg cannot run there at all. A
`[[run.prepare.steps]]` entry, by contrast, runs BEFORE any ACP session and
fails the run when it exits non-zero — which is the gate the observed failure
needed.

RE-MATERIALIZATION WITHOUT THE CLI. Inside the sandbox the installer is the
Claude Agent SDK, which materializes an enabled plugin from its marketplace
clone at session start. So the repair here is the half the sandbox owns: remove
the incomplete cache directory and drop its registry record, leaving the SDK to
re-install the build before the agent runs. Removal is refused for any path that
is not strictly below the cache root.

THE PER-RUN PIN. The same run observed a release cut mid-flight (0.139.0
published between its implement and PR sessions), so consecutive ACP sessions of
ONE run resolved DIFFERENT plugin builds. The gate therefore also rewrites each
marketplace's floating `source.ref` to the exact commit its clone is checked out
at when the run prepares, and records that resolution at
`<plugins root>/livespec-run-plugin-pin.json`. The rewrite is what a later
session's marketplace refresh resolves; the record is what makes a drift
diagnosable from the run's own filesystem afterwards rather than by inference.
"""

from __future__ import annotations

__all__: list[str] = [
    "PLUGIN_BUILD_PIN_FILENAME",
    "SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR",
    "plugin_cache_gate_prepare_steps_block",
    "plugin_cache_gate_script",
]

# The Claude plugins root the gate reads inside the sandbox. `$HOME/.claude/
# plugins` is where the Claude Agent SDK keeps the installed-plugin registry,
# the marketplace clones and the materialized build cache, so the gate defaults
# there and production never sets the override. The lever exists so a test can
# execute the rendered script FOR REAL against a temporary root — the same
# arrangement `_dispatcher_gh_refresh` uses for its bundle root, and for the
# same reason: a gate whose only test asserts the text it renders has never been
# shown to repair anything.
SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR = "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT"

# Written below the plugins root by the gate, recording the build every ACP
# session of this run resolves. Named for the run rather than for a plugin: it
# covers every marketplace the sandbox carries, not just this orchestrator.
PLUGIN_BUILD_PIN_FILENAME = "livespec-run-plugin-pin.json"

# The gate program, run as `python3 - <<'PY'` by the rendered prepare step. It
# is deliberately stdlib-only and free of any livespec import: the sandbox clone
# is the GOVERNED repository, which carries no copy of this plugin's package,
# and the one copy that would carry it is the very cache the gate exists to
# distrust. Every diagnostic goes to stderr so it lands in the run's setup log,
# which is the journal evidence an operator reads when a build changes under a
# run.
_GATE_SOURCE = '''
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(os.environ.get("LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT")
            or (Path.home() / ".claude" / "plugins"))
cache_root = root / "cache"
registry_path = root / "installed_plugins.json"
marketplaces_path = root / "known_marketplaces.json"
pin_path = root / "PIN_FILENAME"


def note(message):
    sys.stderr.write("livespec plugin-cache gate: " + message + "\\n")


def read_json(path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        note("unparseable " + str(path) + "; leaving it to the agent SDK")
        return None


def required_paths(cache_dir):
    """The cache-manifest paths a complete copy of this build must carry."""
    manifest = read_json(cache_dir / "cache-manifest.json")
    if not isinstance(manifest, dict):
        return []
    declared = manifest.get("required_paths")
    if not isinstance(declared, list):
        return []
    return [entry for entry in declared
            if isinstance(entry, str) and entry
            and not Path(entry).is_absolute() and ".." not in Path(entry).parts]


def cache_findings(install_path):
    """Why this build's materialized cache cannot be trusted; empty means it can.

    `plugin.json` is checked SEPARATELY from the manifest rather than left to
    `required_paths`, because the manifest itself lives inside the cache: a copy
    truncated before it arrives declares no required paths at all and would
    otherwise read as complete — the exact half-copy this gate exists to catch.
    """
    cache_dir = Path(install_path)
    if not cache_dir.is_dir():
        return ["installPath " + install_path + " does not exist"]
    if not (cache_dir / "plugin.json").is_file():
        return ["installPath " + install_path + " has no plugin.json"]
    return ["installPath " + install_path + " is missing required path " + entry
            for entry in required_paths(cache_dir)
            if not (cache_dir / entry).exists()]


def remove_cache_dir(install_path):
    """Delete one incomplete build cache, refusing anything outside the root."""
    resolved = Path(install_path).resolve()
    anchor = cache_root.resolve()
    if anchor not in resolved.parents:
        return False
    shutil.rmtree(resolved, ignore_errors=True)
    return not resolved.exists()


def repair_registry():
    """Drop every record naming an incomplete cache; report what resists."""
    registry = read_json(registry_path)
    plugins = registry.get("plugins") if isinstance(registry, dict) else None
    if not isinstance(plugins, dict):
        note("no installed-plugin records under " + str(registry_path))
        return 0
    unrepaired = []
    changed = False
    for plugin in sorted(plugins):
        records = plugins[plugin]
        if not isinstance(records, list):
            continue
        kept = []
        for record in records:
            path = record.get("installPath") if isinstance(record, dict) else None
            findings = cache_findings(path) if isinstance(path, str) and path else []
            if not findings:
                kept.append(record)
                continue
            for finding in findings:
                note(plugin + " " + finding)
            if remove_cache_dir(path):
                note(plugin + " incomplete cache removed; the agent SDK"
                     " re-materializes this build before the agent runs")
                changed = True
            else:
                unrepaired.append(plugin + " at " + path)
                kept.append(record)
        plugins[plugin] = kept
    if changed:
        registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    for entry in unrepaired:
        note("REFUSED to remove a cache outside " + str(cache_root) + ": " + entry)
    return 1 if unrepaired else 0


def head_commit(location):
    try:
        done = subprocess.run(["git", "-C", location, "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=False)
    except OSError:
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


def pin_marketplaces():
    """Rewrite each floating marketplace ref to the commit resolved now."""
    marketplaces = read_json(marketplaces_path)
    pinned = {}
    if not isinstance(marketplaces, dict):
        return pinned
    for name in sorted(marketplaces):
        entry = marketplaces[name]
        source = entry.get("source") if isinstance(entry, dict) else None
        location = entry.get("installLocation") if isinstance(entry, dict) else None
        if not isinstance(source, dict) or not isinstance(location, str):
            continue
        commit = head_commit(location)
        if commit is None:
            continue
        pinned[name] = dict(previous_ref=source.get("ref"), ref=commit)
        source["ref"] = commit
        note("pinned marketplace " + name + " at " + commit)
    if pinned:
        marketplaces_path.write_text(json.dumps(marketplaces, indent=2),
                                     encoding="utf-8")
    return pinned


def registered_builds():
    registry = read_json(registry_path)
    plugins = registry.get("plugins") if isinstance(registry, dict) else None
    builds = {}
    if not isinstance(plugins, dict):
        return builds
    for plugin in sorted(plugins):
        records = plugins[plugin]
        if not isinstance(records, list):
            continue
        builds[plugin] = sorted(
            str(record.get("version")) for record in records if isinstance(record, dict)
        )
    return builds


status = repair_registry()
pin = dict(marketplaces=pin_marketplaces(), builds=registered_builds())
root.mkdir(parents=True, exist_ok=True)
pin_path.write_text(json.dumps(pin, indent=2, sort_keys=True), encoding="utf-8")
note("recorded this run's plugin build at " + str(pin_path))
raise SystemExit(status)
'''


def plugin_cache_gate_script() -> str:
    """The bash prepare-step body: verify, re-materialize, then pin.

    `set -eu` plus the heredoc means the gate's own exit code IS the step's, so
    an incomplete cache that could not be repaired aborts the run in setup —
    seconds of a prepare step instead of the hour of agent nodes the observed
    failure spent before surfacing the same fact.
    """
    return (
        "set -eu\n"
        "python3 - <<'PY'\n"
        f"{_GATE_SOURCE.replace('PIN_FILENAME', PLUGIN_BUILD_PIN_FILENAME).strip()}\n"
        "PY"
    )


def plugin_cache_gate_prepare_steps_block() -> str:
    """Render the gate as an appended `[[run.prepare.steps]]` block.

    Rendered unconditionally: the registry, the cache and the marketplace clones
    are properties of the sandbox rather than of the dispatch, so there is no
    dispatch-time input whose absence would make the verification meaningless.
    A sandbox with nothing registered yet reports exactly that and exits 0.
    """
    lines = [
        "",
        "# --- Dispatcher-materialized Claude plugin-cache materialization gate:",
        "# --- verify every registered build against its cache-manifest.json",
        "# --- required_paths, re-materialize an incomplete one, and pin the",
        "# --- build for the whole run (bd-ib-dbqb, bd-ib-bb41.9) ---",
        "[[run.prepare.steps]]",
        f"script = '''\n{plugin_cache_gate_script()}\n'''",
    ]
    return "\n".join(lines) + "\n"
