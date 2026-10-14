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

# Normal operation: 300.
IDLE_TIMEOUT = 300

IMAGE_DIRECTORY = os.path.expanduser("~/Pictures/screensaver")


#
# MQTT / ambient-light configuration
#

MQTT_BROKER = "pilog3b"
MQTT_PORT = 1883
MQTT_TOPIC = "HA/kiosk/kiosk/lighting"

# Maximum acceptable age of a sensor reading.
#
# 120 seconds is convenient for testing. Production should be longer
# than the sensor's normal 15-minute reporting interval.
LIGHT_READING_MAX_AGE = 120

# Hysteresis:
#
#   level <= DARK_THRESHOLD   -> candidate DARK
#   level >= LIGHT_THRESHOLD  -> candidate LIGHT
#   between thresholds        -> retain current/candidate state
#
DARK_THRESHOLD = 10
LIGHT_THRESHOLD = 20

# How long a candidate condition must persist before becoming the
# authoritative ambient state.
DARK_CONFIRM_TIME = 30
LIGHT_CONFIRM_TIME = 30

# How often the ambient-state monitor reevaluates qualification and
# reading freshness.
AMBIENT_CHECK_INTERVAL = 1


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

ambient_lock = threading.Lock()

ambient_level = None
ambient_timestamp = None

# Unknown/stale data defaults to LIGHT.
ambient_state = "LIGHT"

# Candidate state waiting for its confirmation interval.
ambient_candidate = None
ambient_candidate_since = None


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
# Ambient-light state handling
#

def set_candidate(candidate):
    """
    Start or update a candidate ambient state.

    The caller must hold ambient_lock.
    """

    global ambient_candidate
    global ambient_candidate_since

    if candidate == ambient_state:
        #
        # The reading supports our current authoritative state.
        # Any pending transition in the other direction is cancelled.
        #
        if ambient_candidate is not None:
            print(
                f"Ambient: candidate {ambient_candidate} cancelled",
                flush=True,
            )

        ambient_candidate = None
        ambient_candidate_since = None
        return

    if candidate != ambient_candidate:
        ambient_candidate = candidate
        ambient_candidate_since = time.monotonic()

        print(
            f"Ambient: candidate {candidate} started",
            flush=True,
        )


def update_candidate_from_level(level):
    """
    Apply hysteresis to a newly accepted light reading.

    The caller must hold ambient_lock.
    """

    if level <= DARK_THRESHOLD:
        set_candidate("DARK")

    elif level >= LIGHT_THRESHOLD:
        set_candidate("LIGHT")

    else:
        print(
            f"Ambient: level={level} in hysteresis band; "
            "state unchanged",
            flush=True,
        )


def ambient_monitor():
    """
    Periodically reevaluate reading freshness and candidate-state
    qualification.

    This thread only derives and reports LIGHT/DARK state. It does not
    control swayimg or the display.
    """

    global ambient_level
    global ambient_timestamp
    global ambient_state
    global ambient_candidate
    global ambient_candidate_since

    while True:
        time.sleep(AMBIENT_CHECK_INTERVAL)

        with ambient_lock:
            now = time.time()

            #
            # Missing data means LIGHT.
            #
            if ambient_timestamp is None:
                continue

            age = now - ambient_timestamp

            #
            # Once our most recent accepted reading becomes stale,
            # discard it and return to the safe/default LIGHT state.
            #
            if age > LIGHT_READING_MAX_AGE:
                print(
                    f"Ambient: reading became stale "
                    f"(age={age:.0f}s); defaulting to LIGHT",
                    flush=True,
                )

                ambient_level = None
                ambient_timestamp = None
                ambient_candidate = None
                ambient_candidate_since = None

                if ambient_state != "LIGHT":
                    ambient_state = "LIGHT"

                    print(
                        "Ambient state: LIGHT",
                        flush=True,
                    )

                continue

            if (
                ambient_candidate is None
                or ambient_candidate_since is None
            ):
                continue

            elapsed = time.monotonic() - ambient_candidate_since

            if ambient_candidate == "DARK":
                confirm_time = DARK_CONFIRM_TIME
            else:
                confirm_time = LIGHT_CONFIRM_TIME

            if elapsed < confirm_time:
                continue

            new_state = ambient_candidate

            ambient_state = new_state
            ambient_candidate = None
            ambient_candidate_since = None

            print(
                f"Ambient state: {new_state}",
                flush=True,
            )


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


def on_disconnect(
    client,
    userdata,
    disconnect_flags,
    reason_code,
    properties,
):
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
    # Allow a few seconds for harmless clock differences.
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

        update_candidate_from_level(level)


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

        while True:
            event_type, code, value = read_event(fd)

            if event_type == EV_KEY and code == BTN_TOUCH and value == 1:
                print("Wake touch DOWN.", flush=True)
                break

        if swayimg.poll() is None:
            swayimg.terminate()

        while True:
            event_type, code, value = read_event(fd)

            if event_type == EV_KEY and code == BTN_TOUCH and value == 0:
                print("Wake touch UP.", flush=True)
                break

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

    monitor_thread = threading.Thread(
        target=ambient_monitor,
        name="ambient-monitor",
        daemon=True,
    )

    monitor_thread.start()

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

    finally:
        os.close(fd)

        mqtt_client.loop_stop()
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()