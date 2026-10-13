#!/usr/bin/env python3

import fcntl
import os
import select
import signal
import struct
import subprocess
import time

#
# Configuration
#

DEVICE = "/dev/input/event2"

# Use 10 while testing. Change to 300 when satisfied.
IDLE_TIMEOUT = 300

IMAGE_DIRECTORY = os.path.expanduser("~/Pictures/screensaver")

#
# Linux input constants
#

EV_KEY = 0x01
BTN_TOUCH = 330
EVIOCGRAB = 0x40044590

EVENT_FORMAT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)


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


if __name__ == "__main__":
    main()

