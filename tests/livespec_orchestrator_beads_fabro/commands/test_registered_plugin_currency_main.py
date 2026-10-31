"""CLI coverage for the registered-plugin-currency command."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import registered_plugin_currency


@pytest.mark.parametrize(
    ("warning", "expected_output"),
    [
        (
            "WARNING: registered build 1.2.3 lags latest released version 1.2.4",
            ["WARNING: registered build 1.2.3 lags latest released version 1.2.4\n"],
        ),
        (None, []),
    ],
)
def test_main_prints_only_a_currency_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    warning: str | None,
    expected_output: list[str],
) -> None:
    output: list[str] = []
    module: ModuleType = registered_plugin_currency
    install_record = tmp_path / "installed_plugins.json"
    marketplace_record = tmp_path / "known_marketplaces.json"
    monkeypatch.setattr(module, "default_plugin_install_registry", lambda: install_record)
    monkeypatch.setattr(
        module,
        "default_release_adoption_bases",
        lambda: SimpleNamespace(marketplace_record=marketplace_record),
    )
    monkeypatch.setattr(
        module,
        "registered_plugin_currency_warning",
        lambda **_kwargs: warning,
    )
    monkeypatch.setattr(module, "write_stdout", lambda *, text: output.append(text))

    assert module.main(argv=["--repo", str(tmp_path / "project")]) == 0
    assert output == expected_output
