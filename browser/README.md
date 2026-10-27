# Browser configuration

The Chromium browser was chosen for no particular reason of which I am aware. It is installed by default. It turned out to have an issue that resulted in a white screen when first started. Troubleshooting with AI assistance seemed to indicate that the built in network manager failed and restarted but the URL for the kiosk display was not then fetched. Switching to Firefox-esr seems to have fixed that.

```text
hbarta@ocular:~ $ apt-cache policy firefox-esr rpi-firefox-mods
firefox-esr:
  Installed: 153.5.1esr-1~deb13u1
  Candidate: 153.5.1esr-1~deb13u1
  Version table:
 *** 153.5.1esr-1~deb13u1 500
        500 http://deb.debian.org/debian-security trixie-security/main arm64 Packages
        100 /var/lib/dpkg/status
     140.15.0esr-1~deb13u1 500
        500 http://deb.debian.org/debian trixie/main arm64 Packages
rpi-firefox-mods:
  Installed: 20251016
  Candidate: 20251016
  Version table:
 *** 20251016 500
        500 http://archive.raspberrypi.com/debian trixie/main arm64 Packages
        100 /var/lib/dpkg/status
hbarta@ocular:~ $ 
```

* A normal install was performed using `rpi-imager` v2.0.12 to install "Raspberry Pi OS (64 bit)" specifying user credentials, WiFi credentials, and SSH login via password. (This could be whatever is used for your typical configuration except that the LabWC desktop is required)
* A user `kiosk` was created and given `sudo` permissions. I typically ise "my own" login on these devices but wanted a dedicated user for the kiosk.
* Using `sudo raspi-config` configure the user to boot directly to the desktop.

An [`autostart`](./autostart) file was created in `/home/kiosk/.config/labwc` to start the browser and screen saver. The [browser script](kiosk.sh) is in `/home/kiosk/bin/kiosk.sh` and loops the browser with a 15s delay so the browser will restart if it crashes. The [screensaver controller](../screensaver/screensaver-controller.py) is described in more detail in it's [own section](../screensaver/README.md).
