"""macOS handler: apps from a disk image (.dmg) or ZIP, copied into ~/Applications.

~/Applications needs no admin rights, and Launchpad and Spotlight still find the games there.
macOS has no firewall step: its firewall is off by default, and when it is on it asks the player itself.
"""

from __future__ import annotations

import os
import platform
import plistlib
import tempfile
from pathlib import Path

from .config import Game, MacosSpec
from .download import download, expand_path, extract_matching, file_name_from_url, remove_path
from .runner import Runner
from .steps import Steps

SYSTEM_APPLICATIONS = Path("/Applications")
CERTIFICATE_HINT = (
    "If the details mention CERTIFICATE_VERIFY_FAILED: open Applications -> Python 3.x and run "
    "'Install Certificates.command', then try again."
)


class Macos:
    name = "macOS"

    def __init__(self, runner: Runner, steps: Steps, home: Path | None = None, machine: str | None = None,
                 system_applications: Path = SYSTEM_APPLICATIONS) -> None:
        self.runner = runner
        self.steps = steps
        self.home = home or Path.home()
        self.machine = machine or platform.machine()
        self.applications = self.home / "Applications"
        # Only searched and cleaned up: the old AssaultCube script installed there
        self.system_applications = system_applications

    def check_ready(self) -> None:
        if os.geteuid() == 0:
            raise PermissionError("Do not run this with sudo or as root. Run it as your normal user.")

    def needs_admin(self) -> bool:
        return False

    def supports(self, game: Game) -> bool:
        return game.macos is not None

    def is_installed(self, game: Game) -> bool:
        if game.macos is None:
            return False
        return any((folder / game.macos.apps[0]).exists() for folder in (self.applications, self.system_applications))

    # ---------- install ----------

    def install(self, game: Game) -> None:
        spec = game.macos
        assert spec is not None
        steps = self.steps
        url, sha256 = self._build(spec)
        with tempfile.TemporaryDirectory(prefix="lanparty-") as temp_name:
            temp_dir = Path(temp_name)
            download_path = temp_dir / file_name_from_url(url)
            steps.run(
                f"Download {game.name}",
                f"Check the internet connection and the URL: {url}. {CERTIFICATE_HINT}",
                download, url, download_path, sha256,
            )

            contents = temp_dir / "contents"
            if spec.type == "dmg":
                steps.run(
                    "Open disk image",
                    "The download may be corrupt. Run the install again.",
                    self._attach, download_path, contents,
                )
                try:
                    self._copy_apps(spec, contents)
                finally:
                    steps.attempt(
                        "Close disk image",
                        "Eject it in Finder (sidebar, under Locations).",
                        self._detach, contents,
                    )
            else:
                steps.run(
                    f"Extract {game.name}",
                    "The ZIP may be corrupt. Run the install again.",
                    self.runner.run, ["ditto", "-x", "-k", str(download_path), str(contents)],
                )
                self._copy_apps(spec, contents)

            for asset in game.assets:
                asset_path = temp_dir / file_name_from_url(asset.url)
                dest = self._path(asset.macos_dest)
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

        if game.version:
            steps.info("==> Check version")
            steps.version_result(self._installed_version(spec.apps[0]), game.version)
        if game.ports:
            steps.info("Hosting: if macOS asks whether the game may accept incoming network connections, click Allow.")

    def _build(self, spec: MacosSpec) -> tuple[str, str]:
        if self.machine == "arm64" and spec.arm64_url:
            return spec.arm64_url, spec.arm64_sha256
        return spec.url, spec.sha256

    def _attach(self, image: Path, mount_dir: Path) -> None:
        mount_dir.mkdir()
        # Not captured: a disk image with a license agreement asks on the terminal before it opens
        self.runner.run(["hdiutil", "attach", str(image), "-nobrowse", "-readonly", "-noverify", "-noautoopen",
                         "-mountpoint", str(mount_dir)])

    def _detach(self, mount_dir: Path) -> None:
        result = self.runner.run(["hdiutil", "detach", str(mount_dir), "-quiet"], check=False)
        if result.returncode != 0:
            self.runner.run(["hdiutil", "detach", str(mount_dir), "-quiet", "-force"])

    def _copy_apps(self, spec: MacosSpec, contents: Path) -> None:
        for app in spec.apps:
            self.steps.run(
                f"Copy {app} to {self.applications}",
                f"Open the download manually and drag {app} into {self.applications}.",
                self._copy_app, contents, app,
            )
            # Python downloads don't get the quarantine flag, but an older copy may have it
            self.runner.run(["xattr", "-dr", "com.apple.quarantine", str(self.applications / app)],
                            capture=True, check=False)

    def _copy_app(self, contents: Path, app: str) -> None:
        source = find_app(contents, app)
        target = self.applications / app
        self.applications.mkdir(exist_ok=True)
        remove_path(target)
        # ditto keeps symlinks, permissions and the code signature of the app bundle
        self.runner.run(["ditto", str(source), str(target)])

    def _installed_version(self, app: str) -> str:
        try:
            with open(self.applications / app / "Contents" / "Info.plist", "rb") as plist_file:
                info = plistlib.load(plist_file)
        except (OSError, plistlib.InvalidFileException):
            return ""
        return str(info.get("CFBundleShortVersionString", ""))

    # ---------- uninstall ----------

    def uninstall(self, game: Game) -> None:
        spec = game.macos
        assert spec is not None
        for app in spec.apps:
            self.steps.attempt(
                f"Remove {app}",
                f"Drag {app} from Applications to the Trash.",
                self._remove_app, app,
            )
        folders = [*spec.data, *(asset.macos_dest for asset in game.assets)]
        for folder in dict.fromkeys(self._path(text) for text in folders):
            self.steps.attempt(f"Remove {folder}", f"Delete it manually: rm -rf \"{folder}\"", remove_path, folder)

    def cleanup_after_uninstall_all(self) -> None:
        pass

    def _remove_app(self, app: str) -> str | None:
        removed = False
        for folder in (self.applications, self.system_applications):
            if (folder / app).exists() or (folder / app).is_symlink():
                remove_path(folder / app)
                removed = True
        return None if removed else "not installed, nothing to do"

    # ---------- helpers ----------

    def _path(self, text: str) -> Path:
        return expand_path(text, {}, self.home)


def find_app(contents: Path, app: str) -> Path:
    """Finds the app at the top of the download or one folder deeper."""
    for candidate in (contents / app, *sorted(contents.glob(f"*/{app}"))):
        if candidate.is_dir():
            return candidate
    found = sorted({path.name for pattern in ("*.app", "*/*.app") for path in contents.glob(pattern)})
    raise FileNotFoundError(
        f"{app} not found in the download. It contains: {', '.join(found) or 'no apps'}. "
        "Update apps in games.toml."
    )
