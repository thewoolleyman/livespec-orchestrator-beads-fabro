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

WHY THE PIN ALONE WAS NOT ENOUGH, and what re-entry adds (bd-ib-cewr.3). Prepare
runs ONCE; the registry it verified is mutated afterwards, because every later
ACP session runs its own plugin update. Measured 2026-09-08 across three console
runs, `installed_plugins.json` carried NO orchestrator record at janitor time —
the TUI e2e suite resolved the sandbox clone and went 12/12 green — and named
build `1efcb86825de` by the pr stage, whose cache directory had no `scripts/bin`.
The pre-push hook then failed on a plugin root the run never resolved, twice per
run, after a green janitor and an approved review. Recording a pin cannot prevent
that on its own: nothing re-reads the record. So the gate is RE-ENTRANT. The
prepare pass materializes the gate program at
`<plugins root>/livespec-run-plugin-gate.py` and records the pin; the refresh
stage re-runs that program before it pushes (`plugin_pin_gate_command`), which
drops every record naming a build the run did not resolve at start and refuses,
by name, on an unmaterialized cache it cannot repair.

WHY THE REFRESH COMMAND RE-ENTERS IT. The registry advances INSIDE a later ACP
session, after that session's plugin update. Implementation publication is no
longer an agent turn at all (`SPECIFICATION/contracts.md` section
"Definition-of-Done and Proof-of-Done stages" -> "Scripted publication and
proof-head integrity"), so `pr_refresh` is now the earliest stage that is both
downstream of every such session and upstream of the active pre-push hook — and
its SCRIPTED re-entry observes the mutation without trusting another agent turn
to run the gate at all, which is strictly stronger than the prompt instruction
it replaces.

THIS MODULE ALSO ASSEMBLES THE OTHER TWO MATERIALIZED HELPERS, and that is
cohesion rather than accident: the publication-head reader and the exact-head
push program land below the SAME plugins root, through the same prepare-step
mechanism, and a run whose prepare pass wrote one but not the others would fail
closed at a stage whose refusal names the wrong seam. One block, one root, one
place to read what the sandbox is handed.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_carry_forward_program import (
    carry_forward_program_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_grade_program import (
    proof_grade_program_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    proof_head_program_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    publication_push_program_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge import (
    record_file_merge_program_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "PLUGIN_BUILD_ADVANCED_MARKER",
    "PLUGIN_BUILD_PIN_FILENAME",
    "PLUGIN_CACHE_UNMATERIALIZED_MARKER",
    "PLUGIN_GATE_PROGRAM_FILENAME",
    "SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR",
    "plugin_cache_gate_prepare_steps_block",
    "plugin_cache_gate_script",
    "plugin_pin_gate_command",
]

# The Claude plugins root this gate reads inside the sandbox is now named by
# `_dispatcher_sandbox_plugins`, because THREE materialized helpers resolve it
# and a second spelling of the default would let one of them land somewhere the
# others never look. The name stays in this module's `__all__` so the gate
# remains the surface its own callers address it through.
#
# `$HOME/.claude/plugins` is where the Claude Agent SDK keeps the
# installed-plugin registry, the marketplace clones and the materialized build
# cache, so every helper defaults there and production never sets the override.
# The lever exists so a test can execute the rendered script FOR REAL against a
# temporary root — the same arrangement `_dispatcher_gh_refresh` uses for its
# bundle root, and for the same reason: a gate whose only test asserts the text
# it renders has never been shown to repair anything.

# Written below the plugins root by the gate, recording the build every ACP
# session of this run resolves. Named for the run rather than for a plugin: it
# covers every marketplace the sandbox carries, not just this orchestrator.
PLUGIN_BUILD_PIN_FILENAME = "livespec-run-plugin-pin.json"

# The gate program itself, written below the plugins root by the prepare step so
# a later stage can RE-ENTER it. A heredoc piped into `python3 -` is a one-shot:
# it cannot be re-run by anything that did not already carry the whole program,
# and the refresh stage must EXECUTE a program rather than carry one. Landing it
# on disk also makes the verification an operator can read and re-run inside a
# live sandbox.
PLUGIN_GATE_PROGRAM_FILENAME = "livespec-run-plugin-gate.py"

# The two named conditions the gate prints to stderr. They are constants rather
# than prose because three consumers must agree on one string: the sandbox that
# emits it, the refresh script that reports it, and the test that proves the
# emission. A signature nobody can grep for is not a signature.
PLUGIN_CACHE_UNMATERIALIZED_MARKER = "LIVESPEC_PLUGIN_CACHE_UNMATERIALIZED"
PLUGIN_BUILD_ADVANCED_MARKER = "LIVESPEC_PLUGIN_BUILD_ADVANCED"

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
unmaterialized = "UNMATERIALIZED_MARKER"
advanced = "ADVANCED_MARKER"


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
                note(unmaterialized + ": " + plugin + " " + finding)
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
        note(unmaterialized + ": REFUSED to remove a cache outside "
             + str(cache_root) + ": " + entry)
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


def pinned_builds():
    """The build set this run resolved at prepare time, or None before it exists.

    None is what distinguishes the PREPARE pass from a stage-boundary RE-ENTRY,
    and the two must behave differently: prepare records the resolution, and a
    re-entry enforces it. Deriving the distinction from the pin file rather than
    from an argument keeps the one program correct at both call sites.
    """
    pin = read_json(pin_path)
    builds = pin.get("builds") if isinstance(pin, dict) else None
    return builds if isinstance(builds, dict) else None


def enforce_pin(pinned):
    """Drop every record naming a build this run did not resolve at start.

    The CACHE is left alone. A build registered mid-run may be perfectly
    materialized -- it is simply not this run's -- and removing a sound cache
    would destroy work the next run reuses. Only the registry decides what a
    session resolves, so the registry is the only thing this reverts.
    """
    registry = read_json(registry_path)
    plugins = registry.get("plugins") if isinstance(registry, dict) else None
    if not isinstance(plugins, dict):
        return
    changed = False
    for plugin in sorted(plugins):
        records = plugins[plugin]
        if not isinstance(records, list):
            continue
        allowed = pinned.get(plugin)
        allowed = allowed if isinstance(allowed, list) else []
        kept = []
        for record in records:
            build = str(record.get("version")) if isinstance(record, dict) else None
            if build in allowed:
                kept.append(record)
                continue
            note(advanced + ": " + plugin + " registered build " + str(build)
                 + " after this run resolved " + repr(allowed) + "; dropping that"
                 " record so every stage resolves the build the run started with")
            changed = True
        plugins[plugin] = kept
    if changed:
        registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")


pinned = pinned_builds()
status = repair_registry()
if pinned is None:
    pin = dict(marketplaces=pin_marketplaces(), builds=registered_builds())
    root.mkdir(parents=True, exist_ok=True)
    pin_path.write_text(json.dumps(pin, indent=2, sort_keys=True), encoding="utf-8")
    note("recorded this run's plugin build at " + str(pin_path))
else:
    enforce_pin(pinned)
    note("re-entered at a stage boundary; enforced the build pinned at "
         + str(pin_path))
raise SystemExit(status)
'''


def _gate_program() -> str:
    """The gate program with its three deployment-time tokens substituted in."""
    program = _GATE_SOURCE
    for token, value in (
        ("PIN_FILENAME", PLUGIN_BUILD_PIN_FILENAME),
        ("UNMATERIALIZED_MARKER", PLUGIN_CACHE_UNMATERIALIZED_MARKER),
        ("ADVANCED_MARKER", PLUGIN_BUILD_ADVANCED_MARKER),
    ):
        program = program.replace(token, value)
    return program.strip()


def plugin_cache_gate_script() -> str:
    """The bash prepare-step body: materialize the program, verify, then pin.

    `set -eu` plus the `exec` means the gate's own exit code IS the step's, so
    an incomplete cache that could not be repaired aborts the run in setup —
    seconds of a prepare step instead of the hour of agent nodes the observed
    failure spent before surfacing the same fact.

    The program is WRITTEN before it is run, rather than piped into `python3 -`,
    because the refresh stage has to re-enter the same verification and a pipe
    leaves nothing behind to re-enter.
    """
    return (
        "set -eu\n"
        f'root="{sandbox_plugins_root_expansion()}"\n'
        'mkdir -p "$root"\n'
        f"cat > \"$root/{PLUGIN_GATE_PROGRAM_FILENAME}\" <<'PY'\n"
        f"{_gate_program()}\n"
        "PY\n"
        f'exec python3 "$root/{PLUGIN_GATE_PROGRAM_FILENAME}"'
    )


def plugin_pin_gate_command() -> str:
    """The one command a later stage runs to re-enter the gate before pushing.

    A single argv rather than a script body: its consumer is the `pr_refresh`
    command recipe, which composes it inline. Its exit code is the whole
    contract — zero means the registry now names only builds this run resolved
    at start, non-zero means it does not and could not be repaired.
    """
    return f'python3 "{sandbox_plugins_root_expansion()}/{PLUGIN_GATE_PROGRAM_FILENAME}"'


def plugin_cache_gate_prepare_steps_block() -> str:
    """Render the gate, and the three publication helpers, as prepare steps.

    Rendered unconditionally: the registry, the cache and the marketplace clones
    are properties of the sandbox rather than of the dispatch, so there is no
    dispatch-time input whose absence would make the verification meaningless.
    A sandbox with nothing registered yet reports exactly that and exits 0.

    The publication-head reader, the exact-head push program, the carry-forward
    decision, the declared-record-file merger and the per-assertion proof grade
    ride the SAME block for the reason the module docstring records: all six land
    below one root, and a sandbox given a subset fails closed at a stage whose
    refusal would name the wrong seam. They follow the gate rather than precede
    it so the cheapest refusal — an unrepairable plugin cache — still aborts
    setup first.
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
    return (
        "\n".join(lines)
        + "\n"
        + proof_head_program_prepare_steps_block()
        + publication_push_program_prepare_steps_block()
        + carry_forward_program_prepare_steps_block()
        + record_file_merge_program_prepare_steps_block()
        + proof_grade_program_prepare_steps_block()
    )
