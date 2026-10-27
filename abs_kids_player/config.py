from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .storage import ensure_storage_directory, finalize_storage_file


CONFIG_DIR = Path.home() / ".config" / "abs-kids-player"
CONFIG_PATH = CONFIG_DIR / "config.json"
SCREEN_SAVER_CHAPTER = "chapter"
SCREEN_SAVER_BOOKS = "books"
SCREEN_SAVER_CLOCK = "clock"
SCREEN_SAVER_MODES = (SCREEN_SAVER_CHAPTER, SCREEN_SAVER_BOOKS, SCREEN_SAVER_CLOCK)
LIBRARY_SORT_TITLE = "title"
LIBRARY_SORT_AUTHOR = "author"
LIBRARY_SORT_MODES = (LIBRARY_SORT_TITLE, LIBRARY_SORT_AUTHOR)
ROOT_MENU_IDS = ("continue", "series", "title", "author", "bluetooth", "shutdown")
DEFAULT_ROOT_MENU_ORDER = ROOT_MENU_IDS
DEFAULT_ROOT_MENU_ENABLED = ROOT_MENU_IDS
NAV_ACCELERATION_MODES = ("off", *(f"{multiplier}x" for multiplier in range(2, 11)))
DEFAULT_NAV_ACCELERATION_MODE = "10x"
PLAYBACK_SPEEDS = (1.0, 1.5, 2.0)
DEFAULT_PLAYBACK_SPEED = 1.0
DEFAULT_KNOB_HOLD_SECONDS = 1.0
DEFAULT_MARQUEE_DELAY_SECONDS = 0.15
DEFAULT_MARQUEE_SPEED_PX_PER_SECOND = 48.0
DEFAULT_MARQUEE_LOOP_PAUSE_SECONDS = 2.0
DEFAULT_NAV_ACCEL_THRESHOLD_MILLISECONDS = 40
DEFAULT_BROWSE_RETURN_SECONDS = 10.0
DEFAULT_SCREEN_SAVER_IDLE_SECONDS = 300.0
SCREEN_SAVER_DIM_LEVELS = (10, 15, 20, 25, 35, 50)
DEFAULT_SCREEN_SAVER_DIM_PERCENT = 15
DEFAULT_SLEEP_TIMER_MINUTES = 30
MIN_SLEEP_TIMER_MINUTES = 1
MAX_SLEEP_TIMER_MINUTES = 240
_CONFIG_LOCK = threading.RLock()


@dataclass(frozen=True)
class PodcastConfig:
    url: str
    title: str = ""
    author: str = ""
    feed_url: str = ""
    book_id: str = ""


def default_podcasts() -> list[PodcastConfig]:
    return []


@dataclass
class AppConfig:
    server_url: str = ""
    token: str = ""
    refresh_token: str = ""
    library_id: str = ""
    username: str = ""
    control_click_enabled: bool = True
    spoken_navigation_enabled: bool = False
    library_sort_mode: str = LIBRARY_SORT_TITLE
    playback_speed: float = DEFAULT_PLAYBACK_SPEED
    knob_hold_seconds: float = DEFAULT_KNOB_HOLD_SECONDS
    marquee_delay_seconds: float = DEFAULT_MARQUEE_DELAY_SECONDS
    marquee_speed_px_per_second: float = DEFAULT_MARQUEE_SPEED_PX_PER_SECOND
    marquee_loop_pause_seconds: float = DEFAULT_MARQUEE_LOOP_PAUSE_SECONDS
    navigation_acceleration_mode: str = DEFAULT_NAV_ACCELERATION_MODE
    navigation_accel_threshold_milliseconds: int = DEFAULT_NAV_ACCEL_THRESHOLD_MILLISECONDS
    startup_resume_last_played: bool = False
    browse_return_seconds: float = DEFAULT_BROWSE_RETURN_SECONDS
    screen_saver_idle_seconds: float = DEFAULT_SCREEN_SAVER_IDLE_SECONDS
    root_menu_order: list[str] = field(default_factory=lambda: list(DEFAULT_ROOT_MENU_ORDER))
    root_menu_enabled: list[str] = field(default_factory=lambda: list(DEFAULT_ROOT_MENU_ENABLED))
    screen_saver_mode: str = SCREEN_SAVER_CHAPTER
    screen_saver_dim_percent: int = DEFAULT_SCREEN_SAVER_DIM_PERCENT
    sleep_timer_enabled: bool = False
    sleep_timer_minutes: int = DEFAULT_SLEEP_TIMER_MINUTES
    podcasts: list[PodcastConfig] = field(default_factory=default_podcasts)

    @property
    def is_ready(self) -> bool:
        return bool(self.server_url.strip() and self.token.strip())


def load_config() -> AppConfig:
    with _CONFIG_LOCK:
        path = config_path()
        if not path.exists():
            return AppConfig()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AppConfig()

    legacy_acceleration_mode = str(data.get("navigation_acceleration_mode", "")).strip().lower()
    legacy_threshold_key = {
        "5x": "navigation_accel_5x_milliseconds",
        "10x": "navigation_accel_10x_milliseconds",
    }.get(legacy_acceleration_mode)
    threshold_value = data.get("navigation_accel_threshold_milliseconds")
    if threshold_value is None:
        threshold_value = data.get(legacy_threshold_key) if legacy_threshold_key else None

    raw_root_menu_order = data.get("root_menu_order")
    root_menu_order = valid_root_menu_order(raw_root_menu_order)
    root_menu_enabled_value = data.get("root_menu_enabled")
    raw_order_has_shutdown = isinstance(raw_root_menu_order, (list, tuple)) and any(
        str(item).strip().lower() == "shutdown" for item in raw_root_menu_order
    )
    if not raw_order_has_shutdown:
        if root_menu_enabled_value is None:
            root_menu_enabled_value = list(DEFAULT_ROOT_MENU_ENABLED)
        existing_enabled = root_menu_enabled_value if isinstance(root_menu_enabled_value, (list, tuple)) else ()
        root_menu_enabled_value = [*existing_enabled, "shutdown"]
    legacy_knob_hold = max(
        valid_long_press_seconds(data.get("nav_hold_seconds"), DEFAULT_KNOB_HOLD_SECONDS),
        valid_long_press_seconds(data.get("volume_hold_seconds"), DEFAULT_KNOB_HOLD_SECONDS),
    )

    return AppConfig(
        server_url=str(data.get("server_url", "")),
        token=str(data.get("token", "")),
        refresh_token=str(data.get("refresh_token", "")),
        library_id=str(data.get("library_id", "")),
        username=str(data.get("username", "")),
        control_click_enabled=bool(data.get("control_click_enabled", True)),
        spoken_navigation_enabled=bool(data.get("spoken_navigation_enabled", False)),
        library_sort_mode=valid_library_sort_mode(str(data.get("library_sort_mode", ""))),
        playback_speed=valid_playback_speed(data.get("playback_speed")),
        knob_hold_seconds=valid_long_press_seconds(data.get("knob_hold_seconds"), legacy_knob_hold),
        marquee_delay_seconds=valid_marquee_delay(data.get("marquee_delay_seconds")),
        marquee_speed_px_per_second=valid_marquee_speed(data.get("marquee_speed_px_per_second")),
        marquee_loop_pause_seconds=valid_marquee_loop_pause(data.get("marquee_loop_pause_seconds")),
        navigation_acceleration_mode=valid_navigation_acceleration_mode(data.get("navigation_acceleration_mode")),
        navigation_accel_threshold_milliseconds=valid_acceleration_milliseconds(
            threshold_value, DEFAULT_NAV_ACCEL_THRESHOLD_MILLISECONDS
        ),
        startup_resume_last_played=bool(data.get("startup_resume_last_played", False)),
        browse_return_seconds=valid_browse_return_seconds(data.get("browse_return_seconds")),
        screen_saver_idle_seconds=valid_screen_saver_idle_seconds(data.get("screen_saver_idle_seconds")),
        root_menu_order=root_menu_order,
        root_menu_enabled=valid_root_menu_enabled(root_menu_enabled_value),
        screen_saver_mode=valid_screen_saver_mode(str(data.get("screen_saver_mode", ""))),
        screen_saver_dim_percent=valid_screen_saver_dim_percent(data.get("screen_saver_dim_percent")),
        sleep_timer_enabled=bool(data.get("sleep_timer_enabled", False)),
        sleep_timer_minutes=valid_sleep_timer_minutes(data.get("sleep_timer_minutes")),
        podcasts=podcast_configs_from_json(data["podcasts"]) if "podcasts" in data else default_podcasts(),
    )


def save_config(config: AppConfig) -> None:
    with _CONFIG_LOCK:
        path = config_path()
        temporary_path = path.with_name(
            f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        ensure_storage_directory(path.parent)
        try:
            temporary_path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
            finalize_storage_file(temporary_path)
            temporary_path.replace(path)
            finalize_storage_file(path)
        finally:
            temporary_path.unlink(missing_ok=True)


def saved_auth_tokens(server_url: str, username: str) -> tuple[str, str]:
    with _CONFIG_LOCK:
        config = load_config()
        if not same_login(config, server_url, username):
            return "", ""
        return config.token, config.refresh_token


def update_auth_tokens(
    server_url: str,
    username: str,
    token: str,
    refresh_token: str,
) -> bool:
    with _CONFIG_LOCK:
        config = load_config()
        if not same_login(config, server_url, username):
            return False
        if config.token == token and config.refresh_token == refresh_token:
            return True
        save_config(replace(config, token=token, refresh_token=refresh_token))
        return True


def same_login(config: AppConfig, server_url: str, username: str) -> bool:
    configured_server = config.server_url.strip().rstrip("/").casefold()
    expected_server = server_url.strip().rstrip("/").casefold()
    configured_username = config.username.strip().casefold()
    expected_username = username.strip().casefold()
    return configured_server == expected_server and configured_username == expected_username


def config_path() -> Path:
    configured_path = os.environ.get("ABS_KIDS_PLAYER_CONFIG_PATH", "").strip()
    if configured_path:
        return Path(configured_path).expanduser()

    configured_dir = os.environ.get("ABS_KIDS_PLAYER_CONFIG_DIR", "").strip()
    if configured_dir:
        return Path(configured_dir).expanduser() / "config.json"

    return CONFIG_PATH


def valid_screen_saver_mode(value: str) -> str:
    return value if value in SCREEN_SAVER_MODES else SCREEN_SAVER_CHAPTER


def valid_library_sort_mode(value: str) -> str:
    return value if value in LIBRARY_SORT_MODES else LIBRARY_SORT_TITLE


def valid_playback_speed(value: object) -> float:
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_PLAYBACK_SPEED
    return speed if speed in PLAYBACK_SPEEDS else DEFAULT_PLAYBACK_SPEED


def valid_long_press_seconds(value: object, fallback: float) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return fallback
    return round(min(max(seconds, 0.5), 5.0), 1)


def valid_marquee_delay(value: object) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return DEFAULT_MARQUEE_DELAY_SECONDS
    return round(min(max(seconds, 0.0), 5.0), 2)


def valid_marquee_speed(value: object) -> float:
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_MARQUEE_SPEED_PX_PER_SECOND
    return round(min(max(speed, 8.0), 120.0), 1)


def valid_marquee_loop_pause(value: object) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return DEFAULT_MARQUEE_LOOP_PAUSE_SECONDS
    return round(min(max(seconds, 0.0), 10.0), 1)


def valid_navigation_acceleration_mode(value: object) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in NAV_ACCELERATION_MODES else DEFAULT_NAV_ACCELERATION_MODE


def valid_acceleration_milliseconds(value: object, fallback: int) -> int:
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return fallback
    return min(max(milliseconds, 10), 500)


def valid_browse_return_seconds(value: object) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return DEFAULT_BROWSE_RETURN_SECONDS
    return round(min(max(seconds, 0.0), 120.0), 1)


def valid_screen_saver_idle_seconds(value: object) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return DEFAULT_SCREEN_SAVER_IDLE_SECONDS
    return round(min(max(seconds, 0.0), 3600.0), 1)


def valid_root_menu_order(value: object) -> list[str]:
    candidates = value if isinstance(value, (list, tuple)) else ()
    ordered: list[str] = []
    for item in candidates:
        key = str(item).strip().lower()
        if key in ROOT_MENU_IDS and key not in ordered:
            ordered.append(key)
    return [*ordered, *(key for key in DEFAULT_ROOT_MENU_ORDER if key not in ordered)]


def valid_root_menu_enabled(value: object) -> list[str]:
    candidates = value if isinstance(value, (list, tuple)) else DEFAULT_ROOT_MENU_ENABLED
    enabled: list[str] = []
    for item in candidates:
        key = str(item).strip().lower()
        if key in ROOT_MENU_IDS and key not in enabled:
            enabled.append(key)
    if not enabled:
        enabled.append("title")
    return enabled


def valid_screen_saver_dim_percent(value: object) -> int:
    try:
        percent = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SCREEN_SAVER_DIM_PERCENT
    return percent if percent in SCREEN_SAVER_DIM_LEVELS else DEFAULT_SCREEN_SAVER_DIM_PERCENT


def valid_sleep_timer_minutes(value: object) -> int:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SLEEP_TIMER_MINUTES
    return min(max(minutes, MIN_SLEEP_TIMER_MINUTES), MAX_SLEEP_TIMER_MINUTES)


def podcast_configs_from_json(value: object) -> list[PodcastConfig]:
    if not isinstance(value, list):
        return default_podcasts()

    podcasts: list[PodcastConfig] = []
    for item in value:
        if isinstance(item, str):
            url = item.strip()
            if url:
                podcasts.append(PodcastConfig(url=url))
            continue
        if not isinstance(item, dict):
            continue
        podcast = PodcastConfig(
            url=str(item.get("url", "")).strip(),
            title=str(item.get("title", "")).strip(),
            author=str(item.get("author", "")).strip(),
            feed_url=str(item.get("feed_url", "")).strip(),
            book_id=str(item.get("book_id", "")).strip(),
        )
        if podcast.url or podcast.feed_url:
            podcasts.append(podcast)
    return podcasts
