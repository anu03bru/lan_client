"""Starts an installed game for a few seconds and reports which files and folders it created.

    python smoke_start.py <game>

Answers open questions from .claude/open.md: does the game start at all (exe names, Rosetta), and where does it
keep its user data (the `data` entries in games.toml). CI runners have no GPU, so a crash after a few seconds is
expected and not an error. Prints a markdown report on stdout, progress on stderr. Always exits 0.
"""

from __future__ import annotations

import fnmatch
import json
import os
import plistlib
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import common
from common import IS_LINUX, IS_MACOS, IS_WINDOWS

RUN_SECONDS = 15
NOISY_NAMES = {"temp", "microsoft", "packages", "connecteddevicesplatform", "crashdumps", "pip", ".cache"}


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


# ---------- snapshot ----------

def snapshot_roots(game) -> list[tuple[Path, int]]:
    """(folder, depth) pairs that are searched for new files."""
    home = common.home()
    if IS_WINDOWS:
        variables = common.variables()
        roots = [(Path(variables["APPDATA"]), 2), (Path(variables["LOCALAPPDATA"]), 2),
                 (Path(variables["DOCUMENTS"]), 3), (home, 1)]
        if game.windows.install_dir:
            # Portable games may write settings next to the exe
            roots.append((common.path(game.windows.install_dir), 3))
        return roots
    if IS_MACOS:
        library = home / "Library"
        return [(library / "Application Support", 2), (library / "Caches", 1), (library / "Logs", 1),
                (library / "Preferences", 1), (library / "Containers", 1), (library / "Saved Application State", 1),
                (home / "Documents", 2), (home, 1)]
    return [(home / ".var" / "app" / game.linux.app_id, 3), (home, 1)]


def snapshot(roots: list[tuple[Path, int]]) -> set[Path]:
    found: set[Path] = set()

    def walk(folder: Path, depth: int) -> None:
        try:
            children = list(folder.iterdir())
        except OSError:
            return
        for child in children:
            if child.name.lower() in NOISY_NAMES:
                continue
            found.add(child)
            if depth > 1 and child.is_dir() and not child.is_symlink():
                walk(child, depth - 1)

    for root, depth in roots:
        walk(root, depth)
    return found


def top_level_only(paths: set[Path]) -> list[Path]:
    """Drops entries whose parent is also new, so a new folder shows up once."""
    return sorted(p for p in paths if p.parent not in paths)


def known_paths(game) -> list[Path]:
    spec = common.spec_of(game)
    texts = [*spec.data, *(common.asset_dest(asset) or "" for asset in game.assets)]
    if IS_LINUX:
        texts.append(f"~/.var/app/{spec.app_id}")
    return [common.path(text) for text in texts if text]


def is_known(entry: Path, known: list[Path]) -> bool:
    def norm(p: Path) -> str:
        text = str(p).replace("\\", "/").rstrip("/")
        return text.lower() if IS_WINDOWS else text

    entry_text = norm(entry)
    return any(entry_text == norm(k) or entry_text.startswith(norm(k) + "/") for k in known)


# ---------- launchers ----------

def launchers(game) -> list[tuple[str, list[str] | str, Path | None]]:
    """(label, command, working folder) for each way a player starts the game."""
    if IS_LINUX:
        return [(f"flatpak run {game.linux.app_id}",
                 ["xvfb-run", "-a", "flatpak", "run", "--user", game.linux.app_id], None)]
    if IS_MACOS:
        result = []
        for app in game.macos.apps:
            bundle = common.home() / "Applications" / app
            try:
                with open(bundle / "Contents" / "Info.plist", "rb") as plist_file:
                    executable = plistlib.load(plist_file)["CFBundleExecutable"]
            except (OSError, KeyError, plistlib.InvalidFileException) as error:
                log(f"{app}: no executable found ({error})")
                continue
            # The binary itself, not `open`: a "bad CPU type" error then shows up in the output
            binary = bundle / "Contents" / "MacOS" / executable
            result.append((app, [str(binary)], binary.parent))
        return result
    return windows_launchers(game)


def windows_launchers(game) -> list[tuple[str, str, Path | None]]:
    spec = game.windows
    variables = common.variables()
    if spec.type == "zip":
        links = [Path(variables["DESKTOP"]) / f"{shortcut.name}.lnk" for shortcut in spec.shortcuts]
    else:
        # The Start menu entries the NSIS installer created, as a player would start the game
        folders = [Path(os.environ["ProgramData"]) / "Microsoft/Windows/Start Menu/Programs",
                   Path(variables["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs",
                   Path(variables["DESKTOP"]), Path(os.environ.get("PUBLIC", "C:/Users/Public")) / "Desktop"]
        pattern = spec.uninstall_name.lower()
        links = []
        for folder in folders:
            for link in folder.rglob("*.lnk"):
                names = (link.stem.lower(), link.parent.name.lower())
                if any(fnmatch.fnmatch(name, pattern) for name in names):
                    links.append(link)
        log("Shortcuts found: " + (", ".join(str(link) for link in links) or "none"))
        links = [link for link in links if "uninstall" not in link.stem.lower()]
        # Prefer the shortcut named like the game, e.g. "SuperTuxKart.lnk" over "SuperTuxKart (debug).lnk"
        links.sort(key=lambda link: (len(link.stem), str(link)))
        links = links[:1]

    result = []
    for link in links:
        resolved = resolve_shortcut(link)
        if resolved is None:
            continue
        target, arguments, workdir = resolved
        if target.lower().endswith((".bat", ".cmd")):
            command = f'cmd.exe /c "{target}" {arguments}'
        else:
            command = f'"{target}" {arguments}'
        result.append((f"{link.name} -> {target} {arguments}".strip(), command,
                       Path(workdir) if workdir else Path(target).parent))
    return result


def resolve_shortcut(link: Path) -> tuple[str, str, str] | None:
    from lanparty.windows import ps_quote

    result = common.powershell(
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({ps_quote(str(link))}); "
        "@{target=$s.TargetPath; arguments=$s.Arguments; workdir=$s.WorkingDirectory} | ConvertTo-Json")
    if result.returncode != 0:
        log(f"Could not read {link}: {result.stderr.strip()}")
        return None
    data = json.loads(result.stdout)
    return data["target"] or "", data["arguments"] or "", data["workdir"] or ""


# ---------- run ----------

def start_and_stop(command: list[str] | str, workdir: Path | None, output_path: Path) -> str:
    with open(output_path, "w", encoding="utf-8", errors="replace") as output:
        options = {"cwd": workdir, "stdout": output, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
        if not IS_WINDOWS:
            options["start_new_session"] = True
        try:
            process = subprocess.Popen(command, **options)
        except OSError as error:
            return f"could not start: {error}"
        try:
            code = process.wait(timeout=RUN_SECONDS)
            return f"exited after less than {RUN_SECONDS} s with code {code}"
        except subprocess.TimeoutExpired:
            pass
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()
        return f"still running after {RUN_SECONDS} s (stopped)"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 0
    game = common.load_game(sys.argv[1])
    print(f"### Smoke start: {game.name}\n")

    roots = snapshot_roots(game)
    before = snapshot(roots)
    entries = launchers(game)
    if not entries:
        print("No way to start the game was found (no shortcut / app / exe).\n")
    with tempfile.TemporaryDirectory(prefix="smoke-") as temp_name:
        for number, (label, command, workdir) in enumerate(entries):
            log(f"Starting {label}")
            output_path = Path(temp_name) / f"output-{number}.txt"
            outcome = start_and_stop(command, workdir, output_path)
            tail = output_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-15:]
            print(f"**{label}**: {outcome}\n")
            if tail:
                print("```\n" + "\n".join(tail) + "\n```\n")
        if IS_LINUX:
            subprocess.run(["flatpak", "kill", game.linux.app_id], capture_output=True)
        time.sleep(2)

    new_entries = top_level_only(snapshot(roots) - before)
    known = known_paths(game)
    print("New files and folders after the start (compare with `data` in games.toml):\n")
    if not new_entries:
        print("- none\n")
    for entry in new_entries:
        kind = "folder" if entry.is_dir() else "file"
        status = "listed in games.toml" if is_known(entry, known) else "**not in games.toml `data`**"
        print(f"- `{entry}` ({kind}) - {status}")
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # Never fail the job: this step only collects information
        print(f"Smoke start failed: {error!r}\n")
        sys.exit(0)
