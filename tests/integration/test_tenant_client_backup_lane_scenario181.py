"""Scenario 181 — this repository's committed tenant config disables the client backup lane.

Binds the `Given` of `SPECIFICATION/scenarios.md` "Scenario 181 — A ledger
write from this repository prints no auto-backup warning" and the
`SPECIFICATION/contracts.md` bullet "Client backup lane disabled" in its
section on the beads connection model.

THE SUBJECT IS THIS REPOSITORY'S OWN COMMITTED `.beads/config.yaml`, not a
synthesized fixture, because the ratified rule is about what THIS repository
ships: `bd` opens the committed file at the repository root on every call, so
a fixture would grade bytes no `bd` invocation ever reads. That is why the
case runs at the integration tier rather than as a unit test of a parser.

WHAT THIS FILE CANNOT PROVE, stated so the binding is not over-read. Scenario
181's `When`/`Then` — a live `bd` write against the shared Dolt tenant whose
stderr carries no `auto-backup failed` warning, and the next hourly
`dolt-backup.service` run still reporting every tenant synced — needs the
credential wrapper, the shared server and a backup timer that no sandboxed or
CI process can reach. Work-item `bd-ib-rxf` carries that half as a
HOST-CAPTURED assertion, proved on the ledger host against the released build.
What is mechanically checkable from inside the repository is the `Given`, and
it is the half that can silently regress: the key is one line in a file nobody
reads, and `bd`'s default (`isBackupAutoEnabled` in `cmd/bd/backup_auto.go`)
RE-ENABLES the lane the moment the explicit `false` goes missing, because the
repository has a git remote.

The comment is asserted as well as the key, and deliberately. Without it the
next reader sees a disabled backup setting on a ledger and has no way to tell
"backed up centrally, client lane redundant" from "backups switched off"; the
first reading is correct here and the second would make this line look like a
defect to remove. The assertion is on the comment block ATTACHED to the key
rather than anywhere in the file, since a rationale parked at the bottom of a
flat key-value file does not travel with the line it explains.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _REPO_ROOT / ".beads" / "config.yaml"

# (value, attached comment block) for one flat `key: value` line.
_Entry = tuple[str, str]
_ABSENT: _Entry = ("", "")


def _entries(*, text: str) -> dict[str, _Entry]:
    """Map each flat dotted `key: value` line to its value and attached comment.

    The attached comment is the UNBROKEN run of `#` lines immediately above the
    key, joined with spaces; a blank line or another key ends the run, so a
    rationale written elsewhere in the file does not attach to a key it does
    not sit against. The file is a flat key-value map (`dolt.mode: server`,
    `backup.enabled: false`), so a line scan reads it exactly as written
    without taking a YAML dependency this repository does not declare.
    """
    entries: dict[str, _Entry] = {}
    block: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            block.append(line.lstrip("#").strip())
            continue
        key, separator, remainder = line.partition(":")
        if separator:
            entries[key.strip()] = (remainder.split("#", 1)[0].strip(), " ".join(block))
        block = []
    return entries


def test_scenario181_committed_tenant_config_disables_the_client_backup_lane() -> None:
    """The committed `.beads/config.yaml` sets `backup.enabled: false`, documented.

    One assertion per ratified clause: the key is present and `false`, and the
    comment attached to it states that the tenant is backed up server-side
    every hour by `dolt-backup.service` through `DOLT_BACKUP('sync','s3')` — so
    the lane is disabled because the backup already runs elsewhere, never
    because a tenant grant is being sought.
    """
    entries = _entries(text=_CONFIG_PATH.read_text(encoding="utf-8"))
    value, rationale = entries.get("backup.enabled", _ABSENT)

    assert value == "false", (
        "this repository's committed .beads/config.yaml must set "
        "`backup.enabled: false`; without the explicit key bd auto-enables the "
        f"client backup lane whenever the repository has a git remote. Got: {value!r}"
    )
    assert "dolt-backup.service" in rationale, (
        "the comment attached to `backup.enabled` must name dolt-backup.service "
        f"as the server-side lane that backs this tenant up; got: {rationale!r}"
    )
    assert "DOLT_BACKUP('sync','s3')" in rationale, (
        "the comment attached to `backup.enabled` must name the "
        f"DOLT_BACKUP('sync','s3') procedure the hourly lane calls; got: {rationale!r}"
    )
    assert "hour" in rationale, (
        "the comment attached to `backup.enabled` must state that the "
        f"server-side backup runs every hour; got: {rationale!r}"
    )
