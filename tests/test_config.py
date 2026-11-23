import tomllib
import unittest
from unittest import mock

from lanparty.cli import REPO_DIR
from lanparty.config import ConfigError, fill_share, load_games, parse_games
from lanparty.download import file_name_from_url

# Named directly, not cli.GAMES_FILE, so the tests still check games.toml when the default changes
GAMES_FILE = REPO_DIR / "games.toml"
LAN_GAMES_FILE = REPO_DIR / "games-lan.toml"

VALID_GAME = """
[stk]
name = "SuperTuxKart"
ports = ["2759/udp"]
[stk.linux]
type = "flatpak"
app_id = "net.supertuxkart.SuperTuxKart"
"""

SHA = "c266acdb8a63a3fe30f52652d9b749f5beba4abeb9e54382fbb934b00c53b303"
MACOS_GAME = f"""
[stk]
name = "SuperTuxKart"
[stk.macos]
type = "dmg"
url = "https://example.invalid/x86.dmg"
sha256 = "{SHA}"
apps = ["SuperTuxKart.app"]
arm64 = {{ url = "https://example.invalid/arm.dmg", sha256 = "{SHA}" }}
"""

WINDOWS_GAME = f"""
[stk]
name = "SuperTuxKart"
[stk.windows]
type = "nsis"
url = "https://example.invalid/stk.exe"
sha256 = "{SHA}"
uninstall_name = "SuperTuxKart*"
"""
RUNTIME = f"""
[runtimes.vcredist_x64]
type = "vcredist-x64"
name = "Microsoft Visual C++ Redistributable"
url = "https://example.invalid/VC_redist.x64.exe"
sha256 = "{SHA}"
version = "14.44.35211"
"""


def parse(text: str):
    return parse_games(tomllib.loads(text))


class GamesFileTest(unittest.TestCase):
    def test_repo_games_file_loads(self):
        games = {game.id: game for game in load_games(GAMES_FILE)}
        self.assertEqual(list(games), ["doom", "blobby_volley", "0ad", "supertuxkart", "assaultcube"])
        self.assertEqual(games["supertuxkart"].ports, ("2759/udp", "2757/udp"))
        self.assertEqual(games["supertuxkart"].reply_ports, ("2757/udp",))
        self.assertEqual(games["doom"].linux.type, "flatpak-bundle")
        self.assertEqual(len(games["doom"].assets), 2)
        self.assertEqual(games["doom"].windows.shortcuts[0].target, "odalaunch.exe")
        for game in games.values():
            self.assertIsNotNone(game.linux, game.id)
            self.assertIsNotNone(game.windows, game.id)
            self.assertIsNotNone(game.macos, game.id)
        self.assertIsNotNone(games["0ad"].macos.arm64_url)
        self.assertTrue(all(asset.macos_dest for asset in games["doom"].assets))
        self.assertEqual([runtime.id for runtime in games["0ad"].windows.requires], ["vcredist_x64"])
        self.assertEqual(games["0ad"].windows.settings[0].values, {"gpuskinning": "false"})
        self.assertEqual(games["0ad"].windows.requires[0].type, "vcredist-x64")


class LanGamesFileTest(unittest.TestCase):
    """games-lan.toml must stay games.toml with share URLs. Delete together with games-lan.toml after the party."""

    def load_raw(self, path):
        with open(path, "rb") as games_file:
            return tomllib.load(games_file)

    def test_same_as_games_toml_except_urls(self):
        original = self.load_raw(GAMES_FILE)
        lan = self.load_raw(LAN_GAMES_FILE)
        self.assertEqual(sorted(lan.pop("share")), ["linux", "macos", "windows"])
        self.remove_lan_only(lan)
        self.assertEqual(list(lan), list(original))
        for game_id in original:
            self.assert_same(original[game_id], lan[game_id], game_id, f"[{game_id}]")

    def remove_lan_only(self, lan):
        """Linux Flatpak bundles exist only on the share (scripts/build_flatpak_bundles.py), not in games.toml:
        the flatpak-runtime runtimes, and bundle/requires in the linux tables. Their URLs are checked here."""
        for runtime_id, runtime in list(lan.get("runtimes", {}).items()):
            if runtime["type"] == "flatpak-runtime":
                self.assertEqual(runtime["url"], f"%SHARE%/runtimes/{file_name_from_url(runtime['url'])}", runtime_id)
                del lan["runtimes"][runtime_id]
        for game_id, table in lan.items():
            linux = table.get("linux", {}) if game_id != "runtimes" else {}
            if "bundle" in linux:
                url = linux.pop("bundle")["url"]
                self.assertEqual(url, f"%SHARE%/{game_id}/{file_name_from_url(url)}", game_id)
            linux.pop("requires", None)

    def test_linux_games_come_from_bundles(self):
        games = {game.id: game for game in load_games(LAN_GAMES_FILE)}
        for game in games.values():
            if game.linux.type == "flatpak":
                self.assertIsNotNone(game.linux.bundle_url, game.id)
                self.assertIsNotNone(game.linux.commit, game.id)
            self.assertEqual({runtime.ref.split("//")[0] for runtime in game.linux.requires},
                             {"org.freedesktop.Platform", "org.freedesktop.Platform.GL.default"}, game.id)

    def assert_same(self, original, lan, game_id, where):
        self.assertIs(type(lan), type(original), where)
        if isinstance(original, dict):
            self.assertEqual(sorted(lan), sorted(original), where)
            for key, value in original.items():
                if key == "url":
                    self.assertEqual(lan[key], f"%SHARE%/{game_id}/{file_name_from_url(value)}", where)
                else:
                    self.assert_same(value, lan[key], game_id, f"{where} {key}")
        elif isinstance(original, list):
            self.assertEqual(len(lan), len(original), where)
            for index, (original_item, lan_item) in enumerate(zip(original, lan)):
                self.assert_same(original_item, lan_item, game_id, f"{where} #{index + 1}")
        else:
            self.assertEqual(lan, original, where)

    def test_loads_with_share_folder_of_this_os(self):
        games = {game.id: game for game in load_games(LAN_GAMES_FILE)}
        self.assertNotIn("%SHARE%", games["doom"].assets[0].url)
        self.assertTrue(games["doom"].assets[0].url.endswith("/doom/freedm-0.13.0.zip"))


class ShareTest(unittest.TestCase):
    SHARE = {"windows": "//srv/lan", "macos": "/Volumes/lan", "linux": "~/lan/"}
    TABLES = {"stk": {"url": "%SHARE%/stk/a.zip", "list": [{"url": "%SHARE%/b.zip"}]}}

    def fill(self, platform, share=SHARE):
        with mock.patch("lanparty.config.current_platform", return_value=platform):
            return fill_share({"share": share, **self.TABLES})

    def test_replaced_with_the_folder_of_this_os(self):
        self.assertEqual(self.fill("windows")["stk"]["url"], "//srv/lan/stk/a.zip")
        self.assertEqual(self.fill("macos")["stk"]["list"][0]["url"], "/Volumes/lan/b.zip")
        with mock.patch("lanparty.config.Path.home", return_value=mock.Mock(as_posix=lambda: "/home/a")):
            self.assertEqual(self.fill("linux")["stk"]["url"], "/home/a/lan/stk/a.zip")

    def test_share_table_checked(self):
        with self.assertRaises(ConfigError) as caught:
            self.fill("linux", {"windows": "x", "macos": "y"})
        self.assertIn("missing linux", str(caught.exception))
        with self.assertRaises(ConfigError) as caught:
            self.fill("linux", {**self.SHARE, "bsd": "z"})
        self.assertIn("unknown key bsd", str(caught.exception))

    def test_placeholder_without_share_table(self):
        with self.assertRaises(ConfigError) as caught:
            fill_share(self.TABLES)
        self.assertIn("no [share] table", str(caught.exception))

    def test_without_share_nothing_changes(self):
        tables = {"stk": {"url": "https://x/a.zip"}}
        self.assertEqual(fill_share(tables), tables)


class ValidationTest(unittest.TestCase):
    def assert_error(self, text: str, message: str):
        with self.assertRaises(ConfigError) as caught:
            parse(text)
        self.assertIn(message, str(caught.exception))

    def test_valid_game(self):
        self.assertEqual(parse(VALID_GAME)[0].linux.app_id, "net.supertuxkart.SuperTuxKart")

    def test_typo_in_key(self):
        self.assert_error(VALID_GAME.replace("ports =", "portz ="), "unknown key portz")

    def test_unknown_type(self):
        self.assert_error(VALID_GAME.replace('"flatpak"', '"snap"'), "unknown type 'snap'")

    def test_missing_required_field(self):
        self.assert_error(VALID_GAME.replace('app_id = "net.supertuxkart.SuperTuxKart"', ""), "missing app_id")

    def test_flatpak_commit(self):
        self.assertEqual(parse(VALID_GAME + f'commit = "{SHA}"\n')[0].linux.commit, SHA)
        self.assert_error(VALID_GAME + 'commit = "abc"\n', "commit must be")

    def test_bad_port(self):
        self.assert_error(VALID_GAME.replace("2759/udp", "2759"), "port '2759' must look like")

    def test_reply_ports(self):
        self.assertEqual(parse(VALID_GAME.replace("ports =", 'reply_ports = ["2757/udp"]\nports ='))[0].reply_ports,
                         ("2757/udp",))
        self.assert_error(VALID_GAME.replace("ports =", 'reply_ports = ["2757"]\nports ='), "port '2757' must look like")

    def test_bad_checksum(self):
        text = VALID_GAME + '[stk.windows]\ntype = "nsis"\nurl = "x"\nsha256 = "abc"\nuninstall_name = "S*"\n'
        self.assert_error(text, "sha256 must be 64")

    def test_needs_a_platform(self):
        self.assert_error('[x]\nname = "X"\n', "needs a [x.linux], [x.windows] or [x.macos]")

    def test_macos_only_game(self):
        game = parse(MACOS_GAME)[0]
        self.assertEqual(game.macos.apps, ("SuperTuxKart.app",))
        self.assertEqual(game.macos.arm64_url, "https://example.invalid/arm.dmg")
        self.assertIsNone(game.linux)

    def test_macos_apps_must_be_app_names(self):
        self.assert_error(MACOS_GAME.replace('"SuperTuxKart.app"', '"SuperTuxKart"'), "apps must be")

    def test_macos_arm64_needs_url_and_sha256(self):
        self.assert_error(MACOS_GAME.replace(', sha256 = "' + SHA + '"', ""), "arm64: missing sha256")

    def test_macos_game_assets_need_macos_dest(self):
        asset = (f'[[stk.assets]]\nurl = "x"\nsha256 = "{SHA}"\nextract = "*.wad"\n'
                 'linux_dest = "~/a"\nwindows_dest = "%APPDATA%/a"\n')
        self.assert_error(MACOS_GAME + asset, "needs a macos_dest")
        game = parse(MACOS_GAME + asset + 'macos_dest = "~/a"\n')[0]
        self.assertEqual(game.assets[0].macos_dest, "~/a")

    def test_windows_requires_runtime(self):
        game = parse(RUNTIME + WINDOWS_GAME + 'requires = ["vcredist_x64", "vcredist_x64"]\n')[0]
        self.assertEqual(len(game.windows.requires), 1)
        runtime = game.windows.requires[0]
        self.assertEqual((runtime.id, runtime.type, runtime.version), ("vcredist_x64", "vcredist-x64", "14.44.35211"))
        self.assertEqual(parse(RUNTIME + WINDOWS_GAME)[0].windows.requires, ())

    def test_runtimes_table_is_not_a_game(self):
        self.assertEqual([game.id for game in parse(RUNTIME + WINDOWS_GAME)], ["stk"])

    def test_unknown_runtime(self):
        self.assert_error(WINDOWS_GAME + 'requires = ["vcredist"]\n', "requires unknown runtime 'vcredist'")
        self.assert_error(RUNTIME + WINDOWS_GAME + 'requires = ["vcredist"]\n', "(defined in [runtimes]: vcredist_x64)")

    def test_runtime_fields_checked(self):
        self.assert_error(RUNTIME.replace('"vcredist-x64"', '"dotnet"'), "unknown type 'dotnet'")
        self.assert_error(RUNTIME.replace('version = "14.44.35211"', ""), "missing version")
        self.assert_error(RUNTIME.replace('"14.44.35211"', '"latest"'), "version must look like")
        self.assert_error(RUNTIME.replace(f'"{SHA}"', '"abc"'), "sha256 must be 64")

    def test_linux_bundle_and_runtimes(self):
        runtime = (f'[runtimes.platform]\ntype = "flatpak-runtime"\nname = "Runtime"\n'
                   f'ref = "org.freedesktop.Platform//26.08"\nurl = "/share/p.flatpak"\nsha256 = "{SHA}"\n')
        bundle = f'bundle = {{ url = "/share/stk.flatpak", sha256 = "{SHA}" }}\nrequires = ["platform"]\n'
        game = parse(runtime + VALID_GAME + bundle)[0]
        self.assertEqual(game.linux.bundle_url, "/share/stk.flatpak")
        self.assertEqual(game.linux.requires[0].ref, "org.freedesktop.Platform//26.08")
        self.assertIsNone(parse(VALID_GAME)[0].linux.bundle_url)
        self.assert_error(runtime.replace("//26.08", ""), "ref must look like")
        self.assert_error(runtime + VALID_GAME + bundle.replace(f', sha256 = "{SHA}"', ""), "bundle: missing sha256")

    def test_windows_settings(self):
        setting = '\nsettings = [{ file = "%APPDATA%/x/user.cfg", values = { gpuskinning = "false" } }]\n'
        game = parse(WINDOWS_GAME + setting)[0]
        self.assertEqual(game.windows.settings[0].file, "%APPDATA%/x/user.cfg")
        self.assertEqual(game.windows.settings[0].values, {"gpuskinning": "false"})
        self.assert_error(WINDOWS_GAME + setting.replace('"false"', '\'"false"\''), "without quotes")
        self.assert_error(WINDOWS_GAME + setting.replace("gpuskinning", '"gpu skinning"'), "not a valid setting name")
        self.assert_error(WINDOWS_GAME + setting.replace("values = { gpuskinning = \"false\" }", "values = {}"),
                          "values must be a table")
        self.assert_error(WINDOWS_GAME + setting.replace("file =", "path ="), "missing file")

    def test_runtime_must_fit_the_platform(self):
        self.assert_error(RUNTIME + VALID_GAME + 'requires = ["vcredist_x64"]\n',
                          "runtime 'vcredist_x64' is a vcredist-x64 runtime, not for linux")

    def test_reserved_id(self):
        self.assert_error(VALID_GAME.replace("[stk", "[all"), "not 'all'")


if __name__ == "__main__":
    unittest.main()
