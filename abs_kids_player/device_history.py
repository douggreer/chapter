from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import PlaybackSession
from .storage import ensure_storage_directory, finalize_storage_file


HISTORY_PATH = Path.home() / ".local" / "state" / "abs-kids-player" / "device-playback-history.json"
MAX_DEVICE_HISTORY_ITEMS = 50
_HISTORY_LOCK = threading.RLock()


@dataclass(frozen=True)
class DevicePlaybackEntry:
    book_id: str
    title: str
    author: str
    current_time: float
    duration: float
    started_at: float
    last_played_at: float


def record_device_playback(
    session: PlaybackSession,
    current_time: float | None = None,
    played_at: float | None = None,
) -> None:
    book_id = session.library_item_id.strip()
    if not book_id:
        return
    now = time.time() if played_at is None else played_at
    position = session.current_time if current_time is None else current_time
    entry = DevicePlaybackEntry(
        book_id=book_id,
        title=session.title,
        author=session.author,
        current_time=max(0.0, min(position, session.duration)) if session.duration > 0 else max(0.0, position),
        duration=max(0.0, session.duration),
        started_at=now,
        last_played_at=now,
    )
    with _HISTORY_LOCK:
        history = _read_history_unlocked()
        existing = next((item for item in history if item.book_id == book_id), None)
        if existing is not None:
            entry = DevicePlaybackEntry(
                book_id=entry.book_id,
                title=entry.title or existing.title,
                author=entry.author or existing.author,
                current_time=entry.current_time,
                duration=entry.duration or existing.duration,
                started_at=existing.started_at,
                last_played_at=now,
            )
        history = [entry, *(item for item in history if item.book_id != book_id)][:MAX_DEVICE_HISTORY_ITEMS]
        _write_history_unlocked(history)


def load_device_playback_history(limit: int = MAX_DEVICE_HISTORY_ITEMS) -> list[DevicePlaybackEntry]:
    with _HISTORY_LOCK:
        return _read_history_unlocked()[: max(0, limit)]


def clear_device_playback_history() -> None:
    with _HISTORY_LOCK:
        _write_history_unlocked([])


def _read_history_unlocked() -> list[DevicePlaybackEntry]:
    try:
        raw = json.loads(device_history_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    entries: list[DevicePlaybackEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            entry = DevicePlaybackEntry(
                book_id=str(item.get("book_id", "")).strip(),
                title=str(item.get("title", "")),
                author=str(item.get("author", "")),
                current_time=max(0.0, float(item.get("current_time") or 0)),
                duration=max(0.0, float(item.get("duration") or 0)),
                started_at=max(0.0, float(item.get("started_at") or 0)),
                last_played_at=max(0.0, float(item.get("last_played_at") or 0)),
            )
        except (TypeError, ValueError):
            continue
        if entry.book_id and entry.title:
            entries.append(entry)
    entries.sort(key=lambda entry: entry.last_played_at, reverse=True)
    return entries[:MAX_DEVICE_HISTORY_ITEMS]


def _write_history_unlocked(history: list[DevicePlaybackEntry]) -> None:
    path = device_history_path()
    temporary_path = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        ensure_storage_directory(path.parent)
        temporary_path.write_text(
            json.dumps([asdict(entry) for entry in history], indent=2),
            encoding="utf-8",
        )
        finalize_storage_file(temporary_path)
        temporary_path.replace(path)
        finalize_storage_file(path)
    except OSError as error:
        print(f"Device playback history could not be saved: {error}")
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def device_history_path() -> Path:
    configured_path = os.environ.get("ABS_KIDS_PLAYER_DEVICE_HISTORY_PATH", "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    configured_dir = os.environ.get("ABS_KIDS_PLAYER_STATE_DIR", "").strip()
    if configured_dir:
        return Path(configured_dir).expanduser() / HISTORY_PATH.name
    return HISTORY_PATH
