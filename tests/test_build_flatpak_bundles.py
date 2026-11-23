"""Delete together with scripts/build_flatpak_bundles.py and games-lan.toml after the party."""

import importlib.util
import tomllib
import unittest

from lanparty.cli import REPO_DIR

spec = importlib.util.spec_from_file_location("build_flatpak_bundles", REPO_DIR / "scripts/build_flatpak_bundles.py")
build_flatpak_bundles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_flatpak_bundles)

NEW = "a" * 64


class BuildFlatpakBundlesTest(unittest.TestCase):
    def test_bundles_in_games_lan_toml_runtimes_first(self):
        lan = tomllib.loads((REPO_DIR / "games-lan.toml").read_text(encoding="utf-8"))
        items = build_flatpak_bundles.bundles(lan)
        whats = [item["what"] for item in items]
        self.assertEqual(whats[:4], [
            "runtime org.freedesktop.Platform//26.08", "runtime org.freedesktop.Platform.GL.default//26.08",
            "runtime org.freedesktop.Platform//25.08", "runtime org.freedesktop.Platform.GL.default//25.08",
        ])
        self.assertIn("app com.play0ad.zeroad", whats)
        self.assertNotIn("app net.odamex.Odamex", whats)  # Odamex's bundle comes from GitHub
        self.assertTrue(all(item["check_commit"] for item in items if item["app_id"]))

    def test_write_sha256_inline_table(self):
        text = f'bundle = {{ url = "%SHARE%/0ad/x.flatpak", sha256 = "{"0" * 64}" }}\nsha256 = "keep"\n'
        self.assertEqual(build_flatpak_bundles.write_sha256(text, "%SHARE%/0ad/x.flatpak", NEW),
                         f'bundle = {{ url = "%SHARE%/0ad/x.flatpak", sha256 = "{NEW}" }}\nsha256 = "keep"\n')

    def test_write_sha256_table(self):
        text = f'[a]\nurl = "u1"\nsha256 = "{"0" * 64}"\n[b]\nurl = "u2"\nsha256 = "{"0" * 64}"\n'
        result = build_flatpak_bundles.write_sha256(text, "u2", NEW)
        self.assertEqual(result, f'[a]\nurl = "u1"\nsha256 = "{"0" * 64}"\n[b]\nurl = "u2"\nsha256 = "{NEW}"\n')


if __name__ == "__main__":
    unittest.main()
