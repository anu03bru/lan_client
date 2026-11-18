# Open items

Collected TODOs and open questions from the repository (2026-11-17). Most need a test machine.
When an item is resolved, fix the value in the named file (if needed) and delete the item here.

Many Windows/macOS items can be checked without a machine: run the `e2e install` workflow
(`.github/workflows/e2e.yml`, started by hand). Its job summaries show what installs and uninstalls cleanly, the
exe names and app architectures, and which folders a game creates when it starts.

## Windows (needs a Windows test machine)

- [ ] **Whole Windows install is untested.** Run `py lan.py install all`, start every game, then
      `py lan.py uninstall all` and check nothing is left behind.
- [ ] **Doom: does Odamex write to `Documents/My Games/Odamex`?** `games.toml` → `[doom.windows] data`.
      If it writes somewhere else (or into its install folder), update `data`.
- [ ] **Blobby Volley: exe name.** `games.toml` → `[blobby_volley.windows] shortcuts` assumes `blobby.exe`.
      If wrong, creating the desktop shortcut fails with "blobby.exe not found in ...".
- [ ] **Blobby Volley: user data folder.** `games.toml` → `[blobby_volley.windows] data` lists `%APPDATA%/blobby` and
      `%APPDATA%/.blobby` as guesses. The Blobby source uses `PHYSFS_getPrefDir("org.dk", "blobby")`, which on Windows
      is probably `%APPDATA%/org.dk/blobby`.
- [ ] **ZIP games: settings in the install folder?** A reinstall of a *new* version deletes the install folder
      (`remove_other_version` in `lanparty/windows.py`). Check whether Odamex or Blobby Volley keep the player name
      there; if so, those files need to be carried over.
- [ ] **AssaultCube: user data folder.** `games.toml` → `[assaultcube.windows] data` assumes
      `Documents/My Games/AssaultCube`.

## macOS (needs a Mac, ideally one Apple Silicon and one Intel)

- [ ] **Whole macOS install is untested.** Run `./lan.py install all`, start every game, then
      `./lan.py uninstall all`. Tested only with fakes in `tests/test_macos.py`.
      The README says "not tested on a Mac yet"; remove that line once it works.
- [ ] **Disk images with a license agreement.** `hdiutil attach` asks on the terminal before opening such an image.
      Check whether any of the five images does this, and whether the prompt is usable.
- [ ] **User data folders** (what uninstall deletes), in `games.toml` → `[<id>.macos] data`:
  - [ ] Blobby Volley: `~/Library/Application Support/blobby` (from the current Blobby source, not checked for 1.1.1)
  - [ ] 0 A.D.: `~/Library/Application Support/0ad`, `~/Library/Caches/0ad`, `~/Library/Logs/0ad`
  - [ ] SuperTuxKart: `~/Library/Application Support/SuperTuxKart`
  - [ ] AssaultCube: `~/Library/Application Support/assaultcube` (the app contains the text `assaultcube/v1.3`)
- [ ] **Doom: Odalaunch finds Odamex.** Both apps are copied into `~/Applications`. Check that Odalaunch can start
      Odamex from there when joining a server, and that Odamex finds the WADs in `~/.odamex`.
- [ ] **Rosetta.** AssaultCube and Blobby Volley may be Intel-only builds. Check whether they start on Apple Silicon
      (after installing Rosetta) and adjust the README note.
- [ ] **Gatekeeper.** Python downloads don't get the quarantine flag, so unsigned apps should start without the
      "can't be opened" dialog. Confirm, then the README troubleshooting row about it can be shortened.

## Linux

- [x] **Updating the pinned commits.** `commit` in `games.toml` pins 0 A.D. and SuperTuxKart. A player's own
      `flatpak update` still moves to the newest build. Before the party, re-run `./lan.py install all` on every PC,
      or check `flatpak remote-info --log flathub <app_id>` and update the commits if the game version changed.
        this was done

## AssaultCube server

- [ ] **Old admin password in git history.** `assaultcube-server/config/serverpwd.cfg` is no longer tracked, but
      `changeme` is still in the history. Use a new password on the server, don't reuse it.

## Resolved (2026-11-17)

- 0 A.D. Windows installer URL `0ad-0.28.0-win64.exe` exists on releases.wildfiregames.com, and its official
  `.sha256sum` matches `games.toml`.
- Flathub versions match the other platforms: Blobby Volley 1.1.1, SuperTuxKart 1.5, 0 A.D. 0.28.0,
  AssaultCube 1.3.0.2.
