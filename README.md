# AI disclosure

This project was developed with the help of [Claude Code](https://claude.com/claude-code). All code was reviewed and tested by another instance of CLaude Code. Some Code was even reviewed by humans.

# Introduction
This project was made in preparation for a LAN Party that also provides Laptops and games to non gamers that want to try out computer games.

The Repository contains a python installer and meta information on several open source games. The games information is just entries in `games.toml` and the installer uses that information to get the game releases and install them. games can also be uninstalled via the installer.

# Included games

The `games.toml` file contains the meta information for each game. We tried to include a range of different genres.

- [Blobby Volley 2](https://blobbyvolley.de/): a sports game with blobs
- [0 A.D.](https://play0ad.com/): an open source real-time strategy game, similar to Age of Empires II
- [AssaultCube](https://assault.cubers.net/): a freeware shooter, similar to Counter-Strike
- Doom: the open source [Odamex](https://odamex.net/) engine, bundled with the open source assets from [Freedoom](https://freedoom.github.io/)
- [SuperTuxKart](https://supertuxkart.net/): an open source racing game, similar to Mario Kart

# Prerequisites
## Linux

- **x86_64 PC**: ARM isn't supported
- **Python 3.11 or newer**, available as `python3`
- **Flatpak**: preinstalled on CachyOS, Bazzite and SteamOS.
- **A user account with `sudo` rights**: run `lan.py` without `sudo`, because it asks for your password itself
- **Firewall, optional**: with ufw, rules are added automatically. With firewalld (Fedora, openSUSE, RHEL) you open the ports by hand, and only the player who hosts needs to.

## Windows

- **Windows 10 or 11, 64-bit**: the game downloads are x64 builds. Windows on ARM is untested.
- **Python 3.11 or newer**: python can be installed with winget.
- **Admin rights**: confirm the admin prompt with **your own** account, otherwise the games end up in the other account's folders
- **Windows Defender Firewall**: rules are added automatically. With a third-party firewall, you open the ports by hand, and only the player who hosts needs to.

# Installation
install instructions can be found here (link to the md file)

# At the LAN party
At the party the games are downloaded from the LAN fileserver instead of the internet. Open the fileserver share first, then run `lan.py --games games-lan.toml install all`. Details: [docs/lan-share.md](docs/lan-share.md).

# troubleshooting
here(link to file)

# frequently asked questions

Q: These games are not as good as their paid equivalents. Why play the free version if the real paid versions are so cheap?
A: first of not everyone has the money to pay for games. We have also found that most people don't even know that open source games are an option.
Q: Can I add more games to install with the downloader?
A: Yes. The python installer reads game information from the `games.toml` file. if you add the relevant information to the file it should install and track the new game as well.
Q: which operating system does this installer work on?
A: We have peronally tested the installer on linux(cachyos) and Windows 11. the installer should also work on other linux distributions. MacOS support is also planned but has not been tested yet.
Q: This looks sus, how do I know this won't install a crypto miner or some virus.
A: The installer as well as the linked games are open source. If you don't have the time to check everything yourself, we recommend you use a virtual machine or separate device to try out the installer.