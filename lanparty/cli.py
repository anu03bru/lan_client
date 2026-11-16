"""Command line and menu of lan.py."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import ConfigError, Game, load_games
from .runner import Runner
from .steps import StepFailed, Steps

REPO_DIR = Path(__file__).resolve().parent.parent
GAMES_FILE = REPO_DIR / "games.toml"
LAN_SCRIPT = REPO_DIR / "lan.py"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def make_platform(runner: Runner, steps: Steps):
    if sys.platform.startswith("linux"):
        from .linux import Linux

        return Linux(runner, steps)
    if sys.platform == "win32":
        from .windows import Windows

        return Windows(runner, steps)
    raise OSError("Only Linux and Windows are supported. On macOS use assaultcube/mac_install_assaultcube.sh.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lan.py",
        description="Install or uninstall the LAN party games. Without a command it shows a menu: "
        "pick a game number (or a = all), then 1 = install or 2 = uninstall.",
    )
    parser.add_argument("--elevated", action="store_true", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", metavar="command")
    commands.add_parser("list", help="show all games and whether they are installed")
    install = commands.add_parser("install", help="install a game, or all games")
    install.add_argument("game", help="game id from 'list', or 'all'")
    uninstall = commands.add_parser("uninstall", help="remove a game with its user data and firewall rules")
    uninstall.add_argument("game", help="game id from 'list', or 'all'")
    uninstall.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    return parser


def main(argv: list[str], platform=None, games: list[Game] | None = None, steps: Steps | None = None) -> int:
    args = build_parser().parse_args(argv)
    steps = steps or Steps()
    try:
        games = games if games is not None else load_games(GAMES_FILE)
        platform = platform or make_platform(Runner(), steps)
        platform.check_ready()
    except (ConfigError, OSError) as error:
        steps.info(f"ERROR: {error}", "red")
        return EXIT_FAILED

    try:
        if args.command is None:
            return menu(platform, games, steps)
        if args.command == "list":
            return show_list(platform, games, steps)
        return run_command(args, platform, games, steps)
    finally:
        if args.elevated:
            # The admin window closes when the app ends, so keep it open to read the output
            input("Press Enter to close this window")


def show_list(platform, games: list[Game], steps: Steps) -> int:
    steps.info(f"Games ({platform.name}):")
    for game in games:
        if not platform.supports(game):
            status = f"not available on {platform.name}"
        else:
            status = "installed" if platform.is_installed(game) else ""
        steps.info(f"  {game.id:<15} {game.name:<28} {status}".rstrip())
    return EXIT_OK


def run_command(args: argparse.Namespace, platform, games: list[Game], steps: Steps) -> int:
    selected = select_games(args.game, platform, games, steps)
    if selected is None:
        return EXIT_USAGE

    if args.command == "uninstall" and not args.yes:
        names = ", ".join(game.name for game in selected)
        answer = ask(f"This removes {names} including the user data (settings, player names, saves). Continue? [y/N] ")
        if answer not in ("y", "yes"):
            steps.info("Cancelled.")
            return EXIT_OK

    if platform.needs_admin():
        from .windows import relaunch_as_admin

        steps.info("Restarting with admin rights...")
        # Confirmation already happened here, so the admin window doesn't ask again
        relaunch_arguments = ["--elevated", args.command, args.game, *(["--yes"] if args.command == "uninstall" else [])]
        return relaunch_as_admin(LAN_SCRIPT, relaunch_arguments)

    failed = []
    for game in selected:
        steps.info("")
        steps.info(f"######## {args.command} {game.name}")
        warnings_before = len(steps.warnings)
        try:
            if args.command == "install":
                platform.install(game)
            else:
                platform.uninstall(game)
        except StepFailed:
            failed.append(game.name)
            continue
        if args.command == "uninstall" and len(steps.warnings) > warnings_before:
            failed.append(game.name)
        elif args.command == "install" and game.hint:
            steps.info(game.hint, "green")

    if args.command == "uninstall" and args.game == "all":
        steps.info("")
        platform.cleanup_after_uninstall_all()

    steps.info("")
    if failed:
        steps.info(f"Finished with problems in: {', '.join(failed)}. Check the lines above.", "yellow")
        return EXIT_FAILED
    if steps.warnings:
        # Install warnings (e.g. firewall) don't fail the install: hosting is optional
        steps.info(f"Done, but check the warnings above: {', '.join(steps.warnings)}", "yellow")
    else:
        steps.info("Done!" if args.command == "install" else "Uninstall done.", "green")
    return EXIT_OK


def select_games(game_id: str, platform, games: list[Game], steps: Steps) -> list[Game] | None:
    if game_id == "all":
        return [game for game in games if platform.supports(game)]
    for game in games:
        if game.id == game_id:
            if not platform.supports(game):
                steps.info(f"ERROR: {game.name} is not available on {platform.name}.", "red")
                return None
            return [game]
    steps.info(f"ERROR: Unknown game '{game_id}'. Choose one of: {', '.join(game.id for game in games)}, all", "red")
    return None


def menu(platform, games: list[Game], steps: Steps) -> int:
    available = [game for game in games if platform.supports(game)]
    steps.info(f"LAN party games ({platform.name})")
    for number, game in enumerate(available, start=1):
        status = " [installed]" if platform.is_installed(game) else ""
        steps.info(f"  {number}) {game.name}{status}")
    steps.info("  a) all games")
    steps.info("  q) quit")

    choice = ask("Choose: ")
    if choice in ("", "q"):
        return EXIT_OK
    if choice == "a":
        game_id = "all"
    elif choice.isdigit() and 1 <= int(choice) <= len(available):
        game_id = available[int(choice) - 1].id
    else:
        steps.info(f"ERROR: '{choice}' is not in the list.", "red")
        return EXIT_USAGE

    steps.info("")
    steps.info("  1) install")
    steps.info("  2) uninstall")
    steps.info("  q) quit")
    action = ask("Choose: ")
    commands = {"1": "install", "2": "uninstall"}
    if action not in commands:
        steps.info("Cancelled.")
        return EXIT_OK
    return main([commands[action], game_id], platform=platform, games=games, steps=steps)


def ask(question: str) -> str:
    try:
        return input(question).strip().lower()
    except EOFError:
        return ""
