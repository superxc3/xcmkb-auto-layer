"""
Raw HID communication with xcmkb-600 firmware.
Usage page 0xFF60 / usage 0x61 — standard QMK Raw HID interface.

Protocol (32-byte packets, byte 0 = report ID 0x00):
  Send [0x00, 0x3N, 0x00…]  → switch to layer N  (N = 0–9)
  Send [0x00, 0x40, 0x00…]  → query current layer
  Recv [layer_index, 0x00…] → response to 0x40 query
"""

import hid
import threading
import time

USAGE_PAGE    = 0xFF60
USAGE         = 0x61
REPORT_LENGTH = 32

CMD_LAYER_BASE  = 0x30   # 0x30 = layer 0, 0x31 = layer 1, …, 0x39 = layer 9
CMD_QUERY_LAYER = 0x40
CMD_MAX_LAYER   = 9

POLL_INTERVAL   = 4.0    # seconds between device re-scan


class HIDController:
    def __init__(self, product_name: str, on_status_change=None):
        self._product   = product_name
        self._device    = None
        self._lock      = threading.Lock()
        self._on_status = on_status_change   # callable(connected: bool)

    # ── Public API ────────────────────────────────────────────────────────────

    def switch_layer(self, layer: int) -> bool:
        """Send layer-switch command. Returns True on success."""
        if layer < 0 or layer > CMD_MAX_LAYER:
            return False
        return self._send([CMD_LAYER_BASE + layer])

    def query_layer(self) -> int | None:
        """Ask the keyboard which layer is active. Returns int or None."""
        if not self._send([CMD_QUERY_LAYER]):
            return None
        try:
            with self._lock:
                if self._device is None:
                    return None
                resp = self._device.read(REPORT_LENGTH, timeout_ms=500)
            if resp:
                return int(resp[0])
        except Exception:
            self._handle_disconnect()
        return None

    def is_connected(self) -> bool:
        with self._lock:
            return self._device is not None

    def connect(self) -> bool:
        """Try to find and open the target device."""
        with self._lock:
            if self._device is not None:
                return True
            for info in hid.enumerate():
                if (info["usage_page"] == USAGE_PAGE
                        and info["usage"] == USAGE
                        and self._product.lower() in info["product_string"].lower()):
                    try:
                        dev = hid.device()
                        dev.open_path(info["path"])
                        dev.set_nonblocking(False)
                        self._device = dev
                        if self._on_status:
                            self._on_status(True)
                        return True
                    except Exception:
                        pass
        return False

    def disconnect(self):
        with self._lock:
            if self._device:
                try:
                    self._device.close()
                except Exception:
                    pass
                self._device = None
        if self._on_status:
            self._on_status(False)

    def list_devices(self) -> list[str]:
        """Return product strings of all connected QMK Raw HID devices."""
        seen = []
        for info in hid.enumerate():
            if info["usage_page"] == USAGE_PAGE and info["usage"] == USAGE:
                name = info["product_string"]
                if name and name not in seen:
                    seen.append(name)
        return seen

    # ── Internal ──────────────────────────────────────────────────────────────

    def _send(self, data: list[int]) -> bool:
        packet = [0x00] + data + [0x00] * (REPORT_LENGTH - len(data))
        try:
            with self._lock:
                if self._device is None:
                    return False
                self._device.write(bytes(packet))
            return True
        except Exception:
            self._handle_disconnect()
            return False

    def _handle_disconnect(self):
        with self._lock:
            try:
                if self._device:
                    self._device.close()
            except Exception:
                pass
            self._device = None
        if self._on_status:
            self._on_status(False)
