# Working With The `douggreer/chapter` Fork

This fork's `main` branch is based on upstream Chapter v0.3.12. The navigation, web-control, and shutdown changes listed in the [changelog](../CHANGELOG.md) are fork-specific commits and have not been published as a release tag.

The setup page's stable software updater checks release tags in the upstream `chrismtopher/chapter` repository. It does not deploy untagged commits from this fork. To put the current fork code on a Raspberry Pi, package the Python application and copy it over SSH.

## Build And Transfer The Package

From PowerShell or a shell with `tar` and `scp`, run these commands from the fork's repository root. The `ustar` format avoids extended archive metadata that can cause extraction problems on the Pi.

```powershell
tar --format=ustar --exclude=__pycache__ -czf .\chapter-player-update.tar.gz abs_kids_player
scp .\chapter-player-update.tar.gz chapter@chapter-player.local:/tmp/chapter-player-update.tar.gz
ssh chapter@chapter-player.local
```

If `chapter-player.local` does not resolve, replace it with the Pi's IP address. The generated tarball is a deployment artifact; do not commit it.

## Install On The Pi

After SSH connects, extract to a new staging directory as root, back up the installed package, and copy the update into place:

```bash
set -e
STAGE="$(mktemp -d /tmp/chapter-player-update.XXXXXX)"
sudo tar --no-same-owner -xzf /tmp/chapter-player-update.tar.gz -C "$STAGE"
sudo chmod -R u+rwX "$STAGE/abs_kids_player"
test -f "$STAGE/abs_kids_player/setup_server.py"

sudo systemctl stop audiobookshelf-player-oled.service audiobookshelf-player-setup.service

INSTALL_DIR="/home/chapter/audiobookshelf-player/abs_kids_player"
BACKUP="/home/chapter/abs-kids-player.backup-$(date +%Y%m%d-%H%M%S)"
sudo cp -a "$INSTALL_DIR" "$BACKUP"
echo "Backup: $BACKUP"

sudo cp -a "$STAGE/abs_kids_player/." "$INSTALL_DIR/"
sudo chown -R chapter:chapter "$INSTALL_DIR"
sudo chmod -R u+rwX "$INSTALL_DIR"

sudo systemctl start audiobookshelf-player-setup.service audiobookshelf-player-oled.service
sleep 3
sudo systemctl is-active audiobookshelf-player-setup.service audiobookshelf-player-oled.service
curl -fsS http://localhost:47831/health
```

Using a fresh staging directory and extracting with `sudo` avoids conflicts with read-only files from an earlier archive. The update replaces only `abs_kids_player`; saved Wi-Fi, Audiobookshelf credentials, and player preferences remain in the home configuration directory. The backup is kept in `/home/chapter` for rollback.

If the services do not become active, inspect their logs before trying the update again:

```bash
sudo journalctl -u audiobookshelf-player-setup.service -n 80 --no-pager
sudo journalctl -u audiobookshelf-player-oled.service -n 80 --no-pager
```
