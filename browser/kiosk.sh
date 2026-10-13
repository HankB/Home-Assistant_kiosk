#!/bin/sh

while :
do
        # Allow the desktop and network a moment to settle,
        # and delay restart after Chromium exits.
        sleep 15

        chromium \
                --enable-logging \
                --v=1 \
                --kiosk \
                --noerrdialogs \
                --no-first-run \
                --password-store=basic \
                'http://glencoe:8123/dashboard-kiosk/kiosk'
done
