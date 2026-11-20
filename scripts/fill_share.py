#!/usr/bin/env python3
"""Downloads every game file for the LAN share (temporary, delete after the party with games-lan.toml).

Usage: python3 scripts/fill_share.py <folder>

Each file from games.toml is saved where games-lan.toml expects it (%SHARE% = <folder>) and checked against its
sha256. Files that are already there with the right checksum are skipped, so it is safe to run again.
Then copy the folder's contents to the LAN share. See docs/lan-share.md.
"""

from __future__ import annotations

import hashlib
import sys
import tomllib
from pathlib import Path
from typing import Any, Iterator

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from lanparty.config import SHARE_PLACEHOLDER  # noqa: E402
from lanparty.download import download  # noqa: E402


def downloads(original: Any, lan: Any) -> Iterator[tuple[str, str, str]]:
    """Yields (internet url, share path, sha256) for every url in the two files, which have the same layout."""
    if isinstance(original, dict):
        if "url" in original:
            yield original["url"], lan["url"], original["sha256"]
        for key, value in original.items():
            yield from downloads(value, lan[key])
    elif isinstance(original, list):
        for original_item, lan_item in zip(original, lan, strict=True):
            yield from downloads(original_item, lan_item)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    folder = Path(argv[0]).resolve()
    with open(REPO_DIR / "games.toml", "rb") as file:
        original = tomllib.load(file)
    with open(REPO_DIR / "games-lan.toml", "rb") as file:
        lan = tomllib.load(file)
    lan.pop("share", None)

    failed = []
    for url, share_path, sha256 in downloads(original, lan):
        target = Path(share_path.replace(SHARE_PLACEHOLDER, str(folder)))
        if target.exists() and sha256_of(target) == sha256:
            print(f"OK (already there) {target}")
            continue
        print(f"Download {url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            download(url, target, sha256)
        except (OSError, ValueError) as error:
            print(f"ERROR: {error}")
            failed.append(url)
    if failed:
        print(f"\n{len(failed)} download(s) failed, run again: " + ", ".join(failed))
        return 1
    print(f"\nDone. Copy the contents of {folder} to the LAN share.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
