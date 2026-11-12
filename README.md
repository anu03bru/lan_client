# OpenSource Doom
These are the client file for doom using opendoom(game files) and odamex client(engine)

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