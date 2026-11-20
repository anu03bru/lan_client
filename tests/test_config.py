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


class LanGamesFileTest(unittest.TestCase):
    """games-lan.toml must stay games.toml with share URLs. Delete together with games-lan.toml after the party."""

    def load_raw(self, path):
        with open(path, "rb") as games_file:
            return tomllib.load(games_file)

    def test_same_as_games_toml_except_urls(self):
        original = self.load_raw(GAMES_FILE)
        lan = self.load_raw(LAN_GAMES_FILE)
        self.assertEqual(sorted(lan.pop("share")), ["linux", "macos", "windows"])
        self.assertEqual(list(lan), list(original))
        for game_id in original:
            self.assert_same(original[game_id], lan[game_id], game_id, f"[{game_id}]")

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

    def test_reserved_id(self):
        self.assert_error(VALID_GAME.replace("[stk", "[all"), "not 'all'")


if __name__ == "__main__":
    unittest.main()
