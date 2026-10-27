# Chapter Player for Audiobookshelf

[![CI](https://github.com/douggreer/chapter/actions/workflows/ci.yml/badge.svg)](https://github.com/douggreer/chapter/actions/workflows/ci.yml)

A simple Raspberry Pi friendly Chapter player for Audiobookshelf.

This fork is based on upstream **[v0.3.12](https://github.com/chrismtopher/chapter/releases/tag/v0.3.12)**. Fork-specific work on `main` is documented in [CHANGELOG.md](CHANGELOG.md) and has not been published as a tagged release.

Chapter Player for Audiobookshelf is an independent third-party project and is not affiliated with or supported by the Audiobookshelf project.

Chapter is a native Linux appliance app built with Python and GStreamer. It signs in to Audiobookshelf with a dedicated user account, securely stores the server-issued tokens, shows a simple two-line OLED library and playback interface, resumes from Audiobookshelf progress, and syncs progress back while listening.

The target device is a small enclosure with a 2.08 inch SH1122 SPI OLED, two KY-040 rotary encoders, a MAX98357A I2S amp, and an internal speaker.

## Quick Install

Flash Raspberry Pi OS Lite onto a Raspberry Pi Zero 2 W/WH, enable SSH, and connect to the Pi. The recommended setup username is `chapter` and hostname is `chapter-player`.

To install the upstream stable release, run:

```bash
curl -fsSL https://raw.githubusercontent.com/chrismtopher/chapter/v0.3.12/scripts/install-raspberry-pi.sh | bash
sudo reboot
```

To deploy this fork's untagged `main` changes instead, use the [fork SSH deployment guide](docs/fork-development.md).

The installer handles the software setup:

- system packages
- project clone/update in `/home/chapter/audiobookshelf-player`
- SPI enablement
- MAX98357A I2S audio and ALSA config
- setup web page service
- OLED service and boot splash
- port 80 setup-page proxy
- captive portal DNS helper
- Bluetooth unblock helper
- BlueALSA Bluetooth audio backend

For the complete hardware, flashing, wiring, setup, and troubleshooting walkthrough, see the [Raspberry Pi Zero 2 W install guide](docs/raspberry-pi-zero-2w-install.md).

## Hardware

Recommended build:

- Raspberry Pi Zero 2 WH, or Raspberry Pi Zero 2 W with a soldered 40-pin header
- 16 GB or larger microSD card
- Regulated 5 V power supply rated for at least 2 A; see the install guide for the Adafruit 5993's 1.5 A power-path limitation
- 2.08 inch 256x64 SH1122 SPI OLED
- Two KY-040 rotary encoder modules
- MAX98357A I2S mono amplifier breakout
- 4 ohm speaker
- 1.5 A inline fuse on the USB-C 5 V positive lead
- 3 mm warm-white power indicator LED for the lower-right front-cover hole
- Cross-connect wires for component wiring

The wiring tables are in the [install guide](docs/raspberry-pi-zero-2w-install.md#wire-the-hardware).

Purchase links for the recommended parts are in [docs/hardware-links.md](docs/hardware-links.md).

Printable case files are in [hardware/case](hardware/case).

## Setup

After installation and reboot, open the setup page from a phone or computer on the same network:

```text
http://chapter-player.local
```

If the player is not connected to Wi-Fi, it starts an open setup hotspot:

```text
Network:  Chapter-Setup
Password: none
Page:     http://10.42.0.1
```

The setup page lets you enter your Wi-Fi details and log the player into Audiobookshelf. Create a dedicated Audiobookshelf user for the player and restrict that user to the appropriate library or tags.

For a simple handout, see the [first boot one-sheet](docs/first-boot-one-sheet.md).

For a package-style quick start card, open the [PDF](docs/first-boot-quick-start.pdf) or [JPG](docs/first-boot-quick-start.jpg).

## Controls

- At startup, the player opens the first enabled root-menu item, which is `Continue Listening` by default. This list contains in-progress books only, newest activity first, with listening progress. Finished books are excluded.
- The root menu also includes `Browse by Series`, `Browse by Title`, `Browse by Author`, and `Bluetooth Settings`. The shutdown instruction can be reordered or hidden from the Settings tab; the shutdown gesture still works when it is hidden.
- In series and author views, choose a group to see its books. A book's series position appears only inside its series.
- `Browse by Title` shows plain titles. Long titles scroll across the OLED.
- Turn the Select knob to move through menus and lists; click to choose. Hold it for the configured duration (one second by default) to go back one level.
- Turn the Volume knob to change volume. Click it to play or pause and return to the playback screen. Hold it for the configured duration to return to the root menu.
- While a book is playing in the background, the display returns to playback after 10 seconds without navigation input; this timeout is configurable.
- To shut down cleanly, press and hold both knobs together for the configured hold duration. This works from any menu or screen, whether or not the shutdown instruction is visible. Wait for the player to power off before disconnecting power.
- Bluetooth pairing is available through `Bluetooth Settings`. Choose `Pair`, put the speaker or headphones in pairing mode, then select the device from the scan results.
- Parents can enable `Spoken navigation` on the Settings tab to have the player read highlighted book titles and controls aloud. It is disabled by default. With spoken navigation enabled, Volume-knob changes are announced at 10% intervals, volume stops at 10%, and clicking the Volume knob remains a play/pause action.

## Setup Page Controls And Settings

The setup page includes live Wi-Fi, Audiobookshelf, Bluetooth, and playback status. Its Remote Control tab can search and browse the library, start or resume a book, control playback and volume, skip chapters, manage Bluetooth audio, and review books played on this device. Device history is stored on the Chapter player and is separate from Audiobookshelf account history.

Settings include playback speed, library sorting, spoken navigation, click feedback, screen saver style and dimming, sleep timer, startup behavior, and navigation behavior. Navigation settings include root-menu visibility and order; the shared knob-hold duration; title-marquee start delay, speed, and loop pause; knob-acceleration multiplier and speed threshold; and the delay before returning to playback.

By default, startup opens `Continue Listening`. An optional setting shows a resume prompt for the user's most recently updated in-progress book at startup. The built-in update checker follows stable releases from the upstream `chrismtopher/chapter` repository; it does not install this fork's untagged `main` commits. See [working with this fork](docs/fork-development.md) for the fork's SSH deployment process.

## Features

- Two-line SH1122 OLED with root-menu navigation for continue listening and browsing by series, title, or author
- Continue Listening list of in-progress books, ordered by latest user progress and excluding finished books
- Browse by series, title, or author, with series and author groups
- Configurable root-menu choices and order
- Select and Volume rotary controls with configurable Back, root, play/pause, and simultaneous-hold shutdown gestures
- Speed-sensitive list scrolling and configurable title marquee
- Internal speaker playback through GStreamer
- Audiobookshelf login through the local setup page
- Searchable web remote control for books, playback, chapters, volume, and Bluetooth
- Recent-playback history stored on the device, separate from account-wide history
- Configurable `1x`, `1.5x`, and `2x` playback speed
- Configurable library ordering by title or author last name
- Configurable startup selection, screen saver, sleep timer, marquee, knob holds, and navigation
- Optional offline spoken navigation for book titles and controls using a tuned eSpeak NG voice
- System-tab stable release checks and one-button upstream update installation
- Resume from Audiobookshelf progress
- Periodic progress sync back to Audiobookshelf
- Multi-file audiobook playback
- Continue/start-over prompt when a book has listening history
- Wi-Fi setup fallback hotspot

## Security

The administration page is intentionally passwordless and is intended only for a trusted private home network. Anyone who can reach it can control or reset the player. Do not expose the player to the internet, configure router port forwarding, or connect it to an untrusted network.

CSRF protection prevents unrelated websites from submitting commands through your browser, but it does not authenticate people already connected to the same network. Use a dedicated, restricted Audiobookshelf account for the player. See the full [security policy](SECURITY.md) for details and vulnerability-reporting instructions.

## Development

Run the test suite with:

```bash
python3 -m unittest discover -s tests
```

Run the isolated Raspberry Pi OS Lite installer simulation with:

```bash
tests/mock_raspberry_pi_install.sh
```

See [docs/appliance-design.md](docs/appliance-design.md) for hardware notes, UI behavior, and future direction.

For updates from this fork's `main` branch, see [docs/fork-development.md](docs/fork-development.md).

Release history is recorded in [CHANGELOG.md](CHANGELOG.md).

## License

This project is open source under the terms of the [MIT License](LICENSE).
