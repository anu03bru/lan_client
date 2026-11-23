#!/usr/bin/env python3
"""Builds the Linux Flatpak bundles for the LAN share (temporary, delete after the party with games-lan.toml).

Usage: python3 scripts/build_flatpak_bundles.py <folder> [--write] [--force]

Exports every game with a `bundle` and every `flatpak-runtime` in games-lan.toml from this PC's Flatpak user
installation into <folder>, where games-lan.toml expects it (%SHARE% = <folder>). The games must be installed here
at the commit pinned in games.toml (`./lan.py install <game>` does that), the runtimes at any build.
Then it prints the sha256 of each bundle. With --write it puts them into games-lan.toml.

Bundles that already exist are kept (and only hashed), unless --force is given.
Fill the rest of the share with scripts/fill_share.py, see docs/lan-share.md.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
LAN_GAMES_FILE = REPO_DIR / "games-lan.toml"
FLATPAK_REPO = Path.home() / ".local/share/flatpak/repo"
FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
SHARE_PLACEHOLDER = "%SHARE%"


def bundles(lan: dict) -> list[dict]:
    """Everything to build, in install order: runtimes first."""
    items = []
    for runtime_id, runtime in lan.get("runtimes", {}).items():
        if runtime["type"] == "flatpak-runtime":
            name, branch = runtime["ref"].split("//")
            items.append({"what": f"runtime {runtime['ref']}", "url": runtime["url"],
                          "args": ["--runtime", name, branch], "check_commit": None, "app_id": None})
    for game_id, table in lan.items():
        linux = table.get("linux", {}) if game_id not in ("runtimes", "share") else {}
        if "bundle" in linux:
            items.append({"what": f"app {linux['app_id']}", "url": linux["bundle"]["url"],
                          "args": None, "check_commit": linux.get("commit"), "app_id": linux["app_id"]})
    return items


def flatpak_output(args: list[str]) -> str:
    return subprocess.run(["flatpak", *args], capture_output=True, text=True, check=True).stdout.strip()


def build(item: dict, target: Path) -> None:
    # Written under another name first, so an interrupted build never looks finished
    partial = target.with_name(target.name + ".partial")
    if item["app_id"]:
        commit = flatpak_output(["info", "--user", "--show-commit", item["app_id"]])
        if item["check_commit"] and commit != item["check_commit"]:
            raise RuntimeError(f"{item['app_id']} is installed at {commit[:12]}, games.toml pins "
                               f"{item['check_commit'][:12]}. Run ./lan.py install first.")
        # e.g. app/net.supertuxkart.SuperTuxKart/x86_64/stable
        _kind, app_id, _arch, branch = flatpak_output(["info", "--user", "--show-ref", item["app_id"]]).split("/")
        args = [f"--runtime-repo={FLATHUB_URL}", str(FLATPAK_REPO), str(partial), app_id, branch]
    else:
        flag, name, branch = item["args"]
        args = [flag, str(FLATPAK_REPO), str(partial), name, branch]
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["flatpak", "build-bundle", *args], check=True)
    partial.rename(target)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256(text: str, url: str, sha256: str) -> str:
    """Replaces the first sha256 value after `url` in games-lan.toml (same inline table or the next lines)."""
    start = text.index(f'"{url}"')
    match = re.compile(r'sha256 = "[0-9a-f]*"').search(text, start)
    if match is None:
        raise ValueError(f"no sha256 after {url}")
    return text[:match.start()] + f'sha256 = "{sha256}"' + text[match.end():]


def main(argv: list[str]) -> int:
    flags = {arg for arg in argv if arg.startswith("--")}
    paths = [arg for arg in argv if not arg.startswith("--")]
    if len(paths) != 1 or flags - {"--write", "--force"}:
        print(__doc__, file=sys.stderr)
        return 2
    folder = Path(paths[0]).resolve()
    lan_text = LAN_GAMES_FILE.read_text(encoding="utf-8")
    lan = tomllib.loads(lan_text)

    failed = []
    results = []
    for item in bundles(lan):
        target = Path(item["url"].replace(SHARE_PLACEHOLDER, str(folder)))
        if target.exists() and "--force" not in flags:
            print(f"OK (already there) {target}")
        else:
            print(f"==> Build {item['what']} -> {target}", flush=True)
            started = time.monotonic()
            try:
                build(item, target)
            except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
                print(f"ERROR: {error}")
                failed.append(item["what"])
                continue
            print(f"    {target.stat().st_size / 1e6:.0f} MB in {time.monotonic() - started:.0f} s")
        sha256 = sha256_of(target)
        results.append((item["url"], sha256))
        print(f"    sha256 {sha256}")

    if "--write" in flags:
        for url, sha256 in results:
            lan_text = write_sha256(lan_text, url, sha256)
        LAN_GAMES_FILE.write_text(lan_text, encoding="utf-8")
        print(f"\nWrote {len(results)} sha256 value(s) into {LAN_GAMES_FILE.name}.")
    if failed:
        print(f"\n{len(failed)} bundle(s) failed: " + ", ".join(failed))
        return 1
    print(f"\nDone. Copy the contents of {folder} to the LAN share.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
