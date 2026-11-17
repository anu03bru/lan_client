import unittest
from unittest import mock

from lanparty import cli
from lanparty.config import Game, LinuxSpec
from lanparty.steps import StepFailed
from tests.fakes import quiet_steps


def make_game(game_id: str) -> Game:
    return Game(id=game_id, name=game_id.title(), linux=LinuxSpec(type="flatpak", app_id=f"org.{game_id}"))


class FakePlatform:
    name = "Linux"

    def __init__(self, fail: set[str] = frozenset(), admin_needed: bool = False) -> None:
        self.fail = fail
        self.admin_needed = admin_needed
        self.done: list[tuple[str, str]] = []
        self.cleaned = False

    def check_ready(self): pass
    def needs_admin(self): return self.admin_needed
    def supports(self, game): return game.linux is not None
    def is_installed(self, game): return False
    def cleanup_after_uninstall_all(self): self.cleaned = True

    def install(self, game):
        self.done.append(("install", game.id))
        if game.id in self.fail:
            raise StepFailed("install")

    def uninstall(self, game):
        self.done.append(("uninstall", game.id))


GAMES = [make_game("doom"), make_game("stk")]


def run(argv, platform, answer=""):
    steps, output = quiet_steps()
    with mock.patch.object(cli, "ask", return_value=answer):
        code = cli.main(argv, platform=platform, games=GAMES, steps=steps)
    return code, output.getvalue()


class CliTest(unittest.TestCase):
    def test_install_all_continues_after_a_failure(self):
        platform = FakePlatform(fail={"doom"})
        code, output = run(["install", "all"], platform)
        self.assertEqual(code, cli.EXIT_FAILED)
        self.assertEqual(platform.done, [("install", "doom"), ("install", "stk")])
        self.assertIn("Finished with problems in: Doom", output)

    def test_uninstall_asks_first(self):
        platform = FakePlatform()
        code, output = run(["uninstall", "stk"], platform, answer="n")
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(platform.done, [])
        self.assertIn("Cancelled.", output)

    def test_uninstall_all_with_yes_cleans_up(self):
        platform = FakePlatform()
        code, _output = run(["uninstall", "all", "--yes"], platform)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(platform.done, [("uninstall", "doom"), ("uninstall", "stk")])
        self.assertTrue(platform.cleaned)

    def test_unknown_game(self):
        code, output = run(["install", "tetris"], FakePlatform())
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("Choose one of: doom, stk, all", output)

    def test_admin_relaunch_passes_yes_after_confirmation(self):
        with mock.patch("lanparty.windows.relaunch_as_admin", return_value=0) as relaunch:
            code, _output = run(["uninstall", "stk"], FakePlatform(admin_needed=True), answer="y")
        self.assertEqual(code, 0)
        relaunch.assert_called_once_with(cli.LAN_SCRIPT, ["--elevated", "uninstall", "stk", "--yes"])

    def test_menu_runs_the_chosen_action(self):
        platform = FakePlatform()
        steps, _output = quiet_steps()
        with mock.patch.object(cli, "ask", side_effect=["2", "1"]):
            code = cli.main([], platform=platform, games=GAMES, steps=steps)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(platform.done, [("install", "stk")])

    def test_menu_uninstall_is_2(self):
        platform = FakePlatform()
        steps, _output = quiet_steps()
        # game 1, action 2 (uninstall), then "y" to confirm
        with mock.patch.object(cli, "ask", side_effect=["1", "2", "y"]):
            code = cli.main([], platform=platform, games=GAMES, steps=steps)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(platform.done, [("uninstall", "doom")])

    def test_menu_3_goes_back_to_the_game_list(self):
        platform = FakePlatform()
        steps, output = quiet_steps()
        # game 1, back, then game 2 and install
        with mock.patch.object(cli, "ask", side_effect=["1", "3", "2", "1"]):
            code = cli.main([], platform=platform, games=GAMES, steps=steps)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(platform.done, [("install", "stk")])
        self.assertEqual(output.getvalue().count("LAN party games"), 2)

    def test_menu_typo_asks_again(self):
        platform = FakePlatform()
        steps, output = quiet_steps()
        with mock.patch.object(cli, "ask", side_effect=["x", "9", "2", "1"]):
            code = cli.main([], platform=platform, games=GAMES, steps=steps)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(platform.done, [("install", "stk")])
        self.assertIn("ERROR: 'x' is not in the list. Choose again.", output.getvalue())
        self.assertEqual(output.getvalue().count("LAN party games"), 3)

    def test_version_mismatch_is_in_the_final_summary(self):
        platform = FakePlatform()
        steps, output = quiet_steps()
        platform.install = lambda game: steps.version_result("1.4", "1.5")
        code = cli.main(["install", "stk"], platform=platform, games=GAMES, steps=steps)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("Done, but check the warnings above: Check version", output.getvalue())
        self.assertNotIn("Done!", output.getvalue())

    def test_menu_other_action_cancels(self):
        platform = FakePlatform()
        steps, output = quiet_steps()
        with mock.patch.object(cli, "ask", side_effect=["1", "i"]):
            code = cli.main([], platform=platform, games=GAMES, steps=steps)
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(platform.done, [])
        self.assertIn("Cancelled.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
