import tempfile
import unittest
from pathlib import Path

from lanparty.windows import (VERSION_MARKER, UninstallEntry, Windows, firewall_rules, ps_quote,
                              remove_other_version, uninstaller_path)
from tests.fakes import FakeRunner, game_from_toml, quiet_steps

STK = game_from_toml("""
[supertuxkart]
name = "SuperTuxKart"
ports = ["2759/udp", "2757/udp"]
[supertuxkart.windows]
type = "nsis"
url = "https://example.invalid/stk.exe"
sha256 = "a1260ebb73dd9da13ec3e37f526f29e494b3b66c00c05fd70767b30a4497d95e"
uninstall_name = "SuperTuxKart*"
data = ["%APPDATA%/supertuxkart"]
""")

BLOBBY = game_from_toml("""
[blobby]
name = "Blobby Volley 2"
[blobby.windows]
type = "zip"
url = "https://example.invalid/blobby.zip"
sha256 = "157b8d340bf89d1a6583d689dbb716099762211944c3ca7b588947b6cd7187ff"
install_dir = "%LOCALAPPDATA%/BlobbyVolley2"
shortcuts = [{ name = "Blobby Volley 2", target = "blobby.exe" }]
""")


class FakeRegistry:
    def __init__(self, entries: list[UninstallEntry]) -> None:
        self.entries = list(entries)

    def find(self, pattern):
        return [entry for entry in self.entries if entry.display_name.lower().startswith(pattern.rstrip("*").lower())]

    def exists(self, entry):
        return entry in self.entries


def make_windows(root: Path, registry: FakeRegistry | None = None, respond=None):
    variables = {name: str(root / name.lower()) for name in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "DOCUMENTS", "DESKTOP")}
    runner = FakeRunner(commands=set(), respond=respond)
    steps, output = quiet_steps()
    windows = Windows(runner, steps, variables=variables, registry=registry or FakeRegistry([]), sleep=lambda _: None)
    return windows, runner, output


class HelperTest(unittest.TestCase):
    def test_rule_names_match_old_scripts(self):
        self.assertEqual(firewall_rules(STK), [("SuperTuxKart multiplayer (UDP 2757,2759)", "UDP", "2757,2759")])
        zero_ad = game_from_toml('[zero]\nname = "0 A.D."\nports = ["20595/udp"]\n[zero.linux]\ntype = "flatpak"\napp_id = "a"\n')
        self.assertEqual(firewall_rules(zero_ad)[0][0], "0 A.D. multiplayer (UDP 20595)")

    def test_uninstaller_path(self):
        self.assertEqual(uninstaller_path('"C:\\Program Files\\STK\\Uninstall.exe"'), "C:\\Program Files\\STK\\Uninstall.exe")
        self.assertEqual(uninstaller_path('"C:\\Games\\uninst.exe" /x'), "C:\\Games\\uninst.exe")
        self.assertEqual(uninstaller_path("C:\\Games\\AC\\uninstall.exe /S"), "C:\\Games\\AC\\uninstall.exe")

    def test_ps_quote(self):
        self.assertEqual(ps_quote("it's"), "'it''s'")


class NsisUninstallTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_runs_uninstaller_and_waits_until_entry_is_gone(self):
        uninstaller = self.root / "Uninstall.exe"
        uninstaller.write_text("")
        entry = UninstallEntry("SuperTuxKart 1.5", f'"{uninstaller}"', "HKEY_LOCAL_MACHINE", "Software\\x\\STK")
        registry = FakeRegistry([entry])

        def respond(args):
            if args[0] == str(uninstaller):
                registry.entries.clear()
            if args[0] == "powershell.exe":
                return 0, "removed\n"
            return 0, ""

        (self.root / "appdata/supertuxkart").mkdir(parents=True)
        windows, runner, _output = make_windows(self.root, registry, respond)
        windows.uninstall(STK)
        self.assertEqual(runner.calls[0], [str(uninstaller), "/S"])
        self.assertTrue(any("Remove-NetFirewallRule -DisplayName 'SuperTuxKart multiplayer (UDP 2757,2759)'" in call[-1]
                            for call in runner.calls))
        self.assertFalse((self.root / "appdata/supertuxkart").exists())
        self.assertEqual(windows.steps.warnings, [])

    def test_refuses_unexpected_uninstaller(self):
        entry = UninstallEntry("SuperTuxKart", "MsiExec.exe /X{123}", "HKEY_LOCAL_MACHINE", "Software\\x\\STK")
        windows, runner, output = make_windows(self.root, FakeRegistry([entry]), lambda args: (0, "none\n"))
        windows.uninstall(STK)
        self.assertEqual(windows.steps.warnings, ["Uninstall SuperTuxKart"])
        self.assertFalse(any(call[0].lower().startswith("msiexec") for call in runner.calls))

    def test_not_installed_is_ok(self):
        windows, _runner, output = make_windows(self.root, respond=lambda args: (0, "none\n"))
        windows.uninstall(STK)
        self.assertIn("OK (not installed, nothing to do)", output.getvalue())
        self.assertIn("OK (no rule, nothing to do)", output.getvalue())


class ZipTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_shortcut_target_is_found_in_subfolder(self):
        exe = self.root / "localappdata/BlobbyVolley2/blobby2/blobby.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("")
        windows, runner, _output = make_windows(self.root)
        windows._create_shortcut(BLOBBY.windows, "Blobby Volley 2", "blobby.exe")
        self.assertIn(f"$shortcut.TargetPath = '{exe}'", runner.calls[0][-1])

    def test_uninstall_removes_folder_and_shortcut(self):
        (self.root / "localappdata/BlobbyVolley2").mkdir(parents=True)
        (self.root / "desktop").mkdir()
        (self.root / "desktop/Blobby Volley 2.lnk").write_text("")
        windows, _runner, _output = make_windows(self.root)
        self.assertTrue(windows.is_installed(BLOBBY))
        windows.uninstall(BLOBBY)
        self.assertFalse((self.root / "localappdata/BlobbyVolley2").exists())
        self.assertFalse((self.root / "desktop/Blobby Volley 2.lnk").exists())
        self.assertFalse(windows.is_installed(BLOBBY))


class VersionMarkerTest(unittest.TestCase):
    def setUp(self):
        self.install_dir = Path(tempfile.mkdtemp()) / "BlobbyVolley2"

    def install(self, url: str, files: list[str]):
        self.install_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            (self.install_dir / name).write_text("")
        (self.install_dir / VERSION_MARKER).write_text(url)

    def test_other_version_is_removed(self):
        self.install("https://example.invalid/blobby-1.0.zip", ["old.dll"])
        self.assertIsNone(remove_other_version(self.install_dir, "https://example.invalid/blobby-1.1.zip"))
        self.assertFalse(self.install_dir.exists())

    def test_same_version_keeps_settings(self):
        self.install("https://example.invalid/blobby-1.1.zip", ["config.xml"])
        self.assertEqual(remove_other_version(self.install_dir, "https://example.invalid/blobby-1.1.zip"),
                         "same version, kept")
        self.assertTrue((self.install_dir / "config.xml").exists())

    def test_folder_without_marker_is_removed(self):
        self.install_dir.mkdir(parents=True)
        (self.install_dir / "old.dll").write_text("")
        remove_other_version(self.install_dir, "https://example.invalid/blobby-1.1.zip")
        self.assertFalse(self.install_dir.exists())

    def test_not_installed(self):
        self.assertEqual(remove_other_version(self.install_dir, "x"), "not installed, nothing to do")


if __name__ == "__main__":
    unittest.main()
