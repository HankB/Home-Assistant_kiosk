# Browser configuration

The Chromium browser was chosen for no particular reason of which I am aware. It is installed by default. 

* A normal install was performed using `rpi-imager` v2.0.12 to install "Raspberry Pi OS (64 bit)" specifying user credentials, WiFi credentials, and SSH login via password. (This could be whatever is used for your typical configuration except that the LabWC desktop is required)
* A user `kiosk` was created and given `sudo` permissions. I typically ise "my own" login on these devices but wanted a dedicated user for the kiosk.
* Using `sudo raspi-config` configure the user to boot directly to the desktop.

An [`autostart`](./autostart) file was created in `/home/kiosk/.config/labwc` to start the browser and screen saver. The [browser script](kiosk.sh) is in `/home/kiosk/bin/kiosk.sh` and loops the browser with a 15s delay so the browser will restart if it crashes. The [screensaver controller](../screensaver/screensaver-controller.py) is described in more detail in it's [own section](../screensaver/README.md).
