"""Connection resolution shared across the thin-transport command modules.

The plaintext sibling resolved a pair of filesystem JSONL paths here. The
beads store has no JSONL files; instead this module resolves the per-repo
tenant CONNECTION descriptor (`StoreConfig`) from the `.livespec.jsonc`
connection block, overlaid by environment variables.

Resolution order (later wins):

1. Built-in defaults (`server_host=127.0.0.1`, `server_port=3307`,
   `fake=False`).
2. The `.livespec.jsonc` connection block at `<cwd>/.livespec.jsonc`
   under `livespec-orchestrator-beads-fabro.connection` (and the substrate `format`
   marker / `tenant` key). A missing file or block falls back to
   defaults plus a placeholder tenant. `connection.prefix`, however, is
   REQUIRED: it is bd's server-stored issue-ID create-prefix (e.g.
   `bd-ib`) and is DECOUPLED from the tenant DB name, so it is never
   defaulted — an unset/empty prefix raises `ConnectionPrefixMissingError`
   (`database` and `server_user` still default to the tenant, which they
   ARE).
3. Environment overlay:
   - `LIVESPEC_BD_PATH` — absolute path to the pinned bd v1.0.5 binary
     (NEVER the mise shim). Overrides the config `bd_path`.
   - `LIVESPEC_BEADS_FAKE` — when truthy (`1`/`true`/`yes`), forces the
     hermetic in-memory backend. This is how the default CI tier and the
     no-live-connection runtime fallback select the `FakeBeadsClient`.

The tenant PASSWORD is never resolved here: the shell backend reads
`BEADS_DOLT_PASSWORD` from the environment at `bd`-call time. It is never
stored on the descriptor.

`resolve_fabro_bin` resolves the Dispatcher's `fabro` engine binary by the
same env > config > default precedence (later listed wins the tie-break the
other way — env is highest-priority):

1. `LIVESPEC_FABRO_BIN` — an absolute path to the `fabro` binary. Highest
   priority (mirrors `LIVESPEC_BD_PATH`). A non-empty value wins outright.
2. The `.livespec.jsonc` `livespec-orchestrator-beads-fabro.dispatcher`
   block's `fabro_bin` key, when non-empty.
3. The built-in default, which is a HOST PROBE rather than a configuration
   answer and therefore lives in `_fabro_bin` — `$HOME/.fabro/bin/fabro` when
   it exists and is executable, else a `PATH` lookup, else the concrete
   home-path string, with the two-deploy-environment reasoning recorded there.

`resolve_fabro_factory` resolves the selected `dispatcher.factories` entry,
whose optional `bin` key names the engine CLIENT binary that factory's server
speaks to. It lands on `FactoryTarget.fabro_bin`; what it means NEXT TO the
three global legs above is `_dispatcher_factory_bin`'s, not this module's.

The function signature keeps the plaintext sibling's
`work_items_arg` parameter (`resolve_store_config(*, cwd,
work_items_arg)`) so the command call sites do not change. The
`work_items_arg` parameter is accepted-and-ignored under the beads
substrate (there are no JSONL path overrides); it remains in the
signature only for call-site compatibility.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from returns.io import IOFailure, IOResult, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands import _jsonc
from livespec_orchestrator_beads_fabro.commands._fabro_bin import (
    configured_fabro_bin,
    default_fabro_bin,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    NodeTimeouts,
    node_timeouts_from_block,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variants import (
    WorkflowVariant,
    workflow_variant_from_block,
)
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "ConfigUnreadable",
    "FactoryTarget",
    "dispatcher_block",
    "has_fabro_factories",
    "has_fabro_factory",
    "resolve_credential_wrapper",
    "resolve_fabro_bin",
    "resolve_fabro_factory",
    "resolve_fabro_sandbox_image",
    "resolve_node_timeouts",
    "resolve_store_config",
    "resolve_workflow_variant",
]

_LIVESPEC_CONFIG = ".livespec.jsonc"
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_CONNECTION_KEY = "connection"
_DISPATCHER_KEY = "dispatcher"
_CREDENTIAL_WRAPPER_KEY = "credential_wrapper"

_DEFAULT_SERVER_HOST = "127.0.0.1"
_DEFAULT_SERVER_PORT = 3307
_DEFAULT_BD_PATH = "bd"
_DEFAULT_TENANT = "livespec-orch-beads-fabro"

_ENV_BD_PATH = "LIVESPEC_BD_PATH"
_ENV_FAKE = "LIVESPEC_BEADS_FAKE"
_ENV_FABRO_BIN = "LIVESPEC_FABRO_BIN"
_ENV_FABRO_FACTORY = "LIVESPEC_FABRO_FACTORY"
_FACTORY_BIN_KEY = "bin"
_FABRO_DEV_AUTH_ENV_PREFIX = "FABRO_DEV_TOKEN__"
_ENV_FABRO_SANDBOX_IMAGE = "LIVESPEC_FABRO_SANDBOX_IMAGE"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, kw_only=True)
class FactoryTarget:
    """Resolved Fabro factory target for a dispatcher invocation."""

    name: str
    server: str | None
    dev_token: str | None
    # The engine CLIENT binary this factory declares, from its optional `bin`
    # key. None means the entry declares none, which is a complete answer: the
    # factory runs whatever the host's global resolution supplies.
    # `_dispatcher_factory_bin` owns what the two layers mean together.
    fabro_bin: str | None = None


@dataclass(frozen=True, kw_only=True)
class ConfigUnreadable:
    """`.livespec.jsonc` EXISTS but cannot be read as a configuration object.

    Deliberately NOT inhabited by "the file is absent" or "the block is not
    there". An unconfigured repo has documented defaults and those defaults are
    the ANSWER; a file that will not parse, or whose root is not an object, is
    the operator's configuration being wrong, and that is a different claim.
    """

    detail: str


def resolve_store_config(
    *,
    cwd: Path,
    work_items_arg: str | None,
) -> StoreConfig:
    """Resolve the beads connection descriptor from .livespec.jsonc + env.

    `work_items_arg` is accepted for call-site compatibility with the
    plaintext signature and is intentionally unused under the beads
    substrate (no JSONL path overrides exist).
    """
    _ = work_items_arg
    read = _read_connection_block(cwd=cwd)
    if isinstance(read, IOFailure):
        # ⛔ WITHOUT THIS the next line reads an EMPTY block and `_require_prefix`
        # raises `ConnectionPrefixMissingError` — a true refusal naming the wrong
        # cause. An operator with a stray comma was told their `connection.prefix`
        # was missing. This function's contract is exception-based rather than
        # railway (55 call sites, none of which catch), so the seam's reason is
        # turned into a TRUTHFUL exception here rather than a Result.
        raise LivespecConfigUnreadableError(detail=unsafe_perform_io(read.failure()).detail)
    block = unsafe_perform_io(read.unwrap())
    tenant = _str_or(value=block.get("tenant"), default=_DEFAULT_TENANT)
    prefix = _require_prefix(block=block)
    database = _str_or(value=block.get("database"), default=tenant)
    server_user = _str_or(value=block.get("server_user"), default=tenant)
    server_host = _str_or(value=block.get("server_host"), default=_DEFAULT_SERVER_HOST)
    server_port = _int_or(value=block.get("server_port"), default=_DEFAULT_SERVER_PORT)
    socket = _optional_str(value=block.get("socket"))
    bd_path = _resolve_bd_path(block=block)
    fake = _resolve_fake(block=block)
    return StoreConfig(
        tenant=tenant,
        prefix=prefix,
        server_user=server_user,
        database=database,
        bd_path=bd_path,
        server_host=server_host,
        server_port=server_port,
        socket=socket,
        fake=fake,
        repo_root=cwd,
    )


def resolve_fabro_bin(*, cwd: Path) -> str:
    """Resolve the Dispatcher's `fabro` engine binary path (env > config > default).

    Precedence: a non-empty `LIVESPEC_FABRO_BIN` env value wins outright; else
    the `.livespec.jsonc` `dispatcher.fabro_bin` key, when non-empty; else the
    call-time default from `_default_fabro_bin` (absolute home path, else a
    `PATH` lookup, else the concrete home-path string).
    """
    env_value = os.environ.get(_ENV_FABRO_BIN)
    if env_value is not None and env_value != "":
        return env_value
    # ⚠️ THE ONLY READER LEFT OFF THE RAILWAY, AND THE REASON IS RECORDED RATHER
    # THAN HIDDEN. Its recovery value is its OWN last precedence leg, the probe
    # `default_fabro_bin()` — so a caller writing `.value_or(...)` would need
    # that probe. The probe is now PUBLIC in `_fabro_bin` (the cross-module
    # private import pyright refuses is no longer the obstacle it was), but the
    # obstacle that remains is the same one: it returns a bare `str`, so lifting
    # this reader onto the railway still has nowhere honest to put the recovery.
    # The honest destination is the preflight-error channel
    # `_dispatcher_run_checks._fabro_preflight_error` already owns, which is a
    # flow change rather than a signature change. Tracked as `8o8e.21`; until
    # then the fold stays HERE, next to the probe it needs.
    return unsafe_perform_io(
        _read_dispatcher_block(cwd=cwd)
        .map(lambda block: configured_fabro_bin(block=block))
        .value_or(default_fabro_bin())
    )


def resolve_node_timeouts(*, cwd: Path) -> NodeTimeouts | str:
    """Resolve the dispatch target's node timeouts from its .livespec.jsonc.

    The policy itself -- the 30-minute default, the validation, and the
    worst-case visit map behind the derived subprocess ceiling -- lives in
    `_node_timeouts`; this is the config-reading seam that feeds it. A
    refusal comes back as its message so the caller can report it as a
    failed dispatch before any run exists.
    """
    return node_timeouts_from_block(block=dispatcher_block(cwd=cwd))


def resolve_workflow_variant(*, cwd: Path, name: str | None = None) -> WorkflowVariant:
    """Resolve which named Fabro workflow variant this dispatch runs.

    The policy itself -- the `dispatcher.workflows` registry shape, the
    `dispatcher.default_workflow` precedence and the reserved
    `implement-work-item` name -- lives in `_workflow_variants`; this is the
    config-reading seam that feeds it. Deliberately NO environment layer,
    matching `_codex_model_tiers` and the ACP node adapters: which graph the
    factory runs is a recorded argument, not something an ad-hoc shell changes.
    """
    return workflow_variant_from_block(block=dispatcher_block(cwd=cwd), name=name)


# `has_explicit_codex_implementer_model` used to live here. It answered ONE
# question -- "does this target route implementer work to Codex?" -- for ONE
# caller, the engine branch that chose between a hard-coded Claude adapter
# string and a rendered Codex one. That branch is gone: which adapter a node
# runs is now resolved from configuration through the three layers, and the
# same test is made where it belongs, inside the `codex_models` shorthand
# expansion in `_acp_node_repository`.


def resolve_fabro_factory(*, cwd: Path, factory: str | None = None) -> FactoryTarget:
    """Resolve the Dispatcher's Fabro factory target (env > config > default).

    The selected factory name comes from an explicit CLI value when present;
    otherwise from a non-empty `LIVESPEC_FABRO_FACTORY` value; otherwise it
    comes from `dispatcher.default_factory` when that name exists in
    `dispatcher.factories`; otherwise from a configured `factories.default`
    entry when present; otherwise from the implicit single-factory `"default"`
    target. The implicit target has no server value so downstream callers
    preserve today's ambient Fabro CLI behavior.
    """
    block = dispatcher_block(cwd=cwd)
    if factory is not None and factory != "":
        return _factory_target_for(name=factory, block=block)
    env_value = os.environ.get(_ENV_FABRO_FACTORY)
    if env_value is not None and env_value != "":
        return _factory_target_for(name=env_value, block=block)
    return _factory_target_for(
        name=_resolve_configured_factory_name(block=block),
        block=block,
    )


def has_fabro_factory(*, cwd: Path, factory: str) -> bool:
    """Return whether the current dispatcher config defines a named factory."""
    block = dispatcher_block(cwd=cwd)
    factories_raw = block.get("factories")
    if not isinstance(factories_raw, dict):
        return False
    return factory in cast("dict[str, Any]", factories_raw)


def has_fabro_factories(*, cwd: Path) -> bool:
    """Return whether dispatcher config constrains factory names."""
    block = dispatcher_block(cwd=cwd)
    factories_raw = block.get("factories")
    return isinstance(factories_raw, dict)


def resolve_fabro_sandbox_image(*, cwd: Path) -> IOResult[str | None, ConfigUnreadable]:
    """Resolve the optional Fabro sandbox image override (env > config > unset).

    A non-empty `LIVESPEC_FABRO_SANDBOX_IMAGE` env value wins outright; else
    the `.livespec.jsonc` `dispatcher.fabro_sandbox_image` key, when non-empty;
    else None. None is an explicit no-op: the committed workflow image table
    remains byte-for-byte as shipped.
    """
    env_value = os.environ.get(_ENV_FABRO_SANDBOX_IMAGE)
    if env_value is not None and env_value != "":
        return IOSuccess(env_value)
    return _read_dispatcher_block(cwd=cwd).map(lambda block: _configured_sandbox_image(block=block))


def resolve_credential_wrapper(*, cwd: Path) -> IOResult[list[str], ConfigUnreadable]:
    """The top-level `credential_wrapper` argv-prefix; `[]` when none is configured.

    An ABSENT config file, an absent key, and a non-list value all yield `[]` on
    the SUCCESS track — each is an ANSWER: this repo configures no wrapper. A file
    that EXISTS and will not parse rides the FAILURE track instead.

    ⛔ THE DISTINCTION IS LOAD-BEARING, and it used to be lost here. The sole
    consumer is the pre-push `check-ledger-conformance-live` gate, which invokes
    the ledger check UNDER this wrapper and SKIPS when there is none. Folding an
    unreadable config into `[]` therefore let a stray comma SILENTLY TURN THE
    PRE-PUSH GATE OFF, reported in the same words as a repo that never wanted one.

    ⚠️ It stays fail-SOFT at the consumer by deliberate design — that recipe runs
    on every push and a false-fail would brick them all — so this failure track
    exists to be REPORTED, not to block. Returning it is what makes the two
    outcomes tellable apart; deciding what to do about them is the caller's.
    """
    return _read_root_mapping(cwd=cwd).map(lambda root: _credential_wrapper_tokens(root=root))


def _credential_wrapper_tokens(*, root: dict[str, Any]) -> list[str]:
    """The `credential_wrapper` argv tokens in a root mapping, or [] when unset."""
    raw = root.get(_CREDENTIAL_WRAPPER_KEY)
    if not isinstance(raw, list):
        return []
    return [str(token) for token in cast("list[Any]", raw)]


def _read_root_mapping(*, cwd: Path) -> IOResult[dict[str, Any], ConfigUnreadable]:
    """`.livespec.jsonc`'s root object; `{}` on the SUCCESS track when absent.

    An absent config file is an ANSWER — this repo runs on documented defaults
    without one — so it rides the success track as an empty mapping. A file
    that will not parse, and a root that is not an object, are failures: the
    file is there and says something the loader cannot use.
    """
    config_path = cwd / _LIVESPEC_CONFIG
    if not config_path.is_file():
        return IOSuccess({})
    raw_text = config_path.read_text(encoding="utf-8")
    parsed = _jsonc.parse(text=raw_text)
    if isinstance(parsed, _jsonc.JsoncFailure):
        return IOFailure(
            ConfigUnreadable(detail=f"{_LIVESPEC_CONFIG} does not parse: {parsed.detail}")
        )
    if not isinstance(parsed, dict):
        return IOFailure(ConfigUnreadable(detail=f"{_LIVESPEC_CONFIG} root is not an object"))
    return IOSuccess(cast("dict[str, Any]", parsed))


def _read_connection_block(*, cwd: Path) -> IOResult[dict[str, Any], ConfigUnreadable]:
    """Read the `livespec-orchestrator-beads-fabro.connection` block, or {} when absent."""
    return _read_plugin_sub_block(cwd=cwd, key=_CONNECTION_KEY)


def dispatcher_block(*, cwd: Path) -> dict[str, Any]:
    """The dispatcher block, RAISING when `.livespec.jsonc` cannot be read.

    PUBLIC because a policy module that owns its own resolver reads the block
    from OUTSIDE this module (`_dispatcher_ci_pipeline_view`), and importing a
    `_`-prefixed name across a module boundary is exactly what pyright strict and
    the `private_calls` check refuse. The alternative — a second per-key
    `resolve_*` seam here for every policy module — is what pushed this file at
    its ceiling, so the reader is the interface rather than each of its uses.

    ⛔ THE DEFECT THIS EXISTS TO STOP — and it REGREW in this module while the
    fix sat unlanded. Every caller below answers a question whose negative
    reading is "not configured": a `bool`, a factory target, a model-tier set.
    Folding an UNREADABLE file into that answer tells an operator their factory
    is not defined when what actually happened is a stray comma in their config.

    None of those return types carries a failure track, and none of their
    consumers catches, so this mirrors `resolve_store_config` rather than
    inventing a second convention: turn the seam's reason into a TRUTHFUL
    exception here and leave the public signatures alone.
    """
    read = _read_dispatcher_block(cwd=cwd)
    if isinstance(read, IOFailure):
        raise LivespecConfigUnreadableError(detail=unsafe_perform_io(read.failure()).detail)
    return unsafe_perform_io(read.unwrap())


def _read_dispatcher_block(*, cwd: Path) -> IOResult[dict[str, Any], ConfigUnreadable]:
    """Read the `livespec-orchestrator-beads-fabro.dispatcher` block, or {} when absent."""
    return _read_plugin_sub_block(cwd=cwd, key=_DISPATCHER_KEY)


def _read_plugin_sub_block(*, cwd: Path, key: str) -> IOResult[dict[str, Any], ConfigUnreadable]:
    """Read a named sub-block of the `livespec-orchestrator-beads-fabro` block.

    An ABSENT plugin block or sub-block yields `{}` on the success track, so
    each caller applies its own defaults; an UNREADABLE file propagates the
    failure from `_read_root_mapping`. Shared by the connection and dispatcher
    readers so the JSONC -> plugin-block -> sub-block traversal is
    single-sourced rather than duplicated per sub-block.
    """
    return _read_root_mapping(cwd=cwd).map(lambda root: _sub_block(root=root, key=key))


def _sub_block(*, root: dict[str, Any], key: str) -> dict[str, Any]:
    plugin_block_raw = root.get(_PLUGIN_BLOCK)
    if not isinstance(plugin_block_raw, dict):
        return {}
    plugin_block = cast("dict[str, Any]", plugin_block_raw)
    sub_block_raw = plugin_block.get(key)
    if not isinstance(sub_block_raw, dict):
        return {}
    return cast("dict[str, Any]", sub_block_raw)


def _configured_sandbox_image(*, block: dict[str, Any]) -> str | None:
    configured = _str_or(value=block.get("fabro_sandbox_image"), default="")
    if configured != "":
        return configured
    return None


def _require_prefix(*, block: dict[str, Any]) -> str:
    """Return the explicit `connection.prefix`, or raise if unset/empty.

    `prefix` is bd's server-stored issue-ID create-prefix (e.g. `bd-ib`),
    DECOUPLED from the tenant DB name. It is therefore NEVER defaulted to the
    tenant: an unset/empty prefix would mint tenant-named ids the server
    rejects, so the loader FAILS LOUD instead.
    """
    value = block.get("prefix")
    if isinstance(value, str) and value != "":
        return value
    raise ConnectionPrefixMissingError


def _resolve_bd_path(*, block: dict[str, Any]) -> str:
    env_value = os.environ.get(_ENV_BD_PATH)
    if env_value is not None and env_value != "":
        return env_value
    return _str_or(value=block.get("bd_path"), default=_DEFAULT_BD_PATH)


def _resolve_configured_factory_name(*, block: dict[str, Any]) -> str:
    factories_raw = block.get("factories")
    default_name = _str_or(value=block.get("default_factory"), default="default")
    if isinstance(factories_raw, dict):
        factories = cast("dict[str, Any]", factories_raw)
        if default_name in factories:
            return default_name
    return "default"


def _factory_target_for(*, name: str, block: dict[str, Any]) -> FactoryTarget:
    entry = _factory_entry(block=block, name=name)
    return FactoryTarget(
        name=name,
        server=_optional_str(value=entry.get("server")),
        fabro_bin=_optional_str(value=entry.get(_FACTORY_BIN_KEY)),
        dev_token=_optional_str(value=os.environ.get(f"{_FABRO_DEV_AUTH_ENV_PREFIX}{name}")),
    )


def _factory_entry(*, block: dict[str, Any], name: str) -> dict[str, Any]:
    """One named `dispatcher.factories` entry, or `{}` when it is not declared.

    An undeclared name is not an error here: the implicit single-factory
    `"default"` target is exactly this case, and it must keep resolving to a
    target with no server so an unconfigured repo preserves the ambient Fabro
    CLI behaviour.
    """
    factories_raw = block.get("factories")
    if not isinstance(factories_raw, dict):
        return {}
    factory_raw = cast("dict[str, Any]", factories_raw).get(name)
    if not isinstance(factory_raw, dict):
        return {}
    return cast("dict[str, Any]", factory_raw)


def _resolve_fake(*, block: dict[str, Any]) -> bool:
    env_value = os.environ.get(_ENV_FAKE)
    if env_value is not None:
        return env_value.strip().lower() in _TRUTHY
    block_value = block.get("fake")
    if isinstance(block_value, bool):
        return block_value
    return False


def _str_or(*, value: object, default: str) -> str:
    if isinstance(value, str) and value != "":
        return value
    return default


def _optional_str(*, value: object) -> str | None:
    if isinstance(value, str) and value != "":
        return value
    return None


def _int_or(*, value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default
