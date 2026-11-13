from __future__ import annotations

import base64
import binascii
import json
import math
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from . import __version__
from .models import AudioTrack, Book, Chapter, PlaybackSession


SUPPORTED_MIME_TYPES = [
    "audio/aac",
    "audio/flac",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
]
DEFAULT_REQUEST_TIMEOUT_SECONDS = 8
ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 60
_AUTH_REFRESH_LOCK = threading.Lock()

TokenLoader = Callable[[], tuple[str, str]]
TokenSaver = Callable[[str, str], None]


class AudiobookshelfError(RuntimeError):
    pass


@dataclass
class LibrarySeries:
    id: str
    name: str
    num_books: int = 0
    book_ids: set[str] = field(default_factory=set)
    book_sequences: dict[str, str] = field(default_factory=dict)


class AudiobookshelfClient:
    def __init__(
        self,
        server_url: str,
        token: str,
        refresh_token: str = "",
        token_loader: TokenLoader | None = None,
        token_saver: TokenSaver | None = None,
    ) -> None:
        self.server_url = server_url.rstrip("/") + "/"
        self.token = token
        self.refresh_token = refresh_token
        self.token_loader = token_loader
        self.token_saver = token_saver

    def _url(self, path: str, query: dict[str, Any] | None = None) -> str:
        url = urljoin(self.server_url, path.lstrip("/"))
        if query:
            return f"{url}?{urlencode(query)}"
        return url

    def authenticated_media_url(self, path: str) -> str:
        self.ensure_valid_access_token()
        parsed = urlparse(urljoin(self.server_url, path.lstrip("/")))
        query_items = [(key, value) for key, value in parse_qsl(parsed.query) if key != "token"]
        query_items.append(("token", self.token))
        query = urlencode(query_items)
        return urlunparse(parsed._replace(query=query))

    @classmethod
    def login(cls, server_url: str, username: str, password: str) -> tuple["AudiobookshelfClient", dict[str, Any]]:
        server_url = server_url.rstrip("/") + "/"
        body = json.dumps({"username": username, "password": password}).encode("utf-8")
        request = Request(
            urljoin(server_url, "login"),
            data=body,
            headers={"Content-Type": "application/json", "x-return-tokens": "true"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise AudiobookshelfError(f"Audiobookshelf login failed with {error.code}: {details}") from error
        except TimeoutError as error:
            raise AudiobookshelfError("Audiobookshelf request timed out.") from error
        except URLError as error:
            raise AudiobookshelfError(f"Could not reach Audiobookshelf: {error.reason}") from error

        token = extract_login_token(data)
        if not token:
            raise AudiobookshelfError("Audiobookshelf login did not return a user token.")
        return cls(server_url, token, extract_refresh_token(data)), data

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | list[Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> Any:
        return self._request(method, path, body=body, query=query, allow_refresh=True)

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | list[Any] | None,
        query: dict[str, Any] | None,
        allow_refresh: bool,
    ) -> Any:
        data = None
        failed_token = self.token
        headers = {"Authorization": f"Bearer {self.token}"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(self._url(path, query), data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS) as response:
                payload = response.read()
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            if error.code == 401 and allow_refresh and self.refresh_access_token(failed_token):
                return self._request(method, path, body=body, query=query, allow_refresh=False)
            raise AudiobookshelfError(f"Audiobookshelf returned {error.code}: {details}") from error
        except TimeoutError as error:
            raise AudiobookshelfError("Audiobookshelf request timed out.") from error
        except URLError as error:
            raise AudiobookshelfError(f"Could not reach Audiobookshelf: {error.reason}") from error

        if not payload:
            return None

        try:
            return json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            return payload

    def refresh_access_token(self, failed_token: str | None = None) -> bool:
        with _AUTH_REFRESH_LOCK:
            if self.token_loader is not None:
                stored_token, stored_refresh_token = self.token_loader()
                if stored_token and failed_token and stored_token != failed_token:
                    self.token = stored_token
                    self.refresh_token = stored_refresh_token
                    return True
                if stored_refresh_token:
                    self.refresh_token = stored_refresh_token

            if not self.refresh_token:
                return False

            request = Request(
                self._url("/auth/refresh"),
                data=b"",
                headers={"x-refresh-token": self.refresh_token},
                method="POST",
            )
            try:
                with urlopen(request, timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                error.read()
                raise AudiobookshelfError(
                    "Audiobookshelf login expired. Sign in again from the Chapter admin page."
                ) from error
            except TimeoutError as error:
                raise AudiobookshelfError("Audiobookshelf token refresh timed out.") from error
            except URLError as error:
                raise AudiobookshelfError(f"Could not reach Audiobookshelf: {error.reason}") from error
            except json.JSONDecodeError as error:
                raise AudiobookshelfError("Audiobookshelf returned an invalid token refresh response.") from error

            token = extract_login_token(data)
            if not token:
                raise AudiobookshelfError("Audiobookshelf token refresh did not return an access token.")
            refresh_token = extract_refresh_token(data) or self.refresh_token
            self.token = token
            self.refresh_token = refresh_token
            if self.token_saver is not None:
                self.token_saver(token, refresh_token)
            return True

    def ensure_valid_access_token(self, skew_seconds: int = ACCESS_TOKEN_REFRESH_SKEW_SECONDS) -> None:
        expires_at = jwt_expiration(self.token)
        if expires_at is None or expires_at - time.time() > skew_seconds:
            return
        self.refresh_access_token(self.token)

    def get_libraries(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/api/libraries")
        if isinstance(data, list):
            return list(data)
        return list(data.get("libraries", []))

    def choose_library_id(self, configured_id: str = "") -> str:
        if configured_id:
            return configured_id

        libraries = self.get_libraries()
        for library in libraries:
            if library.get("mediaType") == "book":
                return str(library["id"])
        if libraries:
            return str(libraries[0]["id"])
        raise AudiobookshelfError("No accessible libraries were found for this token.")

    def get_current_user(self) -> dict[str, Any]:
        data = self.request("GET", "/api/me")
        if isinstance(data, dict):
            return data
        raise AudiobookshelfError("Audiobookshelf did not return current user details.")

    def get_books(self, library_id: str) -> list[Book]:
        series_catalog = self.get_series_catalog(library_id)
        data = self.request(
            "GET",
            f"/api/libraries/{library_id}/items",
            query={"sort": "media.metadata.title", "minified": 0},
        )
        try:
            user_progress = self.get_current_user().get("mediaProgress", [])
        except AudiobookshelfError as error:
            print(f"Audiobookshelf playback progress could not be loaded: {error}")
            user_progress = []
        progress_by_id: dict[str, dict[str, Any]] = {}
        progress_entries = user_progress if isinstance(user_progress, list) else []
        for progress_entry in progress_entries:
            if not isinstance(progress_entry, dict):
                continue
            item_id = str(progress_entry.get("libraryItemId") or "")
            if not item_id:
                continue
            previous = progress_by_id.get(item_id)
            try:
                last_update = float(
                    progress_entry.get("lastUpdate")
                    or progress_entry.get("progressLastUpdate")
                    or 0
                )
                previous_last_update = float(
                    (previous or {}).get("lastUpdate")
                    or (previous or {}).get("progressLastUpdate")
                    or 0
                )
            except (TypeError, ValueError):
                last_update = previous_last_update = 0
            if previous is None or last_update >= previous_last_update:
                progress_by_id[item_id] = progress_entry

        books: list[Book] = []
        series_keys: list[str] = []
        fallback_counts: dict[str, int] = {}
        fallback_highest_sequences: dict[str, int] = {}
        for item in data.get("results", []):
            media = item.get("media") or {}
            metadata = media.get("metadata") or {}
            title = metadata.get("title") or item.get("relPath") or "Untitled"
            author = author_from_metadata(metadata)
            author_names = author_names_from_metadata(metadata, author)
            cover_url = self.authenticated_media_url(f"/api/items/{item['id']}/cover")
            progress = progress_by_id.get(str(item["id"])) or extract_progress(item)
            item_id = str(item["id"])
            series_name, series_sequence, series_total = resolve_primary_series(
                metadata,
                item_id,
                series_catalog,
            )
            series_key = series_name.casefold()
            book = Book(
                id=item_id,
                title=str(title),
                author=str(author),
                duration=float(media.get("duration") or 0),
                cover_url=cover_url,
                current_time=float(progress.get("currentTime") or 0),
                progress=float(progress.get("progress") or 0),
                series_name=series_name,
                series_sequence=series_sequence,
                series_total=series_total,
                finished=bool(progress.get("isFinished", False)),
                last_update=float(
                    progress.get("lastUpdate")
                    or progress.get("progressLastUpdate")
                    or 0
                ),
                author_names=author_names,
            )
            books.append(book)
            series_keys.append(series_key)
            if series_key:
                fallback_counts[series_key] = fallback_counts.get(series_key, 0) + 1
                if series_sequence:
                    sequence_ceiling = math.ceil(float(series_sequence))
                    fallback_highest_sequences[series_key] = max(
                        fallback_highest_sequences.get(series_key, 0),
                        sequence_ceiling,
                    )

        for book, series_key in zip(books, series_keys):
            if not series_key:
                continue
            book.series_total = max(
                book.series_total,
                fallback_counts.get(series_key, 0),
                fallback_highest_sequences.get(series_key, 0),
            )
        return books

    def get_series_totals(self, library_id: str) -> dict[str, int]:
        return {
            series.name.casefold(): series.num_books
            for series in self.get_series_catalog(library_id)
            if series.name and series.num_books > 0
        }

    def get_series_catalog(self, library_id: str) -> list[LibrarySeries]:
        page_size = 100
        page = 0
        rows: list[Any] = []
        try:
            while True:
                data = self.request(
                    "GET",
                    f"/api/libraries/{library_id}/series",
                    query={"limit": page_size, "page": page},
                )
                page_rows = data.get("results", []) if isinstance(data, dict) else data
                if not isinstance(page_rows, list):
                    break
                rows.extend(page_rows)
                if not isinstance(data, dict):
                    break
                try:
                    total = int(data.get("total") or 0)
                except (TypeError, ValueError):
                    total = 0
                if not page_rows or len(page_rows) < page_size or (total and len(rows) >= total):
                    break
                page += 1
        except AudiobookshelfError as error:
            print(f"Audiobookshelf series catalog could not be loaded: {error}")
            return []

        catalog: list[LibrarySeries] = []
        for series in rows or []:
            if not isinstance(series, dict):
                continue
            name = str(series.get("name") or "").strip()
            if not name:
                continue
            catalog_entry = LibrarySeries(
                id=str(series.get("id") or "").strip(),
                name=name,
            )
            library_item_ids = series.get("libraryItemIds") or []
            if isinstance(library_item_ids, list):
                catalog_entry.book_ids.update(
                    str(item_id).strip()
                    for item_id in library_item_ids
                    if str(item_id).strip()
                )
            members = series.get("books") or series.get("items") or []
            if isinstance(members, list):
                for member in members:
                    if not isinstance(member, dict):
                        continue
                    item = member.get("libraryItem") or member.get("item") or member
                    if not isinstance(item, dict):
                        continue
                    item_id = str(
                        item.get("id")
                        or member.get("libraryItemId")
                        or member.get("itemId")
                        or ""
                    ).strip()
                    if not item_id:
                        continue
                    catalog_entry.book_ids.add(item_id)
                    sequence = normalized_series_sequence(
                        member.get("seriesSequence")
                        or member.get("sequence")
                        or item.get("seriesSequence")
                    )
                    if sequence:
                        catalog_entry.book_sequences[item_id] = sequence
            try:
                catalog_entry.num_books = int(series.get("numBooks") or 0)
            except (TypeError, ValueError):
                catalog_entry.num_books = 0
            catalog_entry.num_books = max(catalog_entry.num_books, len(catalog_entry.book_ids))
            catalog.append(catalog_entry)
        return catalog

    def get_progress(self, item_id: str) -> dict[str, Any] | None:
        try:
            return self.request("GET", f"/api/me/progress/{item_id}")
        except AudiobookshelfError as error:
            if "404" in str(error):
                return None
            raise

    def start_playback(self, item_id: str, start_over: bool = False, resume_time: float = 0) -> PlaybackSession:
        saved_progress = {} if start_over else self.get_progress(item_id) or {}
        session = self.request(
            "POST",
            f"/api/items/{item_id}/play",
            body={
                "deviceInfo": {
                    "clientName": "ABS Kids Player",
                    "clientVersion": __version__,
                    "manufacturer": "Raspberry Pi",
                    "model": "Ubuntu",
                },
                "mediaPlayer": "gstreamer",
                "supportedMimeTypes": SUPPORTED_MIME_TYPES,
            },
        )
        current_time = 0 if start_over else progress_current_time(saved_progress, {"currentTime": resume_time}, session)
        cover_path = session.get("coverPath") or f"/api/items/{item_id}/cover"
        tracks = [
            AudioTrack(
                index=int(track.get("index") or index + 1),
                start_offset=float(track.get("startOffset") or 0),
                duration=float(track.get("duration") or 0),
                url=self.authenticated_media_url(str(track["contentUrl"])),
                title=str(track.get("title") or ""),
            )
            for index, track in enumerate(session.get("audioTracks") or [])
            if track.get("contentUrl")
        ]
        if not tracks:
            raise AudiobookshelfError("This item did not include playable audio tracks.")

        chapters = parse_chapters(session.get("chapters") or [], session.get("duration") or 0)
        if not chapters:
            chapters = [
                Chapter(
                    index=track.index,
                    title=track.title or f"Track {track.index}",
                    start=track.start_offset,
                    end=track.start_offset + track.duration,
                )
                for track in tracks
            ]

        metadata = session.get("mediaMetadata") or {}
        author = author_from_metadata(metadata) or clean_author(session.get("displayAuthor") or "")

        return PlaybackSession(
            id=str(session["id"]),
            library_item_id=item_id,
            title=str(session.get("displayTitle") or session.get("mediaMetadata", {}).get("title") or "Untitled"),
            author=author,
            duration=float(session.get("duration") or 0),
            current_time=current_time,
            cover_url=self.authenticated_media_url(str(cover_path)),
            tracks=tracks,
            chapters=chapters,
        )

    def sync_session_progress(
        self,
        session_id: str,
        current_time: float,
        duration: float,
        time_listened: float = 0,
    ) -> None:
        self.request(
            "POST",
            f"/api/session/{session_id}/sync",
            body={
                "currentTime": current_time,
                "timeListened": max(0.0, time_listened),
                "duration": duration,
            },
        )

    def update_progress(
        self,
        item_id: str,
        current_time: float,
        duration: float,
        session_id: str = "",
        time_listened: float = 0,
    ) -> None:
        progress = min(max(current_time / duration, 0), 1) if duration else 0
        errors: list[AudiobookshelfError] = []
        synced = False

        if session_id:
            try:
                self.sync_session_progress(session_id, current_time, duration, time_listened)
                synced = True
            except AudiobookshelfError as error:
                errors.append(error)

        try:
            self.request(
                "PATCH",
                f"/api/me/progress/{item_id}",
                body={
                    "duration": duration,
                    "progress": progress,
                    "currentTime": current_time,
                    "isFinished": bool(duration and progress >= 0.995),
                },
            )
            synced = True
        except AudiobookshelfError as error:
            errors.append(error)

        if not synced and errors:
            raise errors[0]


def primary_series_from_metadata(metadata: dict[str, Any]) -> tuple[str, str]:
    raw_series = metadata.get("series") or []
    if isinstance(raw_series, dict):
        raw_series = [raw_series]

    if isinstance(raw_series, list):
        for value in raw_series:
            if not isinstance(value, dict):
                continue
            name = str(value.get("name") or value.get("series") or "").strip()
            if name:
                return name, normalized_series_sequence(value.get("sequence"))

    legacy = str(metadata.get("seriesName") or "").strip()
    match = re.match(r"^(.*?)\s+#\s*(\d+(?:\.\d+)?)\s*$", legacy)
    if match:
        return match.group(1).strip(), normalized_series_sequence(match.group(2))
    return (legacy, "") if legacy else ("", "")


def resolve_primary_series(
    metadata: dict[str, Any],
    item_id: str,
    catalog: list[LibrarySeries],
) -> tuple[str, str, int]:
    """Resolve one book to its first listed series and the server's canonical name."""
    memberships = [series for series in catalog if item_id in series.book_ids]
    raw_series = metadata.get("series") or []
    if isinstance(raw_series, dict):
        raw_series = [raw_series]

    primary: dict[str, Any] | None = None
    if isinstance(raw_series, list):
        primary = next(
            (
                value
                for value in raw_series
                if isinstance(value, dict)
                and (
                    str(value.get("id") or value.get("seriesId") or "").strip()
                    or str(value.get("name") or value.get("series") or "").strip()
                )
            ),
            None,
        )

    if primary is not None:
        series_id = str(primary.get("id") or primary.get("seriesId") or "").strip()
        series_name = str(primary.get("name") or primary.get("series") or "").strip()
        matched = next(
            (series for series in catalog if series_id and series.id == series_id),
            None,
        )
        parsed_sequence = ""
        if matched is None and series_name:
            matched, parsed_sequence = match_canonical_series_label(
                series_name,
                memberships or catalog,
            )
        sequence = normalized_series_sequence(primary.get("sequence")) or parsed_sequence
        if matched is not None:
            sequence = sequence or matched.book_sequences.get(item_id, "")
            return matched.name, sequence, matched.num_books
        if series_name:
            name, legacy_sequence = strip_legacy_series_number(series_name)
            return name, sequence or legacy_sequence, 0

    legacy = str(metadata.get("seriesName") or "").strip()
    if legacy:
        matched, sequence = match_canonical_series_label(legacy, memberships or catalog)
        if matched is not None:
            sequence = sequence or matched.book_sequences.get(item_id, "")
            return matched.name, sequence, matched.num_books
        name, sequence = strip_legacy_series_number(legacy)
        return name, sequence, 0

    if memberships:
        first = memberships[0]
        return first.name, first.book_sequences.get(item_id, ""), first.num_books
    return "", "", 0


def match_canonical_series_label(
    label: str,
    candidates: list[LibrarySeries],
) -> tuple[LibrarySeries | None, str]:
    """Match a legacy/composite label to its leading canonical series name."""
    clean = label.strip()
    for series in sorted(candidates, key=lambda value: len(value.name), reverse=True):
        match = re.match(
            rf"^{re.escape(series.name)}(?:\s*#\s*(\d+(?:\.\d+)?))?(?:\s*,.*)?$",
            clean,
            flags=re.IGNORECASE,
        )
        if match:
            return series, normalized_series_sequence(match.group(1))
    return None, ""


def strip_legacy_series_number(label: str) -> tuple[str, str]:
    clean = label.strip()
    match = re.match(r"^(.*?)\s+#\s*(\d+(?:\.\d+)?)\s*$", clean)
    if match:
        return match.group(1).strip(), normalized_series_sequence(match.group(2))
    return clean, ""


def normalized_series_sequence(value: Any) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return ""
    whole, separator, fraction = text.partition(".")
    normalized_whole = str(int(whole))
    normalized_fraction = fraction.rstrip("0")
    if separator and normalized_fraction:
        return f"{normalized_whole}.{normalized_fraction}"
    return normalized_whole


def parse_chapters(raw_chapters: list[dict[str, Any]], duration: float) -> list[Chapter]:
    chapters: list[Chapter] = []
    for index, chapter in enumerate(raw_chapters):
        start = float(chapter.get("start") or chapter.get("startTime") or 0)
        end = float(chapter.get("end") or chapter.get("endTime") or duration or 0)
        try:
            chapter_index = int(chapter.get("index") or chapter.get("id") or index + 1)
        except (TypeError, ValueError):
            chapter_index = index + 1
        chapters.append(
            Chapter(
                index=chapter_index,
                title=str(chapter.get("title") or f"Chapter {index + 1}"),
                start=start,
                end=end,
            )
        )
    return chapters


def extract_progress(item: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        item.get("mediaProgress"),
        item.get("userMediaProgress"),
        item.get("progress"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return {}


def progress_current_time(*sources: dict[str, Any]) -> float:
    fallback = 0.0
    for source in sources:
        for key in ("currentTime", "current_time"):
            value = source.get(key)
            if value not in (None, ""):
                current_time = float(value)
                if current_time > 0:
                    return current_time
                fallback = current_time
        progress = extract_progress(source)
        value = progress.get("currentTime")
        if value not in (None, ""):
            current_time = float(value)
            if current_time > 0:
                return current_time
            fallback = current_time
    return fallback


def author_from_metadata(metadata: dict[str, Any]) -> str:
    written_by = written_by_author(metadata.get("authors"))
    if written_by:
        return written_by
    written_by = written_by_author(metadata.get("authorName") or metadata.get("author"))
    if written_by:
        return written_by
    return clean_author(metadata.get("authorName") or metadata.get("author") or "")


def author_names_from_metadata(metadata: dict[str, Any], fallback: str = "") -> tuple[str, ...]:
    raw_authors = metadata.get("authors") or []
    if isinstance(raw_authors, dict):
        raw_authors = [raw_authors]

    names: list[str] = []
    seen: set[str] = set()
    if isinstance(raw_authors, list):
        for entry in raw_authors:
            if isinstance(entry, dict):
                role = str(entry.get("role") or entry.get("type") or "").strip().casefold()
                if role and not (role.startswith("written by") or role in {"author", "authors"}):
                    continue
                name = clean_author(
                    entry.get("name")
                    or entry.get("authorName")
                    or entry.get("author")
                    or entry.get("value")
                    or ""
                )
            else:
                name = written_by_author(entry) or clean_author(entry)
            key = name.casefold()
            if name and key not in seen:
                names.append(name)
                seen.add(key)

    if names:
        return tuple(names)
    clean_fallback = clean_author(fallback)
    return (clean_fallback,) if clean_fallback else ()


def written_by_author(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            author = written_by_author(item)
            if author:
                return author
        return ""

    if isinstance(value, dict):
        role = str(value.get("role") or value.get("type") or value.get("label") or "").strip()
        name = value.get("name") or value.get("authorName") or value.get("author") or value.get("value") or ""
        if role.lower().startswith("written by"):
            return clean_author(name)
        return written_by_author(name)

    text = str(value or "").strip()
    match = re.match(r"^written\s+by\s*:?\s*(.+)$", text, flags=re.IGNORECASE)
    if match:
        return clean_author(match.group(1))
    return ""


def clean_author(value: Any) -> str:
    if isinstance(value, list):
        value = ", ".join(clean_author(item) for item in value if clean_author(item))
    elif isinstance(value, dict):
        value = value.get("name") or value.get("authorName") or value.get("author") or ""
    text = str(value or "").strip()
    if not text:
        return ""

    text = re.split(r"\s+(?:narrated by|narrator:?|read by)\s+", text, maxsplit=1, flags=re.IGNORECASE)[0]
    text = re.split(r"\s+[-|/]\s+(?:narrated by|narrator:?|read by)\s*", text, maxsplit=1, flags=re.IGNORECASE)[0]
    return text.strip(" -|/")


def extract_login_token(data: dict[str, Any]) -> str:
    user = data.get("user") or {}
    candidates = [
        user.get("accessToken"),
        user.get("access_token"),
        data.get("accessToken"),
        data.get("access_token"),
        user.get("token"),
        data.get("token"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def extract_refresh_token(data: dict[str, Any]) -> str:
    user = data.get("user") or {}
    candidates = [
        user.get("refreshToken"),
        user.get("refresh_token"),
        data.get("refreshToken"),
        data.get("refresh_token"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def jwt_expiration(token: str) -> float | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        return float(data["exp"])
    except (binascii.Error, KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def client_from_config(config: Any, client_factory=AudiobookshelfClient) -> AudiobookshelfClient:
    if client_factory is not AudiobookshelfClient:
        return client_factory(config.server_url, config.token)

    from .config import saved_auth_tokens, update_auth_tokens

    return client_factory(
        config.server_url,
        config.token,
        refresh_token=config.refresh_token,
        token_loader=lambda: saved_auth_tokens(config.server_url, config.username),
        token_saver=lambda token, refresh_token: update_auth_tokens(
            config.server_url,
            config.username,
            token,
            refresh_token,
        ),
    )
