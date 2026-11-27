#!/usr/bin/env python3
"""Textual TUI for AGY Session Manager."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from rich.markup import escape
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

import data
import tmux_ctrl

SPINNER_RUNNING = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
SPINNER_BG = ["◐", "◓", "◑", "◒"]


class NewSessionModal(ModalScreen[Optional[tuple[str, str]]]):
    """Modal to launch a new agy session."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, default_cwd: str) -> None:
        super().__init__()
        self.default_cwd = default_cwd

    def compose(self) -> ComposeResult:
        with Container(id="modal-box"):
            yield Label("New AGY Session", classes="modal-title")
            yield Label("Workspace directory:", classes="modal-label")
            yield Input(value=self.default_cwd, id="cwd-input", placeholder="/path/to/workspace")
            yield Label("Extra agy flags (optional, e.g. --mode plan):", classes="modal-label")
            yield Input(value="", id="args-input", placeholder="--model ... --mode ...")
            with Horizontal(classes="modal-buttons"):
                yield Button("Launch", variant="primary", id="launch-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#cwd-input", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#launch-btn")
    def _launch(self) -> None:
        cwd = self.query_one("#cwd-input", Input).value.strip() or self.default_cwd
        args = self.query_one("#args-input", Input).value.strip()
        self.dismiss((os.path.expanduser(cwd), args))

    @on(Input.Submitted)
    def _submit(self) -> None:
        self._launch()


class RenameModal(ModalScreen[Optional[str]]):
    """Modal to rename a session (saved as sidecar alias)."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, current_name: str) -> None:
        super().__init__()
        self.current_name = current_name

    def compose(self) -> ComposeResult:
        with Container(id="modal-box"):
            yield Label("Rename Session (leave blank to reset)", classes="modal-title")
            yield Input(value=self.current_name, id="rename-input")
            with Horizontal(classes="modal-buttons"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        inp = self.query_one("#rename-input", Input)
        inp.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save-btn")
    def _save(self) -> None:
        val = self.query_one("#rename-input", Input).value
        self.dismiss(val)

    @on(Input.Submitted)
    def _submit(self) -> None:
        self._save()


class SessionListItem(ListItem):
    """Single row representing either an active tmux session or a history session."""

    def __init__(
        self,
        key_id: str,
        session: Optional[data.SessionInfo] = None,
        unlinked_window: Optional[tmux_ctrl.TmuxSessionWindow] = None,
        section_header: Optional[str] = None,
        selected: bool = False,
    ) -> None:
        super().__init__()
        self.key_id = key_id
        self.session = session
        self.unlinked_window = unlinked_window
        self.section_header = section_header
        self.is_multi_selected = selected
        if section_header is not None:
            self.disabled = True
            self.add_class("section-row")
        if selected:
            self.add_class("is-selected")
        self._label = Static("", markup=True, classes="row-text")

    def set_multi_selected(self, selected: bool, frame: int) -> None:
        self.is_multi_selected = selected
        if selected:
            self.add_class("is-selected")
        else:
            self.remove_class("is-selected")
        self.render_row(frame)

    def compose(self) -> ComposeResult:
        yield self._label

    def on_mount(self) -> None:
        self.render_row(0)

    def render_row(self, frame: int) -> None:
        if self.section_header is not None:
            self._label.update(f"[bold #7aa2f7]{escape(self.section_header)}[/]")
            return

        if self.unlinked_window is not None:
            w = self.unlinked_window
            spin = SPINNER_RUNNING[frame % len(SPINNER_RUNNING)]
            ws = data.shorten_path(w.cwd, 34)
            title = escape(w.title or w.window_name)
            self._label.update(
                f"[bold #7dcfff]{spin}[/] [bold]{title}[/] [dim cyan](active)[/]\n"
                f"  [dim]{escape(ws)}[/]"
            )
            return

        assert self.session is not None
        s = self.session
        kind = s.state_kind
        if kind == "running":
            icon = f"[bold #73daca]{SPINNER_RUNNING[frame % len(SPINNER_RUNNING)]}[/]"
            badge = "[#73daca]running[/]"
        elif kind == "background":
            icon = f"[bold #e0af68]{SPINNER_BG[frame % len(SPINNER_BG)]}[/]"
            badge = "[#e0af68]bg task[/]"
        elif kind == "active_idle":
            icon = "[bold #9ece6a]●[/]"
            badge = "[#9ece6a]active[/]"
        elif kind == "external_idle":
            icon = "[#bb9af7]◉[/]"
            badge = "[#bb9af7]open[/]"
        else:
            icon = "[dim]○[/]"
            badge = ""

        chk = "[bold #f7768e]\\[✓][/] " if self.is_multi_selected else ""
        pin = "[bold #e0af68]★ [/]" if s.pinned else ""
        title = escape(s.display_title)
        rel = data.format_relative_time(s.last_modified_ts)
        ws = escape(data.shorten_path(s.workspace_path, 32))
        meta_bits = [b for b in [badge, rel, f"{s.step_count} steps", ws] if b]
        meta_line = " [dim]·[/] ".join(meta_bits)
        self._label.update(f"{chk}{icon} {pin}[bold]{title}[/]\n  [dim]{meta_line}[/]")


class AgySessionManagerApp(App):
    """Interactive AGY Session Manager TUI."""

    CSS = """
    Screen {
        background: #1a1b26;
        color: #c0caf5;
    }
    #top-bar {
        height: 3;
        background: #16161e;
        border-bottom: solid #292e42;
        padding: 0 1;
        align: left middle;
    }
    #brand {
        width: auto;
        color: #7aa2f7;
        text-style: bold;
        padding-right: 2;
    }
    #scope-badge {
        width: auto;
        color: #9ece6a;
        padding-right: 2;
    }
    #hint-badge {
        width: 1fr;
        text-align: right;
        color: #565f89;
    }
    #search-bar {
        height: 3;
        background: #1f2335;
        border-bottom: solid #292e42;
        padding: 0 1;
        display: none;
    }
    #search-bar.visible {
        display: block;
    }
    #search-input {
        border: none;
        background: #1f2335;
    }
    #main-body {
        height: 1fr;
    }
    #left-pane {
        width: 46%;
        border-right: solid #292e42;
        height: 1fr;
    }
    #session-list {
        background: #1a1b26;
        height: 1fr;
    }
    #session-list > ListItem {
        padding: 0 1;
        height: auto;
        border-left: thick #1a1b26;
    }
    #session-list > ListItem.-highlight {
        background: #2e4070;
        border-left: thick #7dcfff;
    }
    #session-list > ListItem.is-selected {
        background: #2b2135;
        border-left: thick #f7768e;
    }
    #session-list > ListItem.is-selected.-highlight {
        background: #3b528c;
        border-left: thick #7dcfff;
    }
    #session-list > ListItem.section-row {
        background: #16161e;
        border-left: none;
        padding: 0 1;
        height: 1;
    }
    #right-pane {
        width: 54%;
        height: 1fr;
        padding: 1 2;
        background: #16161e;
    }
    #preview-header {
        height: auto;
        border-bottom: solid #292e42;
        padding-bottom: 1;
        margin-bottom: 1;
    }
    #preview-scroll {
        height: 1fr;
    }
    #preview-body {
        height: auto;
    }
    ModalScreen {
        align: center middle;
        background: rgba(15, 16, 24, 0.75);
    }
    #modal-box {
        width: 68;
        height: auto;
        background: #1f2335;
        border: solid #7aa2f7;
        padding: 1 2;
    }
    .modal-title {
        text-style: bold;
        color: #7aa2f7;
        margin-bottom: 1;
    }
    #confirm-bar {
        height: auto;
        min-height: 1;
        padding: 0 2;
        background: #24283b;
        border-top: solid #e0af68;
        color: #c0caf5;
        display: none;
    }
    #confirm-bar.visible {
        display: block;
    }
    #confirm-bar.danger {
        background: #2d1b26;
        border-top: solid #f7768e;
    }
    #hotkey-bar {
        height: auto;
        background: #16161e;
        border-top: solid #292e42;
        padding: 0 1;
        color: #a9b1d6;
    }
    .modal-label {
        color: #a9b1d6;
        margin-top: 1;
    }
    .modal-buttons {
        height: auto;
        margin-top: 1;
        align: right middle;
    }
    .modal-buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("enter", "open_selected", "Open", show=True),
        Binding("space", "toggle_select", "Select", show=True),
        Binding("a", "toggle_select_all", "All", show=True),
        Binding("d", "delete_sessions", "Delete", show=True),
        Binding("delete", "delete_sessions", "Delete", show=False),
        Binding("n", "new_session", "New", show=True),
        Binding("k", "kill_active", "Stop Bg", show=True),
        Binding("r", "rename_selected", "Rename", show=True),
        Binding("p", "pin_selected", "Pin", show=True),
        Binding("slash", "focus_search", "Search", show=True),
        Binding("tab", "toggle_scope", "Scope", show=True, priority=True),
        Binding("q", "quit_prompt", "Quit", show=True),
        Binding("escape", "clear_search", "Clear", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.frame: int = 0
        self.all_workspaces: bool = True
        self.search_query: str = ""
        self.launch_cwd: str = tmux_ctrl.get_launch_cwd()
        self._last_signature: str = ""
        self._preview_key: str = ""
        self._active_windows: list[tmux_ctrl.TmuxSessionWindow] = []
        self._sessions: list[data.SessionInfo] = []
        self.selected_ids: set[str] = set()
        self._pending_mode: Optional[str] = None  # "delete" | "quit" | None
        self._pending_delete_targets: list[data.SessionInfo] = []
        self._rebuilding_list: bool = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-bar"):
            yield Static("◈ AGY Session Manager", id="brand")
            yield Static("", id="scope-badge")
            yield Static("In session: ←← or Alt+← to return", id="hint-badge")
        with Container(id="search-bar"):
            yield Input(placeholder="Search title, workspace, or full-text content... (Esc to close)", id="search-input")
        with Horizontal(id="main-body"):
            with Vertical(id="left-pane"):
                yield ListView(id="session-list")
            with Vertical(id="right-pane"):
                yield Static("", id="preview-header", markup=True)
                with VerticalScroll(id="preview-scroll"):
                    yield Static("", id="preview-body")
        yield Static("", id="confirm-bar", markup=True)
        yield Static(
            "[bold #7aa2f7]Enter[/] 開啟  "
            "[bold #7aa2f7]Space[/] 多選  "
            "[bold #7aa2f7]a[/] 全選  "
            "[bold #f7768e]d[/] 刪除  "
            "[bold #7aa2f7]n[/] 新增  "
            "[bold #7aa2f7]k[/] 關閉背景  "
            "[bold #7aa2f7]r[/] 改名  "
            "[bold #7aa2f7]p[/] 釘選  "
            "[bold #7aa2f7]/[/] 搜尋  "
            "[bold #7aa2f7]Tab[/] 切換範圍  "
            "[bold #e0af68]q[/] 離開",
            id="hotkey-bar",
            markup=True,
        )

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).can_focus = False
        self._refresh_data(force=True)
        self.query_one("#session-list", ListView).focus()
        self.set_interval(0.12, self._tick_animation)
        self.set_interval(1.0, self._poll_data)

    def _tick_animation(self) -> None:
        self.frame = (self.frame + 1) % 1000
        lv = self.query_one("#session-list", ListView)
        for item in lv.children:
            if isinstance(item, SessionListItem) and item.section_header is None:
                if item.unlinked_window is not None or (
                    item.session is not None
                    and item.session.state_kind in ("running", "background")
                ):
                    item.render_row(self.frame)

    def _poll_data(self) -> None:
        if self._pending_mode is not None:
            return
        self.launch_cwd = tmux_ctrl.get_launch_cwd()
        self._refresh_data(force=False)

    def _update_top_bar(self) -> None:
        scope_el = self.query_one("#scope-badge", Static)
        active_cnt = len(self._active_windows)
        sel_cnt = len(self.selected_ids)
        sel_part = f"  [bold #f7768e]Selected: {sel_cnt}[/]" if sel_cnt > 0 else ""
        if self.all_workspaces:
            scope_el.update(f"[bold #9ece6a]All Workspaces[/]  [dim]Active: {active_cnt}[/]{sel_part}")
        else:
            short = data.shorten_path(self.launch_cwd, 28)
            scope_el.update(f"[bold #7dcfff]Workspace: {escape(short)}[/]  [dim]Active: {active_cnt}[/]{sel_part}")

    def _refresh_data(self, force: bool = False) -> None:
        windows = tmux_ctrl.list_session_windows()
        win_by_cid = {w.conv_id: w for w in windows if w.conv_id}
        unlinked = [w for w in windows if not w.conv_id]

        ws_filter = None if self.all_workspaces else self.launch_cwd
        sessions = data.fetch_sessions(
            limit=200,
            workspace_filter=ws_filter,
            search_query=self.search_query,
        )

        for s in sessions:
            w = win_by_cid.get(s.conversation_id)
            if w:
                s.tmux_window_id = w.window_id
                s.tmux_window_name = w.window_name

        # Split into active (in tmux or running) vs history
        active_sessions = [
            s for s in sessions if s.is_active_in_tmux or s.state_kind in ("running", "background")
        ]
        history_sessions = [
            s for s in sessions if not (s.is_active_in_tmux or s.state_kind in ("running", "background"))
        ]

        # Pinned first within each group, then recency
        active_sessions.sort(key=lambda s: (not s.pinned, -s.last_modified_ts))
        history_sessions.sort(key=lambda s: (not s.pinned, -s.last_modified_ts))

        self._active_windows = windows
        self._sessions = sessions
        self._update_top_bar()

        sig = repr(
            (
                [(w.window_id, w.window_name, w.conv_id, w.cwd, w.title) for w in unlinked],
                [
                    (
                        s.conversation_id,
                        s.display_title,
                        s.status,
                        s.not_fully_idle,
                        s.step_count,
                        s.tmux_window_id,
                        s.is_externally_locked,
                        s.pinned,
                    )
                    for s in active_sessions
                ],
                [
                    (s.conversation_id, s.display_title, s.step_count, s.pinned, s.is_externally_locked)
                    for s in history_sessions
                ],
                self.all_workspaces,
                self.search_query,
            )
        )

        if not force and sig == self._last_signature:
            return
        self._last_signature = sig

        lv = self.query_one("#session-list", ListView)
        selected_key = self._current_key()

        self._rebuilding_list = True
        try:
            lv.clear()
            items: list[SessionListItem] = []

            total_active = len(unlinked) + len(active_sessions)
            if total_active > 0:
                items.append(SessionListItem(key_id="__hdr_active", section_header=f"ACTIVE SESSIONS ({total_active})"))
                for w in unlinked:
                    items.append(SessionListItem(key_id=f"win:{w.window_id}", unlinked_window=w))
                for s in active_sessions:
                    items.append(
                        SessionListItem(
                            key_id=f"conv:{s.conversation_id}",
                            session=s,
                            selected=(s.conversation_id in self.selected_ids),
                        )
                    )

            if history_sessions:
                items.append(SessionListItem(key_id="__hdr_history", section_header=f"HISTORY ({len(history_sessions)})"))
                for s in history_sessions:
                    items.append(
                        SessionListItem(
                            key_id=f"conv:{s.conversation_id}",
                            session=s,
                            selected=(s.conversation_id in self.selected_ids),
                        )
                    )

            if not items:
                items.append(SessionListItem(key_id="__empty", section_header="No sessions found. Press 'n' to start one."))

            for it in items:
                lv.append(it)

            # Restore selection
            target_idx: Optional[int] = None
            if selected_key:
                for idx, it in enumerate(items):
                    if it.key_id == selected_key and not it.disabled:
                        target_idx = idx
                        break
            if target_idx is None:
                for idx, it in enumerate(items):
                    if not it.disabled:
                        target_idx = idx
                        break

            if target_idx is not None:
                lv.index = target_idx
                self._render_preview(items[target_idx])
            else:
                self._render_preview(None)
        finally:
            self._rebuilding_list = False

    def _current_item(self) -> Optional[SessionListItem]:
        lv = self.query_one("#session-list", ListView)
        item = lv.highlighted_child
        if isinstance(item, SessionListItem) and not item.disabled:
            return item
        return None

    def _current_key(self) -> Optional[str]:
        it = self._current_item()
        return it.key_id if it else None

    @on(ListView.Highlighted, "#session-list")
    def _on_highlight(self, event: ListView.Highlighted) -> None:
        if not self._rebuilding_list and self._pending_mode is not None:
            self._clear_confirm()
        if isinstance(event.item, SessionListItem) and not event.item.disabled:
            self._render_preview(event.item)

    @on(ListView.Selected, "#session-list")
    def _on_selected(self, event: ListView.Selected) -> None:
        self.action_open_selected()

    def _render_preview(self, item: Optional[SessionListItem]) -> None:
        hdr = self.query_one("#preview-header", Static)
        body = self.query_one("#preview-body", Static)

        if item is None:
            hdr.update("[dim]No session selected[/]")
            body.update("")
            return

        if item.unlinked_window is not None:
            w = item.unlinked_window
            hdr.update(
                f"[bold #7dcfff]{escape(w.title or w.window_name)}[/]\n"
                f"[dim]Window:[/] {escape(w.window_name)}  "
                f"[dim]Dir:[/] {escape(w.cwd)}\n"
                f"[#9ece6a]● Live tmux session (press Enter to attach)[/]"
            )
            pane_text = tmux_ctrl.capture_pane(w.window_id, lines=40)
            body.update(Text(pane_text or "(empty screen)", style="dim"))
            return

        s = item.session
        assert s is not None
        status_map = {
            "running": "[bold #73daca]● RUNNING[/]",
            "background": "[bold #e0af68]◐ BACKGROUND TASK[/]",
            "active_idle": "[bold #9ece6a]● ACTIVE (in background)[/]",
            "external_idle": "[bold #bb9af7]◉ OPEN IN ANOTHER TERMINAL[/]",
            "history": "[dim]○ HISTORY[/]",
        }
        status_label = status_map.get(s.state_kind, s.status)
        rel = data.format_relative_time(s.last_modified_ts)

        hdr.update(
            f"[bold #c0caf5]{escape(s.display_title)}[/]\n"
            f"{status_label}  [dim]·  {s.step_count} steps  ·  {rel}[/]\n"
            f"[dim]Dir:[/] {escape(s.workspace_path or '(none)')}\n"
            f"[dim]ID:[/]  {escape(s.conversation_id)}"
        )

        msgs = data.load_transcript_preview(s.conversation_id, max_messages=8)
        if msgs:
            out = Text()
            for role, text in msgs:
                if role == "USER":
                    out.append("You\n", style="bold #7aa2f7")
                    out.append(text + "\n\n", style="#c0caf5")
                else:
                    out.append("AGY\n", style="bold #9ece6a")
                    out.append(text + "\n\n", style="#a9b1d6")
            body.update(out)
        elif s.tmux_window_id:
            pane_text = tmux_ctrl.capture_pane(s.tmux_window_id, lines=40)
            body.update(Text(pane_text or "(no transcript yet)", style="dim"))
        else:
            fallback = s.preview.strip() if s.preview else "(No transcript preview available)"
            body.update(Text(fallback, style="dim"))

    def action_open_selected(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()
        it = self._current_item()
        if it is None:
            return
        if it.unlinked_window is not None:
            tmux_ctrl.select_window(it.unlinked_window.window_id)
            return
        if it.session is not None:
            s = it.session
            cwd = s.workspace_path or self.launch_cwd
            tmux_ctrl.open_or_resume_session(
                conversation_id=s.conversation_id,
                cwd=cwd,
                title=s.display_title,
            )

    def action_new_session(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()

        def _after(res: Optional[tuple[str, str]]) -> None:
            if res is None:
                return
            cwd, extra_args = res
            tmux_ctrl.spawn_new_session(cwd=cwd, extra_args=extra_args)

        self.push_screen(NewSessionModal(self.launch_cwd), _after)

    def _show_confirm(self, mode: str, message: str, danger: bool = False) -> None:
        self._pending_mode = mode
        bar = self.query_one("#confirm-bar", Static)
        bar.update(message)
        bar.add_class("visible")
        if danger:
            bar.add_class("danger")
        else:
            bar.remove_class("danger")

    def _clear_confirm(self) -> None:
        self._pending_mode = None
        self._pending_delete_targets = []
        bar = self.query_one("#confirm-bar", Static)
        bar.update("")
        bar.remove_class("visible")
        bar.remove_class("danger")

    def action_kill_active(self) -> None:
        if self._pending_mode == "quit":
            self._clear_confirm()
            tmux_ctrl.kill_server()
            self.exit()
            return
        if self._pending_mode is not None:
            self._clear_confirm()
        it = self._current_item()
        if it is None:
            return
        wid: Optional[str] = None
        if it.unlinked_window is not None:
            wid = it.unlinked_window.window_id
        elif it.session is not None and it.session.tmux_window_id:
            wid = it.session.tmux_window_id
        if wid:
            tmux_ctrl.kill_window(wid)
            self._refresh_data(force=True)

    def action_rename_selected(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()
        it = self._current_item()
        if it is None or it.session is None:
            return
        s = it.session

        def _after(new_name: Optional[str]) -> None:
            if new_name is None:
                return
            synced = data.rename_session(s.conversation_id, new_name)
            if s.tmux_window_id and new_name.strip():
                tmux_ctrl.set_window_title(s.tmux_window_id, new_name.strip())
            self._refresh_data(force=True)
            if synced and new_name.strip():
                if s.is_live:
                    self.notify(
                        f'已更名為 "{new_name.strip()}"（已同步至 AGY；開啟中的視窗重開後生效）',
                        severity="information",
                    )
                else:
                    self.notify(f'已更名為 "{new_name.strip()}"', severity="information")

        self.push_screen(RenameModal(s.display_title), _after)

    def action_toggle_select(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()
        it = self._current_item()
        if it is None or it.session is None:
            return
        cid = it.session.conversation_id
        if cid in self.selected_ids:
            self.selected_ids.remove(cid)
            it.set_multi_selected(False, self.frame)
        else:
            self.selected_ids.add(cid)
            it.set_multi_selected(True, self.frame)
        self._update_top_bar()

    def action_toggle_select_all(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()
        if self.selected_ids:
            self.selected_ids.clear()
        else:
            for s in self._sessions:
                self.selected_ids.add(s.conversation_id)
        lv = self.query_one("#session-list", ListView)
        for child in lv.children:
            if isinstance(child, SessionListItem) and child.session is not None:
                child.set_multi_selected(
                    child.session.conversation_id in self.selected_ids,
                    self.frame,
                )
        self._update_top_bar()

    def action_delete_sessions(self) -> None:
        # Second 'd' confirms pending deletion
        if self._pending_mode == "delete" and self._pending_delete_targets:
            targets = list(self._pending_delete_targets)
            self._clear_confirm()
            for s in targets:
                if s.tmux_window_id:
                    tmux_ctrl.kill_window(s.tmux_window_id)
            cids = [s.conversation_id for s in targets]
            deleted, failed = data.delete_sessions(cids)
            for cid in deleted:
                self.selected_ids.discard(cid)
            self._refresh_data(force=True)
            if failed:
                self.notify(
                    f"Deleted {len(deleted)}, failed {len(failed)}: {failed[0][1]}",
                    severity="error",
                )
            else:
                label = "session" if len(deleted) == 1 else "sessions"
                self.notify(f"Deleted {len(deleted)} {label}.", severity="information")
            return

        if self.selected_ids:
            by_id = {s.conversation_id: s for s in self._sessions}
            targets = [by_id[cid] for cid in self.selected_ids if cid in by_id]
            if not targets:
                self.selected_ids.clear()
                self._update_top_bar()
                return
        else:
            it = self._current_item()
            if it is None:
                return
            if it.session is None:
                self.notify("Unsaved session window — press 'k' to close it.", severity="warning")
                return
            targets = [it.session]

        self._pending_delete_targets = targets
        has_live = any(s.is_live or s.state_kind in ("running", "background") for s in targets)
        live_warn = " [bold #e0af68](includes active/running!)[/]" if has_live else ""
        if len(targets) == 1:
            title = escape(targets[0].display_title)
            msg = (
                f"[bold #f7768e]⚠ 確定刪除 \"{title}\" ({targets[0].conversation_id[:8]})？[/]{live_warn}  "
                f"[bold #f7768e]\\[d][/] 確認刪除  [dim]\\[Esc] 取消[/]"
            )
        else:
            msg = (
                f"[bold #f7768e]⚠ 確定刪除已選的 {len(targets)} 個 sessions？[/]{live_warn}  "
                f"[bold #f7768e]\\[d][/] 確認刪除  [dim]\\[Esc] 取消[/]"
            )
        self._show_confirm("delete", msg, danger=True)

    def action_pin_selected(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()
        it = self._current_item()
        if it is None or it.session is None:
            return
        data.toggle_pin(it.session.conversation_id)
        self._refresh_data(force=True)

    def action_toggle_scope(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()
        self.all_workspaces = not self.all_workspaces
        self._refresh_data(force=True)

    def action_focus_search(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()
        bar = self.query_one("#search-bar", Container)
        bar.add_class("visible")
        inp = self.query_one("#search-input", Input)
        inp.can_focus = True
        inp.focus()

    def action_clear_search(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()
            return
        bar = self.query_one("#search-bar", Container)
        inp = self.query_one("#search-input", Input)
        if bar.has_class("visible"):
            if inp.value:
                inp.value = ""
                self.search_query = ""
                self._refresh_data(force=True)
            bar.remove_class("visible")
            inp.can_focus = False
            self.query_one("#session-list", ListView).focus()
            return
        if self.selected_ids:
            self.selected_ids.clear()
            lv = self.query_one("#session-list", ListView)
            for child in lv.children:
                if isinstance(child, SessionListItem) and child.session is not None:
                    child.set_multi_selected(False, self.frame)
            self._update_top_bar()

    @on(Input.Changed, "#search-input")
    def _on_search_changed(self, event: Input.Changed) -> None:
        self.search_query = event.value
        self._refresh_data(force=True)

    @on(Input.Submitted, "#search-input")
    def _on_search_submit(self) -> None:
        self.query_one("#session-list", ListView).focus()

    def action_quit_prompt(self) -> None:
        if self._pending_mode == "quit":
            self._clear_confirm()
            tmux_ctrl.detach_client()
            return
        active_cnt = len(self._active_windows)
        msg = (
            f"[bold #e0af68]離開 AGY Session Manager (背景執行中: {active_cnt})：[/]  "
            f"[bold #9ece6a]\\[q][/] 保持背景執行 (detach)  "
            f"[bold #f7768e]\\[k][/] 全部關閉並離開  "
            f"[dim]\\[Esc] 取消[/]"
        )
        self._show_confirm("quit", msg, danger=False)


def main() -> None:
    app = AgySessionManagerApp()
    app.run()


if __name__ == "__main__":
    main()
