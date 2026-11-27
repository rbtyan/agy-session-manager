"""tmux backend controller for AGY Session Manager (-L agym)."""

from __future__ import annotations

import dataclasses
import os
import shlex
import subprocess
from pathlib import Path
from typing import Optional

TMUX_SOCKET = "agym"
TMUX_SESSION = "main"
MANAGER_WINDOW = "manager"


@dataclasses.dataclass
class TmuxSessionWindow:
    window_id: str
    window_name: str
    conv_id: str
    cwd: str
    title: str
    pane_dead: bool = False


def _run_tmux(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("TMUX", None)
    return subprocess.run(
        ["tmux", "-L", TMUX_SOCKET, *args],
        capture_output=True,
        text=True,
        env=env,
        check=check,
    )


def list_session_windows() -> list[TmuxSessionWindow]:
    """Return all active agy session windows (excluding the manager window)."""
    fmt = "#{window_id}\t#{window_name}\t#{@agy_conv_id}\t#{@agy_cwd}\t#{@agy_title}\t#{pane_dead}"
    res = _run_tmux("list-windows", "-t", TMUX_SESSION, "-F", fmt)
    if res.returncode != 0:
        return []

    windows: list[TmuxSessionWindow] = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        wid, wname, cid, cwd, title, dead = parts[:6]
        if wname == MANAGER_WINDOW:
            continue
        windows.append(
            TmuxSessionWindow(
                window_id=wid,
                window_name=wname,
                conv_id=cid.strip(),
                cwd=cwd.strip(),
                title=title.strip(),
                pane_dead=(dead.strip() == "1"),
            )
        )
    return windows


def select_window(window_id: str) -> bool:
    res = _run_tmux("select-window", "-t", window_id)
    return res.returncode == 0


def select_manager() -> bool:
    res = _run_tmux("select-window", "-t", f"{TMUX_SESSION}:{MANAGER_WINDOW}")
    return res.returncode == 0


def open_or_resume_session(
    conversation_id: str,
    cwd: str,
    title: str = "",
) -> bool:
    """Switch to existing tmux window for conversation_id, or spawn one."""
    for w in list_session_windows():
        if w.conv_id == conversation_id:
            return select_window(w.window_id)

    target_cwd = cwd if (cwd and Path(cwd).is_dir()) else str(Path.home())
    short_id = conversation_id[:8]
    wname = f"s-{short_id}"
    cmd = f"agy --conversation {shlex.quote(conversation_id)}"

    res = _run_tmux(
        "new-window",
        "-t",
        TMUX_SESSION,
        "-n",
        wname,
        "-c",
        target_cwd,
        "-P",
        "-F",
        "#{window_id}",
        cmd,
    )
    if res.returncode != 0:
        return False

    wid = res.stdout.strip()
    if wid:
        _run_tmux("set-option", "-w", "-t", wid, "@agy_conv_id", conversation_id)
        _run_tmux("set-option", "-w", "-t", wid, "@agy_cwd", target_cwd)
        if title:
            _run_tmux("set-option", "-w", "-t", wid, "@agy_title", title)
    return True


def spawn_new_session(cwd: str, extra_args: str = "") -> bool:
    """Spawn a brand-new agy session in a new tmux window."""
    target_cwd = cwd if (cwd and Path(cwd).is_dir()) else str(Path.home())
    # Generate unique placeholder name
    existing = {w.window_name for w in list_session_windows()}
    idx = 1
    while f"new-{idx}" in existing:
        idx += 1
    wname = f"new-{idx}"
    if extra_args.strip():
        try:
            tokens = shlex.split(extra_args)
            cmd = shlex.join(["agy", *tokens])
        except ValueError:
            cmd = f"agy {extra_args.strip()}"
    else:
        cmd = "agy"

    res = _run_tmux(
        "new-window",
        "-t",
        TMUX_SESSION,
        "-n",
        wname,
        "-c",
        target_cwd,
        "-P",
        "-F",
        "#{window_id}",
        cmd,
    )
    if res.returncode != 0:
        return False

    wid = res.stdout.strip()
    if wid:
        _run_tmux("set-option", "-w", "-t", wid, "@agy_conv_id", "")
        _run_tmux("set-option", "-w", "-t", wid, "@agy_cwd", target_cwd)
        _run_tmux("set-option", "-w", "-t", wid, "@agy_title", f"New Session ({Path(target_cwd).name})")
    return True


def kill_window(window_id: str) -> bool:
    res = _run_tmux("kill-window", "-t", window_id)
    return res.returncode == 0


def set_window_title(window_id: str, title: str) -> None:
    _run_tmux("set-option", "-w", "-t", window_id, "@agy_title", title)


def capture_pane(window_id: str, lines: int = 35) -> str:
    res = _run_tmux("capture-pane", "-p", "-t", window_id, "-S", f"-{lines}")
    if res.returncode != 0:
        return ""
    return res.stdout.rstrip()


def detach_client() -> None:
    _run_tmux("detach-client")


def kill_server() -> None:
    _run_tmux("kill-server")


def get_launch_cwd() -> str:
    res = _run_tmux("show-option", "-gv", "@agym_launch_cwd")
    val = res.stdout.strip()
    if val and Path(val).is_dir():
        return val
    return os.environ.get("AGYM_LAUNCH_CWD", os.getcwd())
