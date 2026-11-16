# LAN party games

One terminal app, `lan.py`, installs and uninstalls all games on **Linux (CachyOS)** and **Windows**.
The games and their download links, ports and folders are listed in [`games.toml`](games.toml).

| Game | id | Ports (only for the host) |
|---|---|---|
| Doom (Odamex + Freedoom) | `doom` | – (dedicated server) |
| Blobby Volley 2 | `blobby_volley` | 1234/udp |
| 0 A.D. | `0ad` | 20595/udp |
| SuperTuxKart | `supertuxkart` | 2757/udp, 2759/udp |
| AssaultCube | `assaultcube` | – (dedicated server) |

## Requirements

- **Python 3.11 or newer**
  - Linux (CachyOS): already installed.
  - Windows: `winget install Python.Python.3.12`, or the installer from python.org.
- **Linux:** `flatpak` (`sudo pacman -S flatpak`).

## Usage

Linux:
```bash
./lan.py                          # menu: pick a game number, then 1 = install, 2 = uninstall, 3 = back
./lan.py list                     # all games and whether they are installed
./lan.py install supertuxkart     # one game
./lan.py install all              # all games
./lan.py uninstall supertuxkart
./lan.py uninstall all --yes      # without the confirmation question
```

Windows: the same commands with `py lan.py`, e.g. `py lan.py install supertuxkart`.

- **Linux:** do **not** use `sudo`. The app asks for your password itself when it opens or closes firewall ports (ufw).
- **Windows:** install and uninstall show one admin prompt. That is needed for the installers and the firewall rules.
  If the prompt is confirmed with a **different** Windows account, that account's user folders are used instead of yours.

### What install does
- Linux: installs the game as a user Flatpak, checks the version where all players need the same one, and opens the
  ports with ufw (only when ufw is active).
- Windows: downloads the installer or ZIP, checks its SHA-256, installs it, creates desktop shortcuts for the ZIP games,
  and adds a Windows Defender Firewall rule for the ports.

### What uninstall does
Removes everything the install set up: the game, **its user data (settings, player names, saves)**, desktop shortcuts,
Flatpak permissions and the firewall rules. `uninstall all` also removes Flatpak runtimes no app needs anymore.
Running it twice is safe. It also removes games installed with the old per-game scripts.

### Adding or changing a game
Edit `games.toml`. The comment at the top explains every field. Then run the tests:
```bash
python3 -m unittest
```

Not covered by `lan.py`: the macOS AssaultCube install (`assaultcube/mac_install_assaultcube.sh`) and the AssaultCube
server (`assaultcube-server/`).

# Doom (Odamex + Freedoom)
Odamex is the game engine. Freedoom provides the game files (maps, graphics, sounds). See [doom/ODAMEX.md](doom/ODAMEX.md)
for details.

- `freedm.wad`: arena maps without monsters, for deathmatch
- `freedoom2.wad`: campaign maps with monsters, for co-op

After the install there are 3 new start menu entries (Linux):
- **Odamex**: single player
- **Odalaunch**: multiplayer server list. **Use this at the LAN party.**
- **Odasrv**: game server. Ignore it, the server runs on a separate machine.

On Windows use the **Odamex LAN** desktop shortcut (Odalaunch).

From the terminal (Linux):
```bash
flatpak run net.odamex.Odamex                       # Odamex (game)
flatpak run --command=odalaunch net.odamex.Odamex   # Odalaunch (server list)
```

# 0 A.D.
0 A.D. has no server list. One player hosts, and the others join via the host's IP address.

### Join
1. In the game: **Multiplayer → Join Game**
2. Enter the host's **IP address** and port **20595**
3. Wait in the lobby until the host starts the game.

### Troubleshooting

| Problem | Solution |
|---|---|
| Cannot connect to the host | Check the host's firewall: port 20595/udp must be open (Linux: `sudo ufw status`) |
| Connection fails right away | All players need the same version (**0.28.0**) |
| Windows host not reachable | Set the network profile to **Private** (Settings → Network → your network) |

# SuperTuxKart
The host uses **Online → Local network → Create server**. The others join through **Online → Local network**.

**Server doesn't show up in the list?** Connect directly by IP:
1. Find the host's IP address (Linux: `ip -4 addr`, Windows: `ipconfig`).
2. In SuperTuxKart, go to **Online → Enter server address**.
3. Enter **`<SERVER-IP>:2759`**, e.g. `192.168.1.42:2759`.

The list stays empty most often when a Linux machine with an active firewall searches for a server. The direct
connection still works, as long as the host has UDP 2759 open.

# AssaultCube
Multiplayer: **Multiplayer → Join a LAN server**.
