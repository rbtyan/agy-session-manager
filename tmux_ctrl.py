"""tmux backend controller for AGY Session Manager (-L agym)."""

from __future__ import annotations

import dataclasses
import os
import re
import shlex
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

TMUX_SOCKET = "agym"
TMUX_SESSION = "main"
MANAGER_WINDOW = "manager"

WAITING_PROMPT_RE = re.compile(
    r"(?:"
    r"allow\s+once|always\s+allow|allow\s+for\s+this|allow\s+all|yes,\s*allow"
    r"|approve\s+this|requires\s+approval|permission\s+(?:required|request|prompt)"
    r"|do\s+you\s+want\s+to\s+(?:proceed|allow|run|continue|approve)"
    r"|enter\s+to\s+confirm|esc\s+to\s+(?:cancel|deny|reject)"
    r"|\[[yY]/[nN]\]\s*$|\([yY]/[nN]\)\s*$"
    r")",
    re.IGNORECASE,
)


@dataclasses.dataclass
class TmuxSessionWindow:
    window_id: str
    window_name: str
    conv_id: str
    cwd: str
    title: str
    pane_dead: bool = False
    waiting_for_user: bool = False
    pane_id: str = ""
    window_panes: int = 1


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
    """Return all active agy session panes/windows (excluding the manager window)."""
    fmt = "#{window_id}\t#{window_name}\t#{pane_id}\t#{window_panes}\t#{@agy_conv_id}\t#{@agy_cwd}\t#{@agy_title}\t#{pane_dead}"
    res = _run_tmux("list-panes", "-s", "-t", TMUX_SESSION, "-F", fmt)
    if res.returncode != 0:
        return []

    windows: list[TmuxSessionWindow] = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        wid, wname, pid, wpanes, cid, cwd, title, dead = parts[:8]
        if wname == MANAGER_WINDOW:
            continue
        try:
            pane_count = int(wpanes.strip() or "1")
        except ValueError:
            pane_count = 1
        windows.append(
            TmuxSessionWindow(
                window_id=wid,
                window_name=wname,
                conv_id=cid.strip(),
                cwd=cwd.strip(),
                title=title.strip(),
                pane_dead=(dead.strip() == "1"),
                pane_id=pid.strip(),
                window_panes=pane_count,
            )
        )
    return windows


def select_window(window_id: str, pane_id: str = "") -> bool:
    res = _run_tmux("select-window", "-t", window_id)
    if res.returncode != 0:
        return False
    if pane_id:
        _run_tmux("select-pane", "-t", pane_id)
    return True


def select_manager() -> bool:
    res = _run_tmux("select-window", "-t", f"{TMUX_SESSION}:{MANAGER_WINDOW}")
    return res.returncode == 0


def _spawn_conversation_window(
    conversation_id: str,
    cwd: str,
    title: str = "",
    detached: bool = False,
) -> Optional[tuple[str, str]]:
    """Spawn a new tmux window running `agy --conversation <id>` and tag its pane."""
    target_cwd = cwd if (cwd and Path(cwd).is_dir()) else str(Path.home())
    short_id = conversation_id[:8]
    wname = f"s-{short_id}"
    cmd = f"agy --conversation {shlex.quote(conversation_id)}"

    args = ["new-window"]
    if detached:
        args.append("-d")
    args.extend([
        "-t",
        TMUX_SESSION,
        "-n",
        wname,
        "-c",
        target_cwd,
        "-P",
        "-F",
        "#{window_id}\t#{pane_id}",
        cmd,
    ])
    res = _run_tmux(*args)
    if res.returncode != 0:
        return None

    out = res.stdout.strip().split("\t")
    wid = out[0] if out else ""
    pid = out[1] if len(out) > 1 else ""
    if wid:
        _run_tmux("set-option", "-w", "-t", wid, "@agy_conv_id", conversation_id)
        _run_tmux("set-option", "-w", "-t", wid, "@agy_cwd", target_cwd)
        if title:
            _run_tmux("set-option", "-w", "-t", wid, "@agy_title", title)
    if pid:
        _run_tmux("set-option", "-p", "-t", pid, "@agy_conv_id", conversation_id)
        _run_tmux("set-option", "-p", "-t", pid, "@agy_cwd", target_cwd)
        if title:
            _run_tmux("set-option", "-p", "-t", pid, "@agy_title", title)
    return (wid, pid) if wid else None


def open_or_resume_session(
    conversation_id: str,
    cwd: str,
    title: str = "",
) -> bool:
    """Switch to existing tmux window/pane for conversation_id, or spawn one."""
    for w in list_session_windows():
        if w.conv_id == conversation_id:
            return select_window(w.window_id, w.pane_id)

    return _spawn_conversation_window(conversation_id, cwd, title, detached=False) is not None


def open_split_view(
    sess_a: tuple[str, str, str],
    sess_b: tuple[str, str, str],
) -> bool:
    """Place two sessions side-by-side in a single tmux window (left & right panes).

    Each argument is (conversation_id, cwd, title). Reuses existing tmux panes if open.
    """
    cid_a, cwd_a, title_a = sess_a
    cid_b, cwd_b, title_b = sess_b
    if not cid_a or not cid_b or cid_a == cid_b:
        return False

    existing = {w.conv_id: w for w in list_session_windows() if w.conv_id}

    def _ensure(cid: str, cwd: str, title: str) -> Optional[tuple[str, str]]:
        w = existing.get(cid)
        if w and w.window_id:
            if w.pane_id:
                _run_tmux("set-option", "-p", "-t", w.pane_id, "@agy_conv_id", cid)
                _run_tmux("set-option", "-p", "-t", w.pane_id, "@agy_cwd", w.cwd or cwd)
                if title or w.title:
                    _run_tmux("set-option", "-p", "-t", w.pane_id, "@agy_title", title or w.title)
            return (w.window_id, w.pane_id or w.window_id)
        return _spawn_conversation_window(cid, cwd, title, detached=True)

    a = _ensure(cid_a, cwd_a, title_a)
    if a is None:
        return False
    b = _ensure(cid_b, cwd_b, title_b)
    if b is None:
        return False

    win_a, pane_a = a
    win_b, pane_b = b
    if win_a == win_b:
        _run_tmux("select-layout", "-t", win_a, "even-horizontal")
        return select_window(win_a, pane_a)

    join_res = _run_tmux("join-pane", "-h", "-s", pane_b, "-t", pane_a)
    if join_res.returncode != 0:
        return False
    _run_tmux("select-layout", "-t", win_a, "even-horizontal")
    _run_tmux("rename-window", "-t", win_a, "split")
    return select_window(win_a, pane_a)


def unsplit_pane(pane_id: str) -> bool:
    """Break a pane out of a split window into its own detached window."""
    if not pane_id:
        return False
    res = _run_tmux("break-pane", "-d", "-s", pane_id)
    return res.returncode == 0


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
        "#{window_id}\t#{pane_id}",
        cmd,
    )
    if res.returncode != 0:
        return False

    out = res.stdout.strip().split("\t")
    wid = out[0] if out else ""
    pid = out[1] if len(out) > 1 else ""
    new_title = f"New Session ({Path(target_cwd).name})"
    if wid:
        _run_tmux("set-option", "-w", "-t", wid, "@agy_conv_id", "")
        _run_tmux("set-option", "-w", "-t", wid, "@agy_cwd", target_cwd)
        _run_tmux("set-option", "-w", "-t", wid, "@agy_title", new_title)
    if pid:
        _run_tmux("set-option", "-p", "-t", pid, "@agy_conv_id", "")
        _run_tmux("set-option", "-p", "-t", pid, "@agy_cwd", target_cwd)
        _run_tmux("set-option", "-p", "-t", pid, "@agy_title", new_title)
    return True


def kill_window(window_id: str, pane_id: str = "") -> bool:
    if pane_id:
        res = _run_tmux("kill-pane", "-t", pane_id)
        if res.returncode == 0:
            return True
    res = _run_tmux("kill-window", "-t", window_id)
    return res.returncode == 0


def set_window_title(window_id: str, title: str, pane_id: str = "") -> None:
    _run_tmux("set-option", "-w", "-t", window_id, "@agy_title", title)
    if pane_id:
        _run_tmux("set-option", "-p", "-t", pane_id, "@agy_title", title)


def send_text_to_window(window_id: str, text: str, submit: bool = True) -> bool:
    """Deliver text into a live agy tmux window safely using bracketed paste."""
    if not text or not text.strip():
        return False
    # Exit tmux copy-mode if the target pane is currently scrolled back
    _run_tmux("send-keys", "-t", window_id, "-X", "cancel")

    buf_name = f"agym_msg_{uuid.uuid4().hex[:8]}"
    env = os.environ.copy()
    env.pop("TMUX", None)
    try:
        load_res = subprocess.run(
            ["tmux", "-L", TMUX_SOCKET, "load-buffer", "-b", buf_name, "-"],
            input=text,
            capture_output=True,
            text=True,
            env=env,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if load_res.returncode != 0:
        return False

    paste_res = _run_tmux("paste-buffer", "-p", "-r", "-d", "-b", buf_name, "-t", window_id)
    if paste_res.returncode != 0:
        _run_tmux("delete-buffer", "-b", buf_name)
        return False

    if submit:
        # Small pause lets the target TUI process bracketed paste before Enter
        time.sleep(0.15 if (len(text) > 200 or "\n" in text) else 0.08)
        enter_res = _run_tmux("send-keys", "-t", window_id, "Enter")
        return enter_res.returncode == 0
    return True


def send_background_prompt(conversation_id: str, cwd: str, text: str) -> bool:
    """Run a single non-interactive turn on a history session in the background."""
    if not conversation_id or not text or not text.strip():
        return False
    target_cwd = cwd if (cwd and Path(cwd).is_dir()) else str(Path.home())
    env = os.environ.copy()
    env.pop("TMUX", None)
    try:
        proc = subprocess.Popen(
            ["agy", "--conversation", conversation_id, f"--print={text}"],
            cwd=target_cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
        threading.Thread(target=proc.wait, daemon=True).start()
        return True
    except OSError:
        return False


def capture_pane(window_id: str, lines: int = 35) -> str:
    res = _run_tmux("capture-pane", "-p", "-t", window_id, "-S", f"-{lines}")
    if res.returncode != 0:
        return ""
    return res.stdout.rstrip()


def detect_waiting_prompt(window_id: str) -> bool:
    """Return True if the bottom of a tmux window shows a permission/confirmation prompt."""
    text = capture_pane(window_id, lines=14)
    if not text:
        return False
    non_empty = [ln.strip() for ln in text.splitlines() if ln.strip()]
    tail = non_empty[-10:]
    for line in tail:
        if WAITING_PROMPT_RE.search(line):
            return True
    return False


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
