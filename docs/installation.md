# Installation

Check the [prerequisites](../README.md#prerequisites) first. At the LAN party itself, follow
[lan-share.md](lan-share.md) instead: it is the same install, but the files come from the LAN fileserver.

## Download this repository

- With git: `git clone https://github.com/anu03bru/lan_client.git`
- Without git: on the GitHub page click **Code → Download ZIP** and unpack it.

All commands below are run inside that folder.

## Windows

1. **Install Python 3.11 or newer.** Open PowerShell and run:
   ```powershell
   winget install Python.Python.3.12
   ```
   Or use the installer from [python.org](https://www.python.org/downloads/).
2. **Open PowerShell in the repository folder** (in Explorer: Shift + right-click on the folder → *Open in Terminal*).
3. **Start the menu:**
   ```powershell
   py lan.py
   ```
   Pick a game number (or `a` for all games), then `1` to install.
4. **Confirm the admin prompt.** It is needed for the installers and the firewall rules. Confirm it with **your own**
   Windows account: if a different account confirms it, the games end up in that account's folders.

After the install the games are on the desktop: **Odamex LAN**, **Odamex Singleplayer**, **Blobby Volley 2**,
**0 A.D.** and **SuperTuxKart**. 0 A.D., SuperTuxKart and AssaultCube are also in the start menu.

## Linux

**CachyOS is recommended**, everything is tested there. Other distributions work too, as long as Flatpak is available.

1. **Install Flatpak** (if you don't have it yet):
   ```bash
   sudo pacman -S flatpak       # CachyOS / Arch
   ```
   On other distributions use their package manager (e.g. `sudo apt install flatpak`).
   Python 3.11 or newer is also needed; CachyOS already has it.
2. **Start the menu** in the repository folder:
   ```bash
   ./lan.py
   ```
   Pick a game number (or `a` for all games), then `1` to install.

**Do not use `sudo`** to run `lan.py`. It asks for your password itself when it opens firewall ports.
The games are installed as Flatpaks and show up in your start menu.

## macOS

macOS support is newer and still being tested. Please report what doesn't work.

1. **Install Python 3.11 or newer** with the installer from [python.org](https://www.python.org/downloads/macos/)
   (or `brew install python` if you use Homebrew). The `python3` that comes with macOS is too old.
   After the python.org install, open **Applications → Python 3.x** and double-click
   **Install Certificates.command**. Without it, downloads fail with `CERTIFICATE_VERIFY_FAILED`.
2. **Open Terminal in the repository folder** (in Finder: right-click the folder → *New Terminal at Folder*).
3. **Start the menu:**
   ```bash
   ./lan.py
   ```
   Pick a game number (or `a` for all games), then `1` to install.

The games are copied into the **Applications folder in your home folder** (`~/Applications`), so no admin password
is needed. Launchpad and Spotlight find them there. On Apple Silicon Macs, AssaultCube and Blobby Volley may ask
to install **Rosetta** on first start: confirm it.

When you host a game and macOS asks whether it may accept incoming network connections, click **Allow**.

## Using `lan.py`

The menu (`./lan.py` or `py lan.py`) is all you need. For the terminal there are also commands
(on Windows write `py lan.py` instead of `./lan.py`):

```bash
./lan.py                          # menu
./lan.py list                     # all games and whether they are installed
./lan.py install supertuxkart     # install one game
./lan.py install all              # install all games
./lan.py uninstall supertuxkart   # remove one game
./lan.py uninstall all            # remove all games
```

Game ids: `doom`, `blobby_volley`, `0ad`, `supertuxkart`, `assaultcube`.

Running the install again is safe, e.g. to repair a game.

**Uninstall removes everything**: the game, **its settings, player names and saves**, desktop shortcuts and firewall
rules. It asks before it does that.

## Playing together

**All players need the same version of a game**, otherwise they can't play together. `lan.py` installs the right
version for you.

| Game | Version | How to play together |
|---|---|---|
| Doom (Odamex + Freedoom) | Odamex 12.3.0 | Join the LAN server in **Odalaunch** |
| Blobby Volley 2 | 1.1.1 | One player hosts, the others join |
| 0 A.D. | 0.28.0 | One player hosts, the others join via IP |
| SuperTuxKart | 1.5 | **Online → Local network** |
| AssaultCube | 1.3.0.2 | **Multiplayer → Join a LAN server** |

### Doom (Odamex + Freedoom)
Start **Odalaunch** (Windows: the **Odamex LAN** desktop shortcut) and double-click the LAN server.
- `freedm.wad`: arena maps for deathmatch
- `freedoom2.wad`: campaign maps with monsters for co-op

Linux has three start menu entries: **Odamex** (single player), **Odalaunch** (server list, use this one) and
**Odasrv** (game server, ignore it). macOS has **Odamex** and **odalaunch** in Applications. Set your player name in
Odamex under **Options → Player Setup**. More details in [doom/ODAMEX.md](../doom/ODAMEX.md).

### Blobby Volley 2
One player hosts a network game, the others join it. The host needs port 1234/udp open (`lan.py` does that).

### 0 A.D.
There is no server list.
1. The host chooses **Multiplayer → Host Game**.
2. The others choose **Multiplayer → Join Game** and enter the host's **IP address** and port **20595**.
3. Wait in the lobby until the host starts the game.

On Windows, `lan.py` turns off **GPU skinning**, because on older Intel graphics it makes moving units warp. Units
then look right everywhere. With a good graphics card you can turn it back on under **Options → Graphics**.

### SuperTuxKart
The host uses **Online → Local network → Create server**. The others join through **Online → Local network**.
If the server doesn't show up, see [troubleshooting](troubleshooting.md#supertuxkart-no-server-found).

Keyboard controls:

| Action | Key |
|---|---|
| Accelerate | ↑ |
| Brake / reverse | ↓ |
| Steer | ← / → |
| Use item | Space |
| Nitro | N |
| Skid / drift | V |
| Look back | B |
| Rescue (back onto the track) | Backspace (Mac: **delete**) |
| Pause / menu | Esc |

In menus: arrow keys to move, Enter to select, Esc to go back. Change the keys under **Options → Controls**.
Gamepads work too and show up there.

### AssaultCube
**Multiplayer → Join a LAN server**. Or open the console and type `/connect <SERVER-IP> 28763`.
