"""`/livespec-impl-beads:detect-impl-gaps` thin-transport command.

CLI surface per SPECIFICATION/contracts.md §"detect-impl-gaps":

  detect-impl-gaps [--spec-target <path>] [--project-root <path>] [--json]
                   [--since-version <vN>]

Reads the live Specification via the Spec Reader, enumerates every
MUST / MUST NOT / SHOULD / SHOULD NOT rule, and emits the resulting
gap-id set. Gap-id derivation is a pure function of the spec-file
path + canonical heading path + rule text; the same rule text in the
same context always yields the same gap-id across runs.

When `--since-version <vN>` is set, the scan restricts to files whose
content differs between the historical version `<vN>` and the live
spec — i.e., files present in
`SpecDiff(version_a=<vN>, version_b=<live>).per_file`. For each such
file, only MUST / SHOULD clauses present in the LIVE version are
considered (clauses removed by the diff are not gaps — they were spec
content that no longer exists).

The skill is the canonical gap-detection surface for the plugin.
Consumed by:

- `livespec` doctor's `gap-tracking-one-to-one` and
  `no-stale-gap-tied` invariants via subprocess.
- The heavyweight `capture-impl-gaps` sibling as its detection
  step.
- The heavyweight `implement` skill at gap-tied closure
  verification.

The skill is intrinsically non-mutating: no JSONL writes, no user
prompts, no spec modifications.
"""

import argparse
import hashlib
import json
import re
import sys
from base64 import b32encode
from dataclasses import dataclass
from pathlib import Path

from livespec_impl_beads.errors import SpecVersionNotFoundError
from livespec_impl_beads.spec_reader import (
    read_current_specification,
    read_specification_history,
)

_RULE_KEYWORD_PATTERN = re.compile(r"\b(MUST NOT|SHOULD NOT|MUST|SHOULD)\b")
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_CODE_FENCE_PATTERN = re.compile(r"^\s*```")
_GAP_ID_LENGTH = 8

_EXIT_USAGE_ERROR = 2
_EXIT_PRECONDITION_ERROR = 3


@dataclass(frozen=True, kw_only=True)
class RuleMatch:
    """A single MUST/SHOULD rule detected in the spec."""

    spec_file: str
    heading_path: str
    line_text: str
    gap_id: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="detect-impl-gaps")
    _ = parser.add_argument(
        "--spec-target",
        dest="spec_target",
        default=None,
        help="Path to the spec tree (default: SPECIFICATION/ under --project-root).",
    )
    _ = parser.add_argument(
        "--project-root",
        dest="project_root",
        default=None,
        help="Project root (default: current working directory).",
    )
    _ = parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help='Emit JSON `{"gap_ids": [...]}` instead of human-readable lines.',
    )
    _ = parser.add_argument(
        "--since-version",
        dest="since_version",
        default=None,
        help=(
            "Restrict scan to files differing between this historical "
            "version (positive integer; the vNNN suffix) and the live "
            "spec. When omitted, scans every file."
        ),
    )
    args = parser.parse_args(argv)
    project_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    spec_root = (
        Path(args.spec_target) if args.spec_target is not None else project_root / "SPECIFICATION"
    )
    since_version: int | None = None
    if args.since_version is not None:
        parsed = _parse_since_version(raw=args.since_version)
        if parsed is None:
            parts: list[str] = [
                "ERROR: --since-version requires a positive integer",
                f" (got '{args.since_version}');",
                " accepted forms are 'v<N>' or '<N>' where N is a",
                " positive integer.\n",
            ]
            _ = sys.stderr.write("".join(parts))
            return _EXIT_USAGE_ERROR
        since_version = parsed
    try:
        rules = detect_rules(spec_root=spec_root, since_version=since_version)
    except SpecVersionNotFoundError as exc:
        _ = sys.stderr.write(f"ERROR: {exc}\n")
        return _EXIT_PRECONDITION_ERROR
    if args.as_json:
        _write_json(rules=rules)
    else:
        _write_human(rules=rules)
    return 0


def _parse_since_version(*, raw: str) -> int | None:
    """Parse a `--since-version` argument to a positive integer.

    Accepts either `v<N>` (e.g. `v082`) or a bare `<N>` (e.g. `82`).
    Returns None if the value is not a positive integer.
    """
    candidate = raw.lstrip("vV") if raw.startswith(("v", "V")) else raw
    if not candidate.isdigit():
        return None
    value = int(candidate)
    if value <= 0:
        return None
    return value


def detect_rules(
    *,
    spec_root: Path,
    since_version: int | None = None,
) -> list[RuleMatch]:
    """Enumerate every MUST/SHOULD rule in the live spec tree.

    When `since_version` is None, scans every markdown file in the live
    spec.

    When `since_version` is set, scans only those markdown files whose
    content differs between version `<since_version>` and the live
    spec. For each such file, only rules present in the LIVE version
    are surfaced (removed-in-the-diff content is not a gap).

    Returns rules sorted by (spec_file, heading_path, line_text) so
    output ordering is deterministic across runs and platforms.
    """
    snapshot = read_current_specification(spec_root=spec_root)
    if since_version is None:
        candidate_files = sorted(snapshot.files.keys())
    else:
        candidate_files = sorted(
            _files_changed_since(spec_root=spec_root, since_version=since_version)
            & snapshot.files.keys()
        )
    rules: list[RuleMatch] = []
    for spec_file in candidate_files:
        if not spec_file.endswith(".md"):
            continue
        content = snapshot.files[spec_file]
        rules.extend(_extract_rules_from_file(spec_file=spec_file, content=content))
    rules.sort(key=lambda rule: (rule.spec_file, rule.heading_path, rule.line_text))
    return rules


def _files_changed_since(*, spec_root: Path, since_version: int) -> set[str]:
    """Return the set of file paths that differ between `<since_version>` and the live spec.

    Compares the live tree (everything under `<spec-root>/` except
    `history/` and `proposed_changes/`) against the history snapshot
    at `<since_version>`. A file is "changed" if its content differs,
    or if it appears in only one of the two sides.

    Raises `SpecVersionNotFoundError` if `<since_version>` does not
    exist under `<spec-root>/history/`.
    """
    since_snapshot = read_specification_history(spec_root=spec_root, version=since_version)
    live_snapshot = read_current_specification(spec_root=spec_root)
    changed: set[str] = set()
    all_paths = set(since_snapshot.files.keys()) | set(live_snapshot.files.keys())
    for path in all_paths:
        if since_snapshot.files.get(path, "") != live_snapshot.files.get(path, ""):
            changed.add(path)
    return changed


def _extract_rules_from_file(*, spec_file: str, content: str) -> list[RuleMatch]:
    rules: list[RuleMatch] = []
    heading_stack: list[str] = []
    in_code_fence = False
    for raw_line in content.splitlines():
        if _CODE_FENCE_PATTERN.match(raw_line):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        heading_match = _HEADING_PATTERN.match(raw_line)
        if heading_match is not None:
            level = len(heading_match.group(1))
            title = heading_match.group(2)
            _push_heading(stack=heading_stack, level=level, title=title)
            continue
        if _RULE_KEYWORD_PATTERN.search(raw_line) is None:
            continue
        rule_text = raw_line.strip()
        heading_path = " > ".join(heading_stack) if heading_stack else "(top)"
        gap_id = _derive_gap_id(spec_file=spec_file, heading_path=heading_path, rule_text=rule_text)
        rules.append(
            RuleMatch(
                spec_file=spec_file,
                heading_path=heading_path,
                line_text=rule_text,
                gap_id=gap_id,
            )
        )
    return rules


def _push_heading(*, stack: list[str], level: int, title: str) -> None:
    while len(stack) >= level:
        _ = stack.pop()
    while len(stack) < level - 1:
        stack.append("")
    stack.append(title)


def _derive_gap_id(*, spec_file: str, heading_path: str, rule_text: str) -> str:
    payload = f"{spec_file}\x1f{heading_path}\x1f{rule_text}".encode()
    digest = hashlib.sha256(payload).digest()
    suffix = b32encode(digest).decode("ascii").rstrip("=").lower()[:_GAP_ID_LENGTH]
    return f"gap-{suffix}"


def _write_json(*, rules: list[RuleMatch]) -> None:
    payload = {"gap_ids": [rule.gap_id for rule in rules]}
    _ = sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_human(*, rules: list[RuleMatch]) -> None:
    if not rules:
        _ = sys.stdout.write("(no rules detected)\n")
        return
    for rule in rules:
        line = f"{rule.spec_file} > {rule.heading_path}  [{rule.gap_id}]  {rule.line_text}\n"
        _ = sys.stdout.write(line)
