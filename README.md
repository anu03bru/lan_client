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
