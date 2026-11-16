import tempfile
import unittest
from pathlib import Path

from lanparty.linux import Linux, find_ufw_rule
from lanparty.steps import StepFailed
from tests.fakes import FakeRunner, FakeUfw, game_from_toml, quiet_steps

STK = game_from_toml("""
[supertuxkart]
name = "SuperTuxKart"
version = "1.5"
ports = ["2759/udp", "2757/udp"]
[supertuxkart.linux]
type = "flatpak"
app_id = "net.supertuxkart.SuperTuxKart"
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


class FlatpakState:
    def __init__(self, installed: set[str], version: str = "1.5", remotes: str = "flathub\n") -> None:
        self.installed = set(installed)
        self.version = version
        self.remotes = remotes

    def respond(self, args):
        if args[:2] == ["flatpak", "info"]:
            if args[-1] in self.installed:
                return 0, f"SuperTuxKart\n\n          ID: {args[-1]}\n     Version: {self.version}\n"
            return 1, ""
        if args[:2] == ["flatpak", "install"]:
            self.installed.add(args[-1])
        if args[:2] == ["flatpak", "uninstall"] and "--unused" not in args:
            self.installed.discard(args[-1])
        if args[:2] == ["flatpak", "remote-list"]:
            return 0, self.remotes
        return 0, ""


def make_linux(flatpak: FlatpakState, ufw: FakeUfw, home: Path):
    def respond(args):
        return ufw.respond(args) or flatpak.respond(args)

    runner = FakeRunner(respond=respond)
    steps, output = quiet_steps()
    return Linux(runner, steps, home=home), runner, output


class LinuxInstallTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_install_flatpak_and_open_ports(self):
        ufw = FakeUfw([("22/tcp", "")])
        linux, runner, output = make_linux(FlatpakState(set()), ufw, self.home)
        linux.install(STK)
        self.assertIn("flatpak install --user -y --or-update flathub net.supertuxkart.SuperTuxKart", runner.joined())
        self.assertEqual(ufw.rules, [("22/tcp", ""), ("2759/udp", "SuperTuxKart"), ("2757/udp", "SuperTuxKart")])
        self.assertIn("OK (version 1.5)", output.getvalue())

    def test_version_mismatch_only_warns(self):
        linux, _runner, output = make_linux(FlatpakState(set(), version="1.4"), FakeUfw([]), self.home)
        linux.install(STK)
        self.assertIn('WARNING: Installed version is "1.4", expected "1.5".', output.getvalue())

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
            Linux(runner, steps, home=self.home).install(STK)
        self.assertFalse(any(call[:3] == ["sudo", "ufw", "allow"] for call in runner.calls))


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
        ])
        flatpak = FlatpakState({"net.supertuxkart.SuperTuxKart"})
        linux, runner, output = make_linux(flatpak, ufw, self.home)
        linux.uninstall(STK)
        self.assertEqual(ufw.rules, [("22/tcp", ""), ("20595/udp", "")])
        self.assertEqual(flatpak.installed, set())
        self.assertIn("flatpak uninstall --user -y --delete-data net.supertuxkart.SuperTuxKart", runner.joined())
        self.assertFalse((self.home / ".var/app/net.supertuxkart.SuperTuxKart").exists())
        self.assertEqual(linux.steps.warnings, [])

    def test_uninstall_twice_has_nothing_to_do(self):
        linux, _runner, _output = make_linux(FlatpakState(set()), FakeUfw([]), self.home)
        linux.uninstall(STK)
        linux.uninstall(STK)
        self.assertEqual(linux.steps.warnings, [])

    def test_bundle_uninstall_resets_overrides_and_removes_remote_and_folder(self):
        (self.home / "OdamexLAN/wads").mkdir(parents=True)
        flatpak = FlatpakState({"net.odamex.Odamex"}, remotes="flathub\nodamex-origin\n")
        linux, runner, _output = make_linux(flatpak, FakeUfw([]), self.home)
        linux.uninstall(DOOM)
        calls = runner.joined()
        self.assertIn("flatpak override --user --reset net.odamex.Odamex", calls)
        self.assertIn("flatpak remote-delete --user --force odamex-origin", calls)
        self.assertNotIn("flatpak remote-delete --user --force flathub", calls)
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
[10] 2759/udp (v6)              ALLOW IN    Anywhere (v6)              # SuperTuxKart
"""

    def test_finds_rule_by_comment(self):
        self.assertEqual(find_ufw_rule(self.STATUS, "0 A.D."), 2)
        self.assertEqual(find_ufw_rule(self.STATUS, "SuperTuxKart"), 10)
        self.assertIsNone(find_ufw_rule(self.STATUS, "Blobby Volley 2"))


if __name__ == "__main__":
    unittest.main()
