from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Book:
    id: str
    title: str
    author: str
    duration: float
    cover_url: str
    current_time: float = 0
    progress: float = 0
    series_name: str = ""
    series_sequence: str = ""
    series_total: int = 0
    finished: bool = False
    last_update: float = 0
    author_names: tuple[str, ...] = ()

    @property
    def has_play_history(self) -> bool:
        return self.current_time > 0 and not self.is_finished

    @property
    def is_finished(self) -> bool:
        return self.finished or self.progress >= 0.995

    @property
    def is_in_progress(self) -> bool:
        return self.current_time > 0 and not self.is_finished

    @property
    def authors(self) -> tuple[str, ...]:
        if self.author_names:
            return self.author_names
        author = self.author.strip()
        return (author,) if author else ()

    @property
    def display_title(self) -> str:
        return self.title.strip()

    @property
    def series_position(self) -> str:
        if not self.series_sequence or self.series_total < 2:
            return ""
        return f"{self.series_sequence}/{self.series_total}"


@dataclass
class AudioTrack:
    index: int
    start_offset: float
    duration: float
    url: str
    title: str


@dataclass
class Chapter:
    index: int
    title: str
    start: float
    end: float


@dataclass
class PlaybackSession:
    id: str
    library_item_id: str
    title: str
    author: str
    duration: float
    current_time: float
    cover_url: str
    tracks: list[AudioTrack]
    chapters: list[Chapter]
