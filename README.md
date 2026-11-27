# AGY Session Manager (`agym`)

[English](README.md) | [繁體中文](README.zh-TW.md)

An interactive terminal Session Manager for **Google Antigravity CLI (`agy`)**, inspired by Claude Code's workflow. Monitor live session animations, switch instantly between background sessions, broadcast prompts, hand over context across sessions, view side-by-side splits, and search or batch-manage conversation history.

---

## Key Features

- **Instant Return to Manager**: Press **`←`** on an empty input line (or **`Alt+←`** / **`Ctrl+←`** anytime) inside any `agy` session window to jump back to the Session Manager while your session continues running in the background.
- **Live Status Animations & Permission Alerts**: Integrates read-only with `agy`'s `conversation_summaries.db`, `presence/*.lock`, and live tmux pane inspection:
  - `⚠` (flashing red/amber + `WAITING`): Waiting for user permission/confirmation (pinned to top; press **`w`** to jump through all waiting sessions)
  - `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏` (cyan spinner): `RUNNING`
  - `◐◓◑◒` (amber spinner): Background task / subagent running (`not_fully_idle`)
  - `●` (green): Active in background tmux window (press `Enter` to switch instantly)
  - `◉` (purple): Open in another terminal
  - `○` (dim): History (press `Enter` to `cd` into the original workspace and resume with `agy --conversation <id>`)
- **Cross-Session Collaboration (Message / Broadcast / Handover)**:
  - Press **`m`** to send a prompt to one or multiple selected sessions (delivered via safe bracketed paste to live tmux windows, or background `agy --print=...` for history sessions).
  - Press **`c`** to summarize a source session's recent conversation & artifacts in an editable modal and hand it over to another session (`Ctrl+S`).
- **Side-by-Side Split View (`v`)**: Multi-select 2 sessions and press **`v`** (or press **`v`** on a single session to pick a second one) to place them side-by-side in a single tmux window without restarting active sessions. Supports unsplitting back to standalone windows.
- **Fork / Subagent Tree View (`t`)**: Toggle parent-child tree hierarchy (`├─` / `└─`) with subagent labels.
- **Two-Pane Live Preview & Full-Text Search (`/`)**: Parses `transcript.jsonl` on the right pane (or captures live tmux output for unsaved/waiting panes) and searches titles, workspaces, and SQLite FTS5 full-text content.
- **Single & Batch Deletion (`d`)**: Multi-select with `Space` / `a` and confirm with a second `d` to cleanly remove DB rows, FTS index, `jetbox_summaries_proto.pb` entries, `conversations/`, `brain/`, `annotations/`, `presence/`, cache, and sidecar metadata.
- **Bilingual UI (English / Traditional Chinese)**: Automatically detects system locale (`LC_ALL` / `LC_MESSAGES` / `LANG`), supports `AGYM_LANG=en|zh`, and lets you toggle live inside the TUI with **`l`** (persisted in `~/.config/agy-session-manager/meta.json`).
- **Isolated & Non-Intrusive**: Uses a dedicated tmux socket (`-L agym`) with status bar hidden, so it never interferes with your own tmux sessions and survives SSH disconnects via detach.

---

## Requirements

- **Google Antigravity CLI (`agy`)** installed and in `$PATH`
- **tmux** (`>= 3.2` recommended)
- **Python 3.10+** (with `venv`)

---

## Quick Install

On any Linux / macOS machine:

```bash
git clone https://github.com/rbtyan/agy-session-manager.git ~/.local/share/agy-session-manager
~/.local/share/agy-session-manager/install.sh
```

`install.sh` automatically:
1. Checks `python3`, `tmux`, and `agy`
2. Creates an isolated `.venv` and installs `textual`
3. Symlinks `~/.local/bin/agym`

Ensure `~/.local/bin` is in your `$PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Update

```bash
cd ~/.local/share/agy-session-manager
git pull
./install.sh
agym kill   # Restart background server if running an older version
```

### Uninstall

```bash
agym kill
rm -f ~/.local/bin/agym
rm -rf ~/.local/share/agy-session-manager
# Optional: also remove custom aliases, pins, and language preference:
# rm -rf ~/.config/agy-session-manager
```

---

## Usage

### CLI Commands

| Command | Description |
| :--- | :--- |
| `agym` | Launch (or re-attach to) the interactive Session Manager TUI |
| `agym -l` / `--list` | List recent 25 sessions and states in plain text |
| `agym kill` | Stop the background `agym` tmux server and all managed windows |
| `agym -h` / `--help` | Show CLI help |

### Environment Variables

| Variable | Description |
| :--- | :--- |
| `AGYM_LANG=en\|zh` | Override auto-detected UI language (`en` or `zh`) |

### Keyboard Shortcuts

#### Inside an `agy` Session Window
| Shortcut | Action |
| :--- | :--- |
| **`←`** (empty input) | Return to Session Manager (passes through normally while typing) |
| **`Alt+←`** / **`Ctrl+←`** | Return to Session Manager immediately, anytime |

#### Inside Session Manager TUI
| Shortcut | Action |
| :--- | :--- |
| **`↑` / `↓`** | Navigate list and preview conversation on the right pane |
| **`Enter`** | Switch to an active background session, or `cd` & resume a history session |
| **`Space`** | Toggle multi-select on the highlighted session |
| **`a`** | Select all / clear selection |
| **`d`** / **`Delete`** | Delete highlighted (or multi-selected) session(s): press **`d`** again to confirm, `Esc` to cancel |
| **`m`** | Send a message or broadcast to highlighted / selected session(s) in a background worker |
| **`c`** | Cross-session context handover: auto-summarizes recent transcript & artifacts; edit and press `Ctrl+S` to send |
| **`w`** | Jump to the next session waiting for permission/confirmation (`⚠`) |
| **`v`** | Side-by-side split view: 2 selected sessions split directly; 1 session opens target picker (with unsplit option if already split) |
| **`t`** | Toggle Fork / Subagent tree view |
| **`n`** | Launch a new `agy` session (custom workspace & extra flags like `--mode plan`) |
| **`k`** | Close an active background tmux pane/window (preserves conversation history) |
| **`r`** | Rename session (synced to AGY `annotations/<id>.pbtxt` & `conversation_summaries.db`) |
| **`p`** | Pin / unpin session (`★`) |
| **`/`** | Open search bar (title, workspace, and FTS5 full-text); `Esc` to clear & close |
| **`Tab`** | Toggle `All Workspaces` / `Current Workspace` |
| **`l`** | Toggle UI language live between English and Traditional Chinese |
| **`q`** | Exit prompt: **`q`** to detach (keep running), **`k`** to stop all & exit, `Esc` to cancel |
| **`Esc`** | Cancel confirm bar → close search bar → clear multi-selection |

---

## Architecture & Data Safety

```text
agy-session-manager/
├── agym             # Launcher script (creates/attaches tmux -L agym)
├── tmux.conf        # Isolated tmux config (no status bar, mouse scroll, return bindings)
├── double_left.sh   # Empty-input Left key detection script
├── tui.py           # Textual two-pane TUI & animation scheduler
├── i18n.py          # English / Traditional Chinese localization & locale auto-detection
├── data.py          # Read-only SQLite / FTS5 / presence lock / transcript / tree & cleanup
├── tmux_ctrl.py     # tmux pane/window controller, split view & prompt detection
├── install.sh       # Cross-host one-click installer
└── requirements.txt # Python dependencies (textual)
```

- **Read-only browsing (`mode=ro`)** for `~/.gemini/antigravity-cli/conversation_summaries.db` to avoid lock contention.
- **Sidecar metadata** (aliases, pins, language preference) is stored separately in `~/.config/agy-session-manager/meta.json`.
- **Deletions** use WAL-safe short transactions (`busy_timeout = 5000`) and close managed tmux panes before removing files.

---

## License

MIT
