# Open items

Collected TODOs and open questions from the repository (2026-11-17). Most need a test machine.
When an item is resolved, fix the value in the named file (if needed) and delete the item here.

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

## Resolved (2026-11-17)

- 0 A.D. Windows installer URL `0ad-0.28.0-win64.exe` exists on releases.wildfiregames.com, and its official
  `.sha256sum` matches `games.toml`.
- Flathub versions match the other platforms: Blobby Volley 1.1.1, SuperTuxKart 1.5, 0 A.D. 0.28.0,
  AssaultCube 1.3.0.2.
