# Changelog

All notable changes to Chapter Player for Audiobookshelf are documented here.

## Unreleased

The fork-specific changes below are not yet published as a versioned release.

## Changes in this fork since upstream v0.3.12

This fork's `main` branch is based on upstream Chapter v0.3.12. The following features and behavior changes have been added since that fork point; they are not yet a tagged release.

### Library navigation and progress

- Replaced the single alphabetical browsing list with a root menu for `Continue Listening`, `Browse by Series`, `Browse by Title`, `Browse by Author`, and `Bluetooth Settings`.
- Added a Continue Listening list using the Audiobookshelf user's in-progress books, sorted by most recent progress activity and excluding finished books. Each item shows listening progress.
- Added series and author group lists with book counts and nested book lists. Series browsing uses each book's primary series; series positions are shown only inside that series.
- Changed title browsing to show the plain audiobook title without a series prefix. Removed the large alphabet letter from the OLED and made long-title marquee timing and speed configurable.
- Load and cache library metadata and user progress for navigation. Added a startup option to show a resume prompt for the user's most recently updated in-progress book; the default startup screen is the first root-menu item.

### Knob controls and playback

- Added one-level Back behavior through a Select-knob hold and a Back action on the playing screen. The Volume knob's long hold returns to the root menu.
- Changed the Volume-knob click to play/pause and return to the playback screen. Browsing while a book plays returns to playback after a configurable idle delay (10 seconds by default).
- Added configurable knob acceleration, from off through 10x, and a fast-turn threshold shared by navigation lists.
- Added a configurable Select/Volume hold duration and a clean shutdown gesture: hold both knobs together for that duration. The gesture works from any screen and does not depend on the optional root-menu instruction being visible.

### Setup portal and device state

- Added remote library search and browsing by title, series, author, and in-progress books; the portal can start or resume books and control playback, volume, chapters, and Bluetooth audio.
- Added recent playback history stored on the Chapter device, separate from Audiobookshelf account history, with a control to clear it.
- Added portal controls for root-menu visibility and order, startup behavior, knob hold time, title marquee timing and speed, acceleration, browse-return timing, screen saver, playback speed, sleep timer, and other display/navigation preferences.
- Added device-specific listening history and richer cached progress and author/series metadata. Continue Listening remains based on the Audiobookshelf account's progress, while the portal's recent list records playback performed on this device.
- Added migration for the new settings so existing player configuration is retained when older separate knob-hold settings and earlier root menus are loaded.

### Fork updates

- The built-in stable updater still checks the upstream `chrismtopher/chapter` release tags. It does not distribute this fork's untagged `main` commits. See [the fork development and SSH deployment guide](docs/fork-development.md) for deploying this fork to a Raspberry Pi.

## [0.3.12] - 2026-10-14

- Added a configurable `1x`, `1.5x`, or `2x` playback speed setting with live updates and pitch-preserving audio.

## [0.3.11] - 2026-10-04

- Announce Volume-knob adjustments at 10% intervals when spoken navigation is enabled.
- Keep Volume-knob adjustments at or above 10% and ignore the knob's mute press while spoken navigation is enabled.

## [0.3.10] - 2026-10-03

- Install and immediately enable BlueALSA so Bluetooth speakers and headphones work on clean Raspberry Pi OS Lite installations and after software updates.

## [0.3.9] - 2026-10-02

- Shorten the administration page title and heading to `Chapter Player`.

## [0.3.8] - 2026-10-02

- Start new and restored players with an empty podcast list so parents explicitly choose every podcast.
- Preserve resolver compatibility for previously supported podcast links without adding them to the library automatically.
- Reconcile the wiring and enclosure documentation with the released hardware, including USB-C power, fuse, amplifier, speaker, and control placement guidance.
- Expand the public-release safety notes and ignore locally generated promotional images.

## [0.3.7] - 2026-10-02

- Hide the redundant successful-update detail beneath the current software version.

## [0.3.6] - 2026-10-02

- Enlarge the library alphabet jump letter without changing title, author, or series alignment.

## [0.3.5] - 2026-10-02

- Keep the administration page on rapid update polling while services restart.
- Reload the administration page automatically after the new web service reports completion.

## [0.3.4] - 2026-10-02

- Pause playback and show the OLED update warning before installation work begins.
- Wait for an OLED-ready acknowledgement before starting the updater, with a bounded fallback timeout.

## [0.3.3] - 2026-10-02

- Silence paused and muted playback completely while keeping the I2S audio path active for pop-free resume.

## [0.3.2] - 2026-10-02

- Show an `UPDATING / DO NOT POWER OFF` warning on the OLED for the full software update.
- Refresh the administration page automatically when an update completes.

## [0.3.1] - 2026-10-02

- Consolidated update availability and confirmation controls into the Software Version section.

## [0.3.0] - 2026-10-02

- Added System-tab release checks and one-button stable software updates that preserve device settings.

## [0.2.2] - 2026-10-02

- Return from the library to the current playback controls after five seconds of inactivity while audio is playing.
- Refine the lightweight eSpeak NG spoken-navigation pacing and pitch while retaining its smoother default voice.

## [0.2.1] - 2026-10-02

- Documented the trusted-local-network security model and safe deployment boundaries.
- Added GitHub Actions coverage for the test suite, syntax checks, and Raspberry Pi OS Lite installer simulation.
- Made the installer simulation portable across macOS and Linux.

## [0.2.0] - 2026-10-02

- Added a web setting to order the player library by title or by author last name.
- Added optional offline spoken navigation for highlighted book titles and controls.
- Added the Chapter color logo and refined the tabbed administration interface.
- Added CSRF protection to setup-page forms and live player controls.
- Pinned the Raspberry Pi installer to versioned releases for reproducible installs.

## [0.1.0] - 2026-10-01

Initial public release.

- Raspberry Pi Zero 2 W/WH appliance interface with SH1122 OLED and two rotary controls.
- Audiobookshelf login, library browsing, playback, resume, and progress synchronization.
- Internal MAX98357A speaker output and Bluetooth audio support.
- Podcast support, sleep timer, screensavers, and web administration.
- Automated Raspberry Pi OS Lite installer, first-boot setup hotspot, and captive portal support.
- Printable enclosure files, wiring documentation, assembly references, and parts list.
- Shared storage ownership handling and an isolated installer simulation for clean-install validation.
