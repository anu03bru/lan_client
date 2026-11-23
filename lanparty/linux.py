"""Linux handler: Flatpak (user install) and ufw."""

from __future__ import annotations

import os
import platform
import re
import tempfile
from pathlib import Path

from .config import Game, LinuxSpec, Runtime
from .download import (
    download, download_hint, expand_path, expand_text, extract_matching, file_name_from_url, remove_path,
)
from .runner import Runner
from .steps import Steps

FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
UFW_RULE_NUMBER = re.compile(r"^\[\s*(\d+)\]")
# ufw comments written by earlier install scripts, also removed on uninstall.
# Never add "AssaultCube server": those rules belong to the dedicated server (assaultcube-server/setup.sh).
OLD_UFW_COMMENTS = {"SuperTuxKart": ("SuperTuxKart server",)}
# reply_ports are only allowed from these, so the rules don't open anything to the internet
PRIVATE_NETWORKS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
# The proprietary NVIDIA driver's version. Flatpak games need a matching GL extension from Flathub; Flathub installs
# it with the game, but not when the game comes from a bundle, so lan.py does it then.
NVIDIA_VERSION_FILE = Path("/sys/module/nvidia/version")
NVIDIA_GL_BRANCH = "1.4"
NVIDIA_VERSION_PATTERN = re.compile(r"^\d+(\.\d+)+$")


class Linux:
    name = "Linux"

    def __init__(self, runner: Runner, steps: Steps, home: Path | None = None, machine: str | None = None,
                 nvidia_version_file: Path = NVIDIA_VERSION_FILE) -> None:
        self.runner = runner
        self.steps = steps
        self.home = home or Path.home()
        self.machine = machine or platform.machine()
        self.nvidia_version_file = nvidia_version_file
        self._nvidia_checked = False

    def check_ready(self) -> None:
        if os.geteuid() == 0:
            raise PermissionError(
                "Do not run this with sudo or as root. Run it as your normal user, "
                "it asks for your password itself when it changes firewall rules."
            )

    def needs_admin(self) -> bool:
        return False

    def supports(self, game: Game) -> bool:
        return game.linux is not None

    def is_installed(self, game: Game) -> bool:
        if game.linux is None or not self.runner.exists("flatpak"):
            return False
        return self._flatpak_info(game.linux.app_id) is not None

    # ---------- install ----------

    def install(self, game: Game) -> None:
        spec = game.linux
        assert spec is not None
        steps = self.steps
        steps.run("Check flatpak", "Install it with: sudo pacman -S flatpak", self._require, "flatpak")
        from_flathub = spec.type == "flatpak" and spec.bundle_url is None
        if from_flathub:
            # Downloads Flathub's repo file, so only when the game really comes from Flathub (not at the LAN party)
            steps.run(
                "Add Flathub remote",
                "Could not add Flathub. Check the internet connection.",
                self.runner.run,
                self._add_flathub_command(),
            )

        # Not /tmp: on many distributions (Arch, CachyOS, Fedora) it is a RAM disk, too small for 0 A.D.
        download_parent = self.home / ".cache"
        download_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="lanparty-", dir=download_parent) as temp_name:
            temp_dir = Path(temp_name)
            # Runtime bundles first: a game bundle whose runtime is missing would fetch it from Flathub
            for runtime in spec.requires:
                steps.run(
                    f"Install {runtime.name}",
                    f"{download_hint(runtime.url)} Without the share: flatpak install --user flathub {runtime.ref}",
                    self._install_runtime_bundle, runtime, temp_dir,
                )
            if not from_flathub:
                self._install_nvidia_gl()
            if spec.type == "flatpak" and spec.bundle_url:
                steps.run(
                    f"Install {game.name}",
                    f"{download_hint(spec.bundle_url)} Without the share: flatpak install --user flathub {spec.app_id}",
                    self._install_app_bundle, spec, temp_dir,
                )
            elif spec.type == "flatpak":
                steps.run(
                    f"Install {game.name}",
                    f"Try running: flatpak install --user flathub {spec.app_id}",
                    self.runner.run,
                    ["flatpak", "install", "--user", "-y", "--or-update", "flathub", spec.app_id],
                )
                if spec.commit:
                    self._pin_commit(game, spec)
            else:
                bundle_path = temp_dir / file_name_from_url(spec.url)
                steps.run(
                    f"Download {game.name}",
                    download_hint(spec.url),
                    download, spec.url, bundle_path, spec.sha256,
                )
                steps.run(
                    f"Install {game.name}",
                    f"Try running: flatpak install --user {bundle_path}",
                    self.runner.run,
                    self._bundle_install_command(spec, bundle_path),
                )
            steps.run(
                "Verify installation",
                "Check with: flatpak list --user",
                self._require_installed, spec.app_id,
            )

            for asset in game.assets:
                asset_path = temp_dir / file_name_from_url(asset.url)
                dest = self._path(asset.linux_dest)
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

        self._apply_overrides(spec)
        if game.version:
            self._check_version(game, spec)
        if game.ports:
            steps.attempt(
                f"Open firewall ports (ufw): {' '.join(game.ports)}",
                f"Run manually: sudo ufw allow <port> comment '{game.name}' for each of: {' '.join(game.ports)}",
                self._open_ports, game,
            )
        if game.reply_ports:
            example = reply_port_rule(game.reply_ports[0], "192.168.0.0/16", game.name)
            steps.attempt(
                f"Allow LAN server list replies (ufw): {' '.join(game.reply_ports)}",
                f"Run manually: {' '.join(example[:-1])} '{game.name}' "
                f"(also with 10.0.0.0/8 and 172.16.0.0/12 instead of 192.168.0.0/16)",
                self._allow_reply_ports, game,
            )

    def _install_runtime_bundle(self, runtime: Runtime, temp_dir: Path) -> str | None:
        # Any build of the runtime branch works, also one from Flathub or the system installation
        if self._ref_installed(runtime.ref):
            return "already installed, nothing to do"
        bundle_path = temp_dir / file_name_from_url(runtime.url)
        self.steps.info(f"Downloading {file_name_from_url(runtime.url)}")
        download(runtime.url, bundle_path, runtime.sha256)
        self.steps.info("Installing")
        self.runner.run(["flatpak", "install", "--user", "-y", str(bundle_path)])
        return None

    def _install_app_bundle(self, spec: LinuxSpec, temp_dir: Path) -> str | None:
        """Installs the game from its bundle on the LAN share. The bundle holds the pinned commit."""
        if spec.commit and self._installed_commit(spec.app_id) == spec.commit:
            return "the pinned build is already installed, nothing to do"
        bundle_path = temp_dir / file_name_from_url(spec.bundle_url)
        self.steps.info(f"Downloading {file_name_from_url(spec.bundle_url)}")
        download(spec.bundle_url, bundle_path, spec.bundle_sha256)
        self.steps.info("Installing")
        self.runner.run(self._bundle_install_command(spec, bundle_path))
        installed_commit = self._installed_commit(spec.app_id)
        if spec.commit and installed_commit != spec.commit:
            self.steps.warn(f"The bundle has build {installed_commit[:12]}, games.toml pins {spec.commit[:12]}. "
                            "Tell the organizer.")
            self.steps.warnings.append("Check version")
        return None

    def _bundle_install_command(self, spec: LinuxSpec, bundle_path: Path) -> list[str]:
        # --reinstall also replaces a build from Flathub.
        # A bundle names Flathub as the source of its runtime, and flatpak loads that file even when the runtime is
        # installed, which fails without internet. With `requires`, the runtimes came from bundles just before, so
        # dependencies are skipped. Without (games.toml), Flathub still provides the runtime.
        no_deps = ["--no-deps"] if spec.requires else []
        return ["flatpak", "install", "--user", "-y", "--reinstall", *no_deps, str(bundle_path)]

    def _install_nvidia_gl(self) -> None:
        """With the proprietary NVIDIA driver, games need the matching Flatpak GL extension, or they fall back to
        software rendering. It must match the driver exactly, so it can't be on the share: it comes from Flathub."""
        if self._nvidia_checked:
            return
        self._nvidia_checked = True
        try:
            version = self.nvidia_version_file.read_text().strip()
        except OSError:
            return  # no proprietary NVIDIA driver loaded
        if not NVIDIA_VERSION_PATTERN.match(version):
            self.steps.warn(f"Unexpected NVIDIA driver version {version!r}, skipped the Flatpak graphics driver.")
            return
        ref = f"org.freedesktop.Platform.GL.nvidia-{version.replace('.', '-')}//{NVIDIA_GL_BRANCH}"
        self.steps.attempt(
            f"Install the NVIDIA graphics driver for Flatpak ({version})",
            f"Needs the internet (about 300 MB). Run: flatpak install --user flathub {ref} "
            "Without it, games run with slow software graphics.",
            self._install_nvidia_ref, ref,
        )

    def _install_nvidia_ref(self, ref: str) -> str | None:
        if self._ref_installed(ref):
            return "already installed, nothing to do"
        self.runner.run(self._add_flathub_command())
        self.runner.run(["flatpak", "install", "--user", "-y", "flathub", ref])
        return None

    def _pin_commit(self, game: Game, spec: LinuxSpec) -> None:
        # Flathub always installs its newest build. Going to the pinned commit keeps every Linux PC on the same build
        # as the other players, even when Flathub updates the game shortly before the party.
        if self.machine != "x86_64":
            self.steps.warn(f"The pinned build is for x86_64 PCs, this is {self.machine}. Kept the newest Flathub build.")
            return
        self.steps.run(
            f"Switch {game.name} to the pinned build",
            f"Try running: flatpak update --user --commit={spec.commit} {spec.app_id}",
            self.runner.run,
            ["flatpak", "update", "--user", "-y", f"--commit={spec.commit}", spec.app_id],
        )

    def _apply_overrides(self, spec: LinuxSpec) -> None:
        for name, value in spec.override_env.items():
            self.steps.run(
                f"Set {name} for {spec.app_id}",
                f"Check with: flatpak override --user --show {spec.app_id}",
                self.runner.run,
                ["flatpak", "override", "--user", f"--env={name}={self._text(value)}", spec.app_id],
            )
        for filesystem in spec.override_filesystem:
            self.steps.run(
                f"Give {spec.app_id} access to {self._text(filesystem)}",
                f"Check with: flatpak override --user --show {spec.app_id}",
                self.runner.run,
                ["flatpak", "override", "--user", f"--filesystem={self._text(filesystem)}", spec.app_id],
            )

    def _check_version(self, game: Game, spec: LinuxSpec) -> None:
        self.steps.info("==> Check version")
        self.steps.version_result(self._installed_version(spec.app_id), game.version)

    def _open_ports(self, game: Game) -> str | None:
        reason = self._ufw_unavailable()
        if reason:
            return reason
        for port in game.ports:
            self.runner.run(["sudo", "ufw", "allow", port, "comment", game.name])
        return None

    def _allow_reply_ports(self, game: Game) -> str | None:
        reason = self._ufw_unavailable()
        if reason:
            return reason
        for port in game.reply_ports:
            for network in PRIVATE_NETWORKS:
                self.runner.run(reply_port_rule(port, network, game.name))
        return None

    # ---------- uninstall ----------

    def uninstall(self, game: Game) -> None:
        spec = game.linux
        assert spec is not None
        steps = self.steps
        if spec.override_env or spec.override_filesystem:
            steps.attempt(
                "Reset Flatpak permissions",
                f"Try running: flatpak override --user --reset {spec.app_id}",
                self._reset_overrides, spec.app_id,
            )
        steps.attempt(
            f"Remove {game.name} and its user data",
            f"Try running: flatpak uninstall --user --delete-data {spec.app_id}",
            self._remove_app, spec.app_id,
        )
        # Installing a .flatpak file adds a hidden remote like "odamex-origin". flatpak deletes it by itself when
        # the last app or runtime from it is uninstalled, so there is nothing to clean up here.
        for folder in self._unique_paths([*spec.data, *(asset.linux_dest for asset in game.assets)]):
            steps.attempt(f"Remove {folder}", f"Delete it manually: rm -rf {folder}", remove_path, folder)
        if game.ports or game.reply_ports:
            steps.attempt(
                "Close firewall ports (ufw)",
                "List rules with: sudo ufw status numbered, then delete with: sudo ufw delete <number>",
                self._close_ports, game.name,
            )

    def cleanup_after_uninstall_all(self) -> None:
        if not self.runner.exists("flatpak"):
            return
        self.steps.attempt(
            "Remove Flatpak runtimes no app uses anymore",
            "Try running: flatpak uninstall --user --unused",
            self.runner.run, ["flatpak", "uninstall", "--user", "--unused", "-y"],
        )

    def _reset_overrides(self, app_id: str) -> str | None:
        if not self.runner.exists("flatpak"):
            return "flatpak not installed, nothing to do"
        self.runner.run(["flatpak", "override", "--user", "--reset", app_id])
        return None

    def _remove_app(self, app_id: str) -> str | None:
        note = None
        if not self.runner.exists("flatpak"):
            note = "flatpak not installed"
        elif self._flatpak_info(app_id) is None:
            note = "not installed"
        else:
            # --delete-data also removes ~/.var/app/<app_id>
            self.runner.run(["flatpak", "uninstall", "--user", "-y", "--delete-data", app_id])
        remove_path(self.home / ".var" / "app" / app_id)
        return note

    def _close_ports(self, game_name: str) -> str:
        """Deletes every ufw rule whose comment is the game name (or an old comment of it). Other rules stay."""
        reason = self._ufw_unavailable()
        if reason:
            return reason
        deleted_rules = 0
        # One rule at a time, because rule numbers shift after each delete
        while deleted_rules < 50:
            result = self.runner.run(["sudo", "ufw", "status", "numbered"], capture=True)
            rule_number = find_ufw_rule(result.stdout, (game_name, *OLD_UFW_COMMENTS.get(game_name, ())))
            if rule_number is None:
                break
            self.runner.run(["sudo", "ufw", "--force", "delete", str(rule_number)], capture=True)
            deleted_rules += 1
        return f"deleted {deleted_rules} rule(s)"

    # ---------- helpers ----------

    def _ufw_unavailable(self) -> str | None:
        if not self.runner.exists("ufw"):
            return "ufw not installed, nothing to do"
        result = self.runner.run(["sudo", "ufw", "status"], capture=True)
        if "Status: active" not in result.stdout:
            return "ufw not active, nothing to do"
        return None

    def _require(self, command: str) -> None:
        if not self.runner.exists(command):
            raise FileNotFoundError(f"{command} not found")

    def _add_flathub_command(self) -> list[str]:
        return ["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", FLATHUB_URL]

    def _ref_installed(self, ref: str) -> bool:
        """In the user or the system installation; ref like "org.freedesktop.Platform//26.08"."""
        return self.runner.run(["flatpak", "info", ref], capture=True, check=False).returncode == 0

    def _installed_commit(self, app_id: str) -> str:
        result = self.runner.run(["flatpak", "info", "--user", "--show-commit", app_id], capture=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else ""

    def _require_installed(self, app_id: str) -> None:
        if self._flatpak_info(app_id) is None:
            raise LookupError(f"{app_id} is not installed")

    def _flatpak_info(self, app_id: str) -> str | None:
        result = self.runner.run(["flatpak", "info", "--user", app_id], capture=True, check=False)
        return result.stdout if result.returncode == 0 else None

    def _installed_version(self, app_id: str) -> str:
        for line in (self._flatpak_info(app_id) or "").splitlines():
            if line.strip().startswith("Version:"):
                return line.split(":", 1)[1].strip()
        return ""

    def _text(self, text: str) -> str:
        return expand_text(text, {}, self.home)

    def _path(self, text: str) -> Path:
        return expand_path(text, {}, self.home)

    def _unique_paths(self, texts: list[str]) -> list[Path]:
        return list(dict.fromkeys(self._path(text) for text in texts))


def reply_port_rule(port: str, network: str, comment: str) -> list[str]:
    """ufw command allowing packets *from* `port` (e.g. "2757/udp") of `network` to any local port."""
    number, protocol = port.split("/")
    return ["sudo", "ufw", "allow", "proto", protocol, "from", network, "port", number, "to", "any",
            "comment", comment]


def find_ufw_rule(status_output: str, comments: tuple[str, ...]) -> int | None:
    """Returns the number of the first rule in `ufw status numbered` whose comment is exactly one of `comments`.
    Exact, so uninstalling "AssaultCube" keeps the "AssaultCube server" rules."""
    for line in status_output.splitlines():
        match = UFW_RULE_NUMBER.match(line.strip())
        if match and line.partition("# ")[2].strip() in comments:
            return int(match.group(1))
    return None

