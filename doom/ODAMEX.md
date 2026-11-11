# Doom LAN Client

Client setup for playing Doom.


- **Odamex** is the game engine (the program you run).
- **Freedoom** provides the game files: maps, graphics and sounds. It is an open source replacement for the original Doom files.

The install script downloads both and sets everything up.

## What gets installed

| File | Content | Used for |
|---|---|---|
| `freedm.wad` | Arena maps, no monsters | Multiplayer: Deathmatch / Team Deathmatch |
| `freedoom2.wad` | Campaign maps with monsters | Co-op (play the campaign together) |
| `freedoom1.wad` | Doom 1 style campaign | Not needed, installed anyway |

| Program | What it does |
|---|---|
| **Odamex** | The game itself. Starts directly, for single-player or a direct connection |
| **Odalaunch** | Server browser. **Use this at the LAN party** to find and join the server |
| **Odasrv** | Game server. **Ignore it**: the server runs on a separate machine |

## Installation

### Linux (CachyOS)

Requirements: `curl`, `flatpak` and `unzip` (the script checks for them).

```bash
cd <path-to-this-repo>
bash install_doom.sh
```

Do **not** run the script with `sudo`.

The script:
1. Installs Odamex as a Flatpak (including the Flatpak runtime, about 600 MB on first install)
2. Downloads the Freedoom files to `~/OdamexLAN/wads`
3. Tells Odamex where to find the game files

Running the script again is safe. It reinstalls everything and keeps your settings.

### Windows

> **TODO:** The Windows script has not been tested yet.

```powershell
powershell -ExecutionPolicy Bypass -File install_doom.ps1
```

The script:
1. Downloads Odamex (portable version) to `%LOCALAPPDATA%\OdamexLAN`
2. Downloads the Freedoom files into the same folder
3. Creates an **"Odamex LAN"** shortcut on the desktop (opens Odalaunch)

No admin rights are needed.

## Starting the game

### Using the menu (GUI)

**Linux:** After installation, the start menu has three new entries: **Odamex**, **Odalaunch** and **Odasrv**.

**Windows:** Use the **"Odamex LAN"** shortcut on the desktop (Odalaunch), or open `%LOCALAPPDATA%\OdamexLAN` and start `odamex.exe` or `odalaunch.exe`.

When Odamex starts, pick a game in **Game Select**:
- **FreeDM**: for deathmatch
- **Freedoom: Phase 2**: for co-op

### Using the terminal

**Linux:**
```bash
# Odamex (game)
flatpak run net.odamex.Odamex

# Odalaunch (server browser)
flatpak run --command=odalaunch net.odamex.Odamex
```

**Windows (PowerShell):**
```powershell
# Odamex (game)
& "$env:LOCALAPPDATA\OdamexLAN\odamex.exe"

# Odalaunch (server browser)
& "$env:LOCALAPPDATA\OdamexLAN\odalaunch.exe"
```

## Joining the LAN server

1. Start **Odalaunch**.
2. Find the LAN server in the list. If it doesn't show up, add it manually: **`<SERVER-IP>:10666`**
3. Double-click the server to join.

Or connect directly from the terminal:

**Linux:**
```bash
flatpak run net.odamex.Odamex -iwad freedm.wad -connect <SERVER-IP>:10666
```

**Windows:**
```powershell
& "$env:LOCALAPPDATA\OdamexLAN\odamex.exe" -iwad freedm.wad -connect <SERVER-IP>:10666
```

Use `freedoom2.wad` instead of `freedm.wad` when the server runs co-op.

## Before your first game

Set your **player name** in Odamex under **Options → Player Setup**, so others can see who you are on the scoreboard.

## Troubleshooting

| Problem | Solution |
|---|---|
| Game Select in Odamex is empty (Linux) | Run: `flatpak override --user --env=DOOMWADDIR="$HOME/OdamexLAN/wads" net.odamex.Odamex` and restart Odamex |
| Script fails | Read the `ERROR` and `Hint` lines. They say which step failed and what to check |
| Server not listed in Odalaunch | Add it manually with `<SERVER-IP>:10666` |