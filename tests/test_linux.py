import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lanparty.linux import Linux, find_ufw_rule, reply_port_rule
from lanparty.steps import StepFailed
from tests.fakes import FakeRunner, FakeUfw, game_from_toml, quiet_steps

COMMIT = "a6969d346d0915bc1f4b2ba2fc4e69475d5bbb8ece84cca59480f214e15bc692"
STK_PINNED = game_from_toml(f"""
[supertuxkart]
name = "SuperTuxKart"
version = "1.5"
[supertuxkart.linux]
type = "flatpak"
app_id = "net.supertuxkart.SuperTuxKart"
commit = "{COMMIT}"
""")

STK = game_from_toml("""
[supertuxkart]
name = "SuperTuxKart"
version = "1.5"
ports = ["2759/udp", "2757/udp"]
reply_ports = ["2757/udp"]
[supertuxkart.linux]
type = "flatpak"
app_id = "net.supertuxkart.SuperTuxKart"
""")

SHA = "b5612f397e40847d01e6655adccc309dea9305d9ddc7563ac6296288f1ea94bf"
RUNTIMES = f"""
[runtimes.platform_26_08]
type = "flatpak-runtime"
name = "Flatpak runtime 26.08"
ref = "org.freedesktop.Platform//26.08"
url = "/share/runtimes/org.freedesktop.Platform-26.08.flatpak"
sha256 = "{SHA}"
[runtimes.gl_26_08]
type = "flatpak-runtime"
name = "Flatpak graphics drivers 26.08"
ref = "org.freedesktop.Platform.GL.default//26.08"
url = "/share/runtimes/org.freedesktop.Platform.GL.default-26.08.flatpak"
sha256 = "{SHA}"
"""
STK_BUNDLE = game_from_toml(RUNTIMES + f"""
[supertuxkart]
name = "SuperTuxKart"
version = "1.5"
[supertuxkart.linux]
type = "flatpak"
app_id = "net.supertuxkart.SuperTuxKart"
commit = "{COMMIT}"
bundle = {{ url = "/share/supertuxkart/net.supertuxkart.SuperTuxKart.flatpak", sha256 = "{SHA}" }}
requires = ["platform_26_08", "gl_26_08"]
""")

DOOM = game_from_toml("""
[doom]
name = "Doom"
[doom.linux]
type = "flatpak-bundle"
app_id = "net.odamex.Odamex"
url = "https://example.invalid/odamex.flatpak"
sha256 = "b5612f397e40847d01e6655adccc309dea9305d9ddc7563ac6296288f1ea94bf"
data = ["~/OdamexLAN"]
[doom.linux.overrides]
env = { DOOMWADDIR = "~/OdamexLAN/wads" }
filesystem = ["~/OdamexLAN/wads:ro"]
""")

DOOM_LAN = game_from_toml(f"""
[runtimes.platform_25_08]
type = "flatpak-runtime"
name = "Flatpak runtime 25.08"
ref = "org.freedesktop.Platform//25.08"
url = "/share/runtimes/org.freedesktop.Platform-25.08.flatpak"
sha256 = "{SHA}"
[doom_lan]
name = "Doom"
[doom_lan.linux]
type = "flatpak-bundle"
app_id = "net.odamex.Odamex"
url = "/share/doom/odamex.flatpak"
sha256 = "{SHA}"
requires = ["platform_25_08"]
""")


class FlatpakState:
    """Installed refs and their commits. A bundle install (a path ending in .flatpak) installs `bundles[path]`."""

    def __init__(self, installed: set[str], version: str = "1.5",
                 bundles: dict[str, tuple[str, str]] | None = None) -> None:
        self.installed = {ref: "0" * 64 for ref in installed}
        self.version = version
        self.bundles = bundles or {}

    def respond(self, args):
        if args[:2] == ["flatpak", "info"]:
            if args[-1] not in self.installed:
                return 1, ""
            if "--show-commit" in args:
                return 0, self.installed[args[-1]] + "\n"
            return 0, f"SuperTuxKart\n\n          ID: {args[-1]}\n     Version: {self.version}\n"
        if args[:2] == ["flatpak", "install"]:
            if args[-1].endswith(".flatpak"):
                ref, commit = self.bundles[Path(args[-1]).name]
                self.installed[ref] = commit
            else:
                self.installed[args[-1]] = "0" * 64
        if args[:2] == ["flatpak", "update"] and "--commit=" in " ".join(args):
            self.installed[args[-1]] = [arg for arg in args if arg.startswith("--commit=")][0].split("=", 1)[1]
        if args[:2] == ["flatpak", "uninstall"] and "--unused" not in args:
            self.installed.pop(args[-1], None)
        return 0, ""


def make_linux(flatpak: FlatpakState, ufw: FakeUfw, home: Path, machine: str = "x86_64", nvidia: str | None = None):
    def respond(args):
        return ufw.respond(args) or flatpak.respond(args)

    runner = FakeRunner(respond=respond)
    steps, output = quiet_steps()
    # Never the real /sys file, so a PC with an NVIDIA card runs the same tests
    nvidia_file = home / "nvidia-version"
    if nvidia is not None:
        nvidia_file.write_text(nvidia + "\n")
    linux = Linux(runner, steps, home=home, machine=machine, nvidia_version_file=nvidia_file)
    return linux, runner, output


class LinuxInstallTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_install_flatpak_and_open_ports(self):
        ufw = FakeUfw([("22/tcp", "")])
        linux, runner, output = make_linux(FlatpakState(set()), ufw, self.home)
        linux.install(STK)
        self.assertIn("flatpak install --user -y --or-update flathub net.supertuxkart.SuperTuxKart", runner.joined())
        self.assertEqual(ufw.rules, [
            ("22/tcp", ""),
            ("2759/udp", "SuperTuxKart"),
            ("2757/udp", "SuperTuxKart"),
            ("proto udp from 10.0.0.0/8 port 2757 to any", "SuperTuxKart"),
            ("proto udp from 172.16.0.0/12 port 2757 to any", "SuperTuxKart"),
            ("proto udp from 192.168.0.0/16 port 2757 to any", "SuperTuxKart"),
        ])
        self.assertIn("OK (version 1.5)", output.getvalue())

    def test_reply_port_rule_allows_source_port_from_network(self):
        self.assertEqual(
            " ".join(reply_port_rule("2757/udp", "192.168.0.0/16", "SuperTuxKart")),
            "sudo ufw allow proto udp from 192.168.0.0/16 port 2757 to any comment SuperTuxKart",
        )

    def test_pinned_commit_is_installed_after_flathub_install(self):
        linux, runner, _output = make_linux(FlatpakState(set()), FakeUfw([]), self.home)
        linux.install(STK_PINNED)
        calls = runner.joined()
        install = calls.index("flatpak install --user -y --or-update flathub net.supertuxkart.SuperTuxKart")
        pin = calls.index(f"flatpak update --user -y --commit={COMMIT} net.supertuxkart.SuperTuxKart")
        self.assertLess(install, pin)

    def test_pinned_commit_is_skipped_on_other_architectures(self):
        linux, runner, output = make_linux(FlatpakState(set()), FakeUfw([]), self.home, machine="aarch64")
        linux.install(STK_PINNED)
        self.assertFalse(any("--commit=" in call for call in runner.joined()))
        self.assertIn("The pinned build is for x86_64 PCs, this is aarch64.", output.getvalue())

    def test_version_mismatch_only_warns(self):
        linux, _runner, output = make_linux(FlatpakState(set(), version="1.4"), FakeUfw([]), self.home)
        linux.install(STK)
        self.assertIn('WARNING: Installed version is "1.4", expected "1.5".', output.getvalue())
        self.assertEqual(linux.steps.warnings, ["Check version"])

    def test_inactive_ufw_is_skipped(self):
        ufw = FakeUfw([], active=False)
        linux, runner, output = make_linux(FlatpakState(set()), ufw, self.home)
        linux.install(STK)
        self.assertEqual(ufw.rules, [])
        self.assertIn("ufw not active, nothing to do", output.getvalue())

    def test_failed_install_stops(self):
        runner = FakeRunner(respond=lambda args: (1, "") if args[:2] == ["flatpak", "install"] else (0, ""))
        steps, _output = quiet_steps()
        with self.assertRaises(StepFailed):
            Linux(runner, steps, home=self.home, nvidia_version_file=self.home / "none").install(STK)
        self.assertFalse(any(call[:3] == ["sudo", "ufw", "allow"] for call in runner.calls))


class OdamexBundleTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    @mock.patch("lanparty.linux.download")
    def test_runtimes_from_bundles_only_with_requires(self, _download):
        for game, expected in ((DOOM, False), (DOOM_LAN, True)):
            flatpak = FlatpakState(set(), bundles={
                "odamex.flatpak": ("net.odamex.Odamex", "4" * 64),
                "org.freedesktop.Platform-25.08.flatpak": ("org.freedesktop.Platform//25.08", "5" * 64),
            })
            linux, runner, _output = make_linux(flatpak, FakeUfw([]), self.home)
            linux.install(game)
            install = [call for call in runner.joined() if call.endswith("odamex.flatpak")][0]
            self.assertEqual("--no-deps" in install, expected, game.id)


class LinuxUninstallTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_uninstall_removes_app_data_and_only_own_rules(self):
        (self.home / ".var/app/net.supertuxkart.SuperTuxKart").mkdir(parents=True)
        ufw = FakeUfw([
            ("22/tcp", ""),
            ("2759/udp", "SuperTuxKart server"),  # written by the first version of the install script
            ("20595/udp", ""),  # added by hand, no comment
            ("2757/udp", "SuperTuxKart"),
            ("proto udp from 192.168.0.0/16 port 2757 to any", "SuperTuxKart"),
        ])
        flatpak = FlatpakState({"net.supertuxkart.SuperTuxKart"})
        linux, runner, output = make_linux(flatpak, ufw, self.home)
        linux.uninstall(STK)
        self.assertEqual(ufw.rules, [("22/tcp", ""), ("20595/udp", "")])
        self.assertEqual(flatpak.installed, {})
        self.assertIn("flatpak uninstall --user -y --delete-data net.supertuxkart.SuperTuxKart", runner.joined())
        self.assertFalse((self.home / ".var/app/net.supertuxkart.SuperTuxKart").exists())
        self.assertEqual(linux.steps.warnings, [])

    def test_uninstall_twice_has_nothing_to_do(self):
        linux, _runner, _output = make_linux(FlatpakState(set()), FakeUfw([]), self.home)
        linux.uninstall(STK)
        linux.uninstall(STK)
        self.assertEqual(linux.steps.warnings, [])

    def test_bundle_uninstall_resets_overrides_and_removes_folder(self):
        (self.home / "OdamexLAN/wads").mkdir(parents=True)
        flatpak = FlatpakState({"net.odamex.Odamex"})
        linux, runner, _output = make_linux(flatpak, FakeUfw([]), self.home)
        linux.uninstall(DOOM)
        calls = runner.joined()
        self.assertIn("flatpak override --user --reset net.odamex.Odamex", calls)
        # flatpak removes the bundle's "odamex-origin" remote itself, lan.py never deletes remotes
        self.assertFalse(any("remote-delete" in call for call in calls))
        self.assertFalse((self.home / "OdamexLAN").exists())

    def test_overrides_use_expanded_home(self):
        linux, runner, _output = make_linux(FlatpakState({"net.odamex.Odamex"}), FakeUfw([]), self.home)
        linux._apply_overrides(DOOM.linux)
        self.assertIn(f"flatpak override --user --env=DOOMWADDIR={self.home}/OdamexLAN/wads net.odamex.Odamex",
                      runner.joined())


class UfwParsingTest(unittest.TestCase):
    STATUS = """Status: active

     To                         Action      From
     --                         ------      ----
[ 1] 22/tcp                     ALLOW IN    Anywhere
[ 2] 20595/udp                  ALLOW IN    Anywhere                   # 0 A.D.
[ 4] 28763/udp                  ALLOW IN    Anywhere                   # AssaultCube server
[10] 2759/udp (v6)              ALLOW IN    Anywhere (v6)              # SuperTuxKart
[11] Anywhere/udp               ALLOW IN    192.168.0.0/16 2757/udp    # Blobby Volley 2
"""

    def test_finds_rule_by_comment(self):
        self.assertEqual(find_ufw_rule(self.STATUS, ("0 A.D.",)), 2)
        self.assertEqual(find_ufw_rule(self.STATUS, ("SuperTuxKart",)), 10)
        self.assertEqual(find_ufw_rule(self.STATUS, ("Blobby Volley 2",)), 11)
        self.assertIsNone(find_ufw_rule(self.STATUS, ("Odamex",)))

    def test_comment_must_match_exactly(self):
        self.assertIsNone(find_ufw_rule(self.STATUS, ("AssaultCube",)))
        self.assertIsNone(find_ufw_rule(self.STATUS, ("0 A",)))


@mock.patch("lanparty.linux.download")
class LinuxBundleTest(unittest.TestCase):
    """games-lan.toml: games and their runtimes come from bundles on the LAN share, not from Flathub."""

    BUNDLES = {
        "org.freedesktop.Platform-26.08.flatpak": ("org.freedesktop.Platform//26.08", "1" * 64),
        "org.freedesktop.Platform.GL.default-26.08.flatpak": ("org.freedesktop.Platform.GL.default//26.08", "2" * 64),
        "net.supertuxkart.SuperTuxKart.flatpak": ("net.supertuxkart.SuperTuxKart", COMMIT),
    }

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def install(self, installed=(), nvidia=None, bundles=None):
        flatpak = FlatpakState(set(), bundles=bundles or self.BUNDLES)
        for ref, commit in dict(installed).items():
            flatpak.installed[ref] = commit
        linux, runner, output = make_linux(flatpak, FakeUfw([]), self.home, nvidia=nvidia)
        linux.install(STK_BUNDLE)
        return linux, runner, output.getvalue(), flatpak

    def test_runtimes_then_game_from_the_share_without_flathub(self, download):
        linux, runner, _output, flatpak = self.install()
        installs = [call for call in runner.joined() if call.startswith("flatpak install")]
        self.assertEqual([Path(call.split()[-1]).name for call in installs], list(self.BUNDLES))
        self.assertIn("--reinstall", installs[-1])
        # The runtimes came from bundles, so flatpak must not go to Flathub for dependencies (fails offline)
        self.assertIn("--no-deps", installs[-1])
        self.assertFalse(any("flathub" in call for call in runner.joined()))
        self.assertEqual([call.args[0] for call in download.call_args_list], [
            "/share/runtimes/org.freedesktop.Platform-26.08.flatpak",
            "/share/runtimes/org.freedesktop.Platform.GL.default-26.08.flatpak",
            "/share/supertuxkart/net.supertuxkart.SuperTuxKart.flatpak",
        ])
        self.assertEqual(flatpak.installed["net.supertuxkart.SuperTuxKart"], COMMIT)
        self.assertEqual(linux.steps.warnings, [])

    def test_downloads_go_to_the_cache_folder_not_tmp(self, download):
        self.install()
        target = Path(download.call_args_list[0].args[1])
        self.assertEqual(target.parent.parent, self.home / ".cache")
        self.assertFalse(target.parent.exists())  # removed after the install

    def test_installed_runtime_and_pinned_build_are_kept(self, download):
        _linux, runner, output, _flatpak = self.install(installed={
            "org.freedesktop.Platform//26.08": "9" * 64,  # from Flathub, other build: fine
            "org.freedesktop.Platform.GL.default//26.08": "9" * 64,
            "net.supertuxkart.SuperTuxKart": COMMIT,
        })
        self.assertFalse(any(call.startswith("flatpak install") for call in runner.joined()))
        download.assert_not_called()
        self.assertEqual(output.count("OK (already installed, nothing to do)"), 2)
        self.assertIn("OK (the pinned build is already installed, nothing to do)", output)

    def test_other_build_of_the_game_is_replaced(self, _download):
        _linux, runner, _output, flatpak = self.install(installed={"net.supertuxkart.SuperTuxKart": "9" * 64})
        self.assertTrue(any(call.endswith("net.supertuxkart.SuperTuxKart.flatpak") for call in runner.joined()))
        self.assertEqual(flatpak.installed["net.supertuxkart.SuperTuxKart"], COMMIT)

    def test_bundle_with_wrong_build_warns(self, _download):
        bundles = dict(self.BUNDLES, **{"net.supertuxkart.SuperTuxKart.flatpak": ("net.supertuxkart.SuperTuxKart",
                                                                                  "9" * 64)})
        linux, _runner, output, _flatpak = self.install(bundles=bundles)
        self.assertIn("The bundle has build 999999999999, games.toml pins a6969d346d09.", output)
        self.assertEqual(linux.steps.warnings, ["Check version"])

    def test_nvidia_gl_extension_comes_from_flathub(self, _download):
        linux, runner, output, flatpak = self.install(nvidia="595.84")
        ref = "org.freedesktop.Platform.GL.nvidia-595-84//1.4"
        calls = runner.joined()
        self.assertIn(f"flatpak install --user -y flathub {ref}", calls)
        self.assertLess(calls.index("flatpak remote-add --user --if-not-exists flathub "
                                    "https://dl.flathub.org/repo/flathub.flatpakrepo"),
                        calls.index(f"flatpak install --user -y flathub {ref}"))
        self.assertIn("==> Install the NVIDIA graphics driver for Flatpak (595.84)", output)
        self.assertIn(ref, flatpak.installed)

    def test_nvidia_extension_already_installed(self, _download):
        _linux, runner, output, _flatpak = self.install(
            nvidia="595.84", installed={"org.freedesktop.Platform.GL.nvidia-595-84//1.4": "3" * 64})
        self.assertFalse(any("flathub" in call for call in runner.joined()))

    def test_without_nvidia_driver_nothing_happens(self, _download):
        _linux, _runner, output, _flatpak = self.install()
        self.assertNotIn("NVIDIA", output)

    def test_failed_nvidia_install_only_warns(self, _download):
        flatpak = FlatpakState(set(), bundles=self.BUNDLES)

        def respond(args):
            if args[-1].startswith("org.freedesktop.Platform.GL.nvidia") and args[1] == "install":
                return 1, ""
            return flatpak.respond(args)

        nvidia_file = self.home / "nvidia-version"
        nvidia_file.write_text("595.84\n")
        steps, output = quiet_steps()
        linux = Linux(FakeRunner(respond=respond), steps, home=self.home, nvidia_version_file=nvidia_file)
        linux.install(STK_BUNDLE)
        self.assertEqual(steps.warnings, ["Install the NVIDIA graphics driver for Flatpak (595.84)"])
        self.assertIn("OK (version 1.5)", output.getvalue())


if __name__ == "__main__":
    unittest.main()
