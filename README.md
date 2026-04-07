# 0xPhantomPortal

Desktop app for managing **SSH tunnels** with auto-reconnect: **SOCKS5** (`-D`), **local port forward** (`-L`), and **remote port forward** (`-R`). Includes a built-in **SFTP tab** (upload/download/delete and drag-drop).

Built with **Python 3** and **PySide6 (Qt)**.

## Preview

![Port Forward UI](https://raw.githubusercontent.com/EgieSugina/0xPhantomPortal/refs/heads/main/img/1.png)
![SFTP UI](https://raw.githubusercontent.com/EgieSugina/0xPhantomPortal/refs/heads/main/img/2.png)

## Features

- Tabbed UI: **Port Forward** + **SFTP**
- Port Forward sub-tabs: SOCKS5, local forward, remote forward
- SFTP manager with drag-drop multi-file/folder upload
- SFTP upload workers (parallel upload, adjustable 1-10 workers)
- SFTP progress bar for upload/delete operations
- SFTP connection test button + configurable timeout
- Multiple saved SFTP accounts (select/save/delete)
- Optional password auth via **sshpass** (auto-reconnect)  
- Optional **keyring** integration when running from source (`pip install keyring`) — GNOME Keyring / Secret Service / etc.  
- Falls back to a simple obfuscated on-disk file if keyring is unavailable  
- Config: `~/.config/ssh_tunnel_manager/tunnels.json`  
- App icon from `icon.svg`

## Requirements

- **Python** 3.10+ recommended  
- **OpenSSH** client (`ssh` on `PATH`)  
- **`sshpass`** if you use saved passwords (e.g. `sudo pacman -S sshpass` / `apt install sshpass`)

## Run from source

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python ssh_tunnel_manager.py
```

## Build standalone binary (Linux)

```bash
chmod +x build.sh
./build.sh
```

Output: `dist/0xPhantomPortal` (single executable, PyInstaller + Qt). The script bundles `icon.svg` and `font/` (if present), uses `--strip` on Linux, and optionally runs UPX if installed.

On Windows, adjust `--add-data` in `build.sh` to use `icon.svg;.` instead of `icon.svg:.` if you build there.

## Project layout

| Path | Purpose |
|------|---------|
| `ssh_tunnel_manager.py` | Thin entry point (`stm.app.main`) |
| `stm/` | Multi-file application modules (UI, worker, SFTP, config) |
| `icon.svg` | Window / build icon |
| `img/bg.jpg` | Optional UI background image |
| `build.sh` | PyInstaller build |
| `requirements.txt` | Runtime dependencies |

## License

No license file is included; add one if you distribute the project.
