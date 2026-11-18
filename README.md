# Introduction
This project was made in preparation for a LAN Party that also provides Laptops and games to non gamers that want to try out computer games.

The Repository contains a python installer and meta information on several open source games. The games information is just entries in `games.toml` and the installer uses that information to get the game releases and install them. games can also be uninstalled via the installer.

# Included Games
The `games.toml` file contains meta information on several games. we have tried to include a range of different genres.

- Blobby volley, a sports game with slimes
- 0ad, open source RTS like age of empires 2
- cubeassault, Freeware Shooter game like counter strike
- doom, the open source Doom game engine bundled with the Freedoom open source asset library
- supertuxkart, an open source racing game like mario kart

# Installation
install instructions can be found here (link to the md file)

# troubleshooting
here(link to file)

# frequently asked questions

Q: These games are not as good as their paid equivalents. Why play the free version if the real paid versions are so cheap?
A: first of not everyone has the money to pay for games. We have also found that most people don't even know that open source games are an option.
Q: Can I add more games to install with the downloader?
A: Yes. The python installer reads game information from the `games.toml` file. if you add the relevant information to the file it should install and track the new game as well.
Q: which operating system does this installer work on?
A: We have peronally tested the installer on linux(cachyos) and Windows 11. the installer should also work on other linux distributions. MacOS support is also planned but has not been tested yet.