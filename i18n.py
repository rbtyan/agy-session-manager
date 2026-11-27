"""Lightweight English / Traditional Chinese i18n with system locale auto-detection."""

from __future__ import annotations

import os
from typing import Optional

SUPPORTED_LANGS = ("en", "zh")

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "top_hint": "In session: ← (empty input) or Alt+← to return",
        "scope_all": "All Workspaces",
        "scope_ws": "Workspace: {path}",
        "active_count": "Active: {n}",
        "tree_badge": "Tree",
        "waiting_badge": "⚠ Waiting: {n} (w)",
        "selected_badge": "Selected: {n}",
        "search_placeholder": "Search title, workspace, or full-text content... (Esc to close)",
        "sec_active": "ACTIVE SESSIONS ({n})",
        "sec_history": "HISTORY ({n})",
        "sec_live_windows": "LIVE WINDOWS ({n})",
        "sec_tree": "SESSION TREE ({n})",
        "empty_list": "No sessions found. Press 'n' to start one.",
        "hotkey_bar": (
            "[bold #7aa2f7]Enter[/] Open  "
            "[bold #7aa2f7]Space[/] Select  "
            "[bold #7aa2f7]a[/] All  "
            "[bold #f7768e]d[/] Del  "
            "[bold #7aa2f7]m[/] Msg  "
            "[bold #7aa2f7]c[/] Handover  "
            "[bold #f7768e]w[/] Wait  "
            "[bold #7aa2f7]v[/] Split  "
            "[bold #7aa2f7]t[/] Tree  "
            "[bold #7aa2f7]n[/] New  "
            "[bold #7aa2f7]k[/] Stop  "
            "[bold #7aa2f7]r[/] Rename  "
            "[bold #7aa2f7]p[/] Pin  "
            "[bold #7aa2f7]/[/] Search  "
            "[bold #7aa2f7]Tab[/] Scope  "
            "[bold #7aa2f7]l[/] 中文  "
            "[bold #e0af68]q[/] Quit"
        ),
        "modal_new_title": "New AGY Session",
        "modal_new_cwd": "Workspace directory:",
        "modal_new_args": "Extra agy flags (optional, e.g. --mode plan):",
        "btn_launch": "Launch",
        "btn_cancel": "Cancel",
        "btn_cancel_esc": "Cancel (Esc)",
        "btn_save": "Save",
        "btn_send": "Send",
        "modal_rename_title": "Rename Session (leave blank to reset)",
        "modal_msg_title": "Send Message to Session",
        "modal_msg_placeholder": "Type a prompt or command... (Enter to send / Esc to cancel)",
        "modal_handover_title": "Cross-Session Context Handover",
        "modal_handover_from": 'From: "{title}" ({cid})',
        "modal_handover_pick": "Select target session (↑/↓):",
        "modal_handover_edit": "Handover message (editable, Ctrl+S to send):",
        "btn_send_handover": "Send Handover (Ctrl+S)",
        "modal_split_title": "Side-by-Side Split View (v)",
        "modal_split_left": 'Left pane: "{title}" ({cid})',
        "modal_split_pick": "Select right pane session (↑/↓ + Enter):",
        "btn_open_split": "Open Split",
        "split_unsplit_opt": "[bold #e0af68]⊟ Unsplit (move this session back to its own window)[/]",
        "tag_active": "[#9ece6a](active)[/]",
        "tag_external": "[#bb9af7](open externally)[/]",
        "tag_history": "[dim](history)[/]",
        "preview_none": "[dim]No session selected[/]",
        "preview_live_hint": "[#9ece6a]● Live tmux session (press Enter to attach)[/]",
        "preview_empty_screen": "(empty screen)",
        "preview_no_transcript": "(no transcript yet)",
        "preview_no_preview": "(No transcript preview available)",
        "status_waiting": "[bold #f7768e]⚠ WAITING FOR PERMISSION / INPUT[/]",
        "status_running": "[bold #73daca]● RUNNING[/]",
        "status_background": "[bold #e0af68]◐ BACKGROUND TASK[/]",
        "status_active_idle": "[bold #9ece6a]● ACTIVE (in background)[/]",
        "status_external_idle": "[bold #bb9af7]◉ OPEN IN ANOTHER TERMINAL[/]",
        "status_history": "[dim]○ HISTORY[/]",
        "lbl_window": "Window:",
        "lbl_dir": "Dir:",
        "lbl_id": "ID:",
        "lbl_parent": "Parent:",
        "lbl_agent": "Agent:",
        "lbl_you": "You",
        "mode_tmux": "active tmux window",
        "mode_bg": "background agy -p",
        "msg_target_unlinked": 'Target: "{title}" (active tmux window)',
        "msg_target_one": 'Target: "{title}" ({mode})',
        "msg_target_broadcast": "Broadcast to {total} sessions ({live} active tmux, {bg} background -p)",
        "notify_msg_skipped_only": "Skipped {n} session(s) open in another terminal (open inside agym first)",
        "notify_msg_partial": "Sent {ok}, failed {fail}{extra}",
        "notify_msg_partial_ext": ", skipped {n} external",
        "notify_msg_sent": "Message sent to {n} session(s)",
        "notify_handover_need_saved": "Please select a saved source session first",
        "notify_handover_no_target": "No other target sessions available for handover",
        "notify_handover_empty": "Handover message cannot be empty",
        "notify_handover_missing": "Target session no longer exists",
        "notify_handover_ext": '"{title}" is open in another terminal; open it in agym first before handover',
        "notify_handover_ok": 'Context handed over to "{title}"',
        "notify_handover_fail": 'Failed to hand over context to "{title}"',
        "notify_waiting_ext": '"{title}" is waiting for confirmation in another terminal',
        "notify_waiting_located": 'Located waiting session "{title}" (press Enter to open)',
        "notify_waiting_none": "No sessions currently waiting for confirmation",
        "notify_split_ext": '"{title}" is open in another terminal and cannot be split inside agym',
        "notify_split_fail": "Failed to open side-by-side split view",
        "notify_split_need_two": "Please select exactly 2 sessions to split (currently {n} selected)",
        "notify_split_need_saved": "Please select a saved session first",
        "notify_split_no_target": "No other sessions available for split view",
        "notify_unsplit_ok": 'Moved "{title}" back to its own window',
        "notify_unsplit_fail": "Failed to unsplit pane",
        "notify_target_missing": "Target session no longer exists",
        "notify_renamed_live": 'Renamed to "{name}" (synced to AGY; takes effect in open window after reopen)',
        "notify_renamed": 'Renamed to "{name}"',
        "notify_unsaved_delete": "Unsaved session window — press 'k' to close it.",
        "notify_deleted_partial": "Deleted {deleted}, failed {failed}: {err}",
        "notify_deleted_one": "Deleted 1 session.",
        "notify_deleted_many": "Deleted {n} sessions.",
        "confirm_live_warn": " [bold #e0af68](includes active/running!)[/]",
        "confirm_delete_one": (
            '[bold #f7768e]⚠ Delete "{title}" ({cid})?[/]{warn}  '
            "[bold #f7768e]\\[d][/] Confirm  [dim]\\[Esc] Cancel[/]"
        ),
        "confirm_delete_many": (
            "[bold #f7768e]⚠ Delete {n} selected sessions?[/]{warn}  "
            "[bold #f7768e]\\[d][/] Confirm  [dim]\\[Esc] Cancel[/]"
        ),
        "confirm_quit": (
            "[bold #e0af68]Leave AGY Session Manager (active: {n}):[/]  "
            "[bold #9ece6a]\\[q][/] Detach (keep running)  "
            "[bold #f7768e]\\[k][/] Stop all & exit  "
            "[dim]\\[Esc] Cancel[/]"
        ),
        "notify_lang_switched": "Language switched to English",
        "handover_prompt_footer": "Please continue assisting based on the cross-session context above:",
    },
    "zh": {
        "top_hint": "Session 內：空白輸入按 ← 或 Alt+← 返回",
        "scope_all": "全部 Workspace",
        "scope_ws": "工作目錄：{path}",
        "active_count": "執行中：{n}",
        "tree_badge": "樹狀",
        "waiting_badge": "⚠ 待權限：{n} (w)",
        "selected_badge": "已選：{n}",
        "search_placeholder": "搜尋標題、目錄或對話全文... (Esc 關閉)",
        "sec_active": "執行中 SESSIONS ({n})",
        "sec_history": "歷史紀錄 ({n})",
        "sec_live_windows": "即時視窗 ({n})",
        "sec_tree": "SESSION 樹狀檢視 ({n})",
        "empty_list": "找不到任何 session，按 'n' 開啟新對話。",
        "hotkey_bar": (
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
            "[bold #7aa2f7]Tab[/] 範圍  "
            "[bold #7aa2f7]l[/] EN  "
            "[bold #e0af68]q[/] 離開"
        ),
        "modal_new_title": "新增 AGY Session",
        "modal_new_cwd": "Workspace 目錄：",
        "modal_new_args": "額外 agy 參數（選填，例如 --mode plan）：",
        "btn_launch": "啟動",
        "btn_cancel": "取消",
        "btn_cancel_esc": "取消 (Esc)",
        "btn_save": "儲存",
        "btn_send": "送出",
        "modal_rename_title": "重新命名 Session（留空以重設）",
        "modal_msg_title": "傳送訊息給 Session",
        "modal_msg_placeholder": "輸入要傳送的指令或訊息... (Enter 送出 / Esc 取消)",
        "modal_handover_title": "跨 Session 上下文轉交",
        "modal_handover_from": '來源："{title}" ({cid})',
        "modal_handover_pick": "選擇目標 session (↑/↓)：",
        "modal_handover_edit": "轉交內容（可編輯，Ctrl+S 送出）：",
        "btn_send_handover": "送出轉交 (Ctrl+S)",
        "modal_split_title": "雙視窗並排監看 (v)",
        "modal_split_left": '左側視窗："{title}" ({cid})',
        "modal_split_pick": "選擇右側視窗 session (↑/↓ + Enter)：",
        "btn_open_split": "開啟並排",
        "split_unsplit_opt": "[bold #e0af68]⊟ 取消並排（將此 session 拆回獨立視窗）[/]",
        "tag_active": "[#9ece6a](執行中)[/]",
        "tag_external": "[#bb9af7](外部開啟)[/]",
        "tag_history": "[dim](歷史)[/]",
        "preview_none": "[dim]尚未選取 session[/]",
        "preview_live_hint": "[#9ece6a]● 即時 tmux session（按 Enter 切換進入）[/]",
        "preview_empty_screen": "(空白畫面)",
        "preview_no_transcript": "(尚無對話紀錄)",
        "preview_no_preview": "(無可用預覽內容)",
        "status_waiting": "[bold #f7768e]⚠ 等待權限確認 / 輸入[/]",
        "status_running": "[bold #73daca]● 執行中 (RUNNING)[/]",
        "status_background": "[bold #e0af68]◐ 背景任務執行中[/]",
        "status_active_idle": "[bold #9ece6a]● 背景待命中 (ACTIVE)[/]",
        "status_external_idle": "[bold #bb9af7]◉ 於其他終端開啟中[/]",
        "status_history": "[dim]○ 歷史紀錄[/]",
        "lbl_window": "視窗：",
        "lbl_dir": "目錄：",
        "lbl_id": "ID：",
        "lbl_parent": "父對話：",
        "lbl_agent": "代理：",
        "lbl_you": "你",
        "mode_tmux": "背景執行視窗",
        "mode_bg": "背景 agy -p",
        "msg_target_unlinked": '目標："{title}"（背景執行視窗）',
        "msg_target_one": '目標："{title}"（{mode}）',
        "msg_target_broadcast": "廣播至 {total} 個 sessions（{live} 個執行中視窗、{bg} 個背景 -p）",
        "notify_msg_skipped_only": "略過 {n} 個在其他終端開啟中的 session（請先在 agym 內開啟）",
        "notify_msg_partial": "已送出 {ok} 個，失敗 {fail} 個{extra}",
        "notify_msg_partial_ext": "，略過外部開啟 {n} 個",
        "notify_msg_sent": "已送出訊息給 {n} 個 session",
        "notify_handover_need_saved": "請先選取一個已儲存的來源 session",
        "notify_handover_no_target": "目前沒有其他可轉交的目標 session",
        "notify_handover_empty": "轉交內容不可為空",
        "notify_handover_missing": "目標 session 已不存在",
        "notify_handover_ext": '"{title}" 正在其他終端開啟中，請先在 agym 內開啟後再轉交',
        "notify_handover_ok": '已將上下文轉交給 "{title}"',
        "notify_handover_fail": '轉交給 "{title}" 失敗',
        "notify_waiting_ext": '"{title}" 正在其他終端等待確認',
        "notify_waiting_located": '已定位到等待確認的 "{title}"（按 Enter 開啟）',
        "notify_waiting_none": "目前沒有等待權限確認的 session",
        "notify_split_ext": '"{title}" 正在其他終端開啟中，無法在 agym 內並排',
        "notify_split_fail": "開啟並排視窗失敗",
        "notify_split_need_two": "請剛好選取 2 個 session 進行並排（目前選取 {n} 個）",
        "notify_split_need_saved": "請先選取一個已儲存的 session",
        "notify_split_no_target": "目前沒有其他可並排的 session",
        "notify_unsplit_ok": '已將 "{title}" 拆回獨立視窗',
        "notify_unsplit_fail": "取消並排失敗",
        "notify_target_missing": "目標 session 已不存在",
        "notify_renamed_live": '已更名為 "{name}"（已同步至 AGY；開啟中的視窗重開後生效）',
        "notify_renamed": '已更名為 "{name}"',
        "notify_unsaved_delete": "尚未存檔的 session 視窗 — 請按 'k' 關閉。",
        "notify_deleted_partial": "已刪除 {deleted} 個，失敗 {failed} 個：{err}",
        "notify_deleted_one": "已刪除 1 個 session。",
        "notify_deleted_many": "已刪除 {n} 個 sessions。",
        "confirm_live_warn": " [bold #e0af68]（包含執行中項目！）[/]",
        "confirm_delete_one": (
            '[bold #f7768e]⚠ 確定刪除 "{title}" ({cid})？[/]{warn}  '
            "[bold #f7768e]\\[d][/] 確認刪除  [dim]\\[Esc] 取消[/]"
        ),
        "confirm_delete_many": (
            "[bold #f7768e]⚠ 確定刪除已選的 {n} 個 sessions？[/]{warn}  "
            "[bold #f7768e]\\[d][/] 確認刪除  [dim]\\[Esc] 取消[/]"
        ),
        "confirm_quit": (
            "[bold #e0af68]離開 AGY Session Manager（背景執行中：{n}）：[/]  "
            "[bold #9ece6a]\\[q][/] 保持背景執行 (detach)  "
            "[bold #f7768e]\\[k][/] 全部關閉並離開  "
            "[dim]\\[Esc] 取消[/]"
        ),
        "notify_lang_switched": "已切換語言為繁體中文",
        "handover_prompt_footer": "請根據以上來自另一個 session 的上下文繼續協助：",
    },
}

_current_lang: Optional[str] = None


def _normalize_lang(raw: str) -> Optional[str]:
    val = (raw or "").strip().lower()
    if not val:
        return None
    if val.startswith("zh"):
        return "zh"
    if val.startswith("en"):
        return "en"
    return None


def detect_system_lang() -> str:
    """Detect language from AGYM_LANG env var, saved meta preference, or system locale."""
    env_override = _normalize_lang(os.environ.get("AGYM_LANG", ""))
    if env_override:
        return env_override

    try:
        import data

        saved = _normalize_lang(str(data.load_meta().get("lang", "")))
        if saved:
            return saved
    except Exception:
        pass

    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "").strip().lower()
        if not val or val in ("c", "posix"):
            continue
        if val.startswith("zh"):
            return "zh"
        return "en"

    return "en"


def get_lang() -> str:
    global _current_lang
    if _current_lang is None:
        _current_lang = detect_system_lang()
    return _current_lang


def set_lang(lang: str, persist: bool = True) -> str:
    global _current_lang
    norm = _normalize_lang(lang) or "en"
    _current_lang = norm
    if persist:
        try:
            import data

            meta = data.load_meta()
            meta["lang"] = norm
            data.save_meta(meta)
        except Exception:
            pass
    return norm


def toggle_lang(persist: bool = True) -> str:
    return set_lang("en" if get_lang() == "zh" else "zh", persist=persist)


def reset_cached_lang() -> None:
    """Clear cached language (useful for tests)."""
    global _current_lang
    _current_lang = None


def t(key: str, **kwargs: object) -> str:
    lang = get_lang()
    table = STRINGS.get(lang, STRINGS["en"])
    template = table.get(key) or STRINGS["en"].get(key, key)
    if kwargs:
        return template.format(**kwargs)
    return template
