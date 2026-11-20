# Installing from the LAN share

At the LAN party the internet connection is slow, so the game files are on a fileserver in the LAN.
`games-lan.toml` lists the same games as `games.toml`, but takes every file from that share.

> Temporary: this page, `games-lan.toml` and `scripts/fill_share.py` are deleted after the party.

## For players

1. **Open the share**. Use the address the organizer gives you instead of `FILESERVER/lanparty`:
   - **Windows**: type `\\FILESERVER\lanparty` into the address bar of the File Explorer. If it asks for a login,
     ask the organizer.
   - **macOS**: Finder → Go → Connect to Server → `smb://FILESERVER/lanparty`. It appears under `/Volumes/lanparty`.
   - **Linux**: open `smb://FILESERVER/lanparty` in the file manager (Dolphin, Nautilus, ...).
2. **Install**, the same as at home but with `--games games-lan.toml`:
   - Windows: `py lan.py --games games-lan.toml install all`
   - Linux and macOS: `./lan.py --games games-lan.toml install all`

   Without a command (`lan.py --games games-lan.toml`) you get the usual menu.

Every file is checked against its sha256 checksum, exactly as for internet downloads.

**Linux:** Blobby Volley, 0 A.D., SuperTuxKart and AssaultCube come from Flathub and still need the internet. Only
Doom comes from the share.

| Problem | What to do |
|---|---|
| `Download ...` fails with "Open the LAN share first" | The share is not open, or it is open under another path. Open it (step 1) and try again. If it still fails, tell the organizer the path shown in the error. |
| Linux: the share is open but the download still fails | The file manager mounts it under `/run/user/<your user id>/gvfs/...`. `games-lan.toml` assumes the user id 1000 (`id -u` shows yours). Tell the organizer. |

## For the organizer

1. **Fill the share** at home, where the internet is fast:
   `python3 scripts/fill_share.py <folder>`.
   It downloads every file from `games.toml` into `<folder>/<game id>/<file name>` and checks its sha256. You can run
   it again: files that are already there with the right checksum are skipped. Copy the contents of `<folder>` to
   the root of the share.
2. **Set the share address**: edit the `[share]` table at the top of `games-lan.toml`, one path per OS. Use `/` as
   separator, also for Windows (`//FILESERVER/lanparty` = `\\FILESERVER\lanparty`). To find the Linux path, open the
   share in the file manager and run `ls /run/user/$(id -u)/gvfs/`.
3. **Test it** on one PC per OS before the party: `lan.py --games games-lan.toml install doom`.

`games-lan.toml` must stay a copy of `games.toml` with only the URLs changed. If you change `games.toml`, change
`games-lan.toml` the same way. `python3 -m unittest` fails when the two differ.
