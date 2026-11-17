# Review findings, checked against the current branch

Source: a code review from a separate Claude session that did not have the macOS work or `.claude/open.md`.
Checked on 2026-11-17 against `feat/installer-for-all-games` (after commit `e5eda80`). Point 1 (merge into main)
waits until the points below are resolved. Line numbers refer to the current files.

| # | Recommendation | Status | Effort |
|---|---|---|---|
| 2 | Linux doesn't install the pinned version | **Confirmed** | medium |
| 3 | Version mismatch still ends with "Done!" | **Confirmed**, fix needs a tweak | small |
| 4 | Typo in the menu exits the program | **Confirmed** | small |
| 5 | Reinstalling a Windows ZIP game leaves old files | **Confirmed**, suggested fix needs a change | small |
| 6 | Confusing hint for a failed Windows installer | **Confirmed** | trivial |
| 7a | TODO for the 0 A.D. URL in `games.toml` | **Already resolved** | – |
| 7b | `start.sh` mentions `./setup.sh <url>` | **Confirmed** | trivial |
| 7c | Admin password `changeme` committed | **Confirmed**, fix needs a `start.sh` change | small |
| 7d | `.idea/` is committed | **Confirmed** | trivial |
| 7e | ufw comment matched as substring | **Confirmed**, but the suggested fix breaks a feature | small |
| 8 | Add CI | **Confirmed** (no `.github/`), Windows run unverified | small |

## Resolution (2026-11-17)

All points are fixed on the branch. 62 tests pass; CI is set up but hasn't run yet.

| # | What was done |
|---|---|
| 2 | Optional `commit` field for Flathub apps (`[<id>.linux]`). After `flatpak install`, the handler runs `flatpak update --user -y --commit=<hash>` (x86_64 only, other architectures get a warning). Pinned: 0 A.D. `2aa7e3f4…` (0.28.0), SuperTuxKart `a6969d34…` (1.5), the newest Flathub commit of each version. |
| 3 | `Steps.version_result` adds one `"Check version"` entry to `warnings`, so the summary says "Done, but check the warnings above". |
| 4 | Invalid game choice in the menu prints an error and asks again. |
| 5 | Windows ZIP install writes `.lanparty-version` (the download URL) into the install folder. On reinstall the folder is deleted first only when the URL differs (or the marker is missing). Same version: kept, so settings next to the exe survive. |
| 6 | Hint now says "Download and run it manually". |
| 7a | Was already resolved. |
| 7b | `start.sh` says `Run ./setup.sh first.` |
| 7c | `serverpwd.cfg` untracked and ignored, `serverpwd.cfg.example` committed. `start.sh` stops when the real file is missing, warns on `changeme`, and doesn't copy `*.example`. `setup.sh` tells you to create the file. The old password is still in the git history (see `.claude/open.md`). |
| 7d | `.idea/` ignored and untracked (files stay on disk). |
| 7e | ufw comments now match exactly, plus `OLD_UFW_COMMENTS` (`SuperTuxKart server`). **This was a real bug:** on the server machine, uninstalling the AssaultCube client also deleted the `AssaultCube server` rules from `assaultcube-server/setup.sh`. |
| 8 | `.github/workflows/tests.yml`: `python -m unittest` on Ubuntu, Windows and macOS with Python 3.11 and the newest 3.x. Checked locally that the code uses no syntax newer than 3.11; the Windows and macOS runs are still unverified. |

---

## 2. Linux doesn't install the pinned version — confirmed

`lanparty/linux.py:66` runs `flatpak install --user -y --or-update flathub <app_id>`, which always installs the newest
Flathub build. `version` in `games.toml` is only compared afterwards (`_check_version` → `Steps.version_result`), and a
mismatch only prints a warning. Windows and macOS are pinned through URL + sha256, so only Linux can drift.

Right now there is no actual mismatch: the latest Flathub releases are SuperTuxKart 1.5, 0 A.D. 0.28.0,
Blobby Volley 1.1.1 and AssaultCube 1.3.0.2, the same as the other platforms. The risk is an update shortly before the
party. Doom is not affected because it installs a pinned `.flatpak` bundle.

Options:
- **Pin the commit (real fix).** Add an optional `commit` field to `[<id>.linux]`. After the install, run
  `flatpak update --user -y --commit=<hash> <app_id>`. The hash comes from
  `flatpak remote-info --log flathub <app_id>`. Commits differ per architecture, so it's x86_64 only, which is fine
  for the party PCs. Flathub keeps old commits, but check that before relying on it.
- **Make a mismatch fail loudly (minimum).** Turn it into a failed step, or at least a counted warning (see #3), so
  the player sees it at the end and tells the organizer.

Recommendation: do #3 now (cheap). Add the `commit` pin for the two games with a `version` (0ad, supertuxkart).

## 3. Version mismatch still ends with "Done!" — confirmed

`Steps.warn` (`lanparty/steps.py:49`) only prints. `self.warnings` is filled only by `attempt` (line 41), and
`cli.run_command` (lines 136–140) builds the final summary from `self.warnings`, so the end says "Done!".

The suggested fix, appending in `warn`, would add **two** entries per mismatch, because `Steps.version_result` calls
`warn` twice (once for the mismatch, once for "tell the organizer"). Instead, append one short entry
(e.g. `"Check version"`) in `version_result`, or let `warn` take a flag. `version_result` is shared by Linux and macOS
since this session, so one fix covers both. Side effect to keep in mind: `cli.py:123` counts new warnings during
*uninstall* as a failure, but `warn` isn't used in uninstall, so nothing changes there.

## 4. Typo in the menu exits the program — confirmed

`lanparty/cli.py:174–176`: an invalid game choice prints an error and `return EXIT_USAGE`. Change it to print the
error and `continue` (the loop already exists for "3 = back"). The second prompt (install/uninstall/back) treats any
other input as "Cancelled" and exits. That is acceptable, but could also loop for consistency. No existing test
covers the invalid menu input (`tests/test_cli.py:72` tests an unknown id on the command line), so add one.

## 5. Reinstalling a Windows ZIP game leaves old files — confirmed, fix differs

`lanparty/windows.py:98–103` extracts with `extract_all` over the existing `install_dir`. Files that a newer version
removed or renamed stay behind.

The suggested "keep the WADs" exception is not needed. The Doom assets (WADs) are downloaded and extracted again
right after, in the same `install()` call (lines 105–117), so deleting `install_dir` first is safe.

The real risk is **user settings stored in the install folder**. Portable ZIP builds often keep their config next to
the exe, e.g. Odamex `odamex.cfg` with the player name. Deleting the folder would reset them on every reinstall. This
is the same open question as the Windows data folders in `.claude/open.md`. Options: delete only before extracting a
*different* version, or keep a list of files to preserve. Until that is checked on Windows, keep the current
behaviour or only delete when the version changes. The macOS handler already removes the old app before copying.

## 6. Confusing hint for a failed Windows installer — confirmed

`lanparty/windows.py:94`: `"The installer failed. Try running it manually: {spec.url}"`. Change it to
`"The installer failed. Download and run it manually: {spec.url}"`. Trivial.

## 7. Small issues

**7a. 0 A.D. URL TODO — already resolved.** Removed in this session: the URL exists on releases.wildfiregames.com,
and the official `.sha256sum` matches `games.toml`. The remaining TODOs live in `.claude/open.md`.

**7b. `start.sh` hint — confirmed.** `assaultcube-server/start.sh:9` says `Run ./setup.sh <url> first.`, but
`setup.sh` takes no arguments (the URL is built from `ASSAULTCUBE_VERSION`). Change it to `Run ./setup.sh first.`

**7c. Committed admin password — confirmed, fix needs care.** `assaultcube-server/config/serverpwd.cfg` contains
`changeme`. Low impact on a LAN-only server (`servercmdline.txt` has no `-Y` master key), but the repo is on GitHub.
Note: `start.sh` copies `config/*` into the install, so a committed `serverpwd.cfg.example` would also be copied.
Plan: `git rm --cached` the real file, add it to `.gitignore`, commit `serverpwd.cfg.example`, and have `start.sh`
skip `*.example` and stop with a clear message when `serverpwd.cfg` is missing. Also update the "Edit the files in
config/" hint at the end of `setup.sh`.

**7d. `.idea/` committed — confirmed.** Five files are tracked (`.idea/.gitignore`, `.name`, `lan_client.iml`,
`modules.xml`, `vcs.xml`). Add `.idea/` to `.gitignore` and `git rm -r --cached .idea`.

**7e. ufw comment substring match — confirmed, but the suggested fix breaks a feature.**
`lanparty/linux.py:267` matches `f"# {comment}" in line`. This is **intentional**: it also removes rules with the
comment `SuperTuxKart server` from the first version of the install script, and
`tests/test_linux.py:99–114` tests exactly that. Comparing the full comment would leave those old rules behind
(this contradicts the "uninstall also cleans up after the old scripts" invariant in `CLAUDE.md`).

The concern is still real for the future (a "Doom" game would match "Doom 2" rules). Better fix: parse the comment
out of the line and match it exactly against the game name **or** a short list of known old comments (e.g. a
`legacy_rule_comments` set in `linux.py`, or derived per game). No current game names are prefixes of each other,
so this is not urgent.

## 8. Add CI — confirmed, unverified on Windows

There is no `.github/` folder. A GitHub Actions workflow running `python -m unittest` on `ubuntu-latest`,
`windows-latest` and now `macos-latest` (Python 3.11 and newer) would cover all three handlers, since every test uses
fakes. Not yet checked: whether the tests pass on Windows and macOS runners. For example, `tests/test_macos.py`
builds fake paths and `tests/test_linux.py` uses POSIX-style home paths. Expect a few small fixes on the first run.

## Additional findings while checking

- `Steps.version_result` calls `warn` twice per mismatch, which matters for #3 (see above).
- The Windows handler has no version check at all. That's fine, since URL + sha256 pin the version.
