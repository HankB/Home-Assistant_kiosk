#!/usr/bin/env python3

import fcntl
import json
import os
import select
import struct
import subprocess
import threading
import time

import paho.mqtt.client as mqtt


#
# Configuration
#

DEVICE = "/dev/input/event2"

# Use a short value while testing. Normal operation is 300.
IDLE_TIMEOUT = 300

IMAGE_DIRECTORY = os.path.expanduser("~/Pictures/screensaver")

#
# MQTT / ambient-light configuration
#

MQTT_BROKER = "pilog3b"
MQTT_PORT = 1883
MQTT_TOPIC = "HA/kiosk/kiosk/lighting"

# Maximum acceptable age of a sensor reading, in seconds.
# 120 is convenient for testing. This should be increased when the
# sensor's normal 15-minute reporting interval is put into service.
LIGHT_READING_MAX_AGE = 120

# These aren't used to control anything yet. They're collected here
# now so the eventual light/dark policy remains easy to configure.
DARK_THRESHOLD = 10
LIGHT_THRESHOLD = 20

DARK_CONFIRM_TIME = 30
LIGHT_CONFIRM_TIME = 30


#
# Linux input constants
#

EV_KEY = 0x01
BTN_TOUCH = 330

EVIOCGRAB = 0x40044590

EVENT_FORMAT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)


#
# Ambient-light state
#
# This is populated by the MQTT thread but is deliberately NOT used
# by the screensaver logic yet.
#

ambient_lock = threading.Lock()

ambient_level = None
ambient_timestamp = None


def grab(fd, enable):
    """Enable or disable exclusive access to the touchscreen."""

    fcntl.ioctl(fd, EVIOCGRAB, 1 if enable else 0)


def read_event(fd):
    """Read one Linux input_event."""

    data = os.read(fd, EVENT_SIZE)

    if len(data) != EVENT_SIZE:
        raise RuntimeError("Short read from input device")

    _, _, event_type, code, value = struct.unpack(EVENT_FORMAT, data)

    return event_type, code, value


#
# MQTT callbacks
#

def on_connect(client, userdata, flags, reason_code, properties):
    """Subscribe to the ambient-light topic after connecting."""

    if reason_code == 0:
        print(
            f"MQTT connected to {MQTT_BROKER}:{MQTT_PORT}",
            flush=True,
        )

        client.subscribe(MQTT_TOPIC)

        print(
            f"MQTT subscribed to {MQTT_TOPIC}",
            flush=True,
        )
    else:
        print(
            f"MQTT connection failed: {reason_code}",
            flush=True,
        )


def on_disconnect(client, userdata, disconnect_flags,
                  reason_code, properties):
    """Report loss of the MQTT connection."""

    print(
        f"MQTT disconnected: {reason_code}",
        flush=True,
    )


def on_message(client, userdata, message):
    """Validate and record an ambient-light MQTT message."""

    global ambient_level
    global ambient_timestamp

    try:
        payload = json.loads(message.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(
            f"Lighting: malformed JSON -- ignored ({exc})",
            flush=True,
        )
        return

    if not isinstance(payload, dict):
        print(
            "Lighting: payload is not a JSON object -- ignored",
            flush=True,
        )
        return

    try:
        timestamp = int(payload["t"])
        level = int(payload["level"])
    except (KeyError, TypeError, ValueError):
        print(
            "Lighting: missing or invalid t/level -- ignored",
            flush=True,
        )
        return

    if not 1 <= level <= 100:
        print(
            f"Lighting: invalid level={level} -- ignored",
            flush=True,
        )
        return

    now = time.time()
    age = now - timestamp

    #
    # A future timestamp is also considered invalid. Allow a few
    # seconds for harmless clock/processing differences.
    #
    if age < -5:
        print(
            f"Lighting: timestamp is {-age:.0f}s in the future -- ignored",
            flush=True,
        )
        return

    if age > LIGHT_READING_MAX_AGE:
        print(
            f"Lighting: level={level} age={age:.0f}s STALE -- ignored",
            flush=True,
        )
        return

    with ambient_lock:
        ambient_level = level
        ambient_timestamp = timestamp

    print(
        f"Lighting: level={level} age={max(0, age):.0f}s ACCEPTED",
        flush=True,
    )


def start_mqtt():
    """Create the MQTT client and start its network thread."""

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="ocular-screensaver",
    )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    print(
        f"Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT}...",
        flush=True,
    )

    #
    # connect_async() avoids making MQTT availability a prerequisite
    # for starting the kiosk screensaver controller.
    #
    client.connect_async(
        MQTT_BROKER,
        MQTT_PORT,
        keepalive=60,
    )

    client.loop_start()

    return client


def wait_for_idle(fd):
    """
    Monitor the touchscreen without grabbing it.

    Every BTN_TOUCH down event resets the idle timer. While we're in
    this state, labwc continues receiving all touchscreen events normally.
    """

    deadline = time.monotonic() + IDLE_TIMEOUT

    while True:
        remaining = deadline - time.monotonic()

        if remaining <= 0:
            return

        readable, _, _ = select.select([fd], [], [], remaining)

        if not readable:
            # select() timed out: no relevant activity.
            return

        event_type, code, value = read_event(fd)

        if event_type == EV_KEY and code == BTN_TOUCH and value == 1:
            deadline = time.monotonic() + IDLE_TIMEOUT


def run_screensaver(fd):
    """
    Grab the touchscreen, start swayimg, and consume the first complete
    touch gesture before returning control to labwc.
    """

    print("Idle timeout reached; grabbing touchscreen.", flush=True)

    grab(fd, True)

    swayimg = None

    try:
        env = os.environ.copy()

        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
        env["WAYLAND_DISPLAY"] = "wayland-0"

        swayimg = subprocess.Popen(
            [
                "swayimg",
                "--fullscreen",
                "--slideshow",
                "--order=random",
                "--scale=fill",
                IMAGE_DIRECTORY,
            ],
            env=env,
        )

        print(f"swayimg started as PID {swayimg.pid}", flush=True)

        #
        # Wait for finger DOWN.
        #

        while True:
            event_type, code, value = read_event(fd)

            if event_type == EV_KEY and code == BTN_TOUCH and value == 1:
                print("Wake touch DOWN.", flush=True)
                break

        #
        # Remove the slideshow, but KEEP the touchscreen grabbed.
        #

        if swayimg.poll() is None:
            swayimg.terminate()

        #
        # Consume everything through finger UP.
        #

        while True:
            event_type, code, value = read_event(fd)

            if event_type == EV_KEY and code == BTN_TOUCH and value == 0:
                print("Wake touch UP.", flush=True)
                break

        #
        # Wait briefly for swayimg to exit cleanly.
        #

        try:
            swayimg.wait(timeout=2)
        except subprocess.TimeoutExpired:
            swayimg.kill()
            swayimg.wait()

    finally:
        print("Releasing touchscreen.", flush=True)

        try:
            grab(fd, False)
        finally:
            if swayimg is not None and swayimg.poll() is None:
                swayimg.terminate()

                try:
                    swayimg.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    swayimg.kill()
                    swayimg.wait()


def main():
    mqtt_client = start_mqtt()

    print(f"Opening {DEVICE}", flush=True)

    fd = os.open(DEVICE, os.O_RDONLY)

    try:
        while True:
            print(
                f"Watching for {IDLE_TIMEOUT} seconds of inactivity...",
                flush=True,
            )

            wait_for_idle(fd)
            run_screensaver(fd)

            #
            # run_screensaver() doesn't return until the wake gesture has
            # completely finished and the touchscreen has been released.
            #
            # Start a brand-new idle interval now.
            #

    finally:
        os.close(fd)

        mqtt_client.loop_stop()
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()