# LAN party games

# introduction

This repository contains an installer for all the open source games used for the lan party. The installer was tested on windows and CachyOS. 
Other operating systems might work as well. The installer(lan.py)installs (and later removes) all games for you. Relevant gamedata is listed in `games.toml`.

## The games

| Game | Version | How to play together |
|---|---|---|
| Doom (Odamex + Freedoom) | Odamex 12.3.0 | Join the LAN server in **Odalaunch** |
| Blobby Volley 2 | 1.1.1 | One player hosts, the others join |
| 0 A.D. | **0.28.0** | One player hosts, the others join via IP |
| SuperTuxKart | **1.5** | **Online → Local network** |
| AssaultCube | 1.3.0.2 | **Multiplayer → Join a LAN server** |

**All players need the same version of a game**, otherwise they can't play together. `lan.py` installs the right
version for you. On macOS, pick exactly the version from this table.

## Download this repository

- With git: `git clone https://github.com/anu03bru/lan_client.git`
- Without git: on the GitHub page click **Code → Download ZIP** and unpack it.

All commands below are run inside that folder.

---

## Install on Windows

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

After the install the games are in the start menu. Doom and Blobby Volley get a shortcut on the desktop instead
(**Odamex LAN** and **Blobby Volley 2**).

## Install on Linux

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

## Install on macOS

`lan.py` does not run on macOS.

**AssaultCube** has an install script:
```bash
sh assaultcube/mac_install_assaultcube.sh
```
It downloads AssaultCube into `/Applications`. Then start it from Applications.

**All other games:** download them from the official websites, using the version from the [game table](#the-games):

| Game | Download |
|---|---|
| Doom | Odamex from [odamex.net](https://odamex.net/) and the Freedoom WADs from [freedoom.github.io](https://freedoom.github.io/). See [doom/ODAMEX.md](doom/ODAMEX.md) for which WAD is used for what. |
| Blobby Volley 2 | [blobbyvolley.de](https://blobbyvolley.de/) |
| 0 A.D. | [play0ad.com](https://play0ad.com/download/) |
| SuperTuxKart | [supertuxkart.net](https://supertuxkart.net/Download) |

On first start, macOS may block the app: right-click it in Applications and choose **Open**.
When a game can't find or join a server, allow it in **System Settings → Privacy & Security → Local Network**.

---

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

---

## Playing

### Doom (Odamex + Freedoom)
Start **Odalaunch** (Windows: the **Odamex LAN** desktop shortcut) and double-click the LAN server.
- `freedm.wad`: arena maps for deathmatch
- `freedoom2.wad`: campaign maps with monsters for co-op

Linux has three start menu entries: **Odamex** (single player), **Odalaunch** (server list, use this one) and
**Odasrv** (game server, ignore it). Set your player name in Odamex under **Options → Player Setup**.
More details in [doom/ODAMEX.md](doom/ODAMEX.md).

### Blobby Volley 2
One player hosts a network game, the others join it. The host needs port 1234/udp open (`lan.py` does that).

### 0 A.D.
There is no server list.
1. The host chooses **Multiplayer → Host Game**.
2. The others choose **Multiplayer → Join Game** and enter the host's **IP address** and port **20595**.
3. Wait in the lobby until the host starts the game.

### SuperTuxKart
The host uses **Online → Local network → Create server**. The others join through **Online → Local network**.
If the server doesn't show up, see [Troubleshooting](#troubleshooting-and-workarounds).

### AssaultCube
**Multiplayer → Join a LAN server**. Or open the console and type `/connect <SERVER-IP> 28763`.

---

## Troubleshooting and workarounds

**Find an IP address:** Linux `ip -4 addr`, Windows `ipconfig`, macOS **System Settings → Network**.

### SuperTuxKart: no server found
The server list often stays empty, especially on Linux with an active firewall. Connect **once directly by IP**:
1. Ask the host for their IP address.
2. In SuperTuxKart go to **Online → Enter server address**.
3. Enter **`<SERVER-IP>:2759`**, e.g. `192.168.1.42:2759`.

### Doom: server not listed in Odalaunch
Add it manually in Odalaunch: **`<SERVER-IP>:10666`**.

### Doom: Game Select is empty (Linux)
Run this and restart Odamex:
```bash
flatpak override --user --env=DOOMWADDIR="$HOME/OdamexLAN/wads" net.odamex.Odamex
```

### Can't connect to a game
| Problem | Solution |
|---|---|
| Connection fails right away | Everyone needs the **same version**, see the [game table](#the-games). |
| Others can't reach your game (you host) | Your firewall must allow the game's port. `lan.py install` opens it. Linux: check with `sudo ufw status`. |
| Windows PC not reachable | Set the network profile to **Private**: Settings → Network & Internet → your network. |
| macOS game can't find or join a server | **System Settings → Privacy & Security → Local Network** → enable the game. |

Ports, only needed by the player who hosts: Blobby Volley 1234/udp, 0 A.D. 20595/udp,
SuperTuxKart 2757/udp and 2759/udp. Doom and AssaultCube use a separate server machine.

### `lan.py` problems
| Problem | Solution |
|---|---|
| `Python 3.11 or newer is needed` | Windows: `winget install Python.Python.3.12`. Linux: update Python with your package manager. |
| `Do not run this with sudo or as root` | Run `./lan.py` without `sudo`. |
| `Check flatpak` fails (Linux) | Install Flatpak: `sudo pacman -S flatpak`. |
| A step fails | Read the `ERROR` and `Hint` lines. They say which step failed and what to try. Running the install again is safe. |
| Windows: games installed in the wrong user folder | The admin prompt was confirmed with a different account. Uninstall, then install again and confirm with your own account. |
| macOS: "app can't be opened" | Right-click the app in Applications and choose **Open**. |

---

## For organizers

- The games, versions, download links and ports are in [`games.toml`](games.toml). The comment at the top explains
  every field. After changes run the tests: `python3 -m unittest`
- The AssaultCube dedicated server setup is in [`assaultcube-server/`](assaultcube-server/).
