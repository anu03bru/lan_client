"""Loads games.toml into plain data classes and reports mistakes in it clearly."""

from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """games.toml is missing, unreadable or has a wrong entry."""


@dataclass(frozen=True)
class Shortcut:
    name: str
    target: str


@dataclass(frozen=True)
class Asset:
    url: str
    sha256: str
    extract: str
    linux_dest: str
    windows_dest: str
    macos_dest: str | None = None


@dataclass(frozen=True)
class Runtime:
    """Something a Windows game needs to start, e.g. the Visual C++ Redistributable. Installed only when missing,
    never removed: other programs use it too."""
    id: str
    type: str
    name: str
    url: str
    sha256: str
    version: str


@dataclass(frozen=True)
class LinuxSpec:
    type: str
    app_id: str
    url: str | None = None
    sha256: str | None = None
    commit: str | None = None
    override_env: dict[str, str] = field(default_factory=dict)
    override_filesystem: tuple[str, ...] = ()
    data: tuple[str, ...] = ()


@dataclass(frozen=True)
class WindowsSpec:
    type: str
    url: str
    sha256: str
    uninstall_name: str | None = None
    install_dir: str | None = None
    shortcuts: tuple[Shortcut, ...] = ()
    data: tuple[str, ...] = ()
    requires: tuple[Runtime, ...] = ()


@dataclass(frozen=True)
class MacosSpec:
    type: str
    url: str
    sha256: str
    apps: tuple[str, ...]
    arm64_url: str | None = None
    arm64_sha256: str | None = None
    data: tuple[str, ...] = ()


@dataclass(frozen=True)
class Game:
    id: str
    name: str
    version: str | None = None
    ports: tuple[str, ...] = ()
    reply_ports: tuple[str, ...] = ()
    hint: str | None = None
    linux: LinuxSpec | None = None
    windows: WindowsSpec | None = None
    macos: MacosSpec | None = None
    assets: tuple[Asset, ...] = ()


GAME_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
PORT_PATTERN = re.compile(r"^\d{1,5}/(udp|tcp)$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
VERSION_PATTERN = re.compile(r"^\d+(\.\d+){1,3}$")

# type -> (required keys, optional keys)
LINUX_TYPES = {
    "flatpak": ({"type", "app_id"}, {"commit", "overrides", "data"}),
    "flatpak-bundle": ({"type", "app_id", "url", "sha256"}, {"overrides", "data"}),
}
WINDOWS_TYPES = {
    "nsis": ({"type", "url", "sha256", "uninstall_name"}, {"data", "requires"}),
    "zip": ({"type", "url", "sha256", "install_dir"}, {"shortcuts", "data", "requires"}),
}
MACOS_TYPES = {
    "dmg": ({"type", "url", "sha256", "apps"}, {"arm64", "data"}),
    "zip": ({"type", "url", "sha256", "apps"}, {"arm64", "data"}),
}
RUNTIME_TYPES = {
    "vcredist-x64": ({"type", "name", "url", "sha256", "version"}, set()),
}
PLATFORMS = ("linux", "windows", "macos")
# Stands for the LAN share folder in games-lan.toml, set per OS by its [share] table
SHARE_PLACEHOLDER = "%SHARE%"


def load_games(path: Path) -> list[Game]:
    try:
        with open(path, "rb") as games_file:
            tables = tomllib.load(games_file)
    except FileNotFoundError:
        raise ConfigError(f"{path} not found") from None
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path} is not valid TOML: {error}") from None
    return parse_games(fill_share(tables))


def fill_share(tables: dict[str, Any]) -> dict[str, Any]:
    """Takes the [share] table out and replaces %SHARE% with the share folder for this OS (games-lan.toml)."""
    tables = dict(tables)
    share = tables.pop("share", None)
    uses_share = SHARE_PLACEHOLDER in repr(tables)
    if share is None:
        if uses_share:
            raise ConfigError(f"{SHARE_PLACEHOLDER} is used, but there is no [share] table with the share folder")
        return tables
    _check_keys("[share]", share, set(PLATFORMS), set())
    for platform in PLATFORMS:
        if not isinstance(share[platform], str) or not share[platform]:
            raise ConfigError(f"[share]: {platform} must be a folder path")
    folder = share[current_platform()]
    if folder == "~" or folder.startswith("~/"):
        folder = Path.home().as_posix() + folder[1:]
    return _replace_share(tables, folder.rstrip("/"))


def current_platform() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _replace_share(value: Any, folder: str) -> Any:
    if isinstance(value, str):
        return value.replace(SHARE_PLACEHOLDER, folder)
    if isinstance(value, dict):
        return {key: _replace_share(item, folder) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_share(item, folder) for item in value]
    return value


def parse_games(tables: dict[str, Any]) -> list[Game]:
    tables = dict(tables)
    runtimes = _parse_runtimes(tables.pop("runtimes", {}))
    games = []
    for game_id, table in tables.items():
        if not GAME_ID_PATTERN.match(game_id) or game_id == "all":
            raise ConfigError(f"[{game_id}]: game id must be lowercase letters, digits or _, and not 'all'")
        games.append(_parse_game(game_id, table, runtimes))
    return games


def _parse_runtimes(tables: Any) -> dict[str, Runtime]:
    if not isinstance(tables, dict):
        raise ConfigError("[runtimes]: expected tables like [runtimes.vcredist_x64]")
    runtimes = {}
    for runtime_id, table in tables.items():
        where = f"[runtimes.{runtime_id}]"
        spec_type = _spec_type(where, table, RUNTIME_TYPES)
        required, optional = RUNTIME_TYPES[spec_type]
        _check_keys(where, table, required, optional)
        version = _string(where, table, "version")
        if not VERSION_PATTERN.match(version):
            raise ConfigError(f"{where}: version must look like 14.44.35211")
        runtimes[runtime_id] = Runtime(
            id=runtime_id,
            type=spec_type,
            name=_string(where, table, "name"),
            url=_string(where, table, "url"),
            sha256=_sha256(where, table),
            version=version,
        )
    return runtimes


def _parse_game(game_id: str, table: Any, runtimes: dict[str, Runtime]) -> Game:
    where = f"[{game_id}]"
    _check_keys(where, table, {"name"}, {"version", "ports", "reply_ports", "hint", *PLATFORMS, "assets"})
    ports = _ports(where, table, "ports")
    reply_ports = _ports(where, table, "reply_ports")
    if not any(platform in table for platform in PLATFORMS):
        raise ConfigError(f"{where}: needs a [{game_id}.linux], [{game_id}.windows] or [{game_id}.macos] table")

    assets = table.get("assets", [])
    if not isinstance(assets, list):
        raise ConfigError(f"{where}: assets must be written as [[{game_id}.assets]] tables")
    parsed_assets = tuple(_parse_asset(f"[[{game_id}.assets]] #{index + 1}", asset) for index, asset in enumerate(assets))
    if "macos" in table and any(asset.macos_dest is None for asset in parsed_assets):
        raise ConfigError(f"{where}: every [[{game_id}.assets]] needs a macos_dest, because the game has a macos table")

    return Game(
        id=game_id,
        name=_string(where, table, "name"),
        version=_string(where, table, "version"),
        ports=ports,
        reply_ports=reply_ports,
        hint=_string(where, table, "hint"),
        linux=_parse_linux(f"[{game_id}.linux]", table["linux"]) if "linux" in table else None,
        windows=_parse_windows(f"[{game_id}.windows]", table["windows"], runtimes) if "windows" in table else None,
        macos=_parse_macos(f"[{game_id}.macos]", table["macos"]) if "macos" in table else None,
        assets=parsed_assets,
    )


def _parse_linux(where: str, table: Any) -> LinuxSpec:
    spec_type = _spec_type(where, table, LINUX_TYPES)
    required, optional = LINUX_TYPES[spec_type]
    _check_keys(where, table, required, optional)

    overrides = table.get("overrides", {})
    _check_keys(f"{where} overrides", overrides, set(), {"env", "filesystem"})
    override_env = overrides.get("env", {})
    if not isinstance(override_env, dict) or not all(isinstance(value, str) for value in override_env.values()):
        raise ConfigError(f"{where} overrides: env must be a table of strings")

    return LinuxSpec(
        type=spec_type,
        app_id=_string(where, table, "app_id"),
        url=_string(where, table, "url"),
        sha256=_sha256(where, table),
        commit=_commit(where, table),
        override_env=dict(override_env),
        override_filesystem=_strings(f"{where} overrides", overrides, "filesystem"),
        data=_strings(where, table, "data"),
    )


def _parse_windows(where: str, table: Any, runtimes: dict[str, Runtime]) -> WindowsSpec:
    spec_type = _spec_type(where, table, WINDOWS_TYPES)
    required, optional = WINDOWS_TYPES[spec_type]
    _check_keys(where, table, required, optional)

    shortcuts = table.get("shortcuts", [])
    if not isinstance(shortcuts, list):
        raise ConfigError(f"{where}: shortcuts must be a list of {{ name, target }}")
    for shortcut in shortcuts:
        _check_keys(f"{where} shortcut", shortcut, {"name", "target"}, set())

    requires = _strings(where, table, "requires")
    for runtime_id in requires:
        if runtime_id not in runtimes:
            known = ", ".join(runtimes) or "none"
            raise ConfigError(f"{where}: requires unknown runtime {runtime_id!r} (defined in [runtimes]: {known})")

    return WindowsSpec(
        type=spec_type,
        url=_string(where, table, "url"),
        sha256=_sha256(where, table),
        uninstall_name=_string(where, table, "uninstall_name"),
        install_dir=_string(where, table, "install_dir"),
        shortcuts=tuple(Shortcut(name=str(item["name"]), target=str(item["target"])) for item in shortcuts),
        data=_strings(where, table, "data"),
        requires=tuple(runtimes[runtime_id] for runtime_id in dict.fromkeys(requires)),
    )


def _parse_macos(where: str, table: Any) -> MacosSpec:
    spec_type = _spec_type(where, table, MACOS_TYPES)
    required, optional = MACOS_TYPES[spec_type]
    _check_keys(where, table, required, optional)

    apps = _strings(where, table, "apps")
    if not apps or not all(app.endswith(".app") and "/" not in app for app in apps):
        raise ConfigError(f"{where}: apps must be a non-empty list of names like \"SuperTuxKart.app\"")

    arm64 = table.get("arm64", {})
    _check_keys(f"{where} arm64", arm64, {"url", "sha256"} if arm64 else set(), set() if arm64 else {"url", "sha256"})

    return MacosSpec(
        type=spec_type,
        url=_string(where, table, "url"),
        sha256=_sha256(where, table),
        apps=apps,
        arm64_url=_string(f"{where} arm64", arm64, "url"),
        arm64_sha256=_sha256(f"{where} arm64", arm64),
        data=_strings(where, table, "data"),
    )


def _parse_asset(where: str, table: Any) -> Asset:
    _check_keys(where, table, {"url", "sha256", "extract", "linux_dest", "windows_dest"}, {"macos_dest"})
    return Asset(
        url=_string(where, table, "url"),
        sha256=_sha256(where, table),
        extract=_string(where, table, "extract"),
        linux_dest=_string(where, table, "linux_dest"),
        windows_dest=_string(where, table, "windows_dest"),
        macos_dest=_string(where, table, "macos_dest"),
    )


def _spec_type(where: str, table: Any, types: dict) -> str:
    if not isinstance(table, dict) or "type" not in table:
        raise ConfigError(f"{where}: missing 'type' (one of: {', '.join(types)})")
    if table["type"] not in types:
        raise ConfigError(f"{where}: unknown type {table['type']!r} (one of: {', '.join(types)})")
    return table["type"]


def _check_keys(where: str, table: Any, required: set[str], optional: set[str]) -> None:
    if not isinstance(table, dict):
        raise ConfigError(f"{where}: expected a table")
    missing = sorted(required - table.keys())
    unknown = sorted(table.keys() - required - optional)
    if missing:
        raise ConfigError(f"{where}: missing {', '.join(missing)}")
    if unknown:
        raise ConfigError(f"{where}: unknown key {', '.join(unknown)} (typo?)")


def _string(where: str, table: dict, key: str) -> str | None:
    value = table.get(key)
    if value is not None and not isinstance(value, str):
        raise ConfigError(f"{where}: {key} must be a string")
    return value


def _strings(where: str, table: dict, key: str) -> tuple[str, ...]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{where}: {key} must be a list of strings")
    return tuple(value)


def _ports(where: str, table: dict, key: str) -> tuple[str, ...]:
    ports = _strings(where, table, key)
    for port in ports:
        if not PORT_PATTERN.match(port):
            raise ConfigError(f"{where}: port {port!r} must look like 2759/udp")
    return ports


def _commit(where: str, table: dict) -> str | None:
    value = _string(where, table, "commit")
    if value is not None and not SHA256_PATTERN.match(value):
        raise ConfigError(f"{where}: commit must be the 64 hex characters from flatpak remote-info --log")
    return value


def _sha256(where: str, table: dict) -> str | None:
    value = _string(where, table, "sha256")
    if value is not None and not SHA256_PATTERN.match(value):
        raise ConfigError(f"{where}: sha256 must be 64 lowercase hex characters")
    return value
