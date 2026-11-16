# OpenSource Doom
These are the client file for doom using opendoom(game files) and odamex client(engine)

### Linux (ChachyOS)
on linux(cachyos) just install the flatpak which will add odamex as well as the odamex launcher

after the install script runs. 3 entries will be added to start:
Odamex = singleplayer
Odalaunch =  multyplayer server list
Odasrv game server ignore this

you can also launch via console
# Odamex (game)
```bash
flatpak run net.odamex.Odamex
```
Odalaunch (launcher)
```bash
flatpak run --command=odalaunch net.odamex.Odamex
```


freedm= maps for multyplayer, no monsters
freedoom= singleplayer maps for coop

TODO: verify windows version of the script

### Windows
On Windows just run the "install_doom.ps1" script.

Command:
````bash
$ cd doom
$ .\install_doom.ps1
````

It will create a shortcut on your desktop environment. You can start the game from there.

# Blobby Volley
### Linux (ChachyOS)
on linux(cachyos)
TODO

### Windows
On Windows just run the "install_blobby.ps1" script.

Command:
````bash
$ cd blobby_volley
$ .\install_blobby.ps1
````

It will create a shortcut on your desktop environment. You can start the game from there.

# Assault Cube
### Linux (ChachyOS)
on linux ...

### Windows
On Windows just run the "install_assault_cube.ps1" script.

Command:
````bash
$ cd assaultcube
$ .\install_assault_cube.ps1
````

It will create a shortcut on your desktop environment. You can start the game from there.

# SuperTuxKart
### Linux (CachyOS)
```bash
cd supertuxkart
./install_supertuxkart.sh
```
Do **not** run it with `sudo`. It asks for your password when it opens the firewall ports (UDP 2757 and 2759).

### Windows
```powershell
cd supertuxkart
powershell -ExecutionPolicy Bypass -File install_supertuxkart.ps1
```
Confirm the admin prompt, so the script can open the firewall ports.

### Multiplayer
The host uses **Online → Local network → Create server**. The others join through **Online → Local network**.

**Server doesn't show up in the list?** Connect directly by IP:
1. Find the host's IP address (Linux: `ip -4 addr`, Windows: `ipconfig`).
2. In SuperTuxKart, go to **Online → Enter server address**.
3. Enter **`<SERVER-IP>:2759`**, e.g. `192.168.1.42:2759`.

The list stays empty most often when a Linux machine with an active firewall searches for a server. The direct connection still works, as long as the host has UDP 2759 open.

# Uninstall
Removes everything the install scripts set up: the games, **their user data (settings, player names, saves)**, desktop shortcuts, Flatpak permissions and the firewall rules they opened. Running it twice is safe.

### Linux
Remove all games, then the Flatpak runtimes no app needs anymore:
```bash
./uninstall_all.sh
```
Remove a single game:
```bash
bash supertuxkart/install_supertuxkart.sh --uninstall
```
Do **not** run it with `sudo`. It asks for your password itself when it removes firewall rules.

### Windows
Remove all games (one admin prompt):
```powershell
powershell -ExecutionPolicy Bypass -File uninstall_all.ps1
```
Remove a single game:
```powershell
powershell -ExecutionPolicy Bypass -File supertuxkart\install_supertuxkart.ps1 -Uninstall
```
If the admin prompt is confirmed with a **different** Windows account, that account's user folders are cleaned instead of yours.

The macOS AssaultCube install and the AssaultCube server are not covered.
