"""Downloads with checksum check, ZIP extraction and path placeholders."""

from __future__ import annotations

import fnmatch
import hashlib
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Mapping

# SourceForge sends an HTML page to browsers, but the real file to wget
USER_AGENT = "Wget/1.21"
VARIABLE_PATTERN = re.compile(r"%([A-Za-z_]+)%")


def download(url: str, target: Path, expected_sha256: str) -> None:
    """Downloads url, or copies it when it is a plain path (a file on the LAN share), and checks the sha256."""
    if is_local(url):
        source = Path(url)
        with open(source, "rb") as source_file:
            _copy_checked(source_file, source.stat().st_size, target, expected_sha256)
        return
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        _copy_checked(response, int(response.headers.get("Content-Length") or 0), target, expected_sha256)


def is_local(url: str) -> bool:
    return "://" not in url


def download_hint(url: str) -> str:
    if is_local(url):
        return (f"Open the LAN share first (see docs/lan-share.md), or check the [share] table in games-lan.toml. "
                f"File: {url}")
    return f"Check the internet connection and the URL: {url}"


def _copy_checked(source: BinaryIO, total_bytes: int, target: Path, expected_sha256: str) -> None:
    digest = hashlib.sha256()
    with open(target, "wb") as target_file:
        done_bytes = 0
        shown_percent = -1
        while chunk := source.read(1024 * 1024):
            target_file.write(chunk)
            digest.update(chunk)
            done_bytes += len(chunk)
            percent = done_bytes * 100 // total_bytes if total_bytes else -1
            if percent != shown_percent:
                shown_percent = percent
                total_text = f" / {total_bytes / 1e6:.0f} MB" if total_bytes else " MB"
                print(f"\r    {done_bytes / 1e6:.0f}{total_text}", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)

    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        target.unlink()
        raise ValueError(f"Checksum mismatch. Expected {expected_sha256}, got {actual_sha256}")


def extract_all(zip_path: Path, dest: Path) -> None:
    # extractall strips absolute paths and ".." so nothing lands outside dest
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)


def extract_matching(zip_path: Path, pattern: str, dest: Path) -> str:
    """Copies all files whose name matches the pattern (e.g. *.wad) flat into dest."""
    dest.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            file_name = PurePosixPath(member.filename).name
            if member.is_dir() or not fnmatch.fnmatch(file_name.lower(), pattern.lower()):
                continue
            with archive.open(member) as source, open(dest / file_name, "wb") as target:
                shutil.copyfileobj(source, target)
            extracted.append(file_name)
    if not extracted:
        raise ValueError(f"No file matching {pattern} in {zip_path.name}")
    return ", ".join(extracted)


def expand_text(text: str, variables: Mapping[str, str], home: Path) -> str:
    """Replaces %NAME% from variables and a leading ~ with the home folder."""

    def replace(match: re.Match) -> str:
        name = match.group(1).upper()
        if name not in variables:
            raise ValueError(f"Unknown placeholder %{name}% in {text!r}")
        return variables[name]

    expanded = VARIABLE_PATTERN.sub(replace, text)
    if expanded == "~" or expanded.startswith("~/"):
        expanded = str(home) + expanded[1:]
    return expanded


def expand_path(text: str, variables: Mapping[str, str], home: Path) -> Path:
    return Path(expand_text(text, variables, home))


def file_name_from_url(url: str) -> str:
    # SourceForge URLs end in /download, so take the last part that looks like a file
    parts = [part for part in url.split("?")[0].split("/") if part]
    for part in reversed(parts):
        if "." in part:
            return part
    return "download"


def remove_path(path: Path) -> str | None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return None
    if path.exists() or path.is_symlink():
        path.unlink()
        return None
    return "not found, nothing to do"
