import plistlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lanparty.macos import Macos, find_app
from lanparty.steps import StepFailed
from tests.fakes import FakeRunner, game_from_toml, quiet_steps

ZERO_AD = game_from_toml("""
[0ad]
name = "0 A.D."
version = "0.28.0"
ports = ["20595/udp"]
[0ad.macos]
type = "dmg"
url = "https://example.invalid/0ad-x86_64.dmg"
sha256 = "3d30cbafb293fb1178c08075ed8336d1dbfb1090d3702ada76092e85e9c4f076"
apps = ["0 A.D..app"]
arm64 = { url = "https://example.invalid/0ad-aarch64.dmg", sha256 = "8c53566123fed9a79766c364e543d6e9dc7c84f642c78d2bb5892eeea9c4c052" }
data = ["~/Library/Application Support/0ad"]
""")

STK = game_from_toml("""
[supertuxkart]
name = "SuperTuxKart"
[supertuxkart.macos]
type = "zip"
url = "https://example.invalid/stk-mac.zip"
sha256 = "c266acdb8a63a3fe30f52652d9b749f5beba4abeb9e54382fbb934b00c53b303"
apps = ["SuperTuxKart.app"]
""")


class FakeMac:
    """Fakes hdiutil and ditto: the "disk image" and the "ZIP" contain the apps in `image_apps`."""

    def __init__(self, image_apps: list[str], version: str = "0.28.0") -> None:
        self.image_apps = image_apps
        self.version = version
        self.mounted: set[str] = set()

    def respond(self, args):
        if args[:2] == ["hdiutil", "attach"]:
            mount_dir = Path(args[args.index("-mountpoint") + 1])
            self._fill(mount_dir)
            self.mounted.add(str(mount_dir))
        elif args[:2] == ["hdiutil", "detach"]:
            self.mounted.discard(args[2])
        elif args[:3] == ["ditto", "-x", "-k"]:
            self._fill(Path(args[4]) / "SuperTuxKart-1.5")  # the app is one folder deeper in the ZIP
        elif args[0] == "ditto":
            shutil.copytree(args[1], args[2], symlinks=True)
        return 0, ""

    def _fill(self, folder: Path) -> None:
        for app in self.image_apps:
            contents = folder / app / "Contents"
            contents.mkdir(parents=True)
            with open(contents / "Info.plist", "wb") as plist_file:
                plistlib.dump({"CFBundleShortVersionString": self.version}, plist_file)


def fake_download(url, target, sha256):
    target.write_text(url)


class MacosTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.system_applications = Path(tempfile.mkdtemp())
        patcher = mock.patch("lanparty.macos.download", side_effect=fake_download)
        self.download = patcher.start()
        self.addCleanup(patcher.stop)

    def make(self, fake: FakeMac, machine: str = "x86_64"):
        runner = FakeRunner(commands=set(), respond=fake.respond)
        steps, output = quiet_steps()
        macos = Macos(runner, steps, home=self.home, machine=machine, system_applications=self.system_applications)
        return macos, runner, output

    def test_dmg_install_copies_app_and_closes_image(self):
        fake = FakeMac(["0 A.D..app"])
        macos, runner, output = self.make(fake)
        self.assertFalse(macos.is_installed(ZERO_AD))
        macos.install(ZERO_AD)
        self.assertTrue((self.home / "Applications/0 A.D..app/Contents/Info.plist").exists())
        self.assertTrue(macos.is_installed(ZERO_AD))
        self.assertEqual(fake.mounted, set())
        self.assertEqual(self.download.call_args.args[0], "https://example.invalid/0ad-x86_64.dmg")
        self.assertIn("OK (version 0.28.0)", output.getvalue())
        self.assertEqual(macos.steps.warnings, [])

    def test_arm64_build_is_used_on_apple_silicon(self):
        macos, _runner, _output = self.make(FakeMac(["0 A.D..app"]), machine="arm64")
        macos.install(ZERO_AD)
        self.assertEqual(self.download.call_args.args[0], "https://example.invalid/0ad-aarch64.dmg")

    def test_zip_install_finds_app_one_folder_deeper(self):
        macos, runner, _output = self.make(FakeMac(["SuperTuxKart.app"]))
        macos.install(STK)
        self.assertTrue((self.home / "Applications/SuperTuxKart.app").is_dir())
        self.assertTrue(any(call[:3] == ["ditto", "-x", "-k"] for call in runner.calls))

    def test_reinstall_replaces_the_old_app(self):
        old_file = self.home / "Applications/SuperTuxKart.app/old.txt"
        old_file.parent.mkdir(parents=True)
        old_file.write_text("")
        macos, _runner, _output = self.make(FakeMac(["SuperTuxKart.app"]))
        macos.install(STK)
        self.assertFalse(old_file.exists())

    def test_missing_app_lists_what_is_there_and_still_closes_image(self):
        fake = FakeMac(["0AD.app"])
        macos, _runner, output = self.make(fake)
        with self.assertRaises(StepFailed):
            macos.install(ZERO_AD)
        self.assertIn("0 A.D..app not found in the download. It contains: 0AD.app", output.getvalue())
        self.assertEqual(fake.mounted, set())

    def test_version_mismatch_only_warns(self):
        macos, _runner, output = self.make(FakeMac(["0 A.D..app"], version="0.27.1"))
        macos.install(ZERO_AD)
        self.assertIn('WARNING: Installed version is "0.27.1", expected "0.28.0".', output.getvalue())

    def test_uninstall_removes_apps_in_both_folders_and_data(self):
        (self.home / "Applications/0 A.D..app").mkdir(parents=True)
        (self.system_applications / "0 A.D..app").mkdir()
        (self.home / "Library/Application Support/0ad").mkdir(parents=True)
        macos, _runner, _output = self.make(FakeMac([]))
        macos.uninstall(ZERO_AD)
        self.assertFalse((self.home / "Applications/0 A.D..app").exists())
        self.assertFalse((self.system_applications / "0 A.D..app").exists())
        self.assertFalse((self.home / "Library/Application Support/0ad").exists())
        self.assertFalse(macos.is_installed(ZERO_AD))
        self.assertEqual(macos.steps.warnings, [])

    def test_uninstall_twice_has_nothing_to_do(self):
        macos, _runner, output = self.make(FakeMac([]))
        macos.uninstall(ZERO_AD)
        macos.uninstall(ZERO_AD)
        self.assertIn("OK (not installed, nothing to do)", output.getvalue())
        self.assertEqual(macos.steps.warnings, [])


class FindAppTest(unittest.TestCase):
    def test_top_level_wins(self):
        root = Path(tempfile.mkdtemp())
        (root / "Game.app").mkdir()
        (root / "sub/Game.app").mkdir(parents=True)
        self.assertEqual(find_app(root, "Game.app"), root / "Game.app")


if __name__ == "__main__":
    unittest.main()
