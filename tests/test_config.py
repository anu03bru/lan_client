import tomllib
import unittest

from lanparty.cli import GAMES_FILE
from lanparty.config import ConfigError, load_games, parse_games

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
        self.assertEqual(games["doom"].linux.type, "flatpak-bundle")
        self.assertEqual(len(games["doom"].assets), 2)
        self.assertEqual(games["doom"].windows.shortcuts[0].target, "odalaunch.exe")
        for game in games.values():
            self.assertIsNotNone(game.linux, game.id)
            self.assertIsNotNone(game.windows, game.id)
            self.assertIsNotNone(game.macos, game.id)
        self.assertIsNotNone(games["0ad"].macos.arm64_url)
        self.assertTrue(all(asset.macos_dest for asset in games["doom"].assets))


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

    def test_bad_port(self):
        self.assert_error(VALID_GAME.replace("2759/udp", "2759"), "port '2759' must look like")

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
