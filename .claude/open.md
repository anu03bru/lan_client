# Open items

Collected TODOs and open questions from the repository (2026-11-17). Most need a test machine.
When an item is resolved, fix the value in the named file (if needed) and delete the item here.

Many Windows/macOS items can be checked without a machine: run the `e2e install` workflow
(`.github/workflows/e2e.yml`, started by hand). Its job summaries show what installs and uninstalls cleanly, the
exe names and app architectures, and which folders a game creates when it starts.

## Windows (needs a Windows test machine)

- [ ] **Doom: does Odamex write to `Documents/My Games/Odamex`?** `games.toml` → `[doom.windows] data`.
      If it writes somewhere else (or into its install folder), update `data`.
- [ ] **ZIP games: settings in the install folder?** A reinstall of a *new* version deletes the install folder
      (`remove_other_version` in `lanparty/windows.py`). Check whether Odamex or Blobby Volley keep the player name
      there; if so, those files need to be carried over.
- [ ] **AssaultCube: user data folder.** `games.toml` → `[assaultcube.windows] data` assumes
      `Documents/My Games/AssaultCube`.

## macOS (needs a Mac, ideally one Apple Silicon and one Intel)

- [ ] **Whole macOS install.** Only SuperTuxKart is tested so far. The other games get tested during the big
      network test (Friday or Monday): `./lan.py install all`, start every game, then `./lan.py uninstall all`.
- [ ] **Disk images with a license agreement.** `hdiutil attach` asks on the terminal before opening such an image.
      Check whether any of the five images does this, and whether the prompt is usable.
- [ ] **User data folders** (what uninstall deletes), in `games.toml` → `[<id>.macos] data`:
  - [ ] Blobby Volley: `~/Library/Application Support/blobby` (from the current Blobby source, not checked for 1.1.1)
  - [ ] 0 A.D.: `~/Library/Application Support/0ad`, `~/Library/Caches/0ad`, `~/Library/Logs/0ad`
  - [ ] AssaultCube: `~/Library/Application Support/assaultcube` (the app contains the text `assaultcube/v1.3`)
- [ ] **Doom: Odalaunch finds Odamex.** Both apps are copied into `~/Applications`. Check that Odalaunch can start
      Odamex from there when joining a server, and that Odamex finds the WADs in `~/.odamex`.
- [ ] **Rosetta.** AssaultCube and Blobby Volley may be Intel-only builds. Check whether they start on Apple Silicon
      (after installing Rosetta) and adjust the README note.
- [ ] **Gatekeeper.** Python downloads don't get the quarantine flag, so unsigned apps should start without the
      "can't be opened" dialog. Confirm, then the README troubleshooting row about it can be shortened.

## Linux

- [ ] **Updating the pinned commits.** Done for now; repeat shortly before the party. `commit` in `games.toml` pins
      0 A.D. and SuperTuxKart. A player's own `flatpak update` still moves to the newest build. Before the party,
      re-run `./lan.py install all` on every PC, or check `flatpak remote-info --log flathub <app_id>` and update the commits if the game version changed.

## LAN share (games-lan.toml)

- [ ] **Share address.** Fill in the `[share]` table in `games-lan.toml` once the fileserver exists (still
      `FILESERVER/lanparty`), then run `scripts/fill_share.py` and copy the result to the share.
- [ ] **Windows: share from the admin window.** The install runs elevated. Check that the elevated process can read
      `\\FILESERVER\lanparty` (UNC works there, mapped drive letters don't). If the share needs a login, log in
      in the normal window first.
- [ ] **Linux: gvfs path.** `[share] linux` assumes user id 1000 and the lowercase server name that gvfs uses.
      Check with `ls /run/user/$(id -u)/gvfs/` on a party PC.
- [ ] **Windows ZIP games after a switch.** `.lanparty-version` stores the download URL, so a PC that installed
      Odamex or Blobby from the internet treats a reinstall from the share as a new version and recreates the
      install folder once.
- [ ] **Flathub games on the share (Linux).** Blobby Volley, 0 A.D., SuperTuxKart and AssaultCube still come from
      Flathub. Bundle them (with their runtimes) for the share, e.g. with `flatpak create-usb` at the pinned commits,
      and teach `lan.py` to install from there. Then update the Linux note in `docs/lan-share.md`.
- [ ] **Thursday 2026-11-26: make games-lan.toml the default.** Set `GAMES_FILE` in `lanparty/cli.py` to
      `games-lan.toml`, so players need no `--games`. Update the commands in `README.md` and `docs/lan-share.md`
      (`--games games.toml` then means "from the internet"). Revert this after the party.
- [ ] **After the party:** delete `games-lan.toml`, `scripts/fill_share.py`, `docs/lan-share.md`, the README chapter
      "At the LAN party", `LanGamesFileTest` in `tests/test_config.py`, the `games.toml` header line about it and the
      CLAUDE.md lines. Keep `--games`, `[share]` / `fill_share` and the local-path download (generic, tested).

## Resolved (2026-11-19)

- Whole Windows install was tested by hand.
- Blobby Volley on Windows: exe name `blobby.exe` is correct (the desktop shortcut gets created).
- Blobby Volley on Windows: uninstall was tested and worked.
- SuperTuxKart `reply_ports`: the ufw rule for the private IPv4 ranges fixes the LAN server list. IPv6 not needed.
- AssaultCube server admin password: not a concern, the server is temporary and runs in a closed network.

## Resolved (2026-11-18)

- SuperTuxKart on macOS: install and uninstall work. The data folder `~/Library/Application Support/SuperTuxKart`
  from `games.toml` is correct and uninstall removes it together with the app. The Mac sees a server hosted on
  Linux under Local network.

## Resolved (2026-11-17)

- 0 A.D. Windows installer URL `0ad-0.28.0-win64.exe` exists on releases.wildfiregames.com, and its official
  `.sha256sum` matches `games.toml`.
- Flathub versions match the other platforms: Blobby Volley 1.1.1, SuperTuxKart 1.5, 0 A.D. 0.28.0,
  AssaultCube 1.3.0.2.
