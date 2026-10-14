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
IDLE_TIMEOUT = 60

IMAGE_DIRECTORY = os.path.expanduser("~/Pictures/screensaver")


#
# MQTT / ambient-light configuration
#

MQTT_BROKER = "pilog3b"
MQTT_PORT = 1883
MQTT_TOPIC = "HA/kiosk/kiosk/lighting"

# 120 seconds is convenient for testing.
# Production should be comfortably longer than the sensor's normal
# 15-minute reporting interval.
LIGHT_READING_MAX_AGE = 120

# Hysteresis:
#
#   level <= DARK_THRESHOLD   -> candidate DARK
#   level >= LIGHT_THRESHOLD  -> candidate LIGHT
#   between thresholds        -> retain current/candidate state
#
DARK_THRESHOLD = 10
LIGHT_THRESHOLD = 20

# Short values are useful during testing.
DARK_CONFIRM_TIME = 10
LIGHT_CONFIRM_TIME = 10

# How often qualification and freshness are reevaluated.
AMBIENT_CHECK_INTERVAL = 1


#
# Display configuration
#

XDG_RUNTIME_DIR = f"/run/user/{os.getuid()}"
WAYLAND_DISPLAY = "wayland-0"


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

ambient_candidate = None
ambient_candidate_since = None


def log(message):
    """Print a timestamped diagnostic message."""

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp}  {message}", flush=True)


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


def wayland_environment():
    """Return an environment suitable for Wayland helper programs."""

    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = XDG_RUNTIME_DIR
    env["WAYLAND_DISPLAY"] = WAYLAND_DISPLAY

    return env


def display_on():
    """Turn the Wayland output on."""

    log("Display: ON")

    subprocess.run(
        ["wlopm", "--on", "*"],
        env=wayland_environment(),
        check=False,
    )


def display_off():
    """Turn the Wayland output off."""

    log("Display: OFF")

    subprocess.run(
        ["wlopm", "--off", "*"],
        env=wayland_environment(),
        check=False,
    )


def start_slideshow():
    """Start swayimg and return its process object."""

    swayimg = subprocess.Popen(
        [
            "swayimg",
            "--fullscreen",
            "--slideshow",
            "--order=random",
            "--scale=fill",
            IMAGE_DIRECTORY,
        ],
        env=wayland_environment(),
    )

    log(f"swayimg started as PID {swayimg.pid}")

    return swayimg


def stop_slideshow(swayimg):
    """Stop swayimg if it is still running."""

    if swayimg is None:
        return

    if swayimg.poll() is not None:
        return

    log(f"Stopping swayimg PID {swayimg.pid}")

    swayimg.terminate()

    try:
        swayimg.wait(timeout=2)

    except subprocess.TimeoutExpired:
        log(f"Killing swayimg PID {swayimg.pid}")
        swayimg.kill()
        swayimg.wait()


#
# Ambient-light state handling
#

def get_ambient_state():
    """Return the current authoritative ambient state."""

    with ambient_lock:
        return ambient_state


def set_candidate(candidate):
    """
    Start or update a candidate ambient state.

    The caller must hold ambient_lock.
    """

    global ambient_candidate
    global ambient_candidate_since

    if candidate == ambient_state:
        if ambient_candidate is not None:
            log(
                f"Ambient: candidate {ambient_candidate} cancelled; "
                f"reading supports current state {ambient_state}"
            )

        ambient_candidate = None
        ambient_candidate_since = None
        return

    if candidate != ambient_candidate:
        ambient_candidate = candidate
        ambient_candidate_since = time.monotonic()

        log(
            f"Ambient: candidate {candidate} started; "
            f"current state={ambient_state}"
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
        log(
            f"Ambient: level={level} in hysteresis band; "
            f"state={ambient_state}, "
            f"candidate={ambient_candidate}"
        )


def ambient_monitor():
    """
    Periodically reevaluate reading freshness and candidate-state
    qualification.
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

            if ambient_timestamp is None:
                continue

            age = now - ambient_timestamp

            if age > LIGHT_READING_MAX_AGE:
                log(
                    f"Ambient: reading became stale "
                    f"(age={age:.0f}s); defaulting to LIGHT"
                )

                ambient_level = None
                ambient_timestamp = None
                ambient_candidate = None
                ambient_candidate_since = None

                if ambient_state != "LIGHT":
                    ambient_state = "LIGHT"
                    log("Ambient state: LIGHT")

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

            log(
                f"Ambient state: {new_state} "
                f"(confirmed after {elapsed:.1f}s)"
            )


#
# MQTT callbacks
#

def on_connect(client, userdata, flags, reason_code, properties):
    """Subscribe to the ambient-light topic after connecting."""

    if reason_code == 0:
        log(
            f"MQTT connected to {MQTT_BROKER}:{MQTT_PORT}"
        )

        client.subscribe(MQTT_TOPIC)

        log(
            f"MQTT subscribed to {MQTT_TOPIC}"
        )

    else:
        log(
            f"MQTT connection failed: {reason_code}"
        )


def on_disconnect(
    client,
    userdata,
    disconnect_flags,
    reason_code,
    properties,
):
    """Report loss of the MQTT connection."""

    log(
        f"MQTT disconnected: {reason_code}"
    )


def on_message(client, userdata, message):
    """Validate and record an ambient-light MQTT message."""

    global ambient_level
    global ambient_timestamp

    try:
        payload = json.loads(message.payload.decode("utf-8"))

    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        log(
            f"Lighting: malformed JSON -- ignored ({exc})"
        )
        return

    if not isinstance(payload, dict):
        log(
            "Lighting: payload is not a JSON object -- ignored"
        )
        return

    try:
        timestamp = int(payload["t"])
        level = int(payload["level"])

    except (KeyError, TypeError, ValueError):
        log(
            "Lighting: missing or invalid t/level -- ignored"
        )
        return

    if not 1 <= level <= 100:
        log(
            f"Lighting: invalid level={level} -- ignored"
        )
        return

    now = time.time()
    age = now - timestamp

    if age < -5:
        log(
            f"Lighting: timestamp is {-age:.0f}s in the future -- ignored"
        )
        return

    if age > LIGHT_READING_MAX_AGE:
        log(
            f"Lighting: level={level} age={age:.0f}s STALE -- ignored"
        )
        return

    with ambient_lock:
        ambient_level = level
        ambient_timestamp = timestamp

        log(
            f"Lighting: level={level} "
            f"age={max(0, age):.0f}s ACCEPTED"
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

    log(
        f"Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT}..."
    )

    client.connect_async(
        MQTT_BROKER,
        MQTT_PORT,
        keepalive=60,
    )

    client.loop_start()

    return client


#
# Active kiosk / idle handling
#

def wait_for_idle(fd):
    """
    Monitor the touchscreen without grabbing it.

    Every BTN_TOUCH down event resets the idle timer. While we're in
    this state, labwc receives touchscreen events normally.
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


def wait_for_wake_or_state_change(fd, state):
    """
    Wait for either a wake touch or an ambient-state change.

    Return "TOUCH" or "STATE".
    """

    while True:
        readable, _, _ = select.select(
            [fd],
            [],
            [],
            AMBIENT_CHECK_INTERVAL,
        )

        if readable:
            event_type, code, value = read_event(fd)

            if (
                event_type == EV_KEY
                and code == BTN_TOUCH
                and value == 1
            ):
                return "TOUCH"

        if get_ambient_state() != state:
            return "STATE"


def consume_touch_up(fd):
    """Consume touchscreen events through the corresponding finger UP."""

    while True:
        event_type, code, value = read_event(fd)

        if (
            event_type == EV_KEY
            and code == BTN_TOUCH
            and value == 0
        ):
            log("Wake touch UP")
            return


def run_idle(fd):
    """
    Own the touchscreen while the kiosk is idle.

    LIGHT -> slideshow
    DARK  -> display off

    Ambient-state changes are honored while idle. The first wake
    gesture is consumed completely before returning control to labwc.
    """

    log("Idle timeout reached; grabbing touchscreen")

    grab(fd, True)

    swayimg = None
    display_is_on = True

    try:
        while True:
            state = get_ambient_state()

            if state == "LIGHT":
                if not display_is_on:
                    display_on()
                    display_is_on = True

                if swayimg is None or swayimg.poll() is not None:
                    swayimg = start_slideshow()

            else:
                if swayimg is not None:
                    stop_slideshow(swayimg)
                    swayimg = None

                if display_is_on:
                    display_off()
                    display_is_on = False

            result = wait_for_wake_or_state_change(fd, state)

            if result == "STATE":
                new_state = get_ambient_state()

                log(
                    f"Idle ambient transition: "
                    f"{state} -> {new_state}"
                )

                continue

            #
            # Finger DOWN has occurred. Keep the touchscreen grabbed
            # until the entire gesture has been consumed.
            #

            log("Wake touch DOWN")

            if swayimg is not None:
                stop_slideshow(swayimg)
                swayimg = None

            #
            # If the display was dark, turn it on while we still own
            # the wake gesture.
            #

            if not display_is_on:
                display_on()
                display_is_on = True

            consume_touch_up(fd)

            return

    finally:
        #
        # Never leave the display off or swayimg running when returning
        # control to the active kiosk.
        #

        if swayimg is not None:
            stop_slideshow(swayimg)

        if not display_is_on:
            display_on()

        log("Releasing touchscreen")

        grab(fd, False)


def main():
    mqtt_client = start_mqtt()

    monitor_thread = threading.Thread(
        target=ambient_monitor,
        name="ambient-monitor",
        daemon=True,
    )

    monitor_thread.start()

    log(f"Opening {DEVICE}")

    fd = os.open(DEVICE, os.O_RDONLY)

    try:
        while True:
            log(
                f"Watching for {IDLE_TIMEOUT} seconds of inactivity..."
            )

            wait_for_idle(fd)
            run_idle(fd)

    finally:
        os.close(fd)

        mqtt_client.loop_stop()
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()