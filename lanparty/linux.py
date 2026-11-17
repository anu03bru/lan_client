"""Linux handler: Flatpak (user install) and ufw."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .config import Game, LinuxSpec
from .download import download, expand_path, expand_text, extract_matching, file_name_from_url, remove_path
from .runner import Runner
from .steps import Steps

FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
UFW_RULE_NUMBER = re.compile(r"^\[\s*(\d+)\]")


class Linux:
    name = "Linux"

    def __init__(self, runner: Runner, steps: Steps, home: Path | None = None) -> None:
        self.runner = runner
        self.steps = steps
        self.home = home or Path.home()

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
        steps.run(
            "Add Flathub remote",
            "Could not add Flathub. Check the internet connection.",
            self.runner.run,
            ["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", FLATHUB_URL],
        )

        with tempfile.TemporaryDirectory(prefix="lanparty-") as temp_name:
            temp_dir = Path(temp_name)
            if spec.type == "flatpak":
                steps.run(
                    f"Install {game.name}",
                    f"Try running: flatpak install --user flathub {spec.app_id}",
                    self.runner.run,
                    ["flatpak", "install", "--user", "-y", "--or-update", "flathub", spec.app_id],
                )
            else:
                bundle_path = temp_dir / file_name_from_url(spec.url)
                steps.run(
                    f"Download {game.name}",
                    f"Check the internet connection and the URL: {spec.url}",
                    download, spec.url, bundle_path, spec.sha256,
                )
                steps.run(
                    f"Install {game.name}",
                    f"Try running: flatpak install --user {bundle_path}",
                    self.runner.run,
                    ["flatpak", "install", "--user", "-y", "--reinstall", str(bundle_path)],
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
                    f"Check the internet connection and the URL: {asset.url}",
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
        if spec.type == "flatpak-bundle":
            steps.attempt(
                "Remove Flatpak remote of the bundle",
                "List remotes with: flatpak remote-list --user, then: flatpak remote-delete --user <name>",
                self._remove_bundle_remotes, spec.app_id,
            )
        for folder in self._unique_paths([*spec.data, *(asset.linux_dest for asset in game.assets)]):
            steps.attempt(f"Remove {folder}", f"Delete it manually: rm -rf {folder}", remove_path, folder)
        if game.ports:
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

    def _remove_bundle_remotes(self, app_id: str) -> str | None:
        if not self.runner.exists("flatpak"):
            return "flatpak not installed, nothing to do"
        # Installing a .flatpak file can add a remote named after the app, e.g. "odamex-origin"
        short_name = app_id.rsplit(".", 1)[-1].lower()
        result = self.runner.run(["flatpak", "remote-list", "--user", "--columns=name"], capture=True)
        remotes = [line.strip() for line in result.stdout.splitlines() if short_name in line.strip().lower()]
        for remote in remotes:
            self.runner.run(["flatpak", "remote-delete", "--user", "--force", remote])
        return f"deleted {', '.join(remotes)}" if remotes else "nothing to do"

    def _close_ports(self, comment: str) -> str:
        """Deletes every ufw rule whose comment contains the game name. Other rules are never touched."""
        reason = self._ufw_unavailable()
        if reason:
            return reason
        deleted_rules = 0
        # One rule at a time, because rule numbers shift after each delete
        while deleted_rules < 50:
            result = self.runner.run(["sudo", "ufw", "status", "numbered"], capture=True)
            rule_number = find_ufw_rule(result.stdout, comment)
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


def find_ufw_rule(status_output: str, comment: str) -> int | None:
    """Returns the number of the first rule in `ufw status numbered` whose comment contains the text."""
    for line in status_output.splitlines():
        match = UFW_RULE_NUMBER.match(line.strip())
        if match and f"# {comment}" in line:
            return int(match.group(1))
    return None

