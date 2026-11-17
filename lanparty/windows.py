"""Windows handler: NSIS installers, portable ZIPs, desktop shortcuts and Windows Defender Firewall.

winreg and ctypes.windll only exist on Windows, so they are imported inside the functions.
That keeps this module importable on Linux for the tests.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Game, WindowsSpec
from .download import download, expand_path, extract_all, extract_matching, file_name_from_url, remove_path
from .runner import Runner
from .steps import Steps

UNINSTALL_KEYS = (
    ("HKEY_LOCAL_MACHINE", r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKEY_LOCAL_MACHINE", r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKEY_CURRENT_USER", r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
)
UNINSTALL_TIMEOUT_SECONDS = 300
# Written into a ZIP game's folder; holds the download URL of the installed version
VERSION_MARKER = ".lanparty-version"


@dataclass(frozen=True)
class UninstallEntry:
    display_name: str
    uninstall_string: str
    root: str
    key_path: str


class Windows:
    name = "Windows"

    def __init__(
        self,
        runner: Runner,
        steps: Steps,
        variables: dict[str, str] | None = None,
        registry: "Registry | None" = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.runner = runner
        self.steps = steps
        self.variables = variables if variables is not None else windows_variables()
        self.registry = registry or Registry()
        self.sleep = sleep
        self.home = Path(self.variables.get("USERPROFILE", str(Path.home())))

    def check_ready(self) -> None:
        # Colors: turns on ANSI escape codes in the classic Windows console
        os.system("")

    def needs_admin(self) -> bool:
        return not is_admin()

    def supports(self, game: Game) -> bool:
        return game.windows is not None

    def is_installed(self, game: Game) -> bool:
        spec = game.windows
        if spec is None:
            return False
        if spec.type == "nsis":
            return bool(self.registry.find(spec.uninstall_name))
        return self._path(spec.install_dir).exists()

    # ---------- install ----------

    def install(self, game: Game) -> None:
        spec = game.windows
        assert spec is not None
        steps = self.steps
        with tempfile.TemporaryDirectory(prefix="lanparty-") as temp_name:
            temp_dir = Path(temp_name)
            download_path = temp_dir / file_name_from_url(spec.url)
            steps.run(
                f"Download {game.name}",
                f"Check the internet connection and the URL: {spec.url}",
                download, spec.url, download_path, spec.sha256,
            )
            if spec.type == "nsis":
                steps.run(
                    f"Install {game.name}",
                    f"The installer failed. Download and run it manually: {spec.url}",
                    self._run_installer, download_path,
                )
            else:
                install_dir = self._path(spec.install_dir)
                steps.run(
                    "Remove the old version",
                    f"Close the game and delete {install_dir} manually.",
                    remove_other_version, install_dir, spec.url,
                )
                steps.run(
                    f"Extract {game.name} to {install_dir}",
                    f"The ZIP may be corrupt. Delete {install_dir} and try again.",
                    extract_all, download_path, install_dir,
                )
                (install_dir / VERSION_MARKER).write_text(spec.url, encoding="utf-8")

            for asset in game.assets:
                asset_path = temp_dir / file_name_from_url(asset.url)
                dest = self._path(asset.windows_dest)
                steps.run(
                    f"Download {file_name_from_url(asset.url)}",
                    f"Check the internet connection and the URL: {asset.url}",
                    download, asset.url, asset_path, asset.sha256,
                )
                steps.run(
                    f"Extract {asset.extract} to {dest}",
                    "The ZIP may be corrupt. Run the install again.",
                    extract_matching, asset_path, asset.extract, dest,
                )

        for shortcut in spec.shortcuts:
            steps.run(
                f"Create desktop shortcut '{shortcut.name}'",
                f"Start the game manually from {self._path(spec.install_dir)}.",
                self._create_shortcut, spec, shortcut.name, shortcut.target,
            )
        if game.ports:
            for rule_name, protocol, ports in firewall_rules(game):
                steps.attempt(
                    f"Open firewall ports ({protocol} {ports})",
                    "Run in an admin PowerShell: New-NetFirewallRule -DisplayName "
                    f"{ps_quote(rule_name)} -Direction Inbound -Protocol {protocol} -LocalPort {ports} -Action Allow",
                    self._add_firewall_rule, rule_name, protocol, ports,
                )

    def _run_installer(self, installer_path: Path) -> None:
        result = self.runner.run([str(installer_path), "/S"], check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Installer exited with code {result.returncode}")

    def _create_shortcut(self, spec: WindowsSpec, name: str, target: str) -> None:
        install_dir = self._path(spec.install_dir)
        matches = sorted(install_dir.rglob(target))
        if not matches:
            raise FileNotFoundError(f"{target} not found in {install_dir}. Update the shortcut target in games.toml.")
        target_path = matches[0]
        shortcut_path = self._path(f"%DESKTOP%/{name}.lnk")
        self._powershell(
            f"$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut({ps_quote(str(shortcut_path))}); "
            f"$shortcut.TargetPath = {ps_quote(str(target_path))}; "
            f"$shortcut.WorkingDirectory = {ps_quote(str(target_path.parent))}; "
            "$shortcut.Save()"
        )

    def _add_firewall_rule(self, rule_name: str, protocol: str, ports: str) -> None:
        # Remove first, so running the install again doesn't create duplicates
        self._powershell(
            f"Get-NetFirewallRule -DisplayName {ps_quote(rule_name)} -ErrorAction SilentlyContinue | Remove-NetFirewallRule; "
            f"New-NetFirewallRule -DisplayName {ps_quote(rule_name)} -Direction Inbound -Protocol {protocol} "
            f"-LocalPort {ports} -Action Allow -Profile Any | Out-Null"
        )

    # ---------- uninstall ----------

    def uninstall(self, game: Game) -> None:
        spec = game.windows
        assert spec is not None
        steps = self.steps
        if spec.type == "nsis":
            steps.attempt(
                f"Uninstall {game.name}",
                "Uninstall it via Settings -> Apps -> Installed apps.",
                self._uninstall_nsis, spec.uninstall_name,
            )
        for shortcut in spec.shortcuts:
            shortcut_path = self._path(f"%DESKTOP%/{shortcut.name}.lnk")
            steps.attempt(
                f"Remove desktop shortcut '{shortcut.name}'",
                "Delete the shortcut from the desktop manually.",
                remove_path, shortcut_path,
            )
        folders = [*([spec.install_dir] if spec.install_dir else []), *spec.data,
                   *(asset.windows_dest for asset in game.assets)]
        for folder in dict.fromkeys(self._path(text) for text in folders):
            steps.attempt(f"Remove {folder}", "Close the game and delete the folder manually.", remove_path, folder)
        if game.ports:
            for rule_name, _protocol, _ports in firewall_rules(game):
                steps.attempt(
                    f"Remove firewall rule '{rule_name}'",
                    f"Run in an admin PowerShell: Remove-NetFirewallRule -DisplayName {ps_quote(rule_name)}",
                    self._remove_firewall_rule, rule_name,
                )

    def cleanup_after_uninstall_all(self) -> None:
        pass

    def _uninstall_nsis(self, pattern: str) -> str | None:
        entries = self.registry.find(pattern)
        if not entries:
            return "not installed, nothing to do"
        for entry in entries:
            uninstaller = uninstaller_path(entry.uninstall_string)
            if not uninstaller.lower().endswith(".exe") or not Path(uninstaller).is_file():
                raise RuntimeError(f"Unexpected uninstaller for {entry.display_name}: {entry.uninstall_string}")
            self.steps.info(f"Uninstalling {entry.display_name}")
            self.runner.run([uninstaller, "/S"], check=False)
            # The NSIS uninstaller copies itself to a temp folder and returns at once,
            # so wait until its entry is gone from "Apps & features"
            waited_seconds = 0
            while self.registry.exists(entry) and waited_seconds < UNINSTALL_TIMEOUT_SECONDS:
                self.sleep(2)
                waited_seconds += 2
            if self.registry.exists(entry):
                raise TimeoutError(f"{entry.display_name} is still installed after 5 minutes.")
        return None

    def _remove_firewall_rule(self, rule_name: str) -> str | None:
        result = self._powershell(
            f"if (Get-NetFirewallRule -DisplayName {ps_quote(rule_name)} -ErrorAction SilentlyContinue) "
            f"{{ Remove-NetFirewallRule -DisplayName {ps_quote(rule_name)}; 'removed' }} else {{ 'none' }}",
            capture=True,
        )
        return "no rule, nothing to do" if result.stdout.strip() == "none" else None

    # ---------- helpers ----------

    def _powershell(self, command: str, capture: bool = False) -> subprocess.CompletedProcess:
        return self.runner.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", f"$ErrorActionPreference = 'Stop'; {command}"],
            capture=capture,
        )

    def _path(self, text: str) -> Path:
        return expand_path(text, self.variables, self.home)


def remove_other_version(install_dir: Path, url: str) -> str | None:
    """Deletes a ZIP game's folder when it holds a different version, so no old files stay behind.
    The same version is kept: portable games may store settings (e.g. the player name) next to the exe."""
    marker = install_dir / VERSION_MARKER
    if not install_dir.exists():
        return "not installed, nothing to do"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == url:
        return "same version, kept"
    shutil.rmtree(install_dir)
    return None


def firewall_rules(game: Game) -> list[tuple[str, str, str]]:
    """One rule per protocol. The name matches what the old install scripts created,
    e.g. "SuperTuxKart multiplayer (UDP 2757,2759)", so uninstall also finds those."""
    ports_by_protocol: dict[str, list[int]] = {}
    for port in game.ports:
        number, protocol = port.split("/")
        ports_by_protocol.setdefault(protocol.upper(), []).append(int(number))
    rules = []
    for protocol, numbers in sorted(ports_by_protocol.items()):
        ports = ",".join(str(number) for number in sorted(numbers))
        rules.append((f"{game.name} multiplayer ({protocol} {ports})", protocol, ports))
    return rules


def uninstaller_path(uninstall_string: str) -> str:
    """'"C:\\Program Files\\X\\uninst.exe" /x' -> 'C:\\Program Files\\X\\uninst.exe'"""
    text = uninstall_string.strip()
    quoted = re.match(r'^"([^"]+)"', text)
    if quoted:
        return quoted.group(1)
    exe_end = text.lower().find(".exe")
    return text[: exe_end + 4] if exe_end >= 0 else text


def ps_quote(text: str) -> str:
    """Quotes a string for PowerShell. Single quotes are literal, so nothing inside gets expanded."""
    return "'" + text.replace("'", "''") + "'"


def is_admin() -> bool:
    import ctypes

    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def windows_variables() -> dict[str, str]:
    """Values for the %NAME% placeholders in games.toml."""
    if sys.platform != "win32":
        return {}
    import ctypes

    def folder(csidl: int) -> str:
        buffer = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer)
        return buffer.value

    return {
        "APPDATA": os.environ["APPDATA"],
        "LOCALAPPDATA": os.environ["LOCALAPPDATA"],
        "USERPROFILE": os.environ["USERPROFILE"],
        # The real folders, also when they were moved, e.g. into OneDrive
        "DOCUMENTS": folder(0x0005),  # CSIDL_PERSONAL
        "DESKTOP": folder(0x0010),  # CSIDL_DESKTOPDIRECTORY
    }


def relaunch_as_admin(script: Path, arguments: list[str]) -> int:
    """Starts this app again with admin rights (one UAC prompt) and waits for it."""
    argument_line = subprocess.list2cmdline([str(script), *arguments])
    command = (
        f"$process = Start-Process -FilePath {ps_quote(sys.executable)} -ArgumentList {ps_quote(argument_line)} "
        "-Verb RunAs -Wait -PassThru; exit $process.ExitCode"
    )
    return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]).returncode


class Registry:
    """Reads the "Apps & features" entries from the registry."""

    def find(self, pattern: str) -> list[UninstallEntry]:
        import winreg

        entries = []
        for root_name, key_path in UNINSTALL_KEYS:
            root = getattr(winreg, root_name)
            try:
                parent = winreg.OpenKey(root, key_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            except OSError:
                continue
            with parent:
                for index in range(winreg.QueryInfoKey(parent)[0]):
                    sub_name = winreg.EnumKey(parent, index)
                    try:
                        with winreg.OpenKey(parent, sub_name) as app_key:
                            display_name = winreg.QueryValueEx(app_key, "DisplayName")[0]
                            uninstall_string = winreg.QueryValueEx(app_key, "UninstallString")[0]
                    except OSError:
                        continue
                    if fnmatch.fnmatch(str(display_name).lower(), pattern.lower()):
                        entries.append(UninstallEntry(str(display_name), str(uninstall_string), root_name,
                                                      f"{key_path}\\{sub_name}"))
        return entries

    def exists(self, entry: UninstallEntry) -> bool:
        import winreg

        try:
            winreg.OpenKey(getattr(winreg, entry.root), entry.key_path, 0,
                           winreg.KEY_READ | winreg.KEY_WOW64_64KEY).Close()
            return True
        except OSError:
            return False
