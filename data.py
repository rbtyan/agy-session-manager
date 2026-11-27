"""Read-only data layer for AGY Session Manager."""

from __future__ import annotations

import dataclasses
import datetime
import fcntl
import json
import os
import re
import shutil
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Optional

AGY_DIR = Path.home() / ".gemini" / "antigravity-cli"
DB_PATH = AGY_DIR / "conversation_summaries.db"
JETBOX_PB_PATH = AGY_DIR / "jetbox_summaries_proto.pb"
BRAIN_DIR = AGY_DIR / "brain"
CONVERSATIONS_DIR = AGY_DIR / "conversations"
ANNOTATIONS_DIR = AGY_DIR / "annotations"
IMPLICIT_DIR = AGY_DIR / "implicit"
PRESENCE_DIR = AGY_DIR / "presence"
LAST_CONV_CACHE_PATH = AGY_DIR / "cache" / "last_conversations.json"
META_PATH = Path.home() / ".config" / "agy-session-manager" / "meta.json"

USER_REQ_RE = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.DOTALL)


@dataclasses.dataclass
class SessionInfo:
    conversation_id: str
    title: str
    preview: str
    step_count: int
    last_modified_time: str
    last_modified_ts: float
    workspace_path: str
    status: str  # CASCADE_RUN_STATUS_RUNNING, CASCADE_RUN_STATUS_IDLE, etc.
    not_fully_idle: bool
    parent_conversation_id: str = ""
    agent_name: str = ""
    # Enriched runtime fields
    tmux_window_id: Optional[str] = None
    tmux_window_name: Optional[str] = None
    is_externally_locked: bool = False
    alias: Optional[str] = None
    pinned: bool = False

    @property
    def display_title(self) -> str:
        if self.alias:
            return self.alias
        return self.title.strip() or "(Untitled Session)"

    @property
    def is_active_in_tmux(self) -> bool:
        return self.tmux_window_id is not None

    @property
    def is_live(self) -> bool:
        return self.is_active_in_tmux or self.is_externally_locked

    @property
    def state_kind(self) -> str:
        """Return one of: running, background, active_idle, external_idle, history."""
        if "RUNNING" in self.status:
            return "running"
        if self.not_fully_idle:
            return "background"
        if self.is_active_in_tmux:
            return "active_idle"
        if self.is_externally_locked:
            return "external_idle"
        return "history"


def parse_workspace_uri(raw: str) -> str:
    if not raw:
        return ""
    try:
        items = json.loads(raw)
        if isinstance(items, list) and items:
            uri = str(items[0])
            if uri.startswith("file://"):
                return urllib.parse.unquote(uri[len("file://") :])
            return uri
    except Exception:
        pass
    return raw


def parse_timestamp(ts_str: str) -> float:
    if not ts_str:
        return 0.0
    # Format like: 2026-11-26 17:09:19.534763858+00:00
    s = ts_str.strip().replace(" ", "T")
    # Truncate nanoseconds to microseconds for Python fromisoformat
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(.*)$", s)
    if m:
        base, frac, tz = m.groups()
        if frac:
            frac = frac[:6].ljust(6, "0")
            s = f"{base}.{frac}{tz}"
        else:
            s = f"{base}{tz}"
    try:
        dt = datetime.datetime.fromisoformat(s)
        return dt.timestamp()
    except Exception:
        return 0.0


def format_relative_time(ts: float) -> str:
    if ts <= 0:
        return ""
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    diff = max(0, int(now - ts))
    if diff < 60:
        return f"{diff}s ago"
    if diff < 3600:
        return f"{diff // 60}m ago"
    if diff < 86400:
        return f"{diff // 3600}h ago"
    if diff < 86400 * 30:
        return f"{diff // 86400}d ago"
    if diff < 86400 * 365:
        return f"{diff // (86400 * 30)}mo ago"
    return f"{diff // (86400 * 365)}y ago"


def shorten_path(path: str, max_len: int = 36) -> str:
    if not path:
        return "(no workspace)"
    home = str(Path.home())
    if path.startswith(home):
        path = "~" + path[len(home) :]
    if len(path) <= max_len:
        return path
    parts = path.split("/")
    if len(parts) <= 3:
        return "..." + path[-(max_len - 3) :]
    tail = "/".join(parts[-2:])
    if len(tail) + 4 <= max_len:
        return f"{parts[0]}/.../{tail}"
    return "..." + path[-(max_len - 3) :]


def load_meta() -> dict:
    if not META_PATH.exists():
        return {"aliases": {}, "pinned": []}
    try:
        with META_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"aliases": {}, "pinned": []}
        data.setdefault("aliases", {})
        data.setdefault("pinned", [])
        return data
    except Exception:
        return {"aliases": {}, "pinned": []}


def save_meta(meta: dict) -> None:
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = META_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    tmp.replace(META_PATH)


def toggle_pin(conversation_id: str) -> bool:
    meta = load_meta()
    pinned = list(meta.get("pinned", []))
    if conversation_id in pinned:
        pinned.remove(conversation_id)
        is_pinned = False
    else:
        pinned.append(conversation_id)
        is_pinned = True
    meta["pinned"] = pinned
    save_meta(meta)
    return is_pinned


def set_alias(conversation_id: str, alias: str) -> None:
    meta = load_meta()
    aliases = dict(meta.get("aliases", {}))
    cleaned = alias.strip()
    if cleaned:
        aliases[conversation_id] = cleaned
    else:
        aliases.pop(conversation_id, None)
    meta["aliases"] = aliases
    save_meta(meta)


def check_presence_lock(conversation_id: str) -> bool:
    """Return True if another process holds an flock on presence/<id>.lock."""
    lock_file = PRESENCE_DIR / f"{conversation_id}.lock"
    if not lock_file.exists():
        return False
    fd = None
    try:
        fd = os.open(str(lock_file), os.O_RDONLY)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Acquired lock -> no active process holds it
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except BlockingIOError:
        return True
    except OSError:
        return False
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _connect_ro() -> Optional[sqlite3.Connection]:
    if not DB_PATH.exists():
        return None
    try:
        uri = f"file:{DB_PATH}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=1.0)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def search_fts_ids(query: str, limit: int = 80) -> Optional[set[str]]:
    """Run FTS5 full-text search across conversation bodies, titles, and workspaces."""
    q = query.strip()
    if not q:
        return None
    conn = _connect_ro()
    if conn is None:
        return None
    try:
        # Quote tokens safely for FTS5 prefix search
        tokens = [t.replace('"', '""') for t in q.split() if t.strip()]
        if not tokens:
            return None
        fts_expr = " AND ".join(f'"{t}"*' for t in tokens)
        rows = conn.execute(
            "SELECT DISTINCT conversation_id FROM conversations_fts WHERE conversations_fts MATCH ? LIMIT ?",
            (fts_expr, limit),
        ).fetchall()
        return {r["conversation_id"] for r in rows}
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def fetch_sessions(
    limit: int = 200,
    workspace_filter: Optional[str] = None,
    search_query: str = "",
) -> list[SessionInfo]:
    """Fetch conversation summaries from SQLite (read-only) merged with sidecar meta."""
    conn = _connect_ro()
    if conn is None:
        return []

    meta = load_meta()
    aliases: dict[str, str] = meta.get("aliases", {})
    pinned_set: set[str] = set(meta.get("pinned", []))

    fts_ids: Optional[set[str]] = None
    q_lower = search_query.strip().lower()
    if q_lower:
        fts_ids = search_fts_ids(q_lower)

    try:
        rows = conn.execute(
            """
            SELECT conversation_id, title, preview, step_count,
                   last_modified_time, workspace_uris, status,
                   not_fully_idle, parent_conversation_id, agent_name,
                   source, app_data_dir
            FROM conversation_summaries
            WHERE killed = 0
            ORDER BY last_modified_time DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    norm_filter = os.path.realpath(workspace_filter) if workspace_filter else None
    results: list[SessionInfo] = []

    for r in rows:
        cid = r["conversation_id"]
        locked = check_presence_lock(cid)
        app_dir = str(r["app_data_dir"] or "")
        # Skip ghost summaries re-hydrated from jetbox_summaries_proto.pb after local files were deleted
        if (
            app_dir in ("", "antigravity-cli")
            and not locked
            and not (CONVERSATIONS_DIR / f"{cid}.db").exists()
            and not (BRAIN_DIR / cid).exists()
        ):
            continue

        ws = parse_workspace_uri(r["workspace_uris"] or "")
        if norm_filter:
            if not ws:
                continue
            try:
                if os.path.realpath(ws) != norm_filter:
                    continue
            except OSError:
                if ws != workspace_filter:
                    continue

        alias = aliases.get(cid)
        title = r["title"] or ""
        preview = r["preview"] or ""

        if q_lower:
            haystack = f"{cid} {title} {alias or ''} {ws} {preview}".lower()
            in_meta = q_lower in haystack
            in_fts = fts_ids is not None and cid in fts_ids
            if not (in_meta or in_fts):
                continue

        status_str = str(r["status"] or "")
        not_idle = bool(r["not_fully_idle"])

        results.append(
            SessionInfo(
                conversation_id=cid,
                title=title,
                preview=preview,
                step_count=int(r["step_count"] or 0),
                last_modified_time=str(r["last_modified_time"] or ""),
                last_modified_ts=parse_timestamp(str(r["last_modified_time"] or "")),
                workspace_path=ws,
                status=status_str,
                not_fully_idle=not_idle,
                parent_conversation_id=str(r["parent_conversation_id"] or ""),
                agent_name=str(r["agent_name"] or ""),
                is_externally_locked=locked,
                alias=alias,
                pinned=(cid in pinned_set),
            )
        )

    return results


def load_transcript_preview(conversation_id: str, max_messages: int = 8) -> list[tuple[str, str]]:
    """Return list of (role, text) tuples from the tail of transcript.jsonl."""
    path = BRAIN_DIR / conversation_id / ".system_generated" / "logs" / "transcript.jsonl"
    if not path.exists():
        return []

    messages: list[tuple[str, str]] = []
    try:
        # Read tail efficiently (up to last 256 KB)
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > 262144:
                f.seek(size - 262144)
                f.readline()  # discard partial first line
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        step_type = obj.get("type", "")
        source = obj.get("source", "")

        if step_type == "USER_INPUT" and source == "USER_EXPLICIT":
            content = str(obj.get("content", ""))
            m = USER_REQ_RE.search(content)
            text = m.group(1).strip() if m else content.strip()
            if text:
                messages.append(("USER", text[:600]))
        elif step_type == "PLANNER_RESPONSE":
            # Look for visible response text across possible keys
            text = (
                obj.get("response")
                or obj.get("content")
                or obj.get("text")
                or obj.get("message")
                or ""
            )
            if isinstance(text, str) and text.strip():
                messages.append(("AGENT", text.strip()[:700]))

    return messages[-max_messages:]


def _read_varint(buf: bytes, idx: int) -> tuple[int, int]:
    val = 0
    shift = 0
    while idx < len(buf):
        b = buf[idx]
        idx += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, idx
        shift += 7
    raise ValueError("truncated varint")


def _strip_jetbox_pb(remove_ids: set[str]) -> None:
    """Remove deleted conversation_id entries from jetbox_summaries_proto.pb.

    AGY mirrors conversation summaries in this protobuf map (top-level field 1,
    wire type 2, sub-field 1 = conversation_id string). If not stripped here,
    AGY re-hydrates deleted rows back into conversation_summaries.db on restart.
    """
    if not remove_ids or not JETBOX_PB_PATH.exists():
        return
    try:
        raw = JETBOX_PB_PATH.read_bytes()
    except OSError:
        return

    out = bytearray()
    i = 0
    n = len(raw)
    changed = False
    try:
        while i < n:
            start = i
            tag, i = _read_varint(raw, i)
            field_num = tag >> 3
            wire_type = tag & 7
            if wire_type == 0:
                _, i = _read_varint(raw, i)
                out.extend(raw[start:i])
            elif wire_type == 1:
                i += 8
                out.extend(raw[start:i])
            elif wire_type == 2:
                length, i = _read_varint(raw, i)
                payload_start = i
                i += length
                if i > n:
                    return
                drop = False
                if field_num == 1 and length > 2 and raw[payload_start] == 0x0A:
                    slen, sidx = _read_varint(raw, payload_start + 1)
                    if sidx + slen <= i:
                        cid = raw[sidx : sidx + slen].decode("utf-8", errors="ignore")
                        if cid in remove_ids:
                            drop = True
                            changed = True
                if not drop:
                    out.extend(raw[start:i])
            elif wire_type == 5:
                i += 4
                out.extend(raw[start:i])
            else:
                # Unknown wire type: abort safely without modifying file
                return
    except Exception:
        return

    if changed:
        try:
            tmp = JETBOX_PB_PATH.with_suffix(".tmp")
            tmp.write_bytes(bytes(out))
            tmp.replace(JETBOX_PB_PATH)
        except OSError:
            pass


def delete_sessions(conversation_ids: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Permanently delete sessions from AGY DB, disk artifacts, cache, and sidecar meta.

    Returns (deleted_ids, failed_list[(cid, error_message)]).
    """
    unique_ids = list(dict.fromkeys(cid for cid in conversation_ids if cid))
    if not unique_ids:
        return [], []

    deleted: list[str] = []
    failed: list[tuple[str, str]] = []

    # 1. Remove rows from conversation_summaries.db in a single short WAL-safe transaction
    if DB_PATH.exists():
        conn = None
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
            conn.execute("PRAGMA busy_timeout = 5000")
            with conn:
                for cid in unique_ids:
                    conn.execute("DELETE FROM conversation_summaries WHERE conversation_id = ?", (cid,))
                    try:
                        conn.execute("DELETE FROM conversations_fts WHERE conversation_id = ?", (cid,))
                    except sqlite3.Error:
                        pass
                    try:
                        conn.execute(
                            "DELETE FROM conversation_parents WHERE conversation_id = ? OR parent_id = ?",
                            (cid, cid),
                        )
                    except sqlite3.Error:
                        pass
        except sqlite3.Error as exc:
            for cid in unique_ids:
                failed.append((cid, f"DB error: {exc}"))
            return deleted, failed
        finally:
            if conn is not None:
                conn.close()

    # 1b. Strip entries from jetbox_summaries_proto.pb so AGY doesn't re-hydrate them
    _strip_jetbox_pb(set(unique_ids))

    # 2. Remove per-conversation files & directories on disk
    for cid in unique_ids:
        errs: list[str] = []
        # conversations/<cid>.db (+ -wal, -shm)
        for suffix in ("", "-wal", "-shm"):
            p = CONVERSATIONS_DIR / f"{cid}.db{suffix}"
            try:
                if p.exists():
                    p.unlink()
            except OSError as exc:
                errs.append(str(exc))

        # brain/<cid>/
        brain_path = BRAIN_DIR / cid
        try:
            if brain_path.exists():
                shutil.rmtree(brain_path)
        except OSError as exc:
            errs.append(str(exc))

        # annotations/<cid>.pbtxt & presence/<cid>.lock
        for p in (ANNOTATIONS_DIR / f"{cid}.pbtxt", PRESENCE_DIR / f"{cid}.lock"):
            try:
                if p.exists():
                    p.unlink()
            except OSError as exc:
                errs.append(str(exc))

        # implicit/<cid>* if any
        if IMPLICIT_DIR.exists():
            for p in IMPLICIT_DIR.glob(f"{cid}*"):
                try:
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                except OSError as exc:
                    errs.append(str(exc))

        if errs:
            failed.append((cid, "; ".join(errs)))
        else:
            deleted.append(cid)

    deleted_set = set(deleted)

    # 3. Clean cache/last_conversations.json
    if deleted_set and LAST_CONV_CACHE_PATH.exists():
        try:
            with LAST_CONV_CACHE_PATH.open("r", encoding="utf-8") as f:
                cache = json.load(f)
            if isinstance(cache, dict):
                new_cache = {k: v for k, v in cache.items() if v not in deleted_set}
                if len(new_cache) != len(cache):
                    tmp = LAST_CONV_CACHE_PATH.with_suffix(".tmp")
                    with tmp.open("w", encoding="utf-8") as f:
                        json.dump(new_cache, f, indent=2)
                    tmp.replace(LAST_CONV_CACHE_PATH)
        except Exception:
            pass

    # 4. Clean sidecar metadata (aliases & pinned)
    if deleted_set:
        try:
            meta = load_meta()
            aliases = meta.get("aliases", {})
            pinned = meta.get("pinned", [])
            changed = False
            for cid in deleted_set:
                if cid in aliases:
                    del aliases[cid]
                    changed = True
            new_pinned = [c for c in pinned if c not in deleted_set]
            if len(new_pinned) != len(pinned):
                meta["pinned"] = new_pinned
                changed = True
            if changed:
                meta["aliases"] = aliases
                save_meta(meta)
        except Exception:
            pass

    return deleted, failed

