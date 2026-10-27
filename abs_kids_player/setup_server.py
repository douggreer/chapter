from __future__ import annotations

import argparse
import hmac
import html
import ipaddress
import json
import secrets
import subprocess
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from . import __version__
from .api import AudiobookshelfClient, AudiobookshelfError, client_from_config
from .bluetooth_audio import MAC_ADDRESS_PATTERN, connected_bluetooth_audio_device
from .config import (
    LIBRARY_SORT_AUTHOR,
    LIBRARY_SORT_TITLE,
    MAX_SLEEP_TIMER_MINUTES,
    MIN_SLEEP_TIMER_MINUTES,
    NAV_ACCELERATION_MODES,
    PLAYBACK_SPEEDS,
    ROOT_MENU_IDS,
    DEFAULT_ROOT_MENU_ORDER,
    SCREEN_SAVER_BOOKS,
    SCREEN_SAVER_CHAPTER,
    SCREEN_SAVER_CLOCK,
    SCREEN_SAVER_DIM_LEVELS,
    AppConfig,
    PodcastConfig,
    load_config,
    save_config,
    valid_library_sort_mode,
    valid_long_press_seconds,
    valid_acceleration_milliseconds,
    valid_browse_return_seconds,
    valid_marquee_delay,
    valid_marquee_loop_pause,
    valid_marquee_speed,
    valid_navigation_acceleration_mode,
    valid_root_menu_enabled,
    valid_root_menu_order,
    valid_screen_saver_idle_seconds,
    valid_playback_speed,
    valid_screen_saver_dim_percent,
    valid_screen_saver_mode,
    valid_sleep_timer_minutes,
)
from .library_cache import clear_cached_books, load_cached_books
from .device_history import clear_device_playback_history, load_device_playback_history
from .player_state import clear_last_playback
from .player_control import (
    WebPlayerStatus,
    load_web_bluetooth_devices,
    load_web_player_status,
    queue_web_player_command,
    save_web_bluetooth_devices,
)
from .podcast import PodcastError, resolve_podcast_config
from .software_update import (
    UPDATE_SERVICE_NAME,
    SoftwareUpdateState,
    save_update_state,
    update_status_payload,
    wait_for_update_display_ready,
)
from .wifi import (
    SETUP_HOTSPOT_SSID,
    SETUP_HOTSPOT_URL,
    WifiError,
    WifiStatus,
    connect_wifi,
    ensure_wifi_or_hotspot,
    forget_all_wifi_connections_and_start_hotspot,
    forget_current_wifi_and_start_hotspot,
    wifi_status,
)


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 47831
WIFI_CHANGE_DELAY_SECONDS = 5.0
SYSTEM_ACTION_DELAY_SECONDS = 3.0
PLAYER_EVENT_POLL_SECONDS = 0.25
PLAYER_EVENT_TIME_SECONDS = 1.0
PLAYER_EVENT_HEARTBEAT_SECONDS = 10.0
MAX_POST_BODY_BYTES = 64 * 1024
CSRF_FIELD_NAME = "csrf_token"
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "chapter-logo.png"


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="chapter-csrf-token" content="{csrf_token}">
  <title>Chapter Player</title>
  <link rel="icon" type="image/png" href="/assets/chapter-logo.png">
  <style>
    body {{
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      min-height: 100vh;
      background: #edf1ef;
      color: #1f292b;
    }}
    main {{
      width: min(92vw, 780px);
      margin: 28px auto 48px;
    }}
    .app-header {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: center;
      padding: 0 2px;
    }}
    .app-brand {{
      display: flex;
      align-items: center;
      gap: 14px;
      min-width: 0;
    }}
    .app-logo {{
      width: 84px;
      height: 63px;
      flex: 0 0 auto;
      object-fit: contain;
    }}
    .app-intro {{
      max-width: 500px;
      margin: 0;
      font-size: 0.95rem;
    }}
    .tabs {{
      display: flex;
      gap: 4px;
      margin-top: 22px;
      padding: 4px;
      overflow-x: auto;
      border: 1px solid #cfd9d6;
      border-radius: 8px;
      background: #f8faf9;
      scrollbar-width: none;
    }}
    .tabs::-webkit-scrollbar {{ display: none; }}
    .tab-button {{
      width: auto;
      min-width: 68px;
      min-height: 42px;
      flex: 1 0 auto;
      margin: 0;
      padding: 8px 4px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: #586467;
      font-size: 0.8rem;
      font-weight: 750;
      cursor: pointer;
    }}
    .tab-button:hover {{
      background: #e9efed;
      color: #1f292b;
    }}
    .tab-button.is-active {{
      background: #234f50;
      color: #fff;
      box-shadow: 0 2px 7px rgba(26, 58, 59, 0.2);
    }}
    .tab-button:focus-visible,
    button:focus-visible,
    input:focus-visible,
    select:focus-visible {{
      outline: 3px solid #e8ad55;
      outline-offset: 2px;
    }}
    .tab-panel {{
      margin-top: 14px;
    }}
    .tab-panel[hidden] {{
      display: none;
    }}
    .connection-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .card {{
      background: #fff;
      border: 1px solid #d7dfdc;
      border-radius: 8px;
      padding: 24px;
      margin: 0;
      box-shadow: 0 10px 28px rgba(30, 49, 48, 0.09);
    }}
    h1 {{ margin: 0; font-size: 1.75rem; line-height: 1.15; }}
    h2 {{ margin: 0 0 14px; font-size: 1.05rem; }}
    p {{ color: #5d686b; line-height: 1.45; }}
    label {{ display: block; margin-top: 16px; font-weight: 700; }}
    input {{
      box-sizing: border-box;
      width: 100%;
      min-height: 44px;
      margin-top: 6px;
      padding: 8px 10px;
      border: 1px solid #b9c5c2;
      border-radius: 6px;
      font: inherit;
    }}
    button {{
      width: 100%;
      min-height: 48px;
      margin-top: 22px;
      border: 0;
      border-radius: 6px;
      background: #2e7d79;
      color: #fff;
      font: inherit;
      font-weight: 800;
      cursor: pointer;
    }}
    button:hover {{
      background: #256c68;
    }}
    button:disabled {{
      cursor: wait;
      opacity: 0.65;
    }}
    .playback-form button {{
      margin-top: 12px;
    }}
    .volume-form {{
      margin-top: 12px;
      display: grid;
      grid-template-columns: 28px 1fr 52px;
      gap: 10px;
      align-items: center;
    }}
    .volume-icon {{
      color: #20242a;
      font-size: 1.2rem;
      text-align: center;
      line-height: 1;
    }}
    .volume-percent {{
      color: #20242a;
      font-weight: 800;
      text-align: left;
      white-space: nowrap;
    }}
    .volume-slider {{
      padding: 0;
      margin-top: 0;
      min-height: 44px;
      border: 0;
      border-radius: 0;
      accent-color: #2e7d79;
    }}
    .chapter-buttons {{ display: flex; gap: 8px; margin-top: 10px; }}
    .chapter-buttons button {{ width: auto; flex: 1; min-height: 40px; margin: 0; padding: 7px 10px; }}
    .remote-card {{ margin-top: 14px; }}
    .remote-toolbar {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }}
    .remote-toolbar button {{ width: auto; min-height: 40px; margin: 0; padding: 8px 12px; }}
    .remote-toolbar button.is-active {{ background: #234f50; }}
    .remote-search {{ margin: 0 0 12px; }}
    .remote-library-list, .remote-recent-list {{ display: grid; gap: 8px; }}
    .remote-book, .remote-group, .remote-recent-item {{
      display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: center;
      padding: 10px; border: 1px solid #dfe6e3; border-radius: 8px; background: #f8faf9;
    }}
    .remote-book-title {{ font-weight: 750; overflow-wrap: anywhere; }}
    .remote-book-meta {{ margin-top: 3px; color: #59616d; font-size: 0.84rem; }}
    .remote-book-actions {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .remote-book-actions button {{ width: auto; min-height: 36px; margin: 0; padding: 7px 10px; }}
    .remote-group {{ width: 100%; text-align: left; color: #20242a; background: #f8faf9; }}
    .remote-section {{ margin-top: 20px; }}
    .remote-section h3 {{ margin: 0 0 8px; font-size: 0.98rem; }}
    .remote-empty {{ padding: 10px 0; color: #59616d; }}
    .remote-error {{ color: #9b2c2c; }}
    .message {{
      padding: 12px;
      border-radius: 6px;
      margin: 16px 0 0;
      background: #eef7f5;
      color: #164b47;
    }}
    .error {{
      background: #fbebeb;
      color: #842020;
    }}
    .hint {{
      font-size: 0.92rem;
    }}
    .settings-list {{
      margin-top: 12px;
      border: 1px solid #dfe6e3;
      border-radius: 8px;
      overflow: hidden;
    }}
    .navigation-settings-card {{
      margin-top: 18px;
      padding: 16px;
      border: 1px solid #dfe6e3;
      border-radius: 8px;
      background: #f8faf9;
    }}
    .navigation-settings-card h3 {{ margin: 0; font-size: 1rem; }}
    .navigation-settings-card .hint {{ margin: 5px 0 14px; }}
    .navigation-settings-form {{ margin: 0; }}
    .nav-settings-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 14px; }}
    .nav-settings-grid label {{ margin: 0; color: #59616d; font-size: 0.84rem; }}
    .nav-settings-grid .settings-number, .nav-settings-grid .settings-select {{
      display: block; box-sizing: border-box; width: 100%; min-height: 38px; margin-top: 4px;
    }}
    .root-menu-settings {{ min-width: 0; margin: 16px 0 0; padding: 10px 12px; border: 1px solid #dfe6e3; border-radius: 8px; }}
    .root-menu-settings legend {{ padding: 0 5px; font-weight: 800; }}
    .root-menu-row {{ display: grid; grid-template-columns: minmax(0, 1fr) 130px; gap: 10px; align-items: center; padding: 7px 0; border-top: 1px solid #e5ebe8; }}
    .root-menu-row:first-child {{ border-top: 0; }}
    .root-menu-enabled {{ display: flex; gap: 8px; align-items: center; margin: 0; }}
    .root-menu-enabled input {{ width: 18px; min-height: 18px; margin: 0; }}
    .root-menu-position {{ margin: 0; color: #59616d; font-size: 0.8rem; }}
    .root-menu-position .settings-select {{ width: 100%; min-width: 0; margin-top: 3px; }}
    .navigation-settings-form > button {{ margin-top: 12px; }}
    .settings-row {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: center;
      padding: 12px;
      border-top: 1px solid #dfe6e3;
    }}
    .settings-row:first-child {{ border-top: 0; }}
    .setting-name {{
      font-weight: 800;
    }}
    .setting-state {{
      color: #59616d;
      font-size: 0.88rem;
      margin-top: 3px;
    }}
    .toggle-form {{
      margin: 0;
    }}
    .toggle-button {{
      position: relative;
      width: 54px;
      height: 30px;
      min-height: 30px;
      margin: 0;
      padding: 0;
      display: block;
      box-sizing: border-box;
      border-radius: 999px;
      background: #a9aea9;
      overflow: hidden;
    }}
    .toggle-button::after {{
      content: "";
      position: absolute;
      top: 4px;
      left: 4px;
      width: 22px;
      height: 22px;
      border-radius: 50%;
      background: #fff;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.28);
    }}
    .toggle-button.is-on {{
      background: #2e7d79;
    }}
    .toggle-button.is-on::after {{
      left: 28px;
    }}
    .select-form {{
      display: flex;
      gap: 8px;
      align-items: center;
      margin: 0;
    }}
    .settings-select {{
      min-width: 150px;
      border: 1px solid #d8d0c5;
      border-radius: 8px;
      padding: 8px 10px;
      background: #fff;
      color: #1f2933;
      font: inherit;
    }}
    .screen-saver-settings-form {{
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 0.8fr) auto;
      gap: 8px;
      align-items: end;
      margin: 2px 0 0;
    }}
    .screen-saver-settings-form label {{
      margin: 0;
      color: #59616d;
      font-size: 0.82rem;
    }}
    .screen-saver-settings-form .settings-select {{
      width: 100%;
      min-width: 0;
      margin-top: 4px;
    }}
    .settings-number {{
      width: 76px;
      min-height: 38px;
      margin: 0;
      padding: 7px 8px;
    }}
    .sleep-timer-content {{
      min-width: 0;
    }}
    .sleep-timer-duration-form {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin: 10px 0 0;
      color: #59616d;
      font-size: 0.88rem;
    }}
    .sleep-timer-duration-form .settings-number {{
      width: 68px;
    }}
    .small-button {{
      width: auto;
      min-height: 36px;
      padding: 8px 12px;
      border-radius: 8px;
      white-space: nowrap;
    }}
    .secondary {{
      background: #e8eeec;
      color: #20242a;
    }}
    .secondary:hover {{
      background: #dce6e2;
    }}
    .podcast-form {{
      margin-top: 12px;
    }}
    .podcast-table {{
      display: grid;
      gap: 10px;
    }}
    .podcast-row {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: end;
      padding: 10px;
      border: 1px solid #dfe6e3;
      border-radius: 8px;
      background: #f8faf9;
    }}
    .podcast-row input {{
      margin-top: 0;
    }}
    .podcast-meta {{
      color: #59616d;
      font-size: 0.84rem;
      margin-top: 5px;
    }}
    .podcast-actions {{
      display: flex;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      margin-top: 12px;
    }}
    .podcast-actions button {{
      margin-top: 0;
    }}
    .podcast-save-button {{
      width: auto;
      min-width: 132px;
    }}
    .system-actions {{
      border: 1px solid #dfe6e3;
      border-radius: 8px;
      overflow: hidden;
    }}
    .system-version {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: center;
      gap: 16px;
      margin-bottom: 16px;
      padding: 14px 16px;
      border: 1px solid #dfe6e3;
      border-radius: 8px;
      background: #f8faf9;
    }}
    .system-version-label {{
      color: #59616d;
      font-size: 0.9rem;
    }}
    .system-version-number {{
      display: block;
      margin-top: 2px;
      font-size: 1.05rem;
    }}
    .system-update-status {{
      display: block;
      margin-top: 3px;
      color: #59616d;
      font-size: 0.82rem;
      font-weight: 400;
    }}
    .system-update-description {{
      margin: 5px 0 0;
      font-size: 0.9rem;
    }}
    .system-version > button {{
      width: auto;
      min-width: 112px;
      min-height: 40px;
      margin: 0;
      padding: 8px 14px;
    }}
    .system-version > .confirmation-panel {{
      grid-column: 1 / -1;
    }}
    .system-action {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      align-items: center;
      padding: 16px;
      border-top: 1px solid #dfe6e3;
    }}
    .system-action:first-child {{
      border-top: 0;
    }}
    .system-action h3 {{
      margin: 0;
      font-size: 1rem;
    }}
    .system-action p {{
      margin: 5px 0 0;
      font-size: 0.9rem;
    }}
    .system-action > button {{
      width: auto;
      min-width: 112px;
      min-height: 40px;
      margin: 0;
      padding: 8px 14px;
    }}
    .danger-button {{
      background: #a33a3a;
    }}
    .danger-button:hover {{
      background: #872f2f;
    }}
    .confirmation-panel {{
      grid-column: 1 / -1;
      padding: 14px;
      border: 1px solid #e5c6c6;
      border-radius: 6px;
      background: #fff7f7;
    }}
    .confirmation-panel.update-confirmation {{
      border-color: #b9d4d0;
      background: #f2f8f7;
    }}
    .confirmation-panel[hidden] {{
      display: none;
    }}
    .confirmation-panel strong {{
      display: block;
    }}
    .confirmation-actions {{
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 12px;
    }}
    .confirmation-actions form {{
      margin: 0;
    }}
    .confirmation-actions button {{
      width: auto;
      min-width: 96px;
      min-height: 38px;
      margin: 0;
      padding: 8px 12px;
    }}
    .sr-only {{
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }}
    .status {{
      display: grid;
      grid-template-columns: 1fr;
      border: 1px solid #dfe6e3;
      border-radius: 8px;
      overflow: hidden;
    }}
    .status-row {{
      display: grid;
      grid-template-columns: minmax(140px, 180px) minmax(0, 1fr);
      gap: 16px;
      align-items: start;
      padding: 14px 16px;
      border-top: 1px solid #dfe6e3;
    }}
    .status-row:first-child {{ border-top: 0; }}
    .status-row:last-child {{
      padding: 16px;
    }}
    .status-label {{
      color: #59616d;
      font-size: 0.88rem;
    }}
    .status-value {{
      min-width: 0;
      overflow-wrap: anywhere;
    }}
    .status-value strong {{
      font-weight: 800;
    }}
    .now-playing-title {{
      font-weight: 800;
    }}
    .now-playing-meta {{
      color: #59616d;
      font-size: 0.92rem;
      margin-top: 4px;
    }}
    .hidden {{ display: none; }}
    .ok {{ color: #176c4f; }}
    .bad {{ color: #9b2c2c; }}
    code {{ background: #f1f1f1; padding: 2px 4px; border-radius: 4px; }}
    @media (max-width: 680px) {{
      main {{
        width: min(94vw, 520px);
        margin-top: 20px;
      }}
      .app-header {{
        display: block;
      }}
      .app-intro {{
        margin-top: 8px;
      }}
      .connection-grid {{
        grid-template-columns: 1fr;
      }}
      .card {{
        padding: 18px;
      }}
      .status {{
        grid-template-columns: 1fr;
      }}
      .status-row,
      .status-row:first-child {{
        grid-template-columns: 1fr;
        gap: 3px;
        border-top: 1px solid #dfe6e3;
      }}
      .status-row:first-child {{
        border-top: 0;
      }}
      .screen-saver-settings-form {{
        grid-template-columns: 1fr;
      }}
      .nav-settings-grid {{ grid-template-columns: 1fr; }}
      .remote-book, .remote-group, .remote-recent-item {{ grid-template-columns: 1fr; }}
      .remote-book-actions {{ display: grid; grid-template-columns: 1fr 1fr; }}
      .podcast-row {{
        grid-template-columns: 1fr;
      }}
      .podcast-row .small-button {{
        width: 100%;
      }}
      .system-action {{
        grid-template-columns: 1fr;
      }}
      .system-action > button {{
        width: 100%;
      }}
      .system-version {{
        grid-template-columns: 1fr;
      }}
      .system-version > button {{
        width: 100%;
      }}
      .confirmation-actions {{
        display: grid;
        grid-template-columns: 1fr 1fr;
      }}
      .confirmation-actions button {{
        width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header class="app-header">
      <div class="app-brand">
        <img class="app-logo" src="/assets/chapter-logo.png" width="84" height="63" alt="">
        <h1>Chapter Player</h1>
      </div>
    </header>
    {message}
    <nav class="tabs" role="tablist" aria-label="Player administration">
      <button class="tab-button is-active" id="tab-overview" type="button" role="tab" aria-selected="true" aria-controls="panel-overview" data-tab-target="overview">Overview</button>
      <button class="tab-button" id="tab-settings" type="button" role="tab" aria-selected="false" aria-controls="panel-settings" tabindex="-1" data-tab-target="settings">Settings</button>
      <button class="tab-button" id="tab-podcasts" type="button" role="tab" aria-selected="false" aria-controls="panel-podcasts" tabindex="-1" data-tab-target="podcasts">Podcasts</button>
      <button class="tab-button" id="tab-connections" type="button" role="tab" aria-selected="false" aria-controls="panel-connections" tabindex="-1" data-tab-target="connections">Setup</button>
      <button class="tab-button" id="tab-system" type="button" role="tab" aria-selected="false" aria-controls="panel-system" tabindex="-1" data-tab-target="system">System</button>
    </nav>
    <div class="tab-panel" id="panel-overview" role="tabpanel" aria-labelledby="tab-overview" data-tab-panel="overview">
      {status_panel}
      {remote_control_panel}
    </div>
    <div class="tab-panel" id="panel-settings" role="tabpanel" aria-labelledby="tab-settings" data-tab-panel="settings" hidden>
      {settings_card}
    </div>
    <div class="tab-panel" id="panel-podcasts" role="tabpanel" aria-labelledby="tab-podcasts" data-tab-panel="podcasts" hidden>
      {podcasts_card}
    </div>
    <div class="tab-panel connection-grid" id="panel-connections" role="tabpanel" aria-labelledby="tab-connections" data-tab-panel="connections" hidden>
      {wifi_card}
      <section class="card" aria-labelledby="audiobookshelf-heading">
        <h2 id="audiobookshelf-heading">Audiobookshelf</h2>
        <p class="hint">The password is sent only to your Audiobookshelf server. This player stores the returned user token.</p>
        <form method="post" action="/login">
          {csrf_input}
          <label for="server_url">Audiobookshelf server URL</label>
          <input id="server_url" name="server_url" value="{server_url}" placeholder="https://books.example.com" required>

          <label for="username">Username</label>
          <input id="username" name="username" autocomplete="username" required>

          <label for="password">Password</label>
          <input id="password" name="password" type="password" autocomplete="current-password" required>

          <button type="submit">Log In Player</button>
        </form>
      </section>
    </div>
    <div class="tab-panel" id="panel-system" role="tabpanel" aria-labelledby="tab-system" data-tab-panel="system" hidden>
      {system_card}
    </div>
  </main>
  <script>
    var volumeSlider = document.querySelector("[data-volume-slider]");
    var volumePercent = document.querySelector("[data-volume-percent]");
    var playbackForm = document.querySelector("[data-playback-form]");
    var podcastRows = document.querySelector("[data-podcast-rows]");
    var addPodcastRowButton = document.querySelector("[data-add-podcast-row]");
    var tabButtons = document.querySelectorAll("[data-tab-target]");
    var tabPanels = document.querySelectorAll("[data-tab-panel]");
    var confirmationTriggers = document.querySelectorAll("[data-confirm-trigger]");
    var confirmationPanels = document.querySelectorAll("[data-confirm-panel]");
    var volumeTimer = null;
    var latestPlayerStatus = null;
    var pendingPlaybackAction = null;
    var sseStatusReceived = false;
    var sseFallbackTimer = null;
    var fallbackPollTimer = null;
    var systemUpdatePollTimer = null;
    var softwareUpdateWasInstalling = false;
    var tabStorageKey = "chapter-admin-tab";
    var csrfToken = document.querySelector('meta[name="chapter-csrf-token"]').getAttribute("content");
    function tabExists(tabName) {{
      return Boolean(document.querySelector('[data-tab-target="' + tabName + '"]'));
    }}
    function activateTab(tabName, moveFocus) {{
      if (!tabExists(tabName)) {{
        tabName = "overview";
      }}
      tabButtons.forEach(function(button) {{
        var active = button.getAttribute("data-tab-target") === tabName;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
        button.setAttribute("tabindex", active ? "0" : "-1");
        if (active && moveFocus) {{
          button.focus();
        }}
      }});
      tabPanels.forEach(function(panel) {{
        panel.hidden = panel.getAttribute("data-tab-panel") !== tabName;
      }});
      try {{
        window.localStorage.setItem(tabStorageKey, tabName);
      }} catch (error) {{}}
    }}
    function savedTab() {{
      try {{
        return window.localStorage.getItem(tabStorageKey) || "overview";
      }} catch (error) {{
        return "overview";
      }}
    }}
    tabButtons.forEach(function(button, index) {{
      button.addEventListener("click", function() {{
        activateTab(button.getAttribute("data-tab-target"), false);
      }});
      button.addEventListener("keydown", function(event) {{
        var nextIndex = index;
        if (event.key === "ArrowRight") {{
          nextIndex = (index + 1) % tabButtons.length;
        }} else if (event.key === "ArrowLeft") {{
          nextIndex = (index - 1 + tabButtons.length) % tabButtons.length;
        }} else if (event.key === "Home") {{
          nextIndex = 0;
        }} else if (event.key === "End") {{
          nextIndex = tabButtons.length - 1;
        }} else {{
          return;
        }}
        event.preventDefault();
        activateTab(tabButtons[nextIndex].getAttribute("data-tab-target"), true);
      }});
    }});
    activateTab(savedTab(), false);
    function applySystemUpdateStatus(status) {{
      var statusText = document.querySelector("[data-system-update-status]");
      var description = document.querySelector("[data-system-update-description]");
      var trigger = document.querySelector("[data-system-update-trigger]");
      var versionText = document.querySelector("[data-system-update-version]");
      var latestVersion = status.latestVersion ? "v" + status.latestVersion : "";
      if (status.phase === "installing") {{
        softwareUpdateWasInstalling = true;
      }}
      if (
        softwareUpdateWasInstalling &&
        (status.phase === "completed" || (status.phase === "current" && !status.updateAvailable))
      ) {{
        softwareUpdateWasInstalling = false;
        window.location.replace("/");
        return;
      }}
      var updateServiceIsRestarting = (
        softwareUpdateWasInstalling && status.phase === "available" && status.updateAvailable
      );
      if (status.phase === "installing") {{
        statusText.textContent = latestVersion ? "Installing " + latestVersion + "..." : "Installing update...";
        description.textContent = status.message || "Installing the latest stable release. Chapter will restart its services when ready.";
      }} else if (updateServiceIsRestarting) {{
        statusText.textContent = "Finishing update...";
        description.textContent = "Chapter is restarting with the newly installed version.";
      }} else if (status.phase === "failed") {{
        softwareUpdateWasInstalling = false;
        statusText.textContent = "Update failed";
        description.textContent = status.message || "The software update did not finish.";
      }} else if (status.phase === "error") {{
        statusText.textContent = softwareUpdateWasInstalling ? "Finishing update..." : "Update check needs attention";
        description.textContent = softwareUpdateWasInstalling
          ? "Waiting for the Chapter web service to restart."
          : (status.message || "Chapter could not check for software updates.");
      }} else if (status.updateAvailable) {{
        statusText.textContent = latestVersion + " available";
        description.textContent = "A newer stable version of Chapter is ready to install.";
      }} else if (status.phase === "completed") {{
        statusText.textContent = "Up to date";
        description.textContent = "";
      }} else {{
        statusText.textContent = "Up to date";
        description.textContent = "";
      }}
      description.hidden = !description.textContent.trim();
      if (versionText) {{
        versionText.textContent = latestVersion || "the latest release";
      }}
      if (trigger) {{
        trigger.hidden = softwareUpdateWasInstalling || !status.updateAvailable;
        trigger.textContent = latestVersion ? "Update to " + latestVersion : "Update";
        if (trigger.hidden) {{
          closeConfirmation("update", false);
        }}
      }}
      if (systemUpdatePollTimer) {{
        window.clearTimeout(systemUpdatePollTimer);
      }}
      systemUpdatePollTimer = window.setTimeout(
        refreshSystemUpdateStatus,
        softwareUpdateWasInstalling ? 2000 : (status.phase === "error" ? 5000 : 900000)
      );
    }}
    function refreshSystemUpdateStatus() {{
      var request = new XMLHttpRequest();
      request.open("GET", "/system/update/status", true);
      request.onreadystatechange = function() {{
        if (request.readyState !== 4) {{
          return;
        }}
        if (request.status === 200) {{
          try {{
            applySystemUpdateStatus(JSON.parse(request.responseText));
            return;
          }} catch (error) {{}}
        }}
        applySystemUpdateStatus({{
          phase: "error",
          latestVersion: "",
          updateAvailable: false,
          message: "Chapter could not check for software updates. It will try again automatically."
        }});
      }};
      request.send();
    }}
    refreshSystemUpdateStatus();
    function closeConfirmation(panelName, restoreFocus) {{
      var panel = document.querySelector('[data-confirm-panel="' + panelName + '"]');
      var trigger = document.querySelector('[data-confirm-trigger="' + panelName + '"]');
      if (panel) {{
        panel.hidden = true;
      }}
      if (trigger) {{
        trigger.setAttribute("aria-expanded", "false");
        if (restoreFocus) {{
          trigger.focus();
        }}
      }}
    }}
    confirmationTriggers.forEach(function(trigger) {{
      trigger.addEventListener("click", function() {{
        var panelName = trigger.getAttribute("data-confirm-trigger");
        confirmationPanels.forEach(function(panel) {{
          closeConfirmation(panel.getAttribute("data-confirm-panel"), false);
        }});
        var panel = document.querySelector('[data-confirm-panel="' + panelName + '"]');
        if (!panel) {{
          return;
        }}
        panel.hidden = false;
        trigger.setAttribute("aria-expanded", "true");
        var cancelButton = panel.querySelector("[data-confirm-cancel]");
        if (cancelButton) {{
          cancelButton.focus();
        }}
      }});
    }});
    document.querySelectorAll("[data-confirm-cancel]").forEach(function(button) {{
      button.addEventListener("click", function() {{
        var panel = button.closest("[data-confirm-panel]");
        if (panel) {{
          closeConfirmation(panel.getAttribute("data-confirm-panel"), true);
        }}
      }});
    }});
    function encodeForm(fields) {{
      var parts = [];
      for (var key in fields) {{
        if (Object.prototype.hasOwnProperty.call(fields, key)) {{
          parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(fields[key]));
        }}
      }}
      return parts.join("&");
    }}
    function postPlayer(fields, callback) {{
      var request = new XMLHttpRequest();
      fields["{csrf_field_name}"] = csrfToken;
      request.open("POST", "/player", true);
      request.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
      request.setRequestHeader("X-Requested-With", "fetch");
      request.onreadystatechange = function() {{
        if (request.readyState === 4 && callback) {{
          callback(request.status);
        }}
      }};
      request.send(encodeForm(fields));
    }}
    function sendVolume(value) {{
      postPlayer({{action: "volume", volume: value}});
    }}
    function applyPlayerStatus(status) {{
      latestPlayerStatus = status;
      var playerContainer = document.querySelector("[data-now-playing]");
      var title = document.querySelector("[data-now-playing-title]");
      var meta = document.querySelector("[data-now-playing-meta]");
      var actionInput = document.querySelector("[data-playback-action]");
      var actionButton = document.querySelector("[data-playback-button]");
      var playbackForm = document.querySelector("[data-playback-form]");
      var chapterButtons = document.querySelector(".chapter-buttons");
      var volumeForm = document.querySelector("[data-volume-form]");
      if (!status.hasSession) {{
        pendingPlaybackAction = null;
        if (playerContainer) {{
          playerContainer.setAttribute("data-has-session", "0");
        }}
        if (title) {{
          title.textContent = "Nothing playing";
        }}
        if (meta) {{
          meta.textContent = "";
        }}
        if (playbackForm) {{
          playbackForm.classList.add("hidden");
        }}
        if (volumeForm) {{
          volumeForm.classList.add("hidden");
        }}
        if (chapterButtons) {{
          chapterButtons.classList.add("hidden");
        }}
        return;
      }}
      if (playerContainer) {{
        playerContainer.setAttribute("data-has-session", "1");
      }}
      if (playbackForm) {{
        playbackForm.classList.remove("hidden");
      }}
      if (volumeForm) {{
        volumeForm.classList.remove("hidden");
      }}
      if (chapterButtons) {{
        chapterButtons.classList.remove("hidden");
      }}
      if (title) {{
        title.textContent = status.title;
      }}
      renderLivePlayerTime();
      if (actionInput && actionButton) {{
        if (pendingPlaybackAction) {{
          var pendingReached = pendingPlaybackAction === "play" ? status.isPlaying : !status.isPlaying;
          if (pendingReached) {{
            pendingPlaybackAction = null;
            actionButton.disabled = false;
          }}
        }}
        if (pendingPlaybackAction) {{
          actionButton.disabled = true;
          actionButton.textContent = pendingPlaybackAction === "play" ? "Playing..." : "Pausing...";
        }} else {{
          actionInput.value = status.isPlaying ? "pause" : "play";
          actionButton.textContent = status.isPlaying ? "Pause" : "Play";
          actionButton.disabled = false;
        }}
      }}
      if (volumeSlider && volumePercent && document.activeElement !== volumeSlider) {{
        volumeSlider.value = status.volumePercent;
        volumePercent.textContent = status.volumePercent + "%";
      }}
    }}
    function twoDigit(value) {{
      value = String(value);
      return value.length < 2 ? "0" + value : value;
    }}
    function formatDuration(seconds) {{
      seconds = Math.max(0, Math.floor(seconds || 0));
      var hours = Math.floor(seconds / 3600);
      var minutes = Math.floor((seconds % 3600) / 60);
      var secs = seconds % 60;
      if (hours) {{
        return hours + ":" + twoDigit(minutes) + ":" + twoDigit(secs);
      }}
      return minutes + ":" + twoDigit(secs);
    }}
    function liveTimeInfo(status) {{
      var currentTime = Number(status.currentTime || 0);
      var duration = Number(status.duration || 0);
      if (status.isPlaying) {{
        var updatedAt = Number(status.updatedAt || 0);
        if (updatedAt > 0) {{
          currentTime += Math.max(0, Date.now() / 1000 - updatedAt);
        }}
      }}
      if (duration > 0) {{
        currentTime = Math.min(currentTime, duration);
        return formatDuration(currentTime) + " / " + formatDuration(duration);
      }}
      return formatDuration(currentTime);
    }}
    function renderLivePlayerTime() {{
      var meta = document.querySelector("[data-now-playing-meta]");
      if (!meta || !latestPlayerStatus || !latestPlayerStatus.hasSession) {{
        return;
      }}
      meta.textContent = latestPlayerStatus.state + " · " + liveTimeInfo(latestPlayerStatus);
    }}
    function setPendingPlayback(action) {{
      var actionInput = document.querySelector("[data-playback-action]");
      var actionButton = document.querySelector("[data-playback-button]");
      pendingPlaybackAction = action;
      if (actionInput && actionButton) {{
        actionButton.disabled = true;
        actionButton.textContent = action === "play" ? "Playing..." : "Pausing...";
      }}
    }}
    function refreshPlayerStatus() {{
      var request = new XMLHttpRequest();
      request.open("GET", "/player/status?_=" + Date.now(), true);
      request.onreadystatechange = function() {{
        if (request.readyState !== 4) {{
          return;
        }}
        if (request.status >= 200 && request.status < 300) {{
          try {{
            var status = JSON.parse(request.responseText);
            applyPlayerStatus(status);
          }} catch (error) {{}}
        }}
      }};
      request.send();
    }}
    function startFallbackPolling() {{
      if (fallbackPollTimer) {{
        return;
      }}
      fallbackPollTimer = window.setInterval(refreshPlayerStatus, 1000);
      refreshPlayerStatus();
    }}
    function startPlayerEventStream() {{
      if (!window.EventSource) {{
        startFallbackPolling();
        return false;
      }}
      try {{
        var source = new EventSource("/player/events");
        source.onmessage = function(event) {{
          try {{
            applyPlayerStatus(JSON.parse(event.data));
            sseStatusReceived = true;
            if (sseFallbackTimer) {{
              window.clearTimeout(sseFallbackTimer);
              sseFallbackTimer = null;
            }}
          }} catch (error) {{
            // Keep the fallback polling running.
          }}
        }};
        source.onerror = function() {{
          if (sseFallbackTimer) {{
            window.clearTimeout(sseFallbackTimer);
          }}
          sseFallbackTimer = window.setTimeout(function() {{
            if (!sseStatusReceived) {{
              startFallbackPolling();
            }}
          }}, 4000);
        }};
        return true;
      }} catch (error) {{
        startFallbackPolling();
        return false;
      }}
    }}
    function sendPlayerAction(action) {{
      postPlayer({{action: action}}, function() {{
          window.setTimeout(refreshPlayerStatus, 250);
          window.setTimeout(refreshPlayerStatus, 750);
      }});
    }}
    var remoteBooks = [];
    var remoteMode = "title";
    var remoteGroup = "";
    var remoteSearchText = "";
    function getJson(url, callback) {{
      var request = new XMLHttpRequest();
      request.open("GET", url + (url.indexOf("?") >= 0 ? "&" : "?") + "_=" + Date.now(), true);
      request.onreadystatechange = function() {{
        if (request.readyState === 4) {{
          if (request.status >= 200 && request.status < 300) {{
            try {{ callback(JSON.parse(request.responseText), null); }} catch (error) {{ callback(null, error); }}
          }} else {{ callback(null, new Error("Request failed")); }}
        }}
      }};
      request.send();
    }}
    function textElement(tag, className, text) {{
      var element = document.createElement(tag);
      if (className) {{ element.className = className; }}
      element.textContent = text || "";
      return element;
    }}
    function appendEmpty(container, text, isError) {{
      container.appendChild(textElement("div", "remote-empty" + (isError ? " remote-error" : ""), text));
    }}
    function postRemoteBook(bookId, startOver) {{
      postPlayer({{action: "play_book", book_id: bookId, start_over: startOver ? "1" : "0"}}, function(status) {{
        if (status >= 200 && status < 300) {{
          window.setTimeout(refreshPlayerStatus, 300);
          window.setTimeout(refreshRecentPlayback, 600);
        }}
      }});
    }}
    function addRemoteBook(container, book, recentlyPlayed) {{
      var row = textElement("div", recentlyPlayed ? "remote-recent-item" : "remote-book", "");
      var info = document.createElement("div");
      info.appendChild(textElement("div", "remote-book-title", book.title || "Untitled"));
      var metaParts = [];
      if (book.author) {{ metaParts.push(book.author); }}
      if (book.seriesName) {{
        var seriesMeta = book.seriesName;
        if (!recentlyPlayed && remoteMode === "series" && remoteGroup && book.seriesPosition) {{ seriesMeta += " · " + book.seriesPosition; }}
        metaParts.push(seriesMeta);
      }}
      var duration = Number(book.duration || 0);
      var currentTime = Number(book.currentTime || 0);
      if (duration > 0 && currentTime > 0) {{
        metaParts.push(Math.floor(currentTime / duration * 100) + "% listened · " + formatDuration(currentTime) + " / " + formatDuration(duration));
      }} else if (book.progress > 0) {{
        metaParts.push(Math.floor(book.progress * 100) + "% listened");
      }}
      if (recentlyPlayed && book.lastPlayedAt) {{
        metaParts.push("Last played " + new Date(Number(book.lastPlayedAt) * 1000).toLocaleString());
      }}
      info.appendChild(textElement("div", "remote-book-meta", metaParts.join(" · ")));
      var actions = textElement("div", "remote-book-actions", "");
      var canContinue = Boolean(book.inProgress && !book.finished);
      var playButton = textElement("button", "", canContinue ? "Continue" : "Play");
      playButton.type = "button";
      playButton.addEventListener("click", function() {{ postRemoteBook(book.id || book.bookId, Boolean(book.finished)); }});
      actions.appendChild(playButton);
      if (canContinue) {{
        var startButton = textElement("button", "secondary", "Start over");
        startButton.type = "button";
        startButton.addEventListener("click", function() {{ postRemoteBook(book.id || book.bookId, true); }});
        actions.appendChild(startButton);
      }}
      row.appendChild(info);
      row.appendChild(actions);
      container.appendChild(row);
    }}
    function remoteMatches(book, query) {{
      if (!query) {{ return true; }}
      var haystack = [book.title, book.author, book.seriesName, (book.authors || []).join(" ")].join(" ").toLowerCase();
      return haystack.indexOf(query) >= 0;
    }}
    function renderRemoteLibrary() {{
      var container = document.querySelector("[data-library-results]");
      var backRow = document.querySelector("[data-group-back-row]");
      if (!container) {{ return; }}
      container.textContent = "";
      var query = remoteSearchText.trim().toLowerCase();
      var books = remoteBooks.slice();
      if (remoteMode === "continue") {{
        books = books.filter(function(book) {{ return book.inProgress && !book.finished; }});
        books.sort(function(a, b) {{ return Number(b.lastUpdate || 0) - Number(a.lastUpdate || 0) || a.title.localeCompare(b.title); }});
        books = books.filter(function(book) {{ return remoteMatches(book, query); }});
        if (!books.length) {{ appendEmpty(container, "No in-progress books on this player’s library."); return; }}
        books.forEach(function(book) {{ addRemoteBook(container, book, false); }});
        return;
      }}
      if (remoteMode === "series" || remoteMode === "author") {{
        var groups = {{}};
        books.forEach(function(book) {{
          var names = remoteMode === "series" ? (book.seriesName ? [book.seriesName] : []) : (book.authors || (book.author ? [book.author] : []));
          names.forEach(function(name) {{
            var key = String(name).trim();
            if (!key) {{ return; }}
            if (!groups[key]) {{ groups[key] = []; }}
            if (!groups[key].some(function(existing) {{ return existing.id === book.id; }})) {{ groups[key].push(book); }}
          }});
        }});
        if (remoteGroup) {{
          backRow.hidden = false;
          var groupBooks = (groups[remoteGroup] || []).filter(function(book) {{ return remoteMatches(book, query); }});
          if (remoteMode === "series") {{
            groupBooks.sort(function(a, b) {{
              var aPosition = parseFloat(a.seriesPosition || "");
              var bPosition = parseFloat(b.seriesPosition || "");
              if (!isNaN(aPosition) && !isNaN(bPosition) && aPosition !== bPosition) {{ return aPosition - bPosition; }}
              return a.title.localeCompare(b.title);
            }});
          }} else {{ groupBooks.sort(function(a, b) {{ return a.title.localeCompare(b.title); }}); }}
          if (!groupBooks.length) {{ appendEmpty(container, "No matching books in this group."); return; }}
          groupBooks.forEach(function(book) {{ addRemoteBook(container, book, false); }});
          return;
        }}
        backRow.hidden = true;
        var groupNames = Object.keys(groups).filter(function(name) {{
          return name.toLowerCase().indexOf(query) >= 0 || groups[name].some(function(book) {{ return remoteMatches(book, query); }});
        }}).sort(function(a, b) {{ return a.localeCompare(b); }});
        if (!groupNames.length) {{ appendEmpty(container, "No matching groups found."); return; }}
        groupNames.forEach(function(name) {{
          var button = textElement("button", "remote-group", name + " · " + groups[name].length + (groups[name].length === 1 ? " book" : " books"));
          button.type = "button";
          button.addEventListener("click", function() {{ remoteGroup = name; renderRemoteLibrary(); }});
          container.appendChild(button);
        }});
        return;
      }}
      if (backRow) {{ backRow.hidden = true; }}
      books = books.filter(function(book) {{ return remoteMatches(book, query); }});
      books.sort(function(a, b) {{ return a.title.localeCompare(b.title); }});
      if (!books.length) {{ appendEmpty(container, "No matching books found."); return; }}
      books.forEach(function(book) {{ addRemoteBook(container, book, false); }});
    }}
    function refreshRemoteLibrary() {{
      getJson("/library/books", function(data, error) {{
        if (error || !data || !Array.isArray(data.books)) {{
          var container = document.querySelector("[data-library-results]");
          if (container) {{ container.textContent = ""; appendEmpty(container, "Could not load the cached library. Refresh the library or check the connection.", true); }}
          return;
        }}
        remoteBooks = data.books;
        renderRemoteLibrary();
      }});
    }}
    function refreshRecentPlayback() {{
      var container = document.querySelector("[data-recent-results]");
      if (!container) {{ return; }}
      getJson("/player/recent", function(data, error) {{
        container.textContent = "";
        if (error || !data || !Array.isArray(data.items)) {{ appendEmpty(container, "Could not load device history.", true); return; }}
        if (!data.items.length) {{ appendEmpty(container, "No books have been played on this device yet."); return; }}
        data.items.forEach(function(item) {{
          addRemoteBook(container, {{bookId: item.bookId, title: item.title, author: item.author, currentTime: item.currentTime, duration: item.duration, progress: item.progress, lastPlayedAt: item.lastPlayedAt, inProgress: item.progress > 0 && item.progress < 0.995, finished: item.progress >= 0.995}}, true);
        }});
      }});
    }}
    function renderBluetoothDevices(data) {{
      var container = document.querySelector("[data-bluetooth-devices]");
      if (!container) {{ return; }}
      container.textContent = "";
      var devices = data && Array.isArray(data.devices) ? data.devices : [];
      if (!devices.length) {{ appendEmpty(container, "Scan to find nearby audio devices."); return; }}
      devices.forEach(function(device) {{
        var row = textElement("div", "remote-book", "");
        var info = document.createElement("div");
        info.appendChild(textElement("div", "remote-book-title", device.name));
        info.appendChild(textElement("div", "remote-book-meta", device.address));
        var actions = textElement("div", "remote-book-actions", "");
        var pair = textElement("button", "", "Connect");
        pair.type = "button";
        pair.addEventListener("click", function() {{
          var message = document.querySelector("[data-bluetooth-message]");
          if (message) {{ message.textContent = "Connecting to " + device.name + "…"; }}
          postPlayer({{action: "bluetooth_pair", device_address: device.address, device_name: device.name}}, function() {{
            window.setTimeout(refreshPlayerStatus, 500);
          }});
        }});
        actions.appendChild(pair);
        row.appendChild(info);
        row.appendChild(actions);
        container.appendChild(row);
      }});
    }}
    function refreshBluetoothDevices() {{
      getJson("/bluetooth/devices", function(data, error) {{
        if (!error) {{ renderBluetoothDevices(data); }}
      }});
    }}
    function pollBluetoothScan(startedAt, deadline) {{
      getJson("/bluetooth/devices", function(data, error) {{
        var message = document.querySelector("[data-bluetooth-message]");
        if (!error && data && !data.scanning && Number(data.updatedAt || 0) >= startedAt) {{
          renderBluetoothDevices(data);
          if (message) {{ message.textContent = data.devices.length ? "Choose a device to connect." : "No audio devices found. Try scanning again."; }}
          refreshPlayerStatus();
          return;
        }}
        if (Date.now() >= deadline) {{
          if (message) {{ message.textContent = "Bluetooth scan timed out. Try again."; }}
          return;
        }}
        window.setTimeout(function() {{ pollBluetoothScan(startedAt, deadline); }}, 1500);
      }});
    }}
    document.querySelectorAll("[data-bluetooth-command]").forEach(function(button) {{
      button.addEventListener("click", function() {{
        var action = button.getAttribute("data-bluetooth-command");
        var message = document.querySelector("[data-bluetooth-message]");
        if (message) {{ message.textContent = action === "bluetooth_scan" ? "Scanning for audio devices…" : "Bluetooth command sent."; }}
        if (action === "bluetooth_scan") {{
          var scanStartedAt = Date.now() / 1000 - 1;
          postPlayer({{action: action}}, function() {{ pollBluetoothScan(scanStartedAt, Date.now() + 40000); }});
        }} else {{
          postPlayer({{action: action}}, function() {{ window.setTimeout(refreshPlayerStatus, 500); }});
        }}
      }});
    }});
    refreshBluetoothDevices();
    document.querySelectorAll("[data-browse-mode]").forEach(function(button) {{
      button.addEventListener("click", function() {{
        remoteMode = button.getAttribute("data-browse-mode");
        remoteGroup = "";
        document.querySelectorAll("[data-browse-mode]").forEach(function(choice) {{ choice.classList.toggle("is-active", choice === button); }});
        renderRemoteLibrary();
      }});
    }});
    var librarySearch = document.querySelector("[data-library-search]");
    if (librarySearch) {{ librarySearch.addEventListener("input", function() {{ remoteSearchText = librarySearch.value; renderRemoteLibrary(); }}); }}
    var backToGroupsButton = document.querySelector("[data-back-groups]");
    if (backToGroupsButton) {{ backToGroupsButton.addEventListener("click", function() {{ remoteGroup = ""; renderRemoteLibrary(); }}); }}
    var clearRecentButton = document.querySelector("[data-clear-recent]");
    if (clearRecentButton) {{ clearRecentButton.addEventListener("click", function() {{
      postPlayer({{action: "clear_recent"}}, function(status) {{ if (status >= 200 && status < 300) {{ refreshRecentPlayback(); }} }});
    }}); }}
    var libraryRefreshButton = document.querySelector("[data-library-refresh]");
    if (libraryRefreshButton) {{ libraryRefreshButton.addEventListener("click", function() {{
      libraryRefreshButton.disabled = true;
      postPlayer({{action: "refresh_books"}}, function() {{
        window.setTimeout(function() {{ refreshRemoteLibrary(); libraryRefreshButton.disabled = false; }}, 1500);
      }});
    }}); }}
    document.querySelectorAll("[data-player-command]").forEach(function(button) {{
      button.addEventListener("click", function() {{
        postPlayer({{action: button.getAttribute("data-player-command")}}, function() {{
          window.setTimeout(refreshPlayerStatus, 300);
          window.setTimeout(refreshPlayerStatus, 800);
        }});
      }});
    }});
    refreshRemoteLibrary();
    refreshRecentPlayback();
    function addPodcastRow(value) {{
      if (!podcastRows) {{
        return;
      }}
      var row = document.createElement("div");
      row.className = "podcast-row";
      var inputWrap = document.createElement("div");
      var input = document.createElement("input");
      input.name = "podcast_url";
      input.type = "url";
      input.placeholder = "https://podcasts.apple.com/...";
      input.value = value || "";
      var meta = document.createElement("div");
      meta.className = "podcast-meta";
      meta.textContent = "Paste a show link from podcasts.apple.com";
      var remove = document.createElement("button");
      remove.className = "small-button secondary";
      remove.type = "button";
      remove.textContent = "Remove";
      remove.setAttribute("data-remove-podcast-row", "1");
      inputWrap.appendChild(input);
      inputWrap.appendChild(meta);
      row.appendChild(inputWrap);
      row.appendChild(remove);
      podcastRows.appendChild(row);
      attachPodcastRemoveButtons();
      input.focus();
    }}
    function attachPodcastRemoveButtons() {{
      var buttons = document.querySelectorAll("[data-remove-podcast-row]");
      buttons.forEach(function(button) {{
        if (button.getAttribute("data-bound") === "1") {{
          return;
        }}
        button.setAttribute("data-bound", "1");
        button.addEventListener("click", function() {{
          var row = button.closest(".podcast-row");
          if (row) {{
            row.remove();
          }}
          if (podcastRows && !podcastRows.querySelector(".podcast-row")) {{
            addPodcastRow("");
          }}
        }});
      }});
    }}
    if (playbackForm) {{
      playbackForm.addEventListener("submit", function(event) {{
        event.preventDefault();
        var actionInput = document.querySelector("[data-playback-action]");
        var actionButton = document.querySelector("[data-playback-button]");
        if (!actionInput) {{
          return;
        }}
        setPendingPlayback(actionInput.value);
        sendPlayerAction(actionInput.value);
      }});
    }}
    if (volumeSlider && volumePercent) {{
      volumeSlider.addEventListener("input", function() {{
        volumePercent.textContent = volumeSlider.value + "%";
        window.clearTimeout(volumeTimer);
        volumeTimer = window.setTimeout(function() {{
          sendVolume(volumeSlider.value);
        }}, 120);
      }});
      volumeSlider.addEventListener("change", function() {{
        window.clearTimeout(volumeTimer);
        sendVolume(volumeSlider.value);
      }});
    }}
    if (addPodcastRowButton) {{
      addPodcastRowButton.addEventListener("click", function() {{
        addPodcastRow("");
      }});
    }}
    attachPodcastRemoveButtons();
    startPlayerEventStream();
    refreshPlayerStatus();
    window.setInterval(renderLivePlayerTime, 1000);
  </script>
</body>
</html>
"""


HEALTH_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Audiobookshelf Player Health</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      min-height: 100vh;
      background: #f3f0e8;
      color: #20242a;
      display: grid;
      place-items: center;
    }}
    main {{
      width: min(92vw, 560px);
      background: #fff;
      border: 1px solid #d9d3c7;
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 18px 48px rgba(0, 0, 0, 0.12);
    }}
    h1 {{ margin: 0 0 18px; font-size: 1.5rem; }}
    .row {{
      border-top: 1px solid #eee7dc;
      padding: 16px 0;
    }}
    .label {{
      color: #59616d;
      font-size: 0.92rem;
      margin-bottom: 4px;
    }}
    .value {{ font-size: 1.1rem; }}
    .value strong {{ font-weight: 800; }}
    .ok {{ color: #176c4f; }}
    .bad {{ color: #9b2c2c; }}
    code {{ background: #f1f1f1; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <main>
    <h1>Audiobookshelf Player Health</h1>
    <div class="row">
      <div class="label">Wi-Fi</div>
      <div class="value {wifi_class}">{wifi_value}</div>
    </div>
    <div class="row">
      <div class="label">Audiobookshelf</div>
      <div class="value {abs_class}">{abs_value}</div>
    </div>
    <div class="row">
      <div class="label">Software Version</div>
      <div class="value"><strong>v{version}</strong></div>
    </div>
    <div class="row">
      <div class="label">Setup Page</div>
      <div class="value"><a href="/">Open setup</a></div>
    </div>
  </main>
</body>
</html>
"""


class SetupHandler(BaseHTTPRequestHandler):
    server_version = f"ChapterPlayer/{__version__}"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/assets/chapter-logo.png":
            self.send_logo_png()
            return
        if path == "/player/events":
            self.send_player_events()
            return
        if path == "/player/status":
            self.send_player_status_json()
            return
        if path == "/player/recent":
            self.send_recent_player_history_json()
            return
        if path == "/library/books":
            self.send_library_books_json()
            return
        if path == "/bluetooth/devices":
            self.send_json(load_web_bluetooth_devices())
            return
        if path == "/system/update/status":
            self.send_system_update_status_json()
            return
        if path == "/health":
            self.send_health_page()
            return
        if path != "/":
            self.send_error(404)
            return
        self.send_page()

    def send_logo_png(self) -> None:
        body = LOGO_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/internal/shutdown":
            try:
                is_loopback = ipaddress.ip_address(self.client_address[0]).is_loopback
            except ValueError:
                is_loopback = False
            if not is_loopback:
                self.send_error(403, "Shutdown is available only to local device services.")
                return
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            schedule_system_shutdown()
            return

        handlers = {
            "/wifi": self.handle_wifi_post,
            "/wifi/forget": self.handle_forget_wifi_post,
            "/player": self.handle_player_post,
            "/settings/click": self.handle_click_setting_post,
            "/settings/spoken-navigation": self.handle_spoken_navigation_setting_post,
            "/settings/library-order": self.handle_library_sort_setting_post,
            "/settings/navigation": self.handle_navigation_settings_post,
            "/settings/playback-speed": self.handle_playback_speed_setting_post,
            "/settings/screensaver": self.handle_screen_saver_setting_post,
            "/settings/sleep": self.handle_sleep_setting_post,
            "/podcasts": self.handle_podcasts_post,
            "/system/reboot": self.handle_system_reboot_post,
            "/system/update": self.handle_system_update_post,
            "/system/reset": self.handle_system_reset_post,
            "/login": self.handle_login_post,
        }
        handler = handlers.get(path)
        if handler is None:
            self.send_error(404)
            return

        fields = self.post_fields()
        if fields is None:
            return
        submitted_token = one(fields, CSRF_FIELD_NAME)
        if not submitted_token or not hmac.compare_digest(submitted_token, self.csrf_token()):
            self.send_csrf_error()
            return
        handler()

    def csrf_token(self) -> str:
        return getattr(getattr(self, "server", None), "csrf_token", "")

    def post_fields(self) -> dict[str, list[str]] | None:
        cached = getattr(self, "_post_fields", None)
        if cached is not None:
            return cached
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            self.send_request_error(400, "Invalid request length.")
            return None
        if length < 0:
            self.send_request_error(400, "Invalid request length.")
            return None
        if length > MAX_POST_BODY_BYTES:
            self.send_request_error(413, "Request is too large.")
            return None
        try:
            body = self.rfile.read(length).decode("utf-8")
        except UnicodeDecodeError:
            self.send_request_error(400, "Request must use UTF-8 text.")
            return None
        fields = parse_qs(body, keep_blank_values=True)
        self._post_fields = fields
        return fields

    def handle_wifi_post(self) -> None:
        fields = self.post_fields()
        if fields is None:
            return
        ssid = one(fields, "wifi_ssid")
        password = one(fields, "wifi_password")

        if not ssid:
            self.send_page(message="Wi-Fi network name is required.", is_error=True)
            return

        schedule_wifi_connect(ssid, password)
        self.send_page(
            message="Wi-Fi change submitted. The player will switch networks in a moment."
        )

    def handle_forget_wifi_post(self) -> None:
        schedule_wifi_forget()
        self.send_page(
            message=(
                f"Wi-Fi forget submitted. In about 5 seconds, connect to "
                f"{html.escape(SETUP_HOTSPOT_SSID)}, then browse to {html.escape(SETUP_HOTSPOT_URL)}."
            )
        )

    def handle_login_post(self) -> None:
        fields = self.post_fields()
        if fields is None:
            return
        server_url = one(fields, "server_url")
        username = one(fields, "username")
        password = one(fields, "password")

        try:
            saved_config = login_and_refresh_player(server_url, username, password)
        except AudiobookshelfError as error:
            self.send_page(
                message=f"Login failed: {html.escape(str(error))}",
                is_error=True,
                server_url=server_url,
                library_id="",
            )
            return

        self.send_page(
            message="Player login saved. You can close this page and restart the player.",
            server_url=saved_config.server_url,
            library_id=saved_config.library_id,
        )

    def handle_player_post(self) -> None:
        fields = self.post_fields()
        if fields is None:
            return
        action = one(fields, "action")

        if action in {"play", "pause", "toggle"}:
            queue_web_player_command(action)
            self.send_player_command_response()
            return

        if action in {"previous_chapter", "next_chapter"}:
            queue_web_player_command(action)
            self.send_player_command_response()
            return

        if action in {"bluetooth_enable", "bluetooth_disable", "bluetooth_scan", "bluetooth_unpair"}:
            if action == "bluetooth_scan":
                save_web_bluetooth_devices([], scanning=True)
            queue_web_player_command(action)
            self.send_player_command_response()
            return

        if action == "bluetooth_pair":
            device_address = one(fields, "device_address").upper()
            device_name = one(fields, "device_name")
            if not MAC_ADDRESS_PATTERN.fullmatch(device_address) or not device_name:
                self.send_request_error(400, "Choose a valid Bluetooth device from a recent scan.")
                return
            queue_web_player_command(
                action,
                device_address=device_address,
                device_name=device_name,
            )
            self.send_player_command_response()
            return

        if action == "play_book":
            book_id = one(fields, "book_id").strip()
            book = next((item for item in load_cached_books(load_config()) if item.id == book_id), None)
            if book is None:
                self.send_request_error(404, "That book is not in the player's current library cache.")
                return
            start_over = one(fields, "start_over") == "1"
            queue_web_player_command(
                action,
                book_id=book.id,
                start_over=start_over,
                resume_time=0.0 if start_over else book.current_time,
            )
            self.send_player_command_response()
            return

        if action == "clear_recent":
            clear_device_playback_history()
            self.send_player_command_response()
            return

        if action == "volume":
            try:
                volume = min(max(int(one(fields, "volume")), 0), 100)
            except ValueError:
                self.send_page(message="Volume must be between 0 and 100.", is_error=True)
                return
            queue_web_player_command("volume", volume)
            self.send_player_command_response()
            return

        self.send_page(message="Unknown player command.", is_error=True)

    def handle_click_setting_post(self) -> None:
        fields = self.post_fields()
        if fields is None:
            return
        enabled = one(fields, "enabled") == "1"
        save_click_setting(enabled)
        self.redirect_home()

    def handle_spoken_navigation_setting_post(self) -> None:
        fields = self.post_fields()
        if fields is None:
            return
        enabled = one(fields, "enabled") == "1"
        save_spoken_navigation_setting(enabled)
        self.redirect_home()

    def handle_navigation_settings_post(self) -> None:
        fields = self.post_fields()
        if fields is None:
            return
        save_navigation_settings(fields)
        self.redirect_home()

    def handle_library_sort_setting_post(self) -> None:
        fields = self.post_fields()
        if fields is None:
            return
        save_library_sort_setting(one(fields, "library_sort_mode"))
        self.redirect_home()

    def handle_playback_speed_setting_post(self) -> None:
        fields = self.post_fields()
        if fields is None:
            return
        save_playback_speed_setting(one(fields, "playback_speed"))
        self.redirect_home()

    def handle_screen_saver_setting_post(self) -> None:
        fields = self.post_fields()
        if fields is None:
            return
        mode = valid_screen_saver_mode(one(fields, "screen_saver_mode"))
        if "screen_saver_dim_percent" in fields:
            save_screen_saver_setting(
                mode,
                valid_screen_saver_dim_percent(one(fields, "screen_saver_dim_percent")),
            )
        else:
            save_screen_saver_setting(mode)
        self.redirect_home()

    def handle_sleep_setting_post(self) -> None:
        fields = self.post_fields()
        if fields is None:
            return
        if "enabled" in fields:
            save_sleep_timer_setting(enabled=one(fields, "enabled") == "1")
            self.redirect_home()
            return
        try:
            minutes = int(one(fields, "minutes"))
        except ValueError:
            self.send_page(message="Sleep timer must be a whole number of minutes.", is_error=True)
            return
        save_sleep_timer_setting(minutes=minutes)
        self.redirect_home()

    def handle_podcasts_post(self) -> None:
        fields = self.post_fields()
        if fields is None:
            return
        urls = fields.get("podcast_url", [])
        try:
            save_podcast_settings(urls)
        except PodcastError as error:
            self.send_page(message=f"Podcast save failed: {html.escape(str(error))}", is_error=True)
            return
        self.redirect_home()

    def handle_system_reboot_post(self) -> None:
        self.send_page(message="Rebooting the Chapter player. It will be available again shortly.")
        schedule_system_reboot()

    def handle_system_update_post(self) -> None:
        save_update_state(
            SoftwareUpdateState(
                phase="installing",
                message="Preparing the software update.",
                updated_at=time.time(),
            )
        )
        queue_web_player_command("pause")
        self.send_page(
            message=(
                "Software update started. Playback is paused while Chapter installs the latest "
                "release and restarts its services."
            )
        )
        schedule_software_update()

    def handle_system_reset_post(self) -> None:
        restore_device_defaults()
        self.send_page(
            message=(
                f"Default settings restored. In about 5 seconds, connect to "
                f"{html.escape(SETUP_HOTSPOT_SSID)}, then browse to {html.escape(SETUP_HOTSPOT_URL)}."
            )
        )
        schedule_system_reset()

    def send_page(
        self,
        message: str = "",
        is_error: bool = False,
        server_url: str | None = None,
        library_id: str | None = None,
    ) -> None:
        config = load_config()
        message_html = ""
        if message:
            css_class = "message error" if is_error else "message"
            message_html = f'<div class="{css_class}">{message}</div>'

        wifi = wifi_status()
        csrf_token = self.csrf_token()
        body = PAGE.format(
            status_panel=render_status_panel(
                wifi,
                audiobookshelf_status(),
                load_web_player_status(),
                bluetooth_status(),
                csrf_token,
            ),
            remote_control_panel=render_remote_control_panel(csrf_token),
            settings_card=render_settings_card(config, csrf_token),
            podcasts_card=render_podcasts_card(config, csrf_token),
            wifi_card=render_wifi_card(wifi, csrf_token),
            system_card=render_system_card(csrf_token),
            message=message_html,
            server_url=html.escape(server_url if server_url is not None else config.server_url),
            library_id=html.escape(library_id if library_id is not None else config.library_id),
            csrf_token=html.escape(csrf_token, quote=True),
            csrf_input=render_csrf_input(csrf_token),
            csrf_field_name=CSRF_FIELD_NAME,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_csrf_error(self) -> None:
        self.send_request_error(
            403,
            "This page has expired. Reload the Chapter setup page, then try again.",
        )

    def send_request_error(self, status: int, message: str) -> None:
        body = (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Chapter Player</title></head><body><main>"
            f"<h1>Chapter Player</h1><p>{html.escape(message)}</p>"
            '<p><a href="/">Reload setup page</a></p></main></body></html>'
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect_home(self) -> None:
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_player_command_response(self) -> None:
        if self.headers.get("X-Requested-With") == "fetch":
            self.send_response(204)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.redirect_home()

    def send_text(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data: dict | list) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_player_status_json(self) -> None:
        self.send_json(player_status_payload(load_web_player_status()))

    def send_recent_player_history_json(self) -> None:
        self.send_json(
            {
                "items": [
                    {
                        "bookId": item.book_id,
                        "title": item.title,
                        "author": item.author,
                        "currentTime": item.current_time,
                        "duration": item.duration,
                        "startedAt": item.started_at,
                        "lastPlayedAt": item.last_played_at,
                        "progress": item.current_time / item.duration if item.duration > 0 else 0.0,
                    }
                    for item in load_device_playback_history(30)
                ]
            }
        )

    def send_library_books_json(self) -> None:
        config = load_config()
        books = load_cached_books(config)
        recent_by_id = {item.book_id: item for item in load_device_playback_history(50)}
        payload = []
        for book in books:
            recent = recent_by_id.get(book.id)
            last_update = timestamp_seconds(book.last_update)
            if recent is not None and recent.last_played_at >= last_update:
                book.current_time = recent.current_time
                book.duration = recent.duration or book.duration
                book.progress = book.current_time / book.duration if book.duration > 0 else book.progress
                book.finished = book.progress >= 0.995
                last_update = recent.last_played_at
            payload.append(
                {
                    "id": book.id,
                    "title": book.display_title,
                    "author": book.author,
                    "authors": list(book.authors),
                    "seriesName": book.series_name,
                    "seriesPosition": book.series_position,
                    "duration": book.duration,
                    "currentTime": book.current_time,
                    "progress": book.progress,
                    "finished": book.is_finished,
                    "inProgress": book.is_in_progress,
                    "lastUpdate": last_update,
                }
            )
        self.send_json({"books": payload, "count": len(payload)})

    def send_system_update_status_json(self) -> None:
        self.send_json(update_status_payload())

    def send_player_events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        last_payload = ""
        last_signature = ""
        last_sent = 0.0
        last_heartbeat = time.monotonic()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        while True:
            payload = player_status_payload(load_web_player_status())
            payload_json = json.dumps(payload, separators=(",", ":"))
            signature = player_status_event_signature(payload)
            now = time.monotonic()
            should_send = not last_payload
            should_send = should_send or signature != last_signature
            should_send = should_send or (payload_json != last_payload and now - last_sent >= PLAYER_EVENT_TIME_SECONDS)
            if should_send:
                try:
                    self.wfile.write(player_status_sse(payload_json))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    return
                last_payload = payload_json
                last_signature = signature
                last_sent = now
                last_heartbeat = now
            elif now - last_heartbeat >= PLAYER_EVENT_HEARTBEAT_SECONDS:
                try:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    return
                last_heartbeat = now
            time.sleep(PLAYER_EVENT_POLL_SECONDS)

    def send_health_page(self) -> None:
        wifi = wifi_status()
        abs_status = audiobookshelf_status()
        body = render_health_page(wifi, abs_status).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def one(fields: dict[str, list[str]], name: str) -> str:
    return fields.get(name, [""])[0].strip()


def timestamp_seconds(value: object) -> float:
    try:
        timestamp = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return timestamp / 1000.0 if timestamp >= 100_000_000_000 else timestamp


def render_csrf_input(csrf_token: str) -> str:
    return (
        f'<input type="hidden" name="{CSRF_FIELD_NAME}" '
        f'value="{html.escape(csrf_token, quote=True)}">'
    )


def schedule_wifi_connect(ssid: str, password: str) -> None:
    def worker() -> None:
        try:
            print(f"Wi-Fi connection starting for {ssid}", flush=True)
            connect_wifi(ssid, password)
            print(f"Wi-Fi connection complete for {ssid}", flush=True)
        except WifiError as error:
            print(f"Wi-Fi connection failed: {error}", flush=True)

    timer = threading.Timer(WIFI_CHANGE_DELAY_SECONDS, worker)
    timer.daemon = True
    timer.start()


def schedule_wifi_forget(delay_seconds: float = WIFI_CHANGE_DELAY_SECONDS) -> None:
    def worker() -> None:
        try:
            print(f"Wi-Fi forget starting; switching to {SETUP_HOTSPOT_SSID}", flush=True)
            forget_current_wifi_and_start_hotspot()
            print(f"Wi-Fi forget complete; {SETUP_HOTSPOT_SSID} should be active", flush=True)
        except WifiError as error:
            print(f"Wi-Fi forget failed: {error}", flush=True)

    timer = threading.Timer(delay_seconds, worker)
    timer.daemon = True
    timer.start()


SystemCommandRunner = Callable[[list[str]], subprocess.CompletedProcess]
UpdateDisplayReadyWaiter = Callable[[], bool]


def run_system_command(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, check=True, text=True)


def schedule_system_reboot(
    delay_seconds: float = SYSTEM_ACTION_DELAY_SECONDS,
    runner: SystemCommandRunner = run_system_command,
) -> None:
    def worker() -> None:
        try:
            print("System reboot starting", flush=True)
            runner(["systemctl", "reboot"])
        except (OSError, subprocess.CalledProcessError) as error:
            print(f"System reboot failed: {error}", flush=True)

    timer = threading.Timer(delay_seconds, worker)
    timer.daemon = True
    timer.start()


def schedule_system_shutdown(
    delay_seconds: float = SYSTEM_ACTION_DELAY_SECONDS,
    runner: SystemCommandRunner = run_system_command,
) -> None:
    def worker() -> None:
        try:
            print("System shutdown starting", flush=True)
            runner(["systemctl", "poweroff"])
        except (OSError, subprocess.CalledProcessError) as error:
            print(f"System shutdown failed: {error}", flush=True)

    timer = threading.Timer(delay_seconds, worker)
    timer.daemon = True
    timer.start()


def schedule_software_update(
    delay_seconds: float = SYSTEM_ACTION_DELAY_SECONDS,
    runner: SystemCommandRunner = run_system_command,
    display_ready_waiter: UpdateDisplayReadyWaiter = wait_for_update_display_ready,
) -> None:
    def worker() -> None:
        try:
            if not display_ready_waiter():
                print("Software update display acknowledgement timed out; continuing", flush=True)
            print("Software update starting", flush=True)
            runner(["systemctl", "start", "--no-block", UPDATE_SERVICE_NAME])
        except (OSError, subprocess.CalledProcessError) as error:
            print(f"Software update failed to start: {error}", flush=True)
            save_update_state(
                SoftwareUpdateState(
                    phase="failed",
                    message="Software update could not start. Please try again.",
                    updated_at=time.time(),
                )
            )

    timer = threading.Timer(delay_seconds, worker)
    timer.daemon = True
    timer.start()


def restore_device_defaults() -> AppConfig:
    config = AppConfig()
    save_config(config)
    clear_cached_books()
    clear_last_playback()
    clear_device_playback_history()
    save_web_bluetooth_devices([])
    queue_web_player_command("refresh_library")
    return config


def schedule_system_reset(delay_seconds: float = WIFI_CHANGE_DELAY_SECONDS) -> None:
    def worker() -> None:
        try:
            print(f"System reset starting; switching to {SETUP_HOTSPOT_SSID}", flush=True)
            forget_all_wifi_connections_and_start_hotspot()
            print(f"System reset complete; {SETUP_HOTSPOT_SSID} should be active", flush=True)
        except WifiError as error:
            print(f"System reset Wi-Fi change failed: {error}", flush=True)

    timer = threading.Timer(delay_seconds, worker)
    timer.daemon = True
    timer.start()


def login_and_refresh_player(server_url: str, username: str, password: str) -> AppConfig:
    existing_config = load_config()
    client, login_data = AudiobookshelfClient.login(server_url, username, password)
    resolved_library_id = str(login_data.get("userDefaultLibraryId") or "")
    if not resolved_library_id:
        resolved_library_id = client.choose_library_id()
    config = replace(
        existing_config,
        server_url=server_url.strip(),
        token=client.token,
        refresh_token=getattr(client, "refresh_token", ""),
        library_id=resolved_library_id,
        username=login_username(login_data, username),
    )
    save_config(config)
    queue_web_player_command("pause")
    queue_web_player_command("refresh_library")
    return config


def save_click_setting(enabled: bool) -> AppConfig:
    config = load_config()
    updated = replace(
        config,
        control_click_enabled=enabled,
    )
    save_config(updated)
    return updated


def save_spoken_navigation_setting(enabled: bool) -> AppConfig:
    config = load_config()
    updated = replace(config, spoken_navigation_enabled=enabled)
    save_config(updated)
    return updated


def save_navigation_settings(fields: dict[str, list[str]]) -> AppConfig:
    config = load_config()
    order_with_positions = []
    for fallback_position, menu_id in enumerate(DEFAULT_ROOT_MENU_ORDER):
        try:
            position = int(one(fields, f"menu_order_{menu_id}"))
        except ValueError:
            position = fallback_position
        order_with_positions.append((max(0, min(20, position)), fallback_position, menu_id))
    order = valid_root_menu_order(
        [menu_id for _position, _fallback, menu_id in sorted(order_with_positions)]
    )
    enabled = valid_root_menu_enabled(fields.get("menu_enabled", []))
    updated = replace(
        config,
        knob_hold_seconds=valid_long_press_seconds(one(fields, "knob_hold_seconds"), config.knob_hold_seconds),
        marquee_delay_seconds=(
            valid_marquee_delay(one(fields, "marquee_delay_seconds"))
            if "marquee_delay_seconds" in fields
            else config.marquee_delay_seconds
        ),
        marquee_speed_px_per_second=(
            valid_marquee_speed(one(fields, "marquee_speed_px_per_second"))
            if "marquee_speed_px_per_second" in fields
            else config.marquee_speed_px_per_second
        ),
        marquee_loop_pause_seconds=(
            valid_marquee_loop_pause(one(fields, "marquee_loop_pause_seconds"))
            if "marquee_loop_pause_seconds" in fields
            else config.marquee_loop_pause_seconds
        ),
        navigation_acceleration_mode=valid_navigation_acceleration_mode(
            one(fields, "navigation_acceleration_mode")
            if "navigation_acceleration_mode" in fields
            else config.navigation_acceleration_mode
        ),
        navigation_accel_threshold_milliseconds=valid_acceleration_milliseconds(
            one(fields, "navigation_accel_threshold_milliseconds")
            if "navigation_accel_threshold_milliseconds" in fields
            else config.navigation_accel_threshold_milliseconds,
            config.navigation_accel_threshold_milliseconds,
        ),
        startup_resume_last_played=one(fields, "startup_resume_last_played").lower() in {"1", "true", "on", "yes"},
        browse_return_seconds=(
            valid_browse_return_seconds(one(fields, "browse_return_seconds"))
            if "browse_return_seconds" in fields
            else config.browse_return_seconds
        ),
        screen_saver_idle_seconds=(
            valid_screen_saver_idle_seconds(one(fields, "screen_saver_idle_seconds"))
            if "screen_saver_idle_seconds" in fields
            else config.screen_saver_idle_seconds
        ),
        root_menu_order=order,
        root_menu_enabled=enabled,
    )
    save_config(updated)
    return updated


def save_library_sort_setting(mode: str) -> AppConfig:
    config = load_config()
    updated = replace(config, library_sort_mode=valid_library_sort_mode(mode))
    save_config(updated)
    queue_web_player_command("resort_library")
    return updated


def save_playback_speed_setting(speed: object) -> AppConfig:
    config = load_config()
    updated = replace(config, playback_speed=valid_playback_speed(speed))
    save_config(updated)
    return updated


def save_screen_saver_setting(mode: str, dim_percent: int | None = None) -> AppConfig:
    config = load_config()
    updated = replace(
        config,
        screen_saver_mode=valid_screen_saver_mode(mode),
        screen_saver_dim_percent=(
            config.screen_saver_dim_percent
            if dim_percent is None
            else valid_screen_saver_dim_percent(dim_percent)
        ),
    )
    save_config(updated)
    return updated


def save_sleep_timer_setting(
    enabled: bool | None = None,
    minutes: int | None = None,
) -> AppConfig:
    config = load_config()
    updated = replace(
        config,
        sleep_timer_enabled=config.sleep_timer_enabled if enabled is None else enabled,
        sleep_timer_minutes=(
            config.sleep_timer_minutes
            if minutes is None
            else valid_sleep_timer_minutes(minutes)
        ),
    )
    save_config(updated)
    return updated


def save_podcast_settings(urls: list[str]) -> AppConfig:
    podcasts = [resolve_podcast_config(url) for url in normalized_podcast_urls(urls)]
    config = load_config()
    updated = replace(config, podcasts=podcasts)
    save_config(updated)
    queue_web_player_command("refresh_library")
    return updated


def normalized_podcast_urls(urls: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for url in urls:
        clean_url = url.strip()
        if not clean_url:
            continue
        key = clean_url.lower()
        if key in seen:
            continue
        normalized.append(clean_url)
        seen.add(key)
    return normalized


def audiobookshelf_status() -> tuple[bool, str]:
    config = load_config()
    if not config.is_ready:
        return False, "Not configured"

    try:
        client = client_from_config(config, AudiobookshelfClient)
        client.choose_library_id(config.library_id)
        username = saved_username(config.username)
        if not username:
            username = login_username(client.get_current_user(), "")
            if username:
                save_config(replace(config, username=username))
    except AudiobookshelfError as error:
        return False, str(error)

    if username:
        return True, f"Logged in to {config.server_url} as {username}"
    return True, f"Logged in to {config.server_url}"


def bluetooth_status() -> tuple[bool, str]:
    device = connected_bluetooth_audio_device()
    if device is None:
        return False, "Not connected"
    return True, f"Connected to {device.name}"


def render_health_page(wifi: WifiStatus, abs_status: tuple[bool, str]) -> str:
    abs_ok, abs_message = abs_status
    return HEALTH_PAGE.format(
        wifi_class="ok" if wifi.connected else "bad",
        wifi_value=render_wifi_status_value(wifi),
        abs_class="ok" if abs_ok else "bad",
        abs_value=render_audiobookshelf_status_value(abs_message),
        version=html.escape(__version__),
    )


def render_status_panel(
    wifi: WifiStatus,
    abs_status: tuple[bool, str],
    player_status: WebPlayerStatus | None = None,
    bt_status: tuple[bool, str] = (False, "Not connected"),
    csrf_token: str = "",
) -> str:
    abs_ok, abs_message = abs_status
    bt_ok, bt_message = bt_status
    player_status = player_status or WebPlayerStatus()
    return """
    <section class="card" aria-labelledby="status-heading">
      <h2 id="status-heading">Status</h2>
      <div class="status" aria-label="Player status">
        <div class="status-row">
          <div class="status-label">Wi-Fi</div>
          <div class="status-value {wifi_class}">{wifi_value}</div>
        </div>
        <div class="status-row">
          <div class="status-label">Audiobookshelf</div>
          <div class="status-value {abs_class}">{abs_value}</div>
        </div>
        <div class="status-row">
          <div class="status-label">Bluetooth</div>
          <div class="status-value {bt_class}">{bt_value}</div>
        </div>
        <div class="status-row">
          <div class="status-label">Currently Playing</div>
          {player_value}
        </div>
      </div>
    </section>
    """.format(
        wifi_class="ok" if wifi.connected else "bad",
        wifi_value=render_wifi_status_value(wifi),
        abs_class="ok" if abs_ok else "bad",
        abs_value=render_audiobookshelf_status_value(abs_message),
        bt_class="ok" if bt_ok else "bad",
        bt_value=render_bluetooth_status_value(bt_message),
        player_value=render_player_status_value(player_status, csrf_token),
    )


def render_remote_control_panel(csrf_token: str = "") -> str:
    return """
    <section class="card remote-card" aria-labelledby="remote-heading">
      <h2 id="remote-heading">Remote control</h2>
      <p class="hint">Browse this player’s cached library and start a book without using the knobs.</p>
      <div class="remote-toolbar" role="group" aria-label="Browse library">
        <button class="is-active" type="button" data-browse-mode="title">Titles</button>
        <button type="button" data-browse-mode="continue">Continue listening</button>
        <button type="button" data-browse-mode="series">Series</button>
        <button type="button" data-browse-mode="author">Authors</button>
        <button class="secondary" type="button" data-library-refresh>Refresh library</button>
      </div>
      <div class="remote-toolbar" data-group-back-row hidden>
        <button class="secondary" type="button" data-back-groups>Back to groups</button>
      </div>
      <label class="sr-only" for="remote-library-search">Search the library</label>
      <input class="remote-search" id="remote-library-search" type="search" placeholder="Search title, author, or series" data-library-search>
      <div class="remote-library-list" data-library-results aria-live="polite">
        <div class="remote-empty">Loading the player’s library…</div>
      </div>
      <div class="remote-section">
        <h3>Recently played on this player</h3>
        <p class="hint">This history is stored on the Chapter device and is separate from your Audiobookshelf account history.</p>
        <div class="remote-recent-list" data-recent-results aria-live="polite">
          <div class="remote-empty">Loading recent playback…</div>
        </div>
        <button class="small-button secondary" type="button" data-clear-recent>Clear this player’s history</button>
      </div>
      <div class="remote-section">
        <h3>Bluetooth audio</h3>
        <p class="hint">Manage the headphones or speaker connected to this Chapter player.</p>
        <div class="remote-toolbar" role="group" aria-label="Bluetooth controls">
          <button class="secondary" type="button" data-bluetooth-command="bluetooth_enable">Turn Bluetooth on</button>
          <button class="secondary" type="button" data-bluetooth-command="bluetooth_disable">Turn Bluetooth off</button>
          <button class="secondary" type="button" data-bluetooth-command="bluetooth_scan">Scan for devices</button>
          <button class="secondary" type="button" data-bluetooth-command="bluetooth_unpair">Disconnect device</button>
        </div>
        <div class="remote-book-meta" data-bluetooth-message aria-live="polite"></div>
        <div class="remote-library-list" data-bluetooth-devices></div>
      </div>
    </section>
    """


def render_system_card(csrf_token: str = "") -> str:
    return """
    <section class="card" aria-labelledby="system-heading">
      <h2 id="system-heading">System</h2>
      <div class="system-version">
        <div>
          <span class="system-version-label">Software Version</span>
          <strong class="system-version-number">v{version}</strong>
          <span class="system-update-status" data-system-update-status aria-live="polite">Checking for updates...</span>
          <p class="system-update-description" data-system-update-description></p>
        </div>
        <button type="button" aria-expanded="false" aria-controls="confirm-update" data-confirm-trigger="update" data-system-update-trigger hidden>Update</button>
        <div class="confirmation-panel update-confirmation" id="confirm-update" data-confirm-panel="update" hidden>
          <strong>Install <span data-system-update-version>the latest release</span>?</strong>
          <p>Playback will pause and the player controls may be unavailable for a few minutes. Your Wi-Fi, Audiobookshelf login, podcasts, and settings will be kept.</p>
          <div class="confirmation-actions">
            <button class="secondary" type="button" data-confirm-cancel>Cancel</button>
            <form method="post" action="/system/update">
              {csrf_input}
              <button type="submit">Install Update</button>
            </form>
          </div>
        </div>
      </div>
      <div class="system-actions">
        <div class="system-action">
          <div>
            <h3>Reboot</h3>
            <p>Restart the Chapter player without changing its settings.</p>
          </div>
          <button class="secondary" type="button" aria-expanded="false" aria-controls="confirm-reboot" data-confirm-trigger="reboot">Reboot</button>
          <div class="confirmation-panel" id="confirm-reboot" data-confirm-panel="reboot" hidden>
            <strong>Are you sure you want to reboot?</strong>
            <p>Playback will stop while the device restarts.</p>
            <div class="confirmation-actions">
              <button class="secondary" type="button" data-confirm-cancel>Cancel</button>
              <form method="post" action="/system/reboot">
                {csrf_input}
                <button type="submit">Reboot</button>
              </form>
            </div>
          </div>
        </div>
        <div class="system-action">
          <div>
            <h3>Restore Device to Default Settings</h3>
            <p>Clear this player and return it to Wi-Fi setup mode.</p>
          </div>
          <button class="danger-button" type="button" aria-expanded="false" aria-controls="confirm-restore" data-confirm-trigger="restore">Restore</button>
          <div class="confirmation-panel" id="confirm-restore" data-confirm-panel="restore" hidden>
            <strong>Are you sure you want to restore the device to default settings?</strong>
            <p>This clears the Audiobookshelf login, listening state, saved podcasts, and all saved Wi-Fi networks, and restores player settings to defaults. This cannot be undone.</p>
            <div class="confirmation-actions">
              <button class="secondary" type="button" data-confirm-cancel>Cancel</button>
              <form method="post" action="/system/reset">
                {csrf_input}
                <button class="danger-button" type="submit">Restore Device</button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </section>
    """.format(version=html.escape(__version__), csrf_input=render_csrf_input(csrf_token))


def render_root_menu_rows(config: AppConfig) -> str:
    labels = {
        "continue": "Continue Listening",
        "series": "Browse by Series",
        "title": "Browse by Title",
        "author": "Browse by Author",
        "bluetooth": "Bluetooth Settings",
        "shutdown": "Push and hold both knobs to turn off device",
    }
    order = valid_root_menu_order(config.root_menu_order)
    enabled = set(valid_root_menu_enabled(config.root_menu_enabled))
    rows = []
    for menu_id in ROOT_MENU_IDS:
        position = order.index(menu_id) + 1
        options = "".join(
            f'<option value="{value}"{" selected" if value == position else ""}>{value}</option>'
            for value in range(1, len(ROOT_MENU_IDS) + 1)
        )
        rows.append(
            """
            <div class="root-menu-row">
              <label class="root-menu-enabled">
                <input type="checkbox" name="menu_enabled" value="{menu_id}"{checked}>
                <span>{label}</span>
              </label>
              <label class="root-menu-position">
                Position
                <select class="settings-select" name="menu_order_{menu_id}" aria-label="{label} position">
                  {options}
                </select>
              </label>
            </div>
            """.format(
                menu_id=menu_id,
                label=html.escape(labels[menu_id]),
                checked=" checked" if menu_id in enabled else "",
                options=options,
            )
        )
    return "\n".join(rows)


def render_settings_card(config: AppConfig, csrf_token: str = "") -> str:
    csrf_input = render_csrf_input(csrf_token)
    enabled = config.control_click_enabled
    next_value = "0" if enabled else "1"
    toggle_class = " is-on" if enabled else ""
    aria_pressed = "true" if enabled else "false"
    button_label = "Disable control knob click sound" if enabled else "Enable control knob click sound"
    spoken_navigation_enabled = config.spoken_navigation_enabled
    spoken_navigation_next_value = "0" if spoken_navigation_enabled else "1"
    spoken_navigation_toggle_class = " is-on" if spoken_navigation_enabled else ""
    spoken_navigation_aria_pressed = "true" if spoken_navigation_enabled else "false"
    spoken_navigation_button_label = (
        "Disable spoken navigation" if spoken_navigation_enabled else "Enable spoken navigation"
    )
    sleep_enabled = config.sleep_timer_enabled
    sleep_next_value = "0" if sleep_enabled else "1"
    sleep_toggle_class = " is-on" if sleep_enabled else ""
    sleep_aria_pressed = "true" if sleep_enabled else "false"
    sleep_button_label = "Disable sleep timer" if sleep_enabled else "Enable sleep timer"
    sleep_duration_controls = ""
    if sleep_enabled:
        sleep_duration_controls = """
          <form class="sleep-timer-duration-form" method="post" action="/settings/sleep">
            {csrf_input}
            <span>Ask after</span>
            <input class="settings-number" name="minutes" type="number" min="{sleep_min}" max="{sleep_max}" step="1" value="{sleep_minutes}" aria-label="Sleep timer minutes">
            <span>minutes of listening</span>
            <button class="small-button secondary" type="submit">Save</button>
          </form>
        """.format(
            sleep_minutes=config.sleep_timer_minutes,
            sleep_min=MIN_SLEEP_TIMER_MINUTES,
            sleep_max=MAX_SLEEP_TIMER_MINUTES,
            csrf_input=csrf_input,
        )
    return """
    <section class="card" aria-labelledby="settings-heading">
      <h2 id="settings-heading">Settings</h2>
      <div class="settings-list">
        <div class="settings-row">
          <div>
            <div class="setting-name">Control knob click sound</div>
          </div>
          <form class="toggle-form" method="post" action="/settings/click">
            {csrf_input}
            <input type="hidden" name="enabled" value="{next_value}">
            <button class="toggle-button{toggle_class}" type="submit" aria-pressed="{aria_pressed}">
              <span class="sr-only">{button_label}</span>
            </button>
          </form>
        </div>
        <div class="settings-row">
          <div>
            <div class="setting-name">Spoken navigation</div>
          </div>
          <form class="toggle-form" method="post" action="/settings/spoken-navigation">
            {csrf_input}
            <input type="hidden" name="enabled" value="{spoken_navigation_next_value}">
            <button class="toggle-button{spoken_navigation_toggle_class}" type="submit" aria-pressed="{spoken_navigation_aria_pressed}">
              <span class="sr-only">{spoken_navigation_button_label}</span>
            </button>
          </form>
        </div>
        <div class="settings-row">
          <div>
            <div class="setting-name">Playback speed</div>
          </div>
          <form class="select-form" method="post" action="/settings/playback-speed">
            {csrf_input}
            <select class="settings-select" name="playback_speed" aria-label="Playback speed">
              {playback_speed_options}
            </select>
            <button class="small-button secondary" type="submit">Save</button>
          </form>
        </div>
        <div class="settings-row screen-saver-row">
          <div>
            <div class="setting-name">Screen saver</div>
          </div>
          <form class="screen-saver-settings-form" method="post" action="/settings/screensaver">
            {csrf_input}
            <label>
              Style
              <select class="settings-select" name="screen_saver_mode" aria-label="Screen saver style">
                {screen_saver_options}
              </select>
            </label>
            <label>
              Dim level
              <select class="settings-select" name="screen_saver_dim_percent" aria-label="Screen saver dim level">
                {screen_saver_dim_options}
              </select>
            </label>
            <button class="small-button secondary" type="submit">Save</button>
          </form>
        </div>
        <div class="settings-row">
          <div class="sleep-timer-content">
            <div class="setting-name">Sleep timer</div>
            {sleep_duration_controls}
          </div>
          <form class="toggle-form" method="post" action="/settings/sleep">
            {csrf_input}
            <input type="hidden" name="enabled" value="{sleep_next_value}">
            <button class="toggle-button{sleep_toggle_class}" type="submit" aria-pressed="{sleep_aria_pressed}">
              <span class="sr-only">{sleep_button_label}</span>
            </button>
          </form>
        </div>
      </div>
      <div class="navigation-settings-card">
        <h3>Navigation and display</h3>
        <p class="hint">Navigation and display changes take effect while the player is running. The startup choice applies next time it starts.</p>
        <form class="navigation-settings-form" method="post" action="/settings/navigation">
          {csrf_input}
          <div class="nav-settings-grid">
            <label>Knob hold (seconds)
              <input class="settings-number" name="knob_hold_seconds" type="number" min="0.5" max="5" step="0.1" value="{knob_hold_seconds}">
              <span class="hint">Applies to individual knob holds and the two-knob shutdown gesture.</span>
            </label>
            <label>Marquee start delay (seconds)
              <input class="settings-number" name="marquee_delay_seconds" type="number" min="0" max="5" step="0.05" value="{marquee_delay_seconds}">
            </label>
            <label>Marquee speed (pixels/second)
              <input class="settings-number" name="marquee_speed_px_per_second" type="number" min="8" max="120" step="1" value="{marquee_speed}">
            </label>
            <label>Pause between marquee loops (seconds)
              <input class="settings-number" name="marquee_loop_pause_seconds" type="number" min="0" max="10" step="0.1" value="{marquee_loop_pause_seconds}">
            </label>
            <label>Knob acceleration multiplier
              <select class="settings-select" name="navigation_acceleration_mode">{acceleration_options}</select>
            </label>
            <label>Fast-turn threshold (milliseconds)
              <input class="settings-number" name="navigation_accel_threshold_milliseconds" type="number" min="10" max="500" step="5" value="{accel_threshold_ms}">
              <span class="hint">Acceleration applies when the time between knob steps is at or below this value. Lower values require a faster turn.</span>
            </label>
            <label>Return to playback after browsing (seconds; 0 disables)
              <input class="settings-number" name="browse_return_seconds" type="number" min="0" max="120" step="1" value="{browse_return_seconds}">
            </label>
            <label>Screen saver idle time (seconds; 0 disables)
              <input class="settings-number" name="screen_saver_idle_seconds" type="number" min="0" max="3600" step="30" value="{screen_saver_idle_seconds}">
            </label>
          </div>
          <label class="root-menu-enabled startup-resume-setting">
            <input type="checkbox" name="startup_resume_last_played" value="true"{startup_resume_checked}>
            <span>Open your latest in-progress book at startup</span>
          </label>
          <p class="hint">Uses your Audiobookshelf account’s listening progress. When off, startup selects the first item in the root menu.</p>
          <fieldset class="root-menu-settings">
            <legend>Root menu choices and order</legend>
            <div class="root-menu-list">{root_menu_rows}</div>
            <p class="hint">Choose which sections appear and their order. At least one stays enabled.</p>
          </fieldset>
          <button class="small-button secondary" type="submit">Save navigation settings</button>
        </form>
      </div>
    </section>
    """.format(
        next_value=next_value,
        toggle_class=toggle_class,
        aria_pressed=aria_pressed,
        button_label=button_label,
        spoken_navigation_next_value=spoken_navigation_next_value,
        spoken_navigation_toggle_class=spoken_navigation_toggle_class,
        spoken_navigation_aria_pressed=spoken_navigation_aria_pressed,
        spoken_navigation_button_label=spoken_navigation_button_label,
        playback_speed_options=render_playback_speed_options(config.playback_speed),
        screen_saver_options=render_screen_saver_options(config.screen_saver_mode),
        screen_saver_dim_options=render_screen_saver_dim_options(config.screen_saver_dim_percent),
        sleep_next_value=sleep_next_value,
        sleep_toggle_class=sleep_toggle_class,
        sleep_aria_pressed=sleep_aria_pressed,
        sleep_button_label=sleep_button_label,
        sleep_duration_controls=sleep_duration_controls,
        knob_hold_seconds=config.knob_hold_seconds,
        marquee_delay_seconds=config.marquee_delay_seconds,
        marquee_speed=config.marquee_speed_px_per_second,
        marquee_loop_pause_seconds=config.marquee_loop_pause_seconds,
        acceleration_options=render_acceleration_options(config.navigation_acceleration_mode),
        accel_threshold_ms=config.navigation_accel_threshold_milliseconds,
        browse_return_seconds=config.browse_return_seconds,
        screen_saver_idle_seconds=config.screen_saver_idle_seconds,
        startup_resume_checked=" checked" if config.startup_resume_last_played else "",
        root_menu_rows=render_root_menu_rows(config),
        csrf_input=csrf_input,
    )


def render_podcasts_card(config: AppConfig, csrf_token: str = "") -> str:
    rows = [render_podcast_row(index, podcast) for index, podcast in enumerate(config.podcasts)]
    rows.append(render_podcast_row(len(rows), None))
    return """
    <section class="card" aria-labelledby="podcasts-heading">
      <h2 id="podcasts-heading">Podcasts</h2>
      <p class="hint">Paste the show link from podcasts.apple.com. RSS feed URLs also work. The player will show each podcast as a title and play the latest episode.</p>
      <form class="podcast-form" method="post" action="/podcasts">
        {csrf_input}
        <div class="podcast-table" data-podcast-rows>
          {rows}
        </div>
        <div class="podcast-actions">
          <button class="small-button secondary" type="button" data-add-podcast-row>Add row</button>
          <button class="podcast-save-button" type="submit">Save Podcasts</button>
        </div>
      </form>
    </section>
    """.format(rows="\n".join(rows), csrf_input=render_csrf_input(csrf_token))


def render_podcast_row(index: int, podcast: PodcastConfig | None) -> str:
    podcast = podcast or PodcastConfig(url="")
    metadata = podcast_metadata_label(podcast)
    return """
    <div class="podcast-row">
      <div>
        <label class="sr-only" for="podcast_url_{index}">Podcast URL</label>
        <input id="podcast_url_{index}" name="podcast_url" type="url" value="{url}" placeholder="https://podcasts.apple.com/...">
        <div class="podcast-meta">{metadata}</div>
      </div>
      <button class="small-button secondary" type="button" data-remove-podcast-row>Remove</button>
    </div>
    """.format(
        index=index,
        url=html.escape(podcast.url),
        metadata=html.escape(metadata),
    )


def podcast_metadata_label(podcast: PodcastConfig) -> str:
    if podcast.title and podcast.author:
        return f"{podcast.title} by {podcast.author}"
    if podcast.title:
        return podcast.title
    return "Paste a show link from podcasts.apple.com"


def render_screen_saver_options(selected_mode: str) -> str:
    options = (
        (SCREEN_SAVER_CHAPTER, "Chapter word"),
        (SCREEN_SAVER_BOOKS, "Book titles"),
        (SCREEN_SAVER_CLOCK, "Digital clock"),
    )
    return "\n".join(
        '<option value="{value}"{selected}>{label}</option>'.format(
            value=html.escape(value),
            selected=" selected" if value == selected_mode else "",
            label=html.escape(label),
        )
        for value, label in options
    )


def render_acceleration_options(selected_mode: str) -> str:
    return "\n".join(
        '<option value="{value}"{selected}>{label}</option>'.format(
            value=value,
            selected=" selected" if value == selected_mode else "",
            label="Off" if value == "off" else value,
        )
        for value in NAV_ACCELERATION_MODES
    )


def render_library_sort_options(selected_mode: str) -> str:
    options = (
        (LIBRARY_SORT_TITLE, "Title"),
        (LIBRARY_SORT_AUTHOR, "Author (last name)"),
    )
    return "\n".join(
        '<option value="{value}"{selected}>{label}</option>'.format(
            value=value,
            selected=" selected" if value == selected_mode else "",
            label=label,
        )
        for value, label in options
    )


def render_playback_speed_options(selected_speed: float) -> str:
    return "\n".join(
        '<option value="{value}"{selected}>{label}</option>'.format(
            value=f"{speed:g}",
            selected=" selected" if speed == selected_speed else "",
            label=f"{speed:g}x",
        )
        for speed in PLAYBACK_SPEEDS
    )


def render_screen_saver_dim_options(selected_percent: int) -> str:
    labels = {
        10: "10% (darkest)",
        50: "50% (brightest)",
    }
    return "\n".join(
        '<option value="{value}"{selected}>{label}</option>'.format(
            value=value,
            selected=" selected" if value == selected_percent else "",
            label=labels.get(value, f"{value}%"),
        )
        for value in SCREEN_SAVER_DIM_LEVELS
    )


def render_player_status_value(status: WebPlayerStatus, csrf_token: str = "") -> str:
    volume = min(max(status.volume_percent, 0), 100)
    state = "Playing" if status.is_playing else "Paused"
    if status.muted or volume <= 0:
        state = "Muted"
    button_action = "pause" if status.is_playing else "play"
    button_text = "Pause" if status.is_playing else "Play"
    title = html.escape(status.title) if status.has_session else "Nothing playing"
    meta = f"{html.escape(state)} · {html.escape(render_time_info(status))}" if status.has_session else ""
    hidden_class = "" if status.has_session else " hidden"
    return """
    <div class="status-value" data-now-playing data-has-session="{has_session}">
      <div class="now-playing-title" data-now-playing-title>{title}</div>
      <div class="now-playing-meta" data-now-playing-meta>{meta}</div>
      <form class="playback-form{hidden_class}" data-playback-form method="post" action="/player">
        {csrf_input}
        <input data-playback-action type="hidden" name="action" value="{button_action}">
        <button data-playback-button type="submit">{button_text}</button>
      </form>
      <div class="chapter-buttons{hidden_class}">
        <button class="secondary" type="button" data-player-command="previous_chapter">Previous chapter</button>
        <button class="secondary" type="button" data-player-command="next_chapter">Next chapter</button>
      </div>
      <form class="volume-form{hidden_class}" data-volume-form method="post" action="/player">
        {csrf_input}
        <input type="hidden" name="action" value="volume">
        <div class="volume-icon" aria-hidden="true">&#128266;</div>
        <input class="volume-slider" data-volume-slider aria-label="Volume" name="volume" type="range" min="0" max="100" value="{volume}">
        <div class="volume-percent" data-volume-percent>{volume}%</div>
      </form>
    </div>
    """.format(
        has_session="1" if status.has_session else "0",
        title=title,
        meta=meta,
        hidden_class=hidden_class,
        volume=volume,
        button_action=button_action,
        button_text=button_text,
        csrf_input=render_csrf_input(csrf_token),
    )


def render_time_info(status: WebPlayerStatus) -> str:
    if status.duration <= 0:
        return format_duration(status.current_time)
    return f"{format_duration(status.current_time)} / {format_duration(status.duration)}"


def player_status_payload(status: WebPlayerStatus) -> dict:
    volume = min(max(status.volume_percent, 0), 100)
    state = "Playing" if status.is_playing else "Paused"
    if status.muted or volume <= 0:
        state = "Muted"
    return {
        "hasSession": status.has_session,
        "bookId": status.book_id,
        "title": status.title,
        "state": state,
        "timeInfo": render_time_info(status),
        "currentTime": max(0, status.current_time),
        "duration": max(0, status.duration),
        "updatedAt": status.updated_at,
        "isPlaying": status.is_playing,
        "volumePercent": volume,
    }


def player_status_event_signature(payload: dict) -> str:
    important = {
        "hasSession": payload.get("hasSession"),
        "bookId": payload.get("bookId"),
        "title": payload.get("title"),
        "state": payload.get("state"),
        "isPlaying": payload.get("isPlaying"),
        "volumePercent": payload.get("volumePercent"),
        "duration": payload.get("duration"),
    }
    return json.dumps(important, sort_keys=True, separators=(",", ":"))


def player_status_sse(payload_json: str) -> bytes:
    return f"data: {payload_json}\n\n".encode("utf-8")


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def render_wifi_status_value(wifi: WifiStatus) -> str:
    if wifi.connected and wifi.ssid:
        return f"Connected to <strong>{html.escape(wifi.ssid)}</strong>"
    return html.escape(wifi.message or "Unknown")


def render_audiobookshelf_status_value(message: str) -> str:
    prefix = "Logged in to "
    if not message.startswith(prefix):
        return html.escape(message)

    login_target = message[len(prefix) :]
    if " as " in login_target:
        server_url, username = login_target.rsplit(" as ", 1)
        return (
            f"Logged in to <strong>{html.escape(server_url)}</strong> "
            f"as <strong>{html.escape(username)}</strong>"
        )
    return f"Logged in to <strong>{html.escape(login_target)}</strong>"


def render_bluetooth_status_value(message: str) -> str:
    prefix = "Connected to "
    if message.startswith(prefix):
        device_name = message[len(prefix) :]
        return f"Connected to <strong>{html.escape(device_name)}</strong>"
    return html.escape(message)


def render_wifi_card(wifi: WifiStatus, csrf_token: str = "") -> str:
    if wifi.connected and wifi.ssid and wifi.ssid != SETUP_HOTSPOT_SSID:
        return """
        <section class="card" aria-labelledby="wifi-heading">
          <h2 id="wifi-heading">Wi-Fi</h2>
          <p class="hint">Connected to <strong>{ssid}</strong>.</p>
          <p class="hint">Forgetting this network will make the device form its own open Wi-Fi network. Connect to <code>{hotspot_ssid}</code>, then browse to <code>{hotspot_url}</code>.</p>
          <form method="post" action="/wifi/forget">
            {csrf_input}
            <button type="submit">Forget this WiFi network</button>
          </form>
        </section>
        """.format(
            ssid=html.escape(wifi.ssid),
            hotspot_ssid=html.escape(SETUP_HOTSPOT_SSID),
            hotspot_url=html.escape(SETUP_HOTSPOT_URL),
            csrf_input=render_csrf_input(csrf_token),
        )

    return """
    <section class="card" aria-labelledby="wifi-heading">
      <h2 id="wifi-heading">Wi-Fi</h2>
      <p class="hint">Connect to the open Wi-Fi network <code>{hotspot_ssid}</code>, then browse to <code>{hotspot_url}</code>.</p>
      <form method="post" action="/wifi">
        {csrf_input}
        <label for="wifi_ssid">Wi-Fi network name</label>
        <input id="wifi_ssid" name="wifi_ssid" autocomplete="off" required>

        <label for="wifi_password">Wi-Fi password</label>
        <input id="wifi_password" name="wifi_password" type="password" autocomplete="current-password">

        <button type="submit">Connect to Wi-Fi</button>
      </form>
    </section>
    """.format(
        hotspot_ssid=html.escape(SETUP_HOTSPOT_SSID),
        hotspot_url=html.escape(SETUP_HOTSPOT_URL),
        csrf_input=render_csrf_input(csrf_token),
    )


def login_username(login_data: dict, fallback: str) -> str:
    user = login_data.get("user") or {}
    candidates = [
        user.get("username"),
        user.get("name"),
        user.get("displayName"),
        login_data.get("username"),
        login_data.get("name"),
        login_data.get("displayName"),
        fallback,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def saved_username(username: str) -> str:
    username = username.strip()
    if username.lower() == "unknown user":
        return ""
    return username


def run_setup_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer((host, port), SetupHandler)
    server.csrf_token = secrets.token_urlsafe(32)
    print(f"Setup page listening on http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Chapter Player for Audiobookshelf setup page.")
    parser.add_argument(
        "--ensure-wifi",
        action="store_true",
        help="Start the setup hotspot if no Wi-Fi connection is active.",
    )
    args = parser.parse_args()
    if args.ensure_wifi:
        try:
            print(ensure_wifi_or_hotspot())
        except WifiError as error:
            print(f"Wi-Fi setup mode could not start: {error}")
    run_setup_server()


if __name__ == "__main__":
    main()
