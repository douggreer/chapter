# Chapter Player First Boot One-Sheet

Use this sheet when turning on a Chapter Player for the first time.

## What You Need

- A phone, tablet, or computer.
- Your home Wi-Fi network name and password.
- The Audiobookshelf server address and player account login, if the setup page asks for them.

## Connect The Player To Wi-Fi

1. Turn on the Chapter Player.
2. Wait for the screen to show the setup Wi-Fi network and setup address.
3. On your phone, tablet, or computer, connect to this Wi-Fi network:

```text
Chapter-Setup
```

4. Open a browser and go to the address shown on the Chapter Player screen.
5. Enter your home Wi-Fi network name and password.
6. Submit the form and wait while the Chapter Player joins your Wi-Fi.

## Add Audiobookshelf Server Info

1. Open the setup page again if it does not reconnect automatically.
2. Enter the Audiobookshelf server address.
3. Enter the username and password for the player account.
4. Submit the form and wait for the player to connect.

After setup is complete, the Chapter Player opens `Continue Listening` by default. The setup page can optionally be set to show a resume prompt for the user's latest in-progress book at startup.

## The Two Knobs

### Select Knob

- Turn: move through books, menu items, or playback actions.
- Click: select the highlighted item.
- Hold for the configured duration (one second by default): go back one menu level.

### Volume Knob

- Turn: change volume.
- Click: play or pause, then return to the playback screen.
- Hold for the configured duration: return to the root menu.
- Hold both knobs together for the configured duration: cleanly shut down the player.

The single knob-hold duration is adjustable in the setup page's Settings tab. The two-knob shutdown gesture works from any screen, even if its instruction is hidden from the root menu. Wait for the player to power off before disconnecting power.

## Menus And Playback

- The root menu contains Continue Listening, Browse by Series, Browse by Title, Browse by Author, and Bluetooth Settings. Items can be reordered or hidden in the setup page.
- Continue Listening shows in-progress books, most recently updated first, and does not include finished books.
- In a series or author group, turn the Select knob to choose a book and click to open it. A series position is shown in the series view.
- In any menu, turn the Select knob to move, click it to choose, or hold it to go back one level.
- When choosing a book with listening history, select `Continue` or `Start over`.
- During playback, use the Select knob to choose `Back`, `Prev`, `Play/Pause`, or `Next`.
- `Prev` and `Next` may ask you to confirm before changing chapters.
- If a book continues playing while you browse, the display returns to playback after 10 seconds by default.
- Use Bluetooth Settings to enable or disable Bluetooth, pair a speaker or headphones, or disconnect a paired device.
- To pair Bluetooth audio, put the speaker or headphones in pairing mode, choose `Pair`, select the device name, and click to connect.

## If Setup Is Needed Later

Open the setup page at `http://chapter-player.local` or use the player's IP address. A long hold on the Volume knob returns the OLED to the root menu; it no longer shows the setup address.
