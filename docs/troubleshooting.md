# Troubleshooting

**When a step fails**, read the `ERROR` and `Hint` lines in the output. They say which step failed and what to try.
Running the install again is safe.

**Find an IP address:** Linux `ip -4 addr`, Windows `ipconfig`, macOS **System Settings → Network**.

## `lan.py` problems

| Problem | Solution |
|---|---|
| `Python 3.11 or newer is needed` | Windows: `winget install Python.Python.3.12`. macOS: installer from [python.org](https://www.python.org/downloads/macos/). Linux: update Python with your package manager. |
| macOS: download fails with `CERTIFICATE_VERIFY_FAILED` | Open **Applications → Python 3.x** and double-click **Install Certificates.command**. |
| `Do not run this with sudo or as root` | Run `./lan.py` without `sudo`. |
| `Check flatpak` fails (Linux) | Install Flatpak: `sudo pacman -S flatpak`. |
| `Download ...` fails with "Open the LAN share first" | Only at the LAN party: open the fileserver share, see [lan-share.md](lan-share.md). |
| Windows: games installed in the wrong user folder | The admin prompt was confirmed with a different account. Uninstall, then install again and confirm with your own account. |
| macOS: "app can't be opened" | Right-click the app in **~/Applications** and choose **Open**. If that isn't offered: **System Settings → Privacy & Security** → **Open Anyway**. |
| Windows: 0 A.D. doesn't start, a DLL like `VCRUNTIME140.dll` or `MSVCP140.dll` is missing | Run `lan.py install 0ad` again: it installs the Microsoft Visual C++ Redistributable first. Or install it by hand: [vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe). |
| macOS: a step says `... not found in the download` | The app name in `games.toml` is wrong. The message lists the right name; tell the organizer. |

## Can't connect to a game

| Problem | Solution |
|---|---|
| Connection fails right away | Everyone needs the **same version**, see the [game table](installation.md#playing-together). |
| Others can't reach your game (you host) | Your firewall must allow the game's port. `lan.py install` opens it. Linux: check with `sudo ufw status`. |
| Windows PC not reachable | Set the network profile to **Private**: Settings → Network & Internet → your network. |
| macOS game can't find or join a server | **System Settings → Privacy & Security → Local Network** → enable the game. AssaultCube: see [below](#assaultcube-could-not-connect-to-server-macos). |

Ports, only needed by the player who hosts: Blobby Volley 1234/udp, 0 A.D. 20595/udp,
SuperTuxKart 2757/udp and 2759/udp, AssaultCube 28763/udp, 28764/udp and 28762/udp. Doom uses a separate server machine.
On Linux, SuperTuxKart also needs a rule for **every** player, so the server list works: `lan.py install` adds it.

## SuperTuxKart: no server found

On Linux, `lan.py install` allows the host's answer to the server search through the firewall (UDP from port 2757,
LAN addresses only). If you installed SuperTuxKart before that, run `./lan.py install supertuxkart` again.
If the list still stays empty, connect **once directly by IP**:
1. Ask the host for their IP address.
2. In SuperTuxKart go to **Online → Enter server address**.
3. Enter **`<SERVER-IP>:2759`**, e.g. `192.168.1.42:2759`.

## AssaultCube: "could not connect to server" (macOS)

On the Mac, AssaultCube gets stuck at `attempting to connect` and then says `could not connect to server`, even when
it's enabled under **Local Network**. macOS blocks the game's network access when it's started from Finder.
Start it from **Terminal** instead:
```bash
~/Applications/AssaultCube.app/Contents/MacOS/launcher
```
Then join as usual, or in the console: `/connect <SERVER-IP> 28763`.

If the server answers `server requires a valid game account to connect`, unlock your game account: type
`/checkaccount` in the console and enter its password. If you don't have an account yet, the same command offers
to create one. It is stored only on your computer, no sign-up needed.

## Doom: server not listed in Odalaunch

Add it manually in Odalaunch: **`<SERVER-IP>:10666`**.

## Doom: Game Select is empty (Linux)

Run this and restart Odamex:
```bash
flatpak override --user --env=DOOMWADDIR="$HOME/OdamexLAN/wads" net.odamex.Odamex
```
