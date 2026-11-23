import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lanparty.runner import CommandError
from lanparty.steps import StepFailed
from lanparty.windows import (INSTALL_TIMEOUT_SECONDS, VERSION_MARKER, UninstallEntry, Windows, firewall_rules,
                              ps_quote, remove_other_version, set_config_values, uninstaller_path, version_tuple)
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


ZERO_AD = game_from_toml("""
[runtimes.vcredist_x64]
type = "vcredist-x64"
name = "Microsoft Visual C++ Redistributable"
url = "https://example.invalid/VC_redist.x64.exe"
sha256 = "a1260ebb73dd9da13ec3e37f526f29e494b3b66c00c05fd70767b30a4497d95e"
version = "14.44.35211"
[zero_ad]
name = "0 A.D."
[zero_ad.windows]
type = "nsis"
url = "https://example.invalid/0ad.exe"
sha256 = "a1260ebb73dd9da13ec3e37f526f29e494b3b66c00c05fd70767b30a4497d95e"
uninstall_name = "0 A.D.*"
requires = ["vcredist_x64"]
settings = [{ file = "%APPDATA%/0ad/config/user.cfg", values = { gpuskinning = "false" } }]
""")


class FakeRegistry:
    def __init__(self, entries: list[UninstallEntry], vcredist: tuple[int, ...] | None = None) -> None:
        self.entries = list(entries)
        self.vcredist = vcredist

    def vcredist_x64_version(self):
        return self.vcredist

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

    def test_version_tuple(self):
        self.assertEqual(version_tuple("14.44.35211"), (14, 44, 35211, 0))
        self.assertEqual(version_tuple("14.44.35211.1"), (14, 44, 35211, 1))


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

    def uninstall_with_leftovers(self, folder_name: str, uninstaller_removes_entry: bool = True) -> Path:
        folder = self.root / "programfiles" / folder_name
        folder.mkdir(parents=True)
        (folder / "Uninstall.exe").write_text("")
        (folder / "CONTRIBUTING.md").write_text("")
        entry = UninstallEntry("SuperTuxKart 1.5", f'"{folder / "Uninstall.exe"}" /x', "HKEY_LOCAL_MACHINE", "x")
        registry = FakeRegistry([entry])

        def respond(args):
            if args[0].endswith("Uninstall.exe") and uninstaller_removes_entry:
                registry.entries.clear()
            return 0, "none\n"

        windows, _runner, _output = make_windows(self.root, registry, respond)
        windows.uninstall(STK)
        return folder

    def test_removes_files_the_uninstaller_left_behind(self):
        folder = self.uninstall_with_leftovers("SuperTuxKart 1.5")
        self.assertFalse(folder.exists())

    def test_keeps_folder_whose_name_does_not_match(self):
        folder = self.uninstall_with_leftovers("Games")
        self.assertTrue((folder / "CONTRIBUTING.md").exists())

    def test_keeps_folder_when_uninstall_did_not_finish(self):
        folder = self.uninstall_with_leftovers("SuperTuxKart 1.5", uninstaller_removes_entry=False)
        self.assertTrue((folder / "CONTRIBUTING.md").exists())

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


@mock.patch("lanparty.windows.download")
class NsisInstallTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_installed_version_is_removed_before_the_installer_runs(self, _download):
        uninstaller = self.root / "Uninstall.exe"
        uninstaller.write_text("")
        registry = FakeRegistry([UninstallEntry("SuperTuxKart 1.5", f'"{uninstaller}"', "HKEY_LOCAL_MACHINE", "x")])

        def respond(args):
            if args[0] == str(uninstaller):
                registry.entries.clear()
            return 0, ""

        windows, runner, _output = make_windows(self.root, registry, respond)
        windows.install(STK)
        self.assertEqual(runner.calls[0], [str(uninstaller), "/S"])
        self.assertTrue(runner.calls[1][0].endswith("stk.exe"))
        self.assertEqual(windows.steps.warnings, [])

    def test_first_install_runs_only_the_installer(self, _download):
        windows, runner, output = make_windows(self.root)
        windows.install(STK)
        self.assertTrue(runner.calls[0][0].endswith("stk.exe"))
        self.assertNotIn("Remove the installed version", output.getvalue())

    def test_elapsed_time_is_shown_while_the_installer_runs(self, _download):
        windows, _runner, output = make_windows(self.root)
        windows.install(STK)
        text = output.getvalue()
        self.assertIn("This can take several minutes", text)
        self.assertIn("\r    still installing... 0:05\r    still installing... 1:35\nOK", text)

    def test_installer_has_a_time_limit(self, _download):
        def respond(args):
            if args[0].endswith("stk.exe"):
                raise CommandError("'stk.exe' did not finish within 15 minutes and was stopped")
            return 0, ""

        windows, runner, output = make_windows(self.root, respond=respond)
        with self.assertRaises(StepFailed):
            windows.install(STK)
        self.assertEqual(runner.timeouts[0], INSTALL_TIMEOUT_SECONDS)
        self.assertIn("did not finish within 15 minutes", output.getvalue())


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


@mock.patch("lanparty.windows.download")
class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def install(self, installed, returncode=0):
        def respond(args):
            return (returncode, "") if args[0].endswith("VC_redist.x64.exe") else (0, "")

        windows, runner, output = make_windows(self.root, FakeRegistry([], vcredist=installed), respond)
        try:
            windows.install(ZERO_AD)
        except StepFailed:
            pass
        return windows, runner, output.getvalue()

    def test_missing_runtime_is_installed_before_the_game(self, download):
        _windows, runner, _output = self.install(None)
        self.assertTrue(runner.calls[0][0].endswith("VC_redist.x64.exe"))
        self.assertEqual(runner.calls[0][1:], ["/install", "/quiet", "/norestart"])
        self.assertTrue(runner.calls[1][0].endswith("0ad.exe"))
        self.assertEqual(download.call_args_list[0].args[0], "https://example.invalid/VC_redist.x64.exe")

    def test_older_runtime_is_updated(self, _download):
        _windows, runner, _output = self.install((14, 40, 33810, 0))
        self.assertTrue(runner.calls[0][0].endswith("VC_redist.x64.exe"))

    def test_same_or_newer_runtime_is_kept(self, download):
        for installed in ((14, 44, 35211, 0), (14, 50, 1, 0)):
            _windows, runner, output = self.install(installed)
            self.assertEqual(len(runner.calls), 1, installed)
            self.assertTrue(runner.calls[0][0].endswith("0ad.exe"))
            self.assertIn(f"installed, nothing to do", output)
        self.assertTrue(all(not call.args[0].endswith("VC_redist.x64.exe") for call in download.call_args_list))

    def test_restart_needed_is_a_warning(self, _download):
        windows, runner, output = self.install(None, returncode=3010)
        self.assertIn("Restart Windows", output)
        self.assertEqual(windows.steps.warnings, ["Install Microsoft Visual C++ Redistributable (restart Windows)"])
        self.assertTrue(runner.calls[1][0].endswith("0ad.exe"))

    def test_newer_version_already_installed_is_ok(self, _download):
        windows, runner, output = self.install(None, returncode=1638)
        self.assertIn("OK (a newer version is already installed)", output)
        self.assertEqual(windows.steps.warnings, [])
        self.assertTrue(runner.calls[1][0].endswith("0ad.exe"))

    def test_failed_runtime_stops_the_game_install(self, _download):
        _windows, runner, output = self.install(None, returncode=1603)
        self.assertIn("Installer exited with code 1603", output)
        self.assertIn("https://aka.ms/vs/17/release/vc_redist.x64.exe", output)
        self.assertEqual(len(runner.calls), 1)

    def test_uninstall_leaves_the_runtime(self, _download):
        windows, runner, _output = make_windows(self.root, FakeRegistry([], vcredist=None))
        windows.uninstall(ZERO_AD)
        self.assertFalse(any("VC_redist" in " ".join(call) for call in runner.calls))


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.cfg = self.root / "0ad" / "config" / "user.cfg"

    def test_creates_the_file_when_the_game_has_not_written_it(self):
        self.assertIsNone(set_config_values(self.cfg, {"gpuskinning": "false"}))
        self.assertEqual(self.cfg.read_text(encoding="utf-8"), 'gpuskinning = "false"\n')

    def test_replaces_the_value_and_keeps_other_lines(self):
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text('gpuskinning = "true"\nplayername.multiplayer = "Admin"\n', encoding="utf-8")
        set_config_values(self.cfg, {"gpuskinning": "false"})
        self.assertEqual(self.cfg.read_text(encoding="utf-8").splitlines(),
                         ['playername.multiplayer = "Admin"', 'gpuskinning = "false"'])

    def test_already_set_is_left_alone(self):
        self.cfg.parent.mkdir(parents=True)
        # 0 A.D. sorts user.cfg when it exits, so the line may be anywhere
        original = 'gpuskinning = "false"\nplayername.multiplayer = "Admin"\n'
        self.cfg.write_text(original, encoding="utf-8")
        self.assertEqual(set_config_values(self.cfg, {"gpuskinning": "false"}), "already set, nothing to do")
        self.assertEqual(self.cfg.read_text(encoding="utf-8"), original)

    def test_similar_names_are_not_touched(self):
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text('gpuskinning.extra = "1"\n', encoding="utf-8")
        set_config_values(self.cfg, {"gpuskinning": "false"})
        self.assertIn('gpuskinning.extra = "1"', self.cfg.read_text(encoding="utf-8"))

    @mock.patch("lanparty.windows.download")
    def test_install_sets_the_value_in_appdata(self, _download):
        windows, _runner, output = make_windows(self.root, FakeRegistry([], vcredist=(14, 44, 35211, 0)))
        windows.install(ZERO_AD)
        cfg = self.root / "appdata" / "0ad" / "config" / "user.cfg"
        self.assertEqual(cfg.read_text(encoding="utf-8"), 'gpuskinning = "false"\n')
        self.assertIn("==> Set gpuskinning = false in user.cfg", output.getvalue())
        windows.install(ZERO_AD)
        self.assertIn("OK (already set, nothing to do)", output.getvalue())
