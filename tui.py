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
from textual.widgets import Button, Input, Label, ListItem, ListView, Static, TextArea

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


class SendMessageModal(ModalScreen[Optional[str]]):
    """Modal to send a message to one or more sessions."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, target_summary: str, initial_text: str = "") -> None:
        super().__init__()
        self.target_summary = target_summary
        self.initial_text = initial_text

    def compose(self) -> ComposeResult:
        with Container(id="modal-box"):
            yield Label("Send Message to Session", classes="modal-title")
            yield Label(self.target_summary, classes="modal-label", markup=False)
            yield Input(
                value=self.initial_text,
                id="msg-input",
                placeholder="輸入要傳送的指令或訊息... (Enter 送出 / Esc 取消)",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Send", variant="primary", id="send-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#msg-input", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#send-btn")
    def _send(self) -> None:
        val = self.query_one("#msg-input", Input).value.strip()
        self.dismiss(val if val else None)

    @on(Input.Submitted)
    def _submit(self) -> None:
        self._send()


class HandoverTargetItem(ListItem):
    """Target session option inside HandoverModal."""

    def __init__(self, session: data.SessionInfo) -> None:
        super().__init__()
        self.session = session
        if session.tmux_window_id:
            tag = "[#9ece6a](active)[/]"
        elif session.is_externally_locked:
            tag = "[#bb9af7](open externally)[/]"
        else:
            tag = "[dim](history)[/]"
        ws = escape(data.shorten_path(session.workspace_path, 26))
        self._text = f"[bold]{escape(session.display_title)}[/] {tag} [dim]· {ws}[/]"

    def compose(self) -> ComposeResult:
        yield Static(self._text, markup=True)


class HandoverModal(ModalScreen[Optional[tuple[str, str]]]):
    """Modal to pick a target session and edit handover context before sending."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "confirm_send", "Send", priority=True),
    ]

    def __init__(
        self,
        source: data.SessionInfo,
        targets: list[data.SessionInfo],
        initial_context: str,
    ) -> None:
        super().__init__()
        self.source = source
        self.targets = targets
        self.initial_context = initial_context

    def compose(self) -> ComposeResult:
        with Container(id="handover-modal-box"):
            yield Label("Cross-Session Context Handover", classes="modal-title")
            yield Label(
                f'From: "{self.source.display_title}" ({self.source.conversation_id[:8]})',
                classes="modal-label",
                markup=False,
            )
            yield Label("Select target session (↑/↓):", classes="modal-label")
            yield ListView(
                *[HandoverTargetItem(s) for s in self.targets],
                id="handover-targets",
            )
            yield Label("Handover message (editable, Ctrl+S to send):", classes="modal-label")
            yield TextArea(self.initial_context, id="handover-text")
            with Horizontal(classes="modal-buttons"):
                yield Button("Send Handover (Ctrl+S)", variant="primary", id="handover-send-btn")
                yield Button("Cancel (Esc)", id="cancel-btn")

    def on_mount(self) -> None:
        lv = self.query_one("#handover-targets", ListView)
        if self.targets:
            lv.index = 0
        lv.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm_send(self) -> None:
        lv = self.query_one("#handover-targets", ListView)
        cur = lv.highlighted_child
        if not isinstance(cur, HandoverTargetItem):
            return
        text = self.query_one("#handover-text", TextArea).text.strip()
        if not text:
            self.notify("轉交內容不可為空", severity="warning")
            return
        self.dismiss((cur.session.conversation_id, text))

    @on(ListView.Selected, "#handover-targets")
    def _on_target_enter(self) -> None:
        self.query_one("#handover-text", TextArea).focus()

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#handover-send-btn")
    def _send(self) -> None:
        self.action_confirm_send()


class SplitOptionItem(ListItem):
    """Option row inside SplitTargetModal (either a session or an unsplit action)."""

    def __init__(self, value: str, markup_text: str) -> None:
        super().__init__()
        self.value = value
        self._text = markup_text

    def compose(self) -> ComposeResult:
        yield Static(self._text, markup=True)


class SplitTargetModal(ModalScreen[Optional[str]]):
    """Modal to pick the second session for side-by-side tmux split view."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        first: data.SessionInfo,
        targets: list[data.SessionInfo],
        can_unsplit: bool = False,
    ) -> None:
        super().__init__()
        self.first = first
        self.targets = targets
        self.can_unsplit = can_unsplit

    def compose(self) -> ComposeResult:
        items: list[SplitOptionItem] = []
        if self.can_unsplit:
            items.append(
                SplitOptionItem(
                    "__unsplit__",
                    "[bold #e0af68]⊟ 取消並排（將此 session 拆回獨立視窗）[/]",
                )
            )
        for s in self.targets:
            if s.tmux_window_id:
                tag = "[#9ece6a](active)[/]"
            elif s.is_externally_locked:
                tag = "[#bb9af7](open externally)[/]"
            else:
                tag = "[dim](history)[/]"
            ws = escape(data.shorten_path(s.workspace_path, 26))
            items.append(
                SplitOptionItem(
                    s.conversation_id,
                    f"[bold]{escape(s.display_title)}[/] {tag} [dim]· {ws}[/]",
                )
            )
        with Container(id="split-modal-box"):
            yield Label("Side-by-Side Split View (v)", classes="modal-title")
            yield Label(
                f'Left pane: "{self.first.display_title}" ({self.first.conversation_id[:8]})',
                classes="modal-label",
                markup=False,
            )
            yield Label("Select right pane session (↑/↓ + Enter):", classes="modal-label")
            yield ListView(*items, id="split-targets")
            with Horizontal(classes="modal-buttons"):
                yield Button("Open Split", variant="primary", id="split-open-btn")
                yield Button("Cancel (Esc)", id="cancel-btn")

    def on_mount(self) -> None:
        lv = self.query_one("#split-targets", ListView)
        if lv.children:
            lv.index = 0
        lv.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _confirm(self) -> None:
        lv = self.query_one("#split-targets", ListView)
        cur = lv.highlighted_child
        if isinstance(cur, SplitOptionItem):
            self.dismiss(cur.value)

    @on(ListView.Selected, "#split-targets")
    def _on_pick(self) -> None:
        self._confirm()

    @on(Button.Pressed, "#split-open-btn")
    def _on_btn(self) -> None:
        self._confirm()

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self) -> None:
        self.dismiss(None)


class SessionListItem(ListItem):
    """Single row representing either an active tmux session or a history session."""

    def __init__(
        self,
        key_id: str,
        session: Optional[data.SessionInfo] = None,
        unlinked_window: Optional[tmux_ctrl.TmuxSessionWindow] = None,
        section_header: Optional[str] = None,
        selected: bool = False,
        tree_prefix: str = "",
    ) -> None:
        super().__init__()
        self.key_id = key_id
        self.session = session
        self.unlinked_window = unlinked_window
        self.section_header = section_header
        self.is_multi_selected = selected
        self.tree_prefix = tree_prefix
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
            ws = data.shorten_path(w.cwd, 34)
            title = escape(w.title or w.window_name)
            if w.waiting_for_user:
                blink = (frame // 4) % 2 == 0
                icon = "[bold #f7768e on #3b1d2a]⚠[/]" if blink else "[bold #e0af68]⚠[/]"
                tag = "[bold #f7768e]WAITING[/]"
            else:
                spin = SPINNER_RUNNING[frame % len(SPINNER_RUNNING)]
                icon = f"[bold #7dcfff]{spin}[/]"
                tag = "[dim cyan](active)[/]"
            self._label.update(
                f"{icon} [bold]{title}[/] {tag}\n"
                f"  [dim]{escape(ws)}[/]"
            )
            return

        assert self.session is not None
        s = self.session
        kind = s.state_kind
        if kind == "waiting":
            blink = (frame // 4) % 2 == 0
            icon = "[bold #f7768e on #3b1d2a]⚠[/]" if blink else "[bold #e0af68]⚠[/]"
            badge = "[bold #f7768e]WAITING[/]"
        elif kind == "running":
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
        agent_tag = f" [dim #bb9af7]({escape(s.agent_name)})[/]" if s.agent_name else ""
        prefix_str = f"[dim #565f89]{escape(self.tree_prefix)}[/]" if self.tree_prefix else ""
        sub_indent = " " * len(self.tree_prefix)
        rel = data.format_relative_time(s.last_modified_ts)
        ws = escape(data.shorten_path(s.workspace_path, 32))
        split_tag = "[#7dcfff]split[/]" if s.tmux_window_panes > 1 else ""
        meta_bits = [b for b in [badge, split_tag, rel, f"{s.step_count} steps", ws] if b]
        meta_line = " [dim]·[/] ".join(meta_bits)
        self._label.update(
            f"{chk}{prefix_str}{icon} {pin}[bold]{title}[/]{agent_tag}\n"
            f"{sub_indent}  [dim]{meta_line}[/]"
        )


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
    #handover-modal-box {
        width: 86;
        height: auto;
        max-height: 90%;
        background: #1f2335;
        border: solid #7aa2f7;
        padding: 1 2;
    }
    #handover-targets {
        height: 7;
        background: #16161e;
        border: solid #292e42;
        margin-top: 1;
    }
    #handover-targets > ListItem.-highlight {
        background: #2e4070;
    }
    #handover-text {
        height: 11;
        margin-top: 1;
        border: solid #292e42;
    }
    #split-modal-box {
        width: 78;
        height: auto;
        max-height: 85%;
        background: #1f2335;
        border: solid #7aa2f7;
        padding: 1 2;
    }
    #split-targets {
        height: 10;
        background: #16161e;
        border: solid #292e42;
        margin-top: 1;
    }
    #split-targets > ListItem.-highlight {
        background: #2e4070;
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
        Binding("m", "send_message", "Msg", show=True),
        Binding("c", "handover_context", "Handover", show=True),
        Binding("w", "jump_waiting", "Waiting", show=True),
        Binding("v", "split_view", "Split", show=True),
        Binding("t", "toggle_tree", "Tree", show=True),
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
        self.tree_view: bool = False
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
        self._last_jumped_waiting_wid: Optional[str] = None

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
            "[bold #7aa2f7]m[/] 傳訊  "
            "[bold #7aa2f7]c[/] 轉交  "
            "[bold #f7768e]w[/] 跳權限  "
            "[bold #7aa2f7]v[/] 並排  "
            "[bold #7aa2f7]t[/] 樹狀  "
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
                    and item.session.state_kind in ("waiting", "running", "background")
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
        unlinked_wait = sum(1 for w in self._active_windows if not w.conv_id and w.waiting_for_user)
        sess_wait = sum(1 for s in self._sessions if s.state_kind == "waiting")
        wait_cnt = unlinked_wait + sess_wait
        wait_part = f"  [bold #f7768e]⚠ Waiting: {wait_cnt} (w)[/]" if wait_cnt > 0 else ""
        tree_part = "  [bold #bb9af7]Tree[/]" if self.tree_view else ""
        sel_part = f"  [bold #f7768e]Selected: {sel_cnt}[/]" if sel_cnt > 0 else ""
        if self.all_workspaces:
            scope_el.update(
                f"[bold #9ece6a]All Workspaces[/]  [dim]Active: {active_cnt}[/]{tree_part}{wait_part}{sel_part}"
            )
        else:
            short = data.shorten_path(self.launch_cwd, 28)
            scope_el.update(
                f"[bold #7dcfff]Workspace: {escape(short)}[/]  [dim]Active: {active_cnt}[/]{tree_part}{wait_part}{sel_part}"
            )

    def _refresh_data(self, force: bool = False) -> None:
        windows = tmux_ctrl.list_session_windows()
        for w in windows:
            w.waiting_for_user = tmux_ctrl.detect_waiting_prompt(w.pane_id or w.window_id)
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
                s.tmux_pane_id = w.pane_id or None
                s.tmux_window_panes = w.window_panes
                if w.waiting_for_user:
                    s.waiting_for_user = True

        # Split into active (in tmux, waiting, or running) vs history
        active_sessions = [
            s for s in sessions if s.is_active_in_tmux or s.state_kind in ("waiting", "running", "background")
        ]
        history_sessions = [
            s for s in sessions if not (s.is_active_in_tmux or s.state_kind in ("waiting", "running", "background"))
        ]

        # Waiting first, then pinned, then recency
        active_sessions.sort(key=lambda s: (s.state_kind != "waiting", not s.pinned, -s.last_modified_ts))
        history_sessions.sort(key=lambda s: (not s.pinned, -s.last_modified_ts))

        self._active_windows = windows
        self._sessions = sessions
        self._update_top_bar()

        sig = repr(
            (
                [(w.window_id, w.window_name, w.conv_id, w.cwd, w.title, w.waiting_for_user) for w in unlinked],
                [
                    (
                        s.conversation_id,
                        s.display_title,
                        s.status,
                        s.not_fully_idle,
                        s.step_count,
                        s.tmux_window_id,
                        s.tmux_pane_id,
                        s.tmux_window_panes,
                        s.is_externally_locked,
                        s.waiting_for_user,
                        s.pinned,
                    )
                    for s in active_sessions
                ],
                [
                    (s.conversation_id, s.display_title, s.step_count, s.pinned, s.is_externally_locked)
                    for s in history_sessions
                ],
                self.all_workspaces,
                self.tree_view,
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

            if self.tree_view:
                if unlinked:
                    items.append(
                        SessionListItem(
                            key_id="__hdr_unlinked",
                            section_header=f"LIVE WINDOWS ({len(unlinked)})",
                        )
                    )
                    for w in unlinked:
                        items.append(SessionListItem(key_id=f"win:{w.pane_id or w.window_id}", unlinked_window=w))

                combined = active_sessions + history_sessions
                if combined:
                    tree_rows = data.build_session_tree(combined)
                    items.append(
                        SessionListItem(
                            key_id="__hdr_tree",
                            section_header=f"SESSION TREE ({len(tree_rows)})",
                        )
                    )
                    for s, prefix in tree_rows:
                        items.append(
                            SessionListItem(
                                key_id=f"conv:{s.conversation_id}",
                                session=s,
                                selected=(s.conversation_id in self.selected_ids),
                                tree_prefix=prefix,
                            )
                        )
            else:
                total_active = len(unlinked) + len(active_sessions)
                if total_active > 0:
                    items.append(SessionListItem(key_id="__hdr_active", section_header=f"ACTIVE SESSIONS ({total_active})"))
                    for w in unlinked:
                        items.append(SessionListItem(key_id=f"win:{w.pane_id or w.window_id}", unlinked_window=w))
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
            pane_text = tmux_ctrl.capture_pane(w.pane_id or w.window_id, lines=40)
            body.update(Text(pane_text or "(empty screen)", style="dim"))
            return

        s = item.session
        assert s is not None
        status_map = {
            "waiting": "[bold #f7768e]⚠ WAITING FOR PERMISSION / INPUT[/]",
            "running": "[bold #73daca]● RUNNING[/]",
            "background": "[bold #e0af68]◐ BACKGROUND TASK[/]",
            "active_idle": "[bold #9ece6a]● ACTIVE (in background)[/]",
            "external_idle": "[bold #bb9af7]◉ OPEN IN ANOTHER TERMINAL[/]",
            "history": "[dim]○ HISTORY[/]",
        }
        status_label = status_map.get(s.state_kind, s.status)
        rel = data.format_relative_time(s.last_modified_ts)

        parent_line = ""
        if s.parent_conversation_id:
            agent_bit = f"  [dim]Agent:[/] [#bb9af7]{escape(s.agent_name)}[/]" if s.agent_name else ""
            parent_line = f"\n[dim]Parent:[/] {escape(s.parent_conversation_id[:8])}{agent_bit}"

        hdr.update(
            f"[bold #c0caf5]{escape(s.display_title)}[/]\n"
            f"{status_label}  [dim]·  {s.step_count} steps  ·  {rel}[/]\n"
            f"[dim]Dir:[/] {escape(s.workspace_path or '(none)')}\n"
            f"[dim]ID:[/]  {escape(s.conversation_id)}{parent_line}"
        )

        if s.state_kind == "waiting" and s.tmux_window_id:
            pane_text = tmux_ctrl.capture_pane(s.tmux_pane_id or s.tmux_window_id, lines=40)
            if pane_text:
                body.update(Text(pane_text, style="#f7768e"))
                return

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
            pane_text = tmux_ctrl.capture_pane(s.tmux_pane_id or s.tmux_window_id, lines=40)
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
            tmux_ctrl.select_window(it.unlinked_window.window_id, it.unlinked_window.pane_id)
            return
        if it.session is not None:
            s = it.session
            cwd = s.workspace_path or self.launch_cwd
            tmux_ctrl.open_or_resume_session(
                conversation_id=s.conversation_id,
                cwd=cwd,
                title=s.display_title,
            )

    def action_send_message(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()

        targets_sessions: list[data.SessionInfo] = []
        target_unlinked: Optional[tmux_ctrl.TmuxSessionWindow] = None

        if self.selected_ids:
            by_id = {s.conversation_id: s for s in self._sessions}
            targets_sessions = [by_id[cid] for cid in self.selected_ids if cid in by_id]
            if not targets_sessions:
                self.selected_ids.clear()
                self._update_top_bar()
                return
        else:
            it = self._current_item()
            if it is None:
                return
            if it.unlinked_window is not None:
                target_unlinked = it.unlinked_window
            elif it.session is not None:
                targets_sessions = [it.session]
            else:
                return

        if target_unlinked is not None:
            summary = f'Target: "{target_unlinked.title or target_unlinked.window_name}" (active tmux window)'
        elif len(targets_sessions) == 1:
            s = targets_sessions[0]
            mode_str = "active tmux window" if s.tmux_window_id else "background agy -p"
            summary = f'Target: "{s.display_title}" ({mode_str})'
        else:
            live_n = sum(1 for s in targets_sessions if s.tmux_window_id)
            bg_n = len(targets_sessions) - live_n
            summary = f"Broadcast to {len(targets_sessions)} sessions ({live_n} active tmux, {bg_n} background -p)"

        target_cids = [s.conversation_id for s in targets_sessions]
        target_wid = (
            (target_unlinked.pane_id or target_unlinked.window_id)
            if target_unlinked is not None
            else None
        )
        was_multi = bool(self.selected_ids)

        def _after(msg: Optional[str]) -> None:
            if not msg:
                return
            # Re-resolve fresh state at send time so targets are never stale
            by_id = {s.conversation_id: s for s in self._sessions}
            resolved_sessions = [by_id[cid] for cid in target_cids if cid in by_id]
            launch_cwd = self.launch_cwd

            def _worker() -> None:
                ok_cnt = 0
                fail_cnt = 0
                skipped_ext = 0
                if target_wid is not None:
                    if tmux_ctrl.send_text_to_window(target_wid, msg, submit=True):
                        ok_cnt += 1
                    else:
                        fail_cnt += 1
                else:
                    for s in resolved_sessions:
                        if s.tmux_window_id:
                            ok = tmux_ctrl.send_text_to_window(
                                s.tmux_pane_id or s.tmux_window_id, msg, submit=True
                            )
                        elif s.is_externally_locked:
                            skipped_ext += 1
                            continue
                        else:
                            ok = tmux_ctrl.send_background_prompt(
                                s.conversation_id,
                                s.workspace_path or launch_cwd,
                                msg,
                            )
                        if ok:
                            ok_cnt += 1
                        else:
                            fail_cnt += 1

                def _finish() -> None:
                    if was_multi and self.selected_ids:
                        self.selected_ids.clear()
                    if ok_cnt > 0 or was_multi:
                        self._refresh_data(force=True)
                    if skipped_ext and not ok_cnt and not fail_cnt:
                        self.notify(
                            f"略過 {skipped_ext} 個在其他終端開啟中的 session（請先在 agym 內開啟）",
                            severity="warning",
                        )
                    elif fail_cnt or skipped_ext:
                        extra = f"，略過外部開啟 {skipped_ext} 個" if skipped_ext else ""
                        self.notify(f"已送出 {ok_cnt} 個，失敗 {fail_cnt} 個{extra}", severity="warning")
                    else:
                        self.notify(f"已送出訊息給 {ok_cnt} 個 session", severity="information")

                self.call_from_thread(_finish)

            self.run_worker(_worker, thread=True)

        self.push_screen(SendMessageModal(summary), _after)

    def action_handover_context(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()
        it = self._current_item()
        if it is None or it.session is None:
            self.notify("請先選取一個已儲存的來源 session", severity="warning")
            return
        src = it.session
        targets = [s for s in self._sessions if s.conversation_id != src.conversation_id]
        if not targets:
            self.notify("目前沒有其他可轉交的目標 session", severity="warning")
            return
        targets.sort(key=lambda s: (not s.is_active_in_tmux, not s.pinned, -s.last_modified_ts))

        initial_ctx = data.build_handover_context(src, max_messages=6)

        def _after(res: Optional[tuple[str, str]]) -> None:
            if res is None:
                return
            target_cid, handover_text = res
            by_id = {s.conversation_id: s for s in self._sessions}
            tgt = by_id.get(target_cid)
            if tgt is None:
                self.notify("目標 session 已不存在", severity="error")
                return
            launch_cwd = self.launch_cwd

            def _worker() -> None:
                if tgt.tmux_window_id:
                    ok = tmux_ctrl.send_text_to_window(
                        tgt.tmux_pane_id or tgt.tmux_window_id, handover_text, submit=True
                    )
                    ext_skip = False
                elif tgt.is_externally_locked:
                    ok = False
                    ext_skip = True
                else:
                    ok = tmux_ctrl.send_background_prompt(
                        tgt.conversation_id,
                        tgt.workspace_path or launch_cwd,
                        handover_text,
                    )
                    ext_skip = False

                def _finish() -> None:
                    if ext_skip:
                        self.notify(
                            f'"{tgt.display_title}" 正在其他終端開啟中，請先在 agym 內開啟後再轉交',
                            severity="warning",
                        )
                    elif ok:
                        self._refresh_data(force=True)
                        self.notify(f'已將上下文轉交給 "{tgt.display_title}"', severity="information")
                    else:
                        self.notify(f'轉交給 "{tgt.display_title}" 失敗', severity="error")

                self.call_from_thread(_finish)

            self.run_worker(_worker, thread=True)

        self.push_screen(HandoverModal(src, targets, initial_ctx), _after)

    def action_jump_waiting(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()
        lv = self.query_one("#session-list", ListView)
        waiting_live: list[tuple[int, str, str, str]] = []  # (list_idx, window_id, pane_id, title)
        waiting_other: list[tuple[int, data.SessionInfo]] = []

        for idx, child in enumerate(lv.children):
            if not isinstance(child, SessionListItem) or child.disabled:
                continue
            if child.unlinked_window is not None and child.unlinked_window.waiting_for_user:
                w = child.unlinked_window
                waiting_live.append((idx, w.window_id, w.pane_id, w.title or w.window_name))
            elif child.session is not None and child.session.state_kind == "waiting":
                s = child.session
                if s.tmux_window_id:
                    waiting_live.append((idx, s.tmux_window_id, s.tmux_pane_id or "", s.display_title))
                else:
                    waiting_other.append((idx, s))

        if waiting_live:
            chosen = waiting_live[0]
            if len(waiting_live) > 1 and self._last_jumped_waiting_wid is not None:
                keys = [e[2] or e[1] for e in waiting_live]
                if self._last_jumped_waiting_wid in keys:
                    next_pos = (keys.index(self._last_jumped_waiting_wid) + 1) % len(waiting_live)
                    chosen = waiting_live[next_pos]
            idx, wid, pid, _title = chosen
            self._last_jumped_waiting_wid = pid or wid
            lv.index = idx
            tmux_ctrl.select_window(wid, pid)
            return

        if waiting_other:
            idx, s = waiting_other[0]
            lv.index = idx
            if s.is_externally_locked:
                self.notify(
                    f'"{s.display_title}" 正在其他終端等待確認',
                    severity="warning",
                )
            else:
                self.notify(
                    f'已定位到等待確認的 "{s.display_title}"（按 Enter 開啟）',
                    severity="information",
                )
            return

        self.notify("目前沒有等待權限確認的 session", severity="information")

    def _launch_split(self, first: data.SessionInfo, second: data.SessionInfo) -> None:
        for s in (first, second):
            if s.is_externally_locked and not s.tmux_window_id:
                self.notify(
                    f'"{s.display_title}" 正在其他終端開啟中，無法在 agym 內並排',
                    severity="warning",
                )
                return
        ok = tmux_ctrl.open_split_view(
            (first.conversation_id, first.workspace_path or self.launch_cwd, first.display_title),
            (second.conversation_id, second.workspace_path or self.launch_cwd, second.display_title),
        )
        if self.selected_ids:
            self.selected_ids.clear()
        self._refresh_data(force=True)
        if not ok:
            self.notify("開啟並排視窗失敗", severity="error")

    def action_split_view(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()

        by_id = {s.conversation_id: s for s in self._sessions}
        if len(self.selected_ids) > 2:
            self.notify(
                f"請剛好選取 2 個 session 進行並排（目前選取 {len(self.selected_ids)} 個）",
                severity="warning",
            )
            return

        if len(self.selected_ids) == 2:
            pair = [by_id[cid] for cid in self.selected_ids if cid in by_id]
            if len(pair) == 2:
                self._launch_split(pair[0], pair[1])
                return

        if len(self.selected_ids) == 1:
            cid = next(iter(self.selected_ids))
            first = by_id.get(cid)
        else:
            it = self._current_item()
            first = it.session if it is not None else None

        if first is None:
            self.notify("請先選取一個已儲存的 session", severity="warning")
            return

        candidates = [s for s in self._sessions if s.conversation_id != first.conversation_id]
        candidates.sort(key=lambda s: (not s.is_active_in_tmux, not s.pinned, -s.last_modified_ts))
        can_unsplit = first.tmux_window_panes > 1 and bool(first.tmux_pane_id)

        if not candidates and not can_unsplit:
            self.notify("目前沒有其他可並排的 session", severity="warning")
            return

        def _after(choice: Optional[str]) -> None:
            if not choice:
                return
            if choice == "__unsplit__":
                if first.tmux_pane_id and tmux_ctrl.unsplit_pane(first.tmux_pane_id):
                    self._refresh_data(force=True)
                    self.notify(f'已將 "{first.display_title}" 拆回獨立視窗', severity="information")
                else:
                    self.notify("取消並排失敗", severity="error")
                return
            fresh = {s.conversation_id: s for s in self._sessions}
            f_cur = fresh.get(first.conversation_id, first)
            s_cur = fresh.get(choice)
            if s_cur is None:
                self.notify("目標 session 已不存在", severity="error")
                return
            self._launch_split(f_cur, s_cur)

        self.push_screen(SplitTargetModal(first, candidates, can_unsplit=can_unsplit), _after)

    def action_toggle_tree(self) -> None:
        if self._pending_mode is not None:
            self._clear_confirm()
        self.tree_view = not self.tree_view
        self._refresh_data(force=True)

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
        pid: str = ""
        if it.unlinked_window is not None:
            wid = it.unlinked_window.window_id
            pid = it.unlinked_window.pane_id
        elif it.session is not None and it.session.tmux_window_id:
            wid = it.session.tmux_window_id
            pid = it.session.tmux_pane_id or ""
        if wid:
            tmux_ctrl.kill_window(wid, pid)
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
                tmux_ctrl.set_window_title(s.tmux_window_id, new_name.strip(), s.tmux_pane_id or "")
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
                    tmux_ctrl.kill_window(s.tmux_window_id, s.tmux_pane_id or "")
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

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "toggle_scope" and len(self.screen_stack) > 1:
            return False
        return True

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
