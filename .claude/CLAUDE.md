# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
All paths below are relative to the repository root.

## What this is

`lan.py` installs and uninstalls the LAN party games on Linux (Flatpak + ufw), Windows (NSIS installers / portable
ZIPs + Windows Defender Firewall) and macOS (.dmg / ZIP apps copied into `~/Applications`). Python 3.11+, standard
library only (needs `tomllib`), no build step and no linter configured. `README.md` is written for the players, not
for developers.

## Commands

```bash
python3 -m unittest                                   # all tests (any OS; CI runs them on Linux, Windows and macOS)
python3 -m unittest tests.test_macos                  # one module
python3 -m unittest tests.test_macos.MacosTest.test_arm64_build_is_used_on_apple_silicon   # one test
./lan.py list                                         # quick check that games.toml still loads
./lan.py --games games-lan.toml list                  # same for the LAN party copy (files from the LAN share)
```

Don't run `./lan.py install` / `uninstall` casually: they install real software, change firewall rules (via sudo on
Linux) and delete user data.

## Architecture

- `games.toml` is the single source of truth for games: URLs, sha256, ports, app ids, data folders. Its header comment
  is the field reference. Adding a game should normally need no code change. The `[runtimes]` table is not a game:
  it holds Windows runtimes (Visual C++ Redistributable) that a game lists in `requires`. They are installed when
  missing and never uninstalled.
- `lanparty/config.py` parses it strictly into frozen dataclasses (`Game`, `LinuxSpec`, `WindowsSpec`, `MacosSpec`,
  `Asset`). Unknown keys are errors, and each spec `type` has a required/optional key set in `LINUX_TYPES`,
  `WINDOWS_TYPES` and `MACOS_TYPES`. A new field means: dataclass + type table + `_parse_*` + the `games.toml` header
  comment + `tests/test_config.py`.
- `lanparty/cli.py` handles arguments and the menu, then `make_platform()` picks `Linux`, `Windows` or `Macos` by
  `sys.platform`. All three handlers have the same duck-typed interface: `name`, `check_ready`, `needs_admin`,
  `supports`, `is_installed`, `install`, `uninstall` and `cleanup_after_uninstall_all`. There is no base class.
  `tests/test_cli.py` has a `FakePlatform` showing the interface.
- `lanparty/steps.py` handles the step output (`==> Step`, then `OK` / `WARNING` / `ERROR` + `Hint`).
  `steps.run` is for required steps: on failure it raises `StepFailed`, which stops that game, but the CLI continues
  with the next one. `steps.attempt` is for optional steps and only records a warning. Uninstall uses `attempt` for
  everything, so one stuck item doesn't block the rest.
  Every step gets a hint telling the player exactly what to do or run by hand.
- All external commands go through `lanparty/runner.py` (`Runner.run`, `Runner.exists`). Tests replace it with
  `FakeRunner` and `FakeUfw` from `tests/fakes.py`, so no test runs real commands. Platform-only modules (`winreg`,
  `ctypes.windll`) are imported inside functions, so `windows.py` stays importable on Linux.
- `games-lan.toml` (temporary, LAN party only) is `games.toml` with every `url` set to `%SHARE%/<id>/<file>`. Its
  `[share]` table gives the share folder per OS, filled in by `config.fill_share`. `download()` copies plain paths
  instead of fetching them. A test in `tests/test_config.py` fails when the two files differ in anything but the URLs.
- `lanparty/download.py` handles downloads, which always carry a sha256 check. It also does ZIP extraction and the
  path placeholders (`~` everywhere, `%APPDATA%` and similar only on Windows). SourceForge needs the Wget user agent
  set there.
- On Windows, a command that needs admin re-launches `lan.py` elevated with the hidden `--elevated` flag (one UAC
  prompt), after the uninstall confirmation was already asked in the normal window.

## Invariants

- **Install and uninstall must be safe to run twice.** Removing something that isn't there returns a note like
  `"not installed, nothing to do"`, not an error.
- **A game's `name` identifies its firewall rules** (the ufw comment on Linux, the rule name prefix on Windows).
  Renaming a game breaks uninstall on machines that already have it. ufw comments are matched exactly, plus the
  per-game list `OLD_UFW_COMMENTS` in `lanparty/linux.py`. Never match by substring: the AssaultCube client
  would then delete the `AssaultCube server` rules from `assaultcube-server/setup.sh`.
- **Uninstall also cleans up after the old per-game scripts this tool replaced.** For example, Windows rule names match
  the old scripts, and macOS also removes apps from `/Applications`. Keep that when changing uninstall code.
- **Linux and macOS refuse to run as root.** Linux calls `sudo` itself only for ufw.
- **All players need the same game version.** Windows and macOS are pinned by URL + sha256. On Linux, Flathub
  apps are pinned with `commit` (x86_64 only), and `version` is checked afterwards. A mismatch is a warning that
  shows up in the final summary (`Steps.version_result`).
- **Reinstalling a Windows ZIP game keeps the folder only when it holds the same version** (marker file
  `.lanparty-version` with the download URL), because portable games may keep settings next to the exe.

## Conventions

- Open TODOs and unverified values (mostly things needing a Windows or Mac test machine) go into `.claude/open.md`,
  not into code comments.
- Commit messages use conventional commits (`feat:`, `fix:`, `docs:`, `chore:`).
- `assaultcube-server/` is a separate set of shell scripts for the dedicated server machine and is not part of
  `lan.py`.
