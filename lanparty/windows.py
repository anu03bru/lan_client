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

from .config import Game, Runtime, WindowsSpec
from .download import (
    download, download_hint, expand_path, extract_all, extract_matching, file_name_from_url, remove_path,
)
from .runner import Runner
from .steps import Steps

UNINSTALL_KEYS = (
    ("HKEY_LOCAL_MACHINE", r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKEY_LOCAL_MACHINE", r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKEY_CURRENT_USER", r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
)
UNINSTALL_TIMEOUT_SECONDS = 300
# A silent installer that runs longer than this is most likely waiting on a dialog nobody can see
INSTALL_TIMEOUT_SECONDS = 900
# Written into a ZIP game's folder; holds the download URL of the installed version
VERSION_MARKER = ".lanparty-version"
# Where the Visual C++ 2015-2022 Redistributable (x64) records its version. The installer is 32 bit, so the key is
# usually in the 32-bit registry view (WOW6432Node); both views are checked.
VCREDIST_X64_KEY = r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
# Always the newest build, so it can't be pinned in games.toml, but it's the right link for a manual install
VCREDIST_X64_LATEST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
# Turned off in the console, see disable_quick_edit
ENABLE_QUICK_EDIT_MODE = 0x0040
ENABLE_EXTENDED_FLAGS = 0x0080
# Exit codes of the Visual C++ Redistributable installer that aren't errors
VCREDIST_RESTART_NEEDED = 3010
VCREDIST_NEWER_INSTALLED = 1638


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
        disable_quick_edit()

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
            # Before the game: without it the game installs fine but doesn't start
            for runtime in spec.requires:
                steps.run(
                    f"Install {runtime.name}",
                    f"Download and run it manually: {VCREDIST_X64_LATEST_URL}",
                    self._install_runtime, runtime, temp_dir,
                )
            download_path = temp_dir / file_name_from_url(spec.url)
            steps.run(
                f"Download {game.name}",
                download_hint(spec.url),
                download, spec.url, download_path, spec.sha256,
            )
            if spec.type == "nsis":
                # Some installers (0 A.D.) ask a question when the game is already installed, even with /S,
                # so the installed version is removed silently first. User data folders are kept.
                if self.registry.find(spec.uninstall_name):
                    steps.run(
                        f"Remove the installed version of {game.name}",
                        "Uninstall it via Settings -> Apps -> Installed apps, then run the install again.",
                        self._uninstall_nsis, spec.uninstall_name,
                    )
                steps.run(
                    f"Install {game.name}",
                    "The installer failed or is waiting on a dialog. Close it and download and run it "
                    f"manually: {spec.url}",
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
                    download_hint(asset.url),
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

    def _install_runtime(self, runtime: Runtime, temp_dir: Path) -> str | None:
        """Installs the runtime unless this version or a newer one is there. Never removed on uninstall."""
        wanted = version_tuple(runtime.version)
        installed = self._runtime_version(runtime)
        if installed is not None and installed >= wanted:
            return f"version {'.'.join(map(str, installed))} installed, nothing to do"
        installer_path = temp_dir / file_name_from_url(runtime.url)
        self.steps.info(f"Downloading {file_name_from_url(runtime.url)}")
        download(runtime.url, installer_path, runtime.sha256)
        result = self._run_silent_installer([str(installer_path), "/install", "/quiet", "/norestart"])
        if result.returncode == VCREDIST_NEWER_INSTALLED:
            return "a newer version is already installed"
        if result.returncode == VCREDIST_RESTART_NEEDED:
            self.steps.warn("Restart Windows before starting the game, so the update can finish.")
            self.steps.warnings.append(f"Install {runtime.name} (restart Windows)")
            return "installed, restart needed"
        if result.returncode != 0:
            raise RuntimeError(f"Installer exited with code {result.returncode}")
        return None

    def _runtime_version(self, runtime: Runtime) -> tuple[int, ...] | None:
        if runtime.type == "vcredist-x64":
            return self.registry.vcredist_x64_version()
        raise ValueError(f"Unknown runtime type {runtime.type!r}")

    def _run_installer(self, installer_path: Path) -> None:
        result = self._run_silent_installer([str(installer_path), "/S"])
        if result.returncode != 0:
            raise RuntimeError(f"Installer exited with code {result.returncode}")

    def _run_silent_installer(self, args: list[str]) -> subprocess.CompletedProcess:
        """Silent installers print nothing and show no window, so the elapsed time shows that it's still working."""
        self.steps.info("    This can take several minutes, the installer runs in the background.")
        try:
            return self.runner.run(args, check=False, timeout=INSTALL_TIMEOUT_SECONDS,
                                   on_wait=lambda seconds: self.steps.waiting("still installing", seconds))
        finally:
            self.steps.end_waiting()

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
            # Read before the uninstaller removes the "Apps & features" entry
            leftover_folders = self._nsis_install_folders(spec.uninstall_name)
            steps.attempt(
                f"Uninstall {game.name}",
                "Uninstall it via Settings -> Apps -> Installed apps.",
                self._uninstall_nsis, spec.uninstall_name,
            )
            # Some uninstallers leave files behind (AssaultCube keeps its .md files)
            for entry, folder in leftover_folders:
                steps.attempt(
                    f"Remove leftover files in {folder}",
                    f"Close the game and delete {folder} manually.",
                    self._remove_leftover_folder, entry, folder,
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

    def _nsis_install_folders(self, pattern: str) -> list[tuple[UninstallEntry, Path]]:
        """The uninstaller's folder of each matching entry, but only when the folder name matches the pattern too,
        so a strange uninstall string can never point this at e.g. C:\\Program Files."""
        folders = []
        for entry in self.registry.find(pattern):
            folder = Path(uninstaller_path(entry.uninstall_string)).parent
            if folder.is_absolute() and fnmatch.fnmatch(folder.name.lower(), pattern.lower()):
                folders.append((entry, folder))
        return folders

    def _remove_leftover_folder(self, entry: UninstallEntry, folder: Path) -> str | None:
        if self.registry.exists(entry):
            raise RuntimeError(f"{entry.display_name} is still installed, so {folder} was kept.")
        return remove_path(folder)

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


def version_tuple(version: str) -> tuple[int, ...]:
    """"14.44.35211" -> (14, 44, 35211, 0), padded to the four parts the registry has."""
    parts = [int(part) for part in version.split(".")]
    return tuple(parts + [0] * (4 - len(parts)))


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


def disable_quick_edit() -> None:
    """Turns off QuickEdit in the classic console (conhost) while lan.py runs. With QuickEdit, a click into the
    window starts a text selection, and Windows pauses lan.py at its next output until Enter or Esc is pressed,
    so the install looks frozen. The old mode comes back when lan.py exits."""
    if sys.platform != "win32":
        return
    import atexit
    import ctypes

    kernel32 = ctypes.windll.kernel32
    console_input = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
    mode = ctypes.c_uint32()
    if not kernel32.GetConsoleMode(console_input, ctypes.byref(mode)):
        return  # no console, e.g. input redirected
    new_mode = (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS
    if new_mode != mode.value and kernel32.SetConsoleMode(console_input, new_mode):
        atexit.register(kernel32.SetConsoleMode, console_input, mode.value)


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

    def vcredist_x64_version(self) -> tuple[int, ...] | None:
        """(major, minor, build, revision) of the installed Visual C++ Redistributable (x64), None if missing."""
        import winreg

        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, VCREDIST_X64_KEY, 0, winreg.KEY_READ | view) as key:
                    if winreg.QueryValueEx(key, "Installed")[0] != 1:
                        continue
                    return tuple(int(winreg.QueryValueEx(key, name)[0]) for name in ("Major", "Minor", "Bld", "Rbld"))
            except (OSError, ValueError):
                continue
        return None

    def exists(self, entry: UninstallEntry) -> bool:
        import winreg

        try:
            winreg.OpenKey(getattr(winreg, entry.root), entry.key_path, 0,
                           winreg.KEY_READ | winreg.KEY_WOW64_64KEY).Close()
            return True
        except OSError:
            return False
