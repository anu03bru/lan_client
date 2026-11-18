"""Shared helpers for the end-to-end scripts in this folder (used by .github/workflows/e2e.yml)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR))

from lanparty.config import Game, load_games  # noqa: E402
from lanparty.download import expand_path  # noqa: E402

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def load_game(game_id: str) -> Game:
    for game in load_games(REPO_DIR / "games.toml"):
        if game.id == game_id:
            return game
    raise SystemExit(f"Unknown game '{game_id}'")


def spec_of(game: Game):
    if IS_WINDOWS:
        return game.windows
    if IS_MACOS:
        return game.macos
    return game.linux


def variables() -> dict[str, str]:
    if not IS_WINDOWS:
        return {}
    from lanparty.windows import windows_variables

    return windows_variables()


def home() -> Path:
    return Path(variables().get("USERPROFILE", str(Path.home())))


def path(text: str) -> Path:
    return expand_path(text, variables(), home())


def asset_dest(asset) -> str | None:
    if IS_WINDOWS:
        return asset.windows_dest
    if IS_MACOS:
        return asset.macos_dest
    return asset.linux_dest


def run(args: list[str]) -> subprocess.CompletedProcess:
    """Runs a command and captures its output. A missing command counts as exit code 127."""
    try:
        return subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError:
        return subprocess.CompletedProcess(args, 127, "", f"{args[0]} not found")


def powershell(command: str) -> subprocess.CompletedProcess:
    return run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                f"$ErrorActionPreference = 'Stop'; {command}"])
