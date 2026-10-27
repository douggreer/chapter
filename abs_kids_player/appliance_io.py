from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .rotary_ui import (
    BluetoothDevicesFrame,
    BluetoothMenuFrame,
    ChapterConfirmFrame,
    DisplayFrame,
    HomeFrame,
    PlayingFrame,
    ResumeChoiceFrame,
    ScreenSaverFrame,
    SleepConfirmFrame,
    SplashFrame,
    StartupResumeFrame,
    TwoLineFrame,
    VolumeFrame,
    WifiSetupFrame,
)


class TextDisplay(Protocol):
    def show(self, frame: DisplayFrame) -> None:
        ...

    def set_brightness(self, percent: int) -> None:
        ...


class ConsoleDisplay:
    def show(self, frame: DisplayFrame) -> None:
        print(f"{frame.top}\n{frame.bottom}\n")

    def set_brightness(self, percent: int) -> None:
        pass


class Sh1122Display:
    width = 256
    height = 64
    default_contrast = 0x80
    brightness_gamma = 2.2

    def __init__(
        self,
        spi_bus: int = 0,
        spi_device: int = 0,
        dc_pin: int = 24,
        reset_pin: int = 25,
        cs_pin: int | None = None,
        max_speed_hz: int = 1_000_000,
    ) -> None:
        from gpiozero import OutputDevice
        from PIL import Image, ImageDraw, ImageFont
        import spidev

        self.image = Image.new("L", (self.width, self.height), 0)
        self.draw = ImageDraw.Draw(self.image)
        self.font_splash = load_font(ImageFont, 26)
        self.font_home_title = load_font(ImageFont, 18)
        self.font_home_author = load_font(ImageFont, 13)
        self.font_top = load_font(ImageFont, 16)
        self.font_bottom = load_font(ImageFont, 12)
        self.font_screen_saver = load_screen_saver_fonts(ImageFont)
        self.dc = OutputDevice(dc_pin, initial_value=False)
        self.reset = OutputDevice(reset_pin, initial_value=True)
        self.cs = OutputDevice(cs_pin, initial_value=True) if cs_pin is not None else None
        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = max_speed_hz
        self.spi.mode = 0
        self.spi.no_cs = cs_pin is not None
        self.reset_display()
        self.init_display()

    def reset_display(self) -> None:
        self.reset.on()
        time.sleep(0.001)
        self.reset.off()
        time.sleep(0.01)
        self.reset.on()
        time.sleep(0.01)

    def init_display(self) -> None:
        self.command(
            [
                0xAE,  # display off
                0x00,  # low column address
                0x10,  # high column address
                0x40,  # display start line
                0xA0,  # segment remap
                0xA8,
                self.height - 1,  # mux ratio
                0xC0,  # COM output scan direction
                0xD3,
                0x00,  # display offset
                0x81,
                self.default_contrast,
                0xA4,  # display follows RAM
                0xA6,  # normal display
                0xAF,  # display on
            ]
        )
        self.clear()

    def set_brightness(self, percent: int) -> None:
        percent = min(max(int(percent), 0), 100)
        contrast = round(self.default_contrast * ((percent / 100) ** self.brightness_gamma))
        self.command([0x81, contrast])

    def command(self, values: list[int]) -> None:
        self.dc.off()
        self.select()
        self.spi.xfer2(values)
        self.deselect()

    def data(self, values: bytes | bytearray) -> None:
        self.dc.on()
        self.select()
        for index in range(0, len(values), 4096):
            self.spi.xfer2(list(values[index : index + 4096]))
        self.deselect()

    def select(self) -> None:
        if self.cs is not None:
            self.cs.off()

    def deselect(self) -> None:
        if self.cs is not None:
            self.cs.on()

    def clear(self) -> None:
        self.draw.rectangle((0, 0, self.width, self.height), fill=0)
        self.flush()

    def flush(self) -> None:
        self.command([0x00, 0x10, 0xB0])
        self.data(pack_sh1122(self.image))

    def show(self, frame: DisplayFrame) -> None:
        self.draw.rectangle((0, 0, self.width, self.height), fill=0)
        if isinstance(frame, SplashFrame):
            self.draw_splash(frame)
        elif isinstance(frame, ScreenSaverFrame):
            self.draw_screen_saver(frame)
        elif isinstance(frame, HomeFrame):
            self.draw_home(frame)
        elif isinstance(frame, VolumeFrame):
            self.draw_volume(frame)
        elif isinstance(frame, PlayingFrame):
            self.draw_playing(frame)
        elif isinstance(frame, ChapterConfirmFrame):
            self.draw_chapter_confirm(frame)
        elif isinstance(frame, SleepConfirmFrame):
            self.draw_sleep_confirm(frame)
        elif isinstance(frame, ResumeChoiceFrame):
            self.draw_resume_choice(frame)
        elif isinstance(frame, StartupResumeFrame):
            self.draw_startup_resume(frame)
        elif isinstance(frame, BluetoothMenuFrame):
            self.draw_bluetooth_menu(frame)
        elif isinstance(frame, BluetoothDevicesFrame):
            self.draw_bluetooth_devices(frame)
        elif isinstance(frame, WifiSetupFrame):
            self.draw_wifi_setup(frame)
        else:
            self.draw_two_line(frame)
        muted = not isinstance(frame, VolumeFrame) and getattr(frame, "muted", False)
        bluetooth_connected = getattr(frame, "bluetooth_connected", False)
        if muted:
            self.draw_muted_icon(x=2)
        if bluetooth_connected:
            self.draw_bluetooth_icon(x=24 if muted else 2)
        if isinstance(frame, ScreenSaverFrame):
            self.apply_grayscale_brightness(frame.brightness_percent)
        self.flush()

    def apply_grayscale_brightness(self, percent: int) -> None:
        lookup = [scale_grayscale_value(value, percent) for value in range(256)]
        self.image.paste(self.image.point(lookup))

    def draw_two_line(self, frame: TwoLineFrame) -> None:
        top_font = self.font_top
        if text_width(self.draw, frame.top, top_font) > self.width:
            top_font = self.font_bottom
        top = fit_text(self.draw, frame.top, top_font, self.width)
        bottom = fit_text(self.draw, frame.bottom, self.font_bottom, self.width)
        self.draw_centered_text(top, top_font, y=11, fill=255)
        self.draw_centered_text(bottom, self.font_bottom, y=40, fill=180)

    def draw_splash(self, frame: SplashFrame) -> None:
        text = fit_text(self.draw, frame.text, self.font_splash, self.width)
        left, top, right, bottom = self.draw.textbbox((0, 0), text, font=self.font_splash)
        x = max(0, (self.width - (right - left)) // 2)
        y = max(0, (self.height - (bottom - top)) // 2 - top)
        self.draw.text((x, y), text, font=self.font_splash, fill=255)

    def draw_home(self, frame: HomeFrame) -> None:
        if frame.is_podcast:
            self.draw_right_aligned_text("PODCAST", self.font_bottom, y=0, right=self.width - 2, fill=140)
        title_y = 12
        if text_width(self.draw, frame.title, self.font_home_title) > self.width:
            self.draw_scrolling_text(
                frame.title,
                self.font_home_title,
                y=title_y,
                fill=255,
                offset=frame.title_scroll_px,
                pause_distance=frame.scroll_pause_px,
            )
        else:
            title = fit_text(self.draw, frame.title, self.font_home_title, self.width)
            self.draw_centered_text(title, self.font_home_title, y=title_y, fill=255)
        author = fit_text(self.draw, frame.bottom, self.font_home_author, self.width)
        self.draw_centered_text(author, self.font_home_author, y=34, fill=180)
        if frame.series_position:
            self.draw_bottom_left_text(frame.series_position, self.font_bottom, fill=140, margin=3)
    def draw_volume(self, frame: VolumeFrame) -> None:
        label = fit_text(self.draw, frame.top, self.font_top, self.width)
        self.draw_centered_text(label, self.font_top, y=9, fill=255)
        bar_width = round(self.width * 0.8)
        bar_height = 14
        bar_x = (self.width - bar_width) // 2
        bar_y = 42
        radius = bar_height // 2
        effective_percent = 0 if frame.is_muted else frame.percent
        fill_width = round((effective_percent / 100) * (bar_width - 2))
        self.draw.rounded_rectangle(
            (bar_x, bar_y, bar_x + bar_width - 1, bar_y + bar_height - 1),
            radius=radius,
            outline=180,
        )
        if fill_width > 0:
            self.draw.rounded_rectangle(
                (bar_x + 1, bar_y + 1, bar_x + fill_width, bar_y + bar_height - 2),
                radius=max(1, radius - 1),
                fill=255,
            )

    def draw_playing(self, frame: PlayingFrame) -> None:
        remaining = fit_text(self.draw, frame.remaining_text, self.font_bottom, self.width // 2)
        self.draw_right_aligned_text(remaining, self.font_bottom, y=0, right=self.width - 2, fill=180)

        title_y = 18
        chapter = frame.chapter_text
        if text_width(self.draw, chapter, self.font_top) > self.width:
            self.draw_scrolling_text(
                chapter,
                self.font_top,
                y=title_y,
                fill=255,
                offset=frame.title_scroll_px,
                pause_distance=frame.scroll_pause_px,
            )
        else:
            label = fit_text(self.draw, chapter, self.font_top, self.width)
            self.draw_centered_text(label, self.font_top, y=title_y, fill=255)
        self.draw_option_row(frame.actions, frame.selected_index, y=40)

    def draw_resume_choice(self, frame: ResumeChoiceFrame) -> None:
        title = fit_text(self.draw, frame.top, self.font_top, self.width)
        self.draw_centered_text(title, self.font_top, y=9, fill=255)
        self.draw_option_row(frame.options, frame.selected_index, y=40)

    def draw_startup_resume(self, frame: StartupResumeFrame) -> None:
        prompt = fit_text(self.draw, "You were listening to", self.font_bottom, self.width)
        title = fit_text(self.draw, frame.title, self.font_top, self.width)
        self.draw_centered_text(prompt, self.font_bottom, y=4, fill=180)
        self.draw_centered_text(title, self.font_top, y=20, fill=255)
        self.draw_option_row(frame.options, frame.selected_index, y=43)

    def draw_chapter_confirm(self, frame: ChapterConfirmFrame) -> None:
        first = fit_text(self.draw, "Are you sure you want to", self.font_bottom, self.width)
        second = fit_text(self.draw, f"listen to the {frame.direction} chapter?", self.font_bottom, self.width)
        self.draw_centered_text(first, self.font_bottom, y=7, fill=255)
        self.draw_centered_text(second, self.font_bottom, y=23, fill=255)
        self.draw_option_row(frame.options, frame.selected_index, y=43)

    def draw_sleep_confirm(self, frame: SleepConfirmFrame) -> None:
        prompt = fit_text(self.draw, frame.top, self.font_bottom, self.width)
        self.draw_centered_text(prompt, self.font_bottom, y=12, fill=255)
        self.draw_option_row(frame.options, frame.selected_index, y=39)

    def draw_bluetooth_menu(self, frame: BluetoothMenuFrame) -> None:
        title = fit_text(self.draw, frame.top, self.font_top, self.width)
        self.draw_centered_text(title, self.font_top, y=9, fill=255)
        self.draw_option_row(frame.options, frame.selected_index, y=40)

    def draw_bluetooth_devices(self, frame: BluetoothDevicesFrame) -> None:
        title = fit_text(self.draw, frame.top, self.font_top, self.width)
        bottom = fit_text(self.draw, frame.bottom, self.font_bottom, self.width)
        self.draw_centered_text(title, self.font_top, y=9, fill=255)
        self.draw_centered_text(bottom, self.font_bottom, y=40, fill=180)

    def draw_option_row(self, options: tuple[str, ...], selected_index: int, y: int) -> None:
        margin = 5
        gap = 4
        option_h = 18
        count = max(1, len(options))
        option_w = (self.width - margin * 2 - gap * (count - 1)) // count
        for index, option in enumerate(options):
            if count == 1:
                option_w = min(90, self.width - margin * 2)
                x = (self.width - option_w) // 2
                right = x + option_w
            else:
                x = margin + index * (option_w + gap)
                right = self.width - margin if index == count - 1 else x + option_w
            box = (x, y, right, y + option_h)
            selected = index == selected_index
            fill = 255 if selected else 0
            outline = 255 if selected else 120
            text_fill = 0 if selected else 255
            self.draw.rounded_rectangle(box, radius=3, fill=fill, outline=outline)
            label = fit_text(self.draw, option, self.font_bottom, max(1, right - x - 8))
            self.draw_centered_in_box(label, self.font_bottom, box, fill=text_fill)

    def draw_wifi_setup(self, frame: WifiSetupFrame) -> None:
        top = fit_text(self.draw, frame.top, self.font_bottom, self.width)
        bottom = fit_text(self.draw, frame.bottom, self.font_bottom, self.width)
        self.draw_centered_text(top, self.font_bottom, y=13, fill=255)
        self.draw_centered_text(bottom, self.font_bottom, y=40, fill=180)

    def draw_screen_saver(self, frame: ScreenSaverFrame) -> None:
        if frame.mode == "clock":
            clock_text = frame.clock_text or "--:-- --"
            label = fit_text(self.draw, clock_text, self.font_splash, self.width)
            self.draw_centered_text(label, self.font_splash, y=17, fill=255)
            return

        fonts = self.font_screen_saver or [self.font_top]
        words = frame.words or ("chapter",)
        for index, word in enumerate(screen_saver_word_specs(frame.frame_index, self.width, self.height)):
            font = fonts[word["font_index"] % len(fonts)]
            text = oled_safe_text(words[index % len(words)])
            self.draw.text((word["x"], word["y"]), text, font=font, fill=word["fill"])

    def draw_centered_text(self, text: str, font, y: int, fill: int) -> None:
        text = oled_safe_text(text)
        left, _top, right, _bottom = self.draw.textbbox((0, 0), text, font=font)
        x = max(0, (self.width - (right - left)) // 2)
        self.draw.text((x, y), text, font=font, fill=fill)

    def draw_right_aligned_text(self, text: str, font, y: int, right: int, fill: int) -> None:
        text = oled_safe_text(text)
        left, _top, text_right, _bottom = self.draw.textbbox((0, 0), text, font=font)
        x = max(0, right - (text_right - left))
        self.draw.text((x, y), text, font=font, fill=fill)

    def draw_bottom_left_text(self, text: str, font, fill: int, margin: int = 0) -> None:
        text = oled_safe_text(text)
        left, top, _right, bottom = self.draw.textbbox((0, 0), text, font=font)
        x = max(0, margin - left)
        y = max(0, self.height - margin - (bottom - top) - top)
        self.draw.text((x, y), text, font=font, fill=fill)

    def draw_centered_in_box(self, text: str, font, box: tuple[int, int, int, int], fill: int) -> None:
        text = oled_safe_text(text)
        left, top, right, bottom = self.draw.textbbox((0, 0), text, font=font)
        box_left, box_top, box_right, box_bottom = box
        x = box_left + max(0, (box_right - box_left - (right - left)) // 2) - left
        y = box_top + max(0, (box_bottom - box_top - (bottom - top)) // 2) - top
        self.draw.text((x, y), text, font=font, fill=fill)

    def draw_muted_icon(self, x: int = 2) -> None:
        y = 1
        self.draw.rectangle((x, y + 5, x + 4, y + 10), outline=255)
        self.draw.polygon(
            [
                (x + 5, y + 5),
                (x + 10, y + 1),
                (x + 10, y + 14),
                (x + 5, y + 10),
            ],
            outline=255,
        )
        self.draw.line((x + 13, y + 4, x + 18, y + 11), fill=255, width=2)
        self.draw.line((x + 18, y + 4, x + 13, y + 11), fill=255, width=2)

    def draw_bluetooth_icon(self, x: int = 2) -> None:
        y = 1
        mid = y + 7
        self.draw.line((x + 7, y, x + 7, y + 14), fill=255, width=1)
        self.draw.line((x + 7, y, x + 13, y + 5), fill=255, width=1)
        self.draw.line((x + 13, y + 5, x + 4, y + 12), fill=255, width=1)
        self.draw.line((x + 4, y + 2, x + 13, y + 9), fill=255, width=1)
        self.draw.line((x + 13, y + 9, x + 7, y + 14), fill=255, width=1)

    def draw_scrolling_text(
        self,
        text: str,
        font,
        y: int,
        fill: int,
        offset: int,
        pause_distance: int = 48,
    ) -> None:
        text = oled_safe_text(text)
        width = text_width(self.draw, text, font)
        gap = 48
        scroll_distance = width + gap
        pause_distance = max(0, pause_distance)
        cycle_position = offset % max(1, scroll_distance + pause_distance)
        scroll_offset = 0 if cycle_position < pause_distance else cycle_position - pause_distance
        x = -scroll_offset
        while x < self.width:
            self.draw.text((x, y), text, font=font, fill=fill)
            x += scroll_distance

    def close(self) -> None:
        self.command([0xAE])
        self.spi.close()


@dataclass(frozen=True)
class Ky040Pins:
    clk: int
    dt: int
    sw: int
    reversed: bool = False


@dataclass(frozen=True)
class InputEvent:
    name: str
    steps: int = 0
    timestamp: float = field(default_factory=time.monotonic, compare=False)


class AmpShutdownPin:
    def __init__(self, pin: int) -> None:
        from gpiozero import DigitalInputDevice
        from gpiozero import OutputDevice

        self.pin = pin
        self._input_device = DigitalInputDevice
        self._output_device = OutputDevice
        self.input = None
        self.output = None
        self.set_shutdown(False)

    def set_shutdown(self, shutdown: bool) -> None:
        if shutdown:
            if self.input is not None:
                self.input.close()
                self.input = None
            if self.output is None:
                self.output = self._output_device(self.pin, initial_value=False)
            else:
                self.output.off()
            return

        if self.output is not None:
            self.output.close()
            self.output = None
        if self.input is None:
            # Keep SD/MODE high-Z with no internal pull so the breakout's mode resistor
            # selects its default mono mix while still letting us pull low for shutdown.
            self.input = self._input_device(self.pin, pull_up=None, active_state=True)

    def close(self) -> None:
        if self.output is not None:
            self.output.close()
            self.output = None
        if self.input is not None:
            self.input.close()
            self.input = None


class KnobButtonCoordinator:
    _BUTTON_NAMES = ("nav", "volume")
    _CLICK_EVENTS = {"nav": "nav_click", "volume": "volume_click"}
    _HOLD_EVENTS = {"nav": "nav_hold", "volume": "volume_hold"}

    def __init__(self, events: queue.SimpleQueue[InputEvent], hold_seconds: float = 1.0) -> None:
        self.events = events
        self._lock = threading.RLock()
        self._hold_seconds = max(0.1, float(hold_seconds))
        self._pressed = {name: False for name in self._BUTTON_NAMES}
        self._pressed_at: dict[str, float] = {}
        self._hold_fired = {name: False for name in self._BUTTON_NAMES}
        self._single_timers: dict[str, threading.Timer] = {}
        self._chord_timer: threading.Timer | None = None
        self._chord_active = False
        self._shutdown_fired = False
        self._closed = False

    def set_hold_seconds(self, seconds: float) -> None:
        with self._lock:
            self._hold_seconds = max(0.1, float(seconds))
            now = time.monotonic()
            if self._chord_active:
                self._schedule_chord_locked(now)
                return
            for name in self._BUTTON_NAMES:
                if self._pressed[name] and not self._hold_fired[name]:
                    self._schedule_single_locked(name, now)

    def press(self, name: str) -> None:
        if name not in self._BUTTON_NAMES:
            return
        with self._lock:
            if self._closed or self._pressed[name]:
                return
            now = time.monotonic()
            self._pressed[name] = True
            self._pressed_at[name] = now
            if self._shutdown_fired:
                return
            if all(self._pressed.values()):
                self._chord_active = True
                for button_name in self._BUTTON_NAMES:
                    self._cancel_single_locked(button_name)
                self._schedule_chord_locked(now)
                return
            self._schedule_single_locked(name, now)

    def release(self, name: str) -> None:
        if name not in self._BUTTON_NAMES:
            return
        with self._lock:
            if self._closed or not self._pressed[name]:
                return
            now = time.monotonic()
            held_seconds = now - self._pressed_at.get(name, now)
            self._pressed[name] = False
            self._cancel_single_locked(name)

            if self._shutdown_fired:
                self._pressed_at.pop(name, None)
                if not any(self._pressed.values()):
                    self._reset_idle_locked()
                return

            if self._chord_active:
                self._chord_active = False
                self._cancel_chord_locked()
                if not self._hold_fired[name]:
                    event_name = (
                        self._HOLD_EVENTS[name]
                        if held_seconds >= self._hold_seconds
                        else self._CLICK_EVENTS[name]
                    )
                    self.events.put(InputEvent(event_name))
                self._hold_fired[name] = False
                self._pressed_at.pop(name, None)
                other_name = "volume" if name == "nav" else "nav"
                if self._pressed[other_name] and not self._hold_fired[other_name]:
                    self._schedule_single_locked(other_name, now)
                if not any(self._pressed.values()):
                    self._reset_idle_locked()
                return

            if not self._hold_fired[name]:
                self.events.put(InputEvent(self._CLICK_EVENTS[name]))
            self._hold_fired[name] = False
            self._pressed_at.pop(name, None)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for name in self._BUTTON_NAMES:
                self._cancel_single_locked(name)
            self._cancel_chord_locked()

    def _schedule_single_locked(self, name: str, now: float) -> None:
        self._cancel_single_locked(name)
        pressed_at = self._pressed_at.get(name, now)
        delay = max(0.0, self._hold_seconds - (now - pressed_at))
        timer = threading.Timer(delay, self._fire_single, args=(name,))
        timer.daemon = True
        self._single_timers[name] = timer
        timer.start()

    def _schedule_chord_locked(self, now: float) -> None:
        self._cancel_chord_locked()
        latest_press = max(self._pressed_at.get(name, now) for name in self._BUTTON_NAMES)
        delay = max(0.0, self._hold_seconds - (now - latest_press))
        self._chord_timer = threading.Timer(delay, self._fire_chord)
        self._chord_timer.daemon = True
        self._chord_timer.start()

    def _fire_single(self, name: str) -> None:
        with self._lock:
            self._single_timers.pop(name, None)
            if self._closed or self._chord_active or self._shutdown_fired or not self._pressed[name]:
                return
            self._hold_fired[name] = True
            self.events.put(InputEvent(self._HOLD_EVENTS[name]))

    def _fire_chord(self) -> None:
        with self._lock:
            self._chord_timer = None
            if self._closed or not self._chord_active or not all(self._pressed.values()):
                return
            self._shutdown_fired = True
            self._chord_active = False
            for name in self._BUTTON_NAMES:
                self._cancel_single_locked(name)
            self.events.put(InputEvent("device_shutdown"))

    def _cancel_single_locked(self, name: str) -> None:
        timer = self._single_timers.pop(name, None)
        if timer is not None:
            timer.cancel()

    def _cancel_chord_locked(self) -> None:
        timer = self._chord_timer
        self._chord_timer = None
        if timer is not None:
            timer.cancel()

    def _reset_idle_locked(self) -> None:
        for name in self._BUTTON_NAMES:
            self._cancel_single_locked(name)
            self._pressed_at.pop(name, None)
            self._hold_fired[name] = False
        self._cancel_chord_locked()
        self._chord_active = False
        self._shutdown_fired = False


class RotaryEncoderInputs:
    def __init__(
        self,
        events: queue.SimpleQueue[InputEvent],
        nav: Ky040Pins = Ky040Pins(clk=5, dt=6, sw=13),
        volume: Ky040Pins = Ky040Pins(clk=12, dt=16, sw=26),
        hold_seconds: float = 1.0,
    ) -> None:
        from gpiozero import Button

        self.events = events
        self.button_coordinator = KnobButtonCoordinator(events, hold_seconds)
        self.nav_encoder = QuadratureInput(
            nav.clk,
            nav.dt,
            lambda step: events.put(InputEvent("nav", step)),
            reversed=nav.reversed,
        )
        self.volume_encoder = QuadratureInput(
            volume.clk,
            volume.dt,
            lambda step: events.put(InputEvent("volume", step)),
            reversed=volume.reversed,
        )
        self.nav_button = Button(nav.sw, pull_up=True, bounce_time=0.05)
        self.volume_button = Button(volume.sw, pull_up=True, bounce_time=0.05)
        self.nav_button.when_pressed = lambda: self.button_coordinator.press("nav")
        self.nav_button.when_released = lambda: self.button_coordinator.release("nav")
        self.volume_button.when_pressed = lambda: self.button_coordinator.press("volume")
        self.volume_button.when_released = lambda: self.button_coordinator.release("volume")

    def set_hold_seconds(self, seconds: float) -> None:
        self.button_coordinator.set_hold_seconds(seconds)


class NavigationRotaryInput:
    def __init__(
        self,
        events: queue.SimpleQueue[InputEvent],
        nav: Ky040Pins = Ky040Pins(clk=5, dt=6, sw=13),
        hold_seconds: float = 1.0,
        button_coordinator: KnobButtonCoordinator | None = None,
    ) -> None:
        from gpiozero import Button

        self.events = events
        self.button_coordinator = button_coordinator or KnobButtonCoordinator(events, hold_seconds)
        self.encoder = QuadratureInput(
            nav.clk,
            nav.dt,
            lambda step: events.put(InputEvent("nav", step)),
            reversed=nav.reversed,
        )
        self.button = Button(nav.sw, pull_up=True, bounce_time=0.05)
        self.button.when_pressed = lambda: self.button_coordinator.press("nav")
        self.button.when_released = lambda: self.button_coordinator.release("nav")

    def set_hold_seconds(self, seconds: float) -> None:
        self.button_coordinator.set_hold_seconds(seconds)


class VolumeRotaryInput:
    def __init__(
        self,
        events: queue.SimpleQueue[InputEvent],
        volume: Ky040Pins = Ky040Pins(clk=12, dt=16, sw=26),
        hold_seconds: float = 1.0,
        button_coordinator: KnobButtonCoordinator | None = None,
    ) -> None:
        from gpiozero import Button

        self.events = events
        self.button_coordinator = button_coordinator or KnobButtonCoordinator(events, hold_seconds)
        self.encoder = QuadratureInput(
            volume.clk,
            volume.dt,
            lambda step: events.put(InputEvent("volume", step)),
            reversed=volume.reversed,
        )
        self.button = Button(volume.sw, pull_up=True, bounce_time=0.05)
        self.button.when_pressed = lambda: self.button_coordinator.press("volume")
        self.button.when_released = lambda: self.button_coordinator.release("volume")

    def set_hold_seconds(self, seconds: float) -> None:
        self.button_coordinator.set_hold_seconds(seconds)


class QuadratureInput:
    transitions = {
        (0b00, 0b01): 1,
        (0b01, 0b11): 1,
        (0b11, 0b10): 1,
        (0b10, 0b00): 1,
        (0b00, 0b10): -1,
        (0b10, 0b11): -1,
        (0b11, 0b01): -1,
        (0b01, 0b00): -1,
    }

    def __init__(
        self,
        clk_pin: int,
        dt_pin: int,
        on_step,
        steps_per_detent: int = 4,
        reversed: bool = False,
    ) -> None:
        from gpiozero import DigitalInputDevice

        self.clk = DigitalInputDevice(clk_pin, pull_up=True, bounce_time=0.001)
        self.dt = DigitalInputDevice(dt_pin, pull_up=True, bounce_time=0.001)
        self.on_step = on_step
        self.steps_per_detent = steps_per_detent
        self.reversed = reversed
        self.accumulator = 0
        self.previous = self.state
        self.clk.when_activated = self.changed
        self.clk.when_deactivated = self.changed
        self.dt.when_activated = self.changed
        self.dt.when_deactivated = self.changed

    @property
    def state(self) -> int:
        return (int(self.clk.value) << 1) | int(self.dt.value)

    def changed(self) -> None:
        current = self.state
        delta = self.transitions.get((self.previous, current), 0)
        self.previous = current
        if not delta:
            return
        self.accumulator += delta
        if abs(self.accumulator) >= self.steps_per_detent:
            step = 1 if self.accumulator > 0 else -1
            self.on_step(-step if self.reversed else step)
            self.accumulator = 0


def load_font(image_font_module, size: int):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    candidates = [Path(path) for path in paths]
    font_root = Path("/usr/share/fonts")
    if font_root.exists():
        candidates.extend(font_root.rglob("*Sans*Bold*.ttf"))
        candidates.extend(font_root.rglob("*Sans*.ttf"))

    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        try:
            font = image_font_module.truetype(str(path), size=size)
            print(f"Loaded OLED font {path} at size {size}")
            return font
        except OSError:
            pass
    print(f"Could not find a scalable OLED font; using PIL default at requested size {size}")
    return image_font_module.load_default()


def load_screen_saver_fonts(image_font_module):
    specs = [
        ("/usr/share/fonts/truetype/courier-prime/Courier Prime.ttf", 14),
        ("/usr/share/fonts/truetype/courier-prime/Courier Prime Bold.ttf", 15),
        ("/usr/share/fonts/truetype/courier-prime/Courier Prime Italic.ttf", 16),
        ("/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf", 14),
        ("/usr/share/fonts/truetype/liberation2/LiberationMono-Italic.ttf", 16),
        ("/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf", 12),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 12),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf", 14),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-BoldOblique.ttf", 16),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSerifCondensed-Bold.ttf", 13),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf", 17),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf", 16),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", 14),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Oblique.ttf", 15),
        ("/usr/share/fonts/truetype/freefont/FreeMono.ttf", 14),
        ("/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf", 15),
        ("/usr/share/fonts/truetype/freefont/FreeMonoOblique.ttf", 16),
        ("/usr/share/fonts/truetype/liberation2/LiberationSerif-Italic.ttf", 17),
        ("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf", 18),
        ("/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf", 14),
        ("/usr/share/fonts/truetype/noto/NotoSansMono-Bold.ttf", 15),
        ("/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf", 16),
        ("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", 15),
    ]
    fonts = []
    seen: set[tuple[Path, int]] = set()
    for font_path, size in specs:
        path = Path(font_path)
        key = (path, size)
        if key in seen:
            continue
        seen.add(key)
        try:
            fonts.append(image_font_module.truetype(str(path), size=size))
        except OSError:
            pass
    if not fonts:
        fonts.append(load_font(image_font_module, 14))
    return fonts


def screen_saver_word_specs(frame_index: int, width: int, height: int) -> list[dict[str, int]]:
    travel = width + 150
    lanes = max(1, height - 18)
    specs: list[dict[str, int]] = []
    for index in range(8):
        speed = 2 + index % 4
        raw = (frame_index * speed + index * 71) % travel
        x = raw - 120
        y = 2 + (index * 11 + round(math.sin((frame_index + index * 9) / 9) * 5)) % lanes
        fill = 95 + ((frame_index * 7 + index * 43) % 160)
        specs.append(
            {
                "x": x,
                "y": y,
                "fill": fill,
                "font_index": index + frame_index // 96,
            }
        )
    return specs


def fit_text(draw, text: str, font, max_width: int) -> str:
    text = oled_safe_text(text)
    if text_width(draw, text, font) <= max_width:
        return text
    ellipsis = "..."
    trimmed = text
    while trimmed and text_width(draw, trimmed + ellipsis, font) > max_width:
        trimmed = trimmed[:-1]
    return trimmed + ellipsis


def text_width(draw, text: str, font) -> int:
    text = oled_safe_text(text)
    left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
    return right - left


def oled_safe_text(text: str) -> str:
    translated = text.translate(
        str.maketrans(
            {
                "\u2018": "'",
                "\u2019": "'",
                "\u201b": "'",
                "\u2032": "'",
                "\u02bc": "'",
                "\uff07": "'",
                "\u201c": '"',
                "\u201d": '"',
                "\u2033": '"',
                "\uff02": '"',
                "\u2013": "-",
                "\u2014": "-",
                "\u2212": "-",
                "\u2026": "...",
                "\u00a0": " ",
            }
        )
    )
    characters = list(translated)
    for index, character in enumerate(characters):
        if character != "\ufffd":
            continue
        previous = characters[index - 1] if index > 0 else ""
        following = characters[index + 1] if index + 1 < len(characters) else ""
        characters[index] = "'" if previous.isalnum() and following.isalnum() else "?"
    return "".join(characters)


def scale_grayscale_value(value: int, percent: int) -> int:
    value = min(max(int(value), 0), 255)
    percent = min(max(int(percent), 0), 100)
    return round(value * (percent / 100))


def pack_sh1122(image) -> bytearray:
    pixels = image.load()
    packed = bytearray()
    for y in range(image.height):
        for x in range(0, image.width, 2):
            left = pixels[x, y] >> 4
            right = pixels[x + 1, y] >> 4
            packed.append((left << 4) | right)
    return packed
