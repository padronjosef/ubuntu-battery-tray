"""Helpers to find and query Linux hidraw nodes."""

import glob
import logging
import os
import threading
import select
import time
from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")

log = logging.getLogger(__name__)

RETRY_SECONDS = 5


def find(vendor_id: int, product_ids: Iterable[int] | None, *descriptor_markers: bytes) -> str | None:
    """Return the first /dev/hidrawN of the device whose report descriptor contains every marker."""
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(node, "device/uevent")) as uevent:
                hid_id = next((line for line in uevent.read().upper().splitlines() if line.startswith("HID_ID=")), "")
            with open(os.path.join(node, "device/report_descriptor"), "rb") as descriptor_file:
                descriptor = descriptor_file.read()
        except OSError:
            continue
        if f":{vendor_id:08X}:" not in hid_id:
            continue
        if product_ids is not None and not any(hid_id.endswith(f":{pid:08X}") for pid in product_ids):
            continue
        if all(marker in descriptor for marker in descriptor_markers):
            return "/dev/" + os.path.basename(node)
    return None


def transact(path: str, request: bytes, match: Callable[[bytes], T | None], timeout: float = 1.5) -> T | None:
    """Write one report and return the first reply accepted by `match`, or None on timeout."""
    fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    try:
        os.write(fd, request)
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                break
            result = match(os.read(fd, 64))
            if result is not None:
                return result
    finally:
        os.close(fd)
    return None


def listen(name: str, find_path: Callable[[], str | None], handle: Callable[[bytes], None]) -> None:
    """Read every input report of a device in a daemon thread, reopening it after unplug."""

    def run() -> None:
        while True:
            path = find_path()
            if path is None:
                time.sleep(RETRY_SECONDS)
                continue
            try:
                fd = os.open(path, os.O_RDONLY)
            except OSError as error:
                log.error("%s: cannot open %s: %s", name, path, error)
                time.sleep(RETRY_SECONDS)
                continue
            try:
                while True:
                    select.select([fd], [], [])
                    handle(os.read(fd, 64))
            except OSError as error:
                log.warning("%s: %s disconnected: %s", name, path, error)
            finally:
                os.close(fd)

    threading.Thread(target=run, name=f"{name}-listener", daemon=True).start()
