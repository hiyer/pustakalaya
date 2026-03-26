# Pustakalaya

A self-hosted personal book library for Linux. Manage your collection via a terminal UI and browse/download via a local web interface.

Supports EPUB, PDF, CBZ, and CBR formats.

## Features

- **TUI** — Scan library directories, edit metadata, open books with your default viewer
- **Web server** — Browse and download books from a browser; runs as a systemd user service
- Automatic file watching (while TUI is open) + manual full scan
- Cover extraction from book files
- PAM-based HTTP Basic Auth (uses your Linux login credentials)

## Requirements

- Python 3.11+
- Linux (PAM auth is Linux-specific)
- `unrar` system package for CBR support:
  ```
  sudo apt install unrar
  ```
- User must be in the `shadow` group for PAM auth to work:
  ```
  sudo usermod -aG shadow $USER
  ```
  Log out and back in after running this.

## Installation

```bash
pip install .
```

For development (includes test dependencies):

```bash
pip install -e '.[dev]'
```

## Usage

### TUI

```bash
pustakalaya
```

Opens the terminal UI. Add library root directories on the **Library Roots** tab; books are scanned automatically. The **All Books** tab shows your collection with search.

**Key bindings:**

| Key | Action |
|-----|--------|
| `o` | Open book with `xdg-open` |
| `e` | Edit metadata |
| `s` | Full scan of all library roots |
| `/` | Focus search bar |
| `1`/`2`/`3` | Switch between panes |
| `q` | Quit |

### Web server

```bash
pustakalaya-web [--host HOST] [--port PORT]
```

Default: `http://127.0.0.1:7788`

Log in with your Linux username and password. The web interface is read-only — use the TUI to manage the library.

## Running as a systemd service

```bash
cp pustakalaya-web.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pustakalaya-web
```

## Data

All data is stored under `~/.local/share/pustakalaya/`:

- `library.db` — SQLite database (shared between TUI and web server via WAL mode)
- `covers/` — Extracted cover images

## Testing

```bash
pytest
```

## Notes

- The file watcher only runs while the TUI is open. If you add files without the TUI running, open the TUI and press `s` to rescan.
- TLS is not handled by the web server — use a reverse proxy (nginx, Caddy) if you need HTTPS. This does not provide any security whatsoever, so please ensure however you expose the service (ngrok, tailscale, etc) provides its own security.
- In-browser reading is not supported; books are download-only via the web interface.
