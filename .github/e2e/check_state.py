"""Checks on its own (without lan.py's is_installed) what a game left on this machine.

    python check_state.py <game> present    after install: app, shortcuts, assets, firewall rules are there
    python check_state.py <game> absent     after uninstall: all of that plus the user data folders are gone
    python check_state.py <game> supported  prints true/false: does games.toml have a table for this OS

Prints PASS / FAIL / INFO per item and exits 1 if anything failed.
"""

from __future__ import annotations

import fnmatch
import os
import plistlib
import sys
from pathlib import Path

import common
from common import IS_LINUX, IS_MACOS, IS_WINDOWS

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {message}", flush=True)
    if not ok:
        failures.append(message)


def info(message: str) -> None:
    print(f"INFO  {message}", flush=True)


def check_gone(target: Path) -> None:
    check(not target.exists() and not target.is_symlink(), f"{target} is gone")


def check_assets(game, present: bool) -> None:
    for asset in game.assets:
        dest_text = common.asset_dest(asset)
        if not dest_text:
            continue
        dest = common.path(dest_text)
        if present:
            matches = sorted(p.name for p in dest.glob("*") if fnmatch.fnmatch(p.name.lower(), asset.extract.lower()))
            check(bool(matches), f"{dest} contains {asset.extract}: {', '.join(matches) or 'nothing'}")
        else:
            check_gone(dest)


def check_data_gone(spec) -> None:
    for text in spec.data:
        check_gone(common.path(text))


# ---------- Linux ----------

def linux(game, present: bool) -> None:
    spec = game.linux
    result = common.run(["flatpak", "info", "--user", spec.app_id])
    if present:
        check(result.returncode == 0, f"flatpak {spec.app_id} is installed")
        fields = {}
        for line in result.stdout.splitlines():
            key, _, value = line.strip().partition(":")
            fields[key.strip()] = value.strip()
        info(f"version {fields.get('Version', '?')}, commit {fields.get('Commit', '?')}")
        if spec.commit:
            check(fields.get("Commit") == spec.commit, f"pinned commit {spec.commit[:12]} is installed")
        if game.version:
            check(fields.get("Version", "").startswith(game.version), f"version is {game.version}")
    else:
        check(result.returncode != 0, f"flatpak {spec.app_id} is not installed")
        check_gone(common.home() / ".var" / "app" / spec.app_id)

    override_file = common.home() / ".local/share/flatpak/overrides" / spec.app_id
    if spec.override_env or spec.override_filesystem:
        if present:
            text = override_file.read_text() if override_file.is_file() else ""
            for name in spec.override_env:
                check(f"{name}=" in text, f"flatpak override sets {name}")
        else:
            check_gone(override_file)

    check_assets(game, present)
    if not present:
        check_data_gone(spec)
    if game.ports:
        linux_ufw(game, present)


def linux_ufw(game, present: bool) -> None:
    status = common.run(["sudo", "-n", "ufw", "status"])
    if status.returncode != 0 or "Status: active" not in status.stdout:
        info(f"ufw not active, firewall not checked ({(status.stdout + status.stderr).strip()[:200]})")
        return
    # Exact comment match, like lan.py: "AssaultCube server" rules are not ours
    rules = [line for line in status.stdout.splitlines() if line.partition("# ")[2].strip() == game.name]
    for port in game.ports:
        found = [line for line in rules if line.split()[0] == port]
        check(bool(found) == present, f"ufw rule {port} '{game.name}' {'exists' if present else 'is gone'}")


# ---------- Windows ----------

def windows(game, present: bool) -> None:
    from lanparty.windows import VERSION_MARKER, Registry, firewall_rules, ps_quote

    spec = game.windows
    variables = common.variables()
    if spec.type == "nsis":
        entries = Registry().find(spec.uninstall_name)
        for entry in entries:
            info(f"Apps & features: {entry.display_name} -> {entry.uninstall_string}")
        check(bool(entries) == present,
              f"'Apps & features' entry {spec.uninstall_name} {'exists' if present else 'is gone'}")
        # Leftovers in Program Files, e.g. files the uninstaller doesn't know about
        for root in {os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")} - {None}:
            for folder in sorted(Path(root).glob("*")):
                if fnmatch.fnmatch(folder.name.lower(), spec.uninstall_name.lower()):
                    if present:
                        info(f"install folder {folder}")
                    else:
                        check(False, f"{folder} is gone (left over: {', '.join(p.name for p in folder.iterdir())})")
    else:
        install_dir = common.path(spec.install_dir)
        if present:
            marker = install_dir / VERSION_MARKER
            check(marker.is_file() and marker.read_text(encoding="utf-8").strip() == spec.url,
                  f"{install_dir} holds {VERSION_MARKER} with the download URL")
            exes = sorted(str(p.relative_to(install_dir)) for p in install_dir.rglob("*.exe"))
            info(f"exe files: {', '.join(exes)}")
        else:
            check_gone(install_dir)

    for shortcut in spec.shortcuts:
        link = Path(variables["DESKTOP"]) / f"{shortcut.name}.lnk"
        if present:
            check(link.is_file(), f"desktop shortcut {link.name} exists")
        else:
            check_gone(link)

    check_assets(game, present)
    if not present:
        check_data_gone(spec)

    for rule_name, _protocol, _ports in firewall_rules(game):
        result = common.powershell(
            f"@(Get-NetFirewallRule -DisplayName {ps_quote(rule_name)} -ErrorAction SilentlyContinue).Count")
        count = int(result.stdout.strip() or 0) if result.returncode == 0 else -1
        # Exactly one: installing twice must not create duplicates
        check(count == (1 if present else 0), f"firewall rule '{rule_name}' count is {count}")


# ---------- macOS ----------

def macos(game, present: bool) -> None:
    spec = game.macos
    applications = common.home() / "Applications"
    for app in spec.apps:
        target = applications / app
        if present:
            check(target.is_dir(), f"{target} exists")
            try:
                with open(target / "Contents" / "Info.plist", "rb") as plist_file:
                    plist = plistlib.load(plist_file)
            except (OSError, plistlib.InvalidFileException) as error:
                check(False, f"{app} Info.plist readable ({error})")
                continue
            executable = target / "Contents" / "MacOS" / str(plist.get("CFBundleExecutable", ""))
            archs = common.run(["lipo", "-archs", str(executable)]).stdout.strip()
            info(f"{app}: version {plist.get('CFBundleShortVersionString', '?')}, architectures: {archs or '?'}")
            quarantine = common.run(["xattr", "-p", "com.apple.quarantine", str(target)])
            check(quarantine.returncode != 0, f"{app} has no quarantine flag")
        else:
            check_gone(target)
            check_gone(Path("/Applications") / app)
    check_assets(game, present)
    if not present:
        check_data_gone(spec)


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[2] not in ("present", "absent", "supported"):
        print(__doc__)
        return 2
    game = common.load_game(sys.argv[1])
    if sys.argv[2] == "supported":
        print("true" if common.spec_of(game) is not None else "false")
        return 0
    present = sys.argv[2] == "present"
    if IS_LINUX:
        linux(game, present)
    elif IS_WINDOWS:
        windows(game, present)
    elif IS_MACOS:
        macos(game, present)
    if failures:
        for message in failures:
            print(f"::error title={game.id} ({sys.argv[2]})::{message}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
