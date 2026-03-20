"""
xcmkb Auto-Layer — system tray companion app.
Detects the active application and automatically switches the keyboard layer.

Tray icon states:
  Green  (running)  — monitoring, keyboard connected
  Orange (paused)   — user-paused
  Red    (error)    — keyboard not found / disconnected
  Blue   (grabbing) — waiting for user to switch app for grab
"""

import sys
import threading
import time

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QSpinBox, QLineEdit, QListWidget, QListWidgetItem, QMessageBox
from PySide6.QtGui import QIcon, QColor, QPixmap
from PySide6.QtCore import Qt, QTimer, Signal, QObject

import rule_engine
import window_detector
from hid_controller import HIDController

POLL_DEFAULT_MS = 500
GRAB_WAIT_S     = 4


# ── Signals bridge (worker thread → Qt main thread) ──────────────────────────

class _Signals(QObject):
    status_changed   = Signal(str)   # "running" | "paused" | "error" | "grabbing"
    layer_changed    = Signal(int)
    grab_done        = Signal(str, int)   # app_name, layer


# ── Tray icon helpers ─────────────────────────────────────────────────────────

def _make_icon(color: str) -> QIcon:
    px = QPixmap(16, 16)
    px.fill(QColor(color))
    return QIcon(px)

ICONS = {}

def _icons():
    global ICONS
    if not ICONS:
        ICONS = {
            "running":  _make_icon("#4CAF50"),   # green
            "paused":   _make_icon("#FF9800"),   # orange
            "error":    _make_icon("#F44336"),   # red
            "grabbing": _make_icon("#2196F3"),   # blue
        }
    return ICONS


# ── Main application ──────────────────────────────────────────────────────────

class AutoLayerApp:
    def __init__(self):
        self._app     = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        self._config  = rule_engine.load_config()
        self._hid     = HIDController(
            product_name    = self._config.get("product", ""),
            on_status_change= self._on_hid_status
        )
        self._signals = _Signals()
        self._state   = "error"       # running | paused | error | grabbing
        self._paused  = False
        self._current_layer = -1
        self._grab_layer    = None

        self._build_tray()
        self._signals.status_changed.connect(self._apply_status)
        self._signals.grab_done.connect(self._on_grab_done)

        # Device scan + monitoring thread
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    # ── Tray ──────────────────────────────────────────────────────────────────

    def _build_tray(self):
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(_icons()["error"])
        self._tray.setToolTip("xcmkb Auto-Layer — not connected")

        menu = QMenu()
        self._status_action = menu.addAction("Not connected")
        self._status_action.setEnabled(False)
        menu.addSeparator()

        self._pause_action = menu.addAction("Pause")
        self._pause_action.triggered.connect(self._toggle_pause)

        grab_action = menu.addAction("Grab (assign current app → layer)")
        grab_action.triggered.connect(self._start_grab)

        menu.addSeparator()
        settings_action = menu.addAction("Settings…")
        settings_action.triggered.connect(self._open_settings)

        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)

        self._tray.setContextMenu(menu)
        self._tray.show()

    def _apply_status(self, state: str):
        self._state = state
        icons = _icons()
        self._tray.setIcon(icons.get(state, icons["error"]))
        labels = {
            "running":  "Running — connected",
            "paused":   "Paused",
            "error":    "Keyboard not found",
            "grabbing": f"Grabbing in {GRAB_WAIT_S}s — switch app now…",
        }
        self._status_action.setText(labels.get(state, state))
        self._tray.setToolTip(f"xcmkb Auto-Layer — {labels.get(state, state)}")
        self._pause_action.setText("Resume" if state == "paused" else "Pause")

    # ── Controls ──────────────────────────────────────────────────────────────

    def _toggle_pause(self):
        self._paused = not self._paused
        self._signals.status_changed.emit("paused" if self._paused else "running")

    def _start_grab(self):
        """Pause monitoring, wait GRAB_WAIT_S seconds, then record current app + layer."""
        self._paused = True
        self._signals.status_changed.emit("grabbing")

        def _grab():
            time.sleep(GRAB_WAIT_S)
            layer = self._hid.query_layer()
            app, _ = window_detector.get_active_window()
            self._paused = False
            if layer is not None and app:
                self._signals.grab_done.emit(app, layer)
            else:
                self._signals.status_changed.emit(
                    "running" if self._hid.is_connected() else "error"
                )

        threading.Thread(target=_grab, daemon=True).start()

    def _on_grab_done(self, app: str, layer: int):
        # Add rule to config and save
        new_rule = {
            "layer": layer,
            "conditions": [{"field": "app", "type": "contains", "value": app}]
        }
        self._config.setdefault("rules", []).append(new_rule)
        rule_engine.save_config(self._config)
        self._tray.showMessage(
            "Auto-Layer",
            f"Saved: '{app}' → Layer {layer}",
            QSystemTrayIcon.MessageIcon.Information,
            3000
        )
        self._signals.status_changed.emit(
            "running" if self._hid.is_connected() else "error"
        )

    def _on_hid_status(self, connected: bool):
        if not self._paused:
            self._signals.status_changed.emit("running" if connected else "error")

    # ── Monitor loop (background thread) ─────────────────────────────────────

    def _monitor_loop(self):
        last_app   = None
        last_title = None
        last_layer = -1

        while True:
            poll_ms = self._config.get("poll_ms", POLL_DEFAULT_MS)

            # Try to connect if not already
            if not self._hid.is_connected():
                if self._hid.connect():
                    self._signals.status_changed.emit("running")
                else:
                    time.sleep(poll_ms / 1000.0)
                    continue

            if self._paused:
                time.sleep(poll_ms / 1000.0)
                continue

            app, title = window_detector.get_active_window()
            block_list = self._config.get("block_list", [])

            if rule_engine.is_blocked(app, block_list):
                time.sleep(poll_ms / 1000.0)
                continue

            # Only re-evaluate if app or title changed
            if app != last_app or title != last_title:
                last_app   = app
                last_title = title
                target = rule_engine.evaluate(app, title, self._config.get("rules", []))
                if target != last_layer:
                    if self._hid.switch_layer(target):
                        last_layer = target
                        self._signals.layer_changed.emit(target)

            time.sleep(poll_ms / 1000.0)

    # ── Settings dialog ───────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self._config, self._hid)
        if dlg.exec():
            self._config = dlg.get_config()
            rule_engine.save_config(self._config)
            # Re-connect with potentially new product name
            self._hid.disconnect()
            self._hid = HIDController(
                product_name     = self._config.get("product", ""),
                on_status_change = self._on_hid_status
            )

    def _quit(self):
        self._hid.disconnect()
        self._app.quit()

    def run(self):
        sys.exit(self._app.exec())


# ── Settings dialog ───────────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    def __init__(self, config: dict, hid: HIDController):
        super().__init__()
        self.setWindowTitle("xcmkb Auto-Layer — Settings")
        self.setMinimumWidth(500)
        self._config = dict(config)
        self._hid    = hid
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Device selection
        dev_row = QHBoxLayout()
        dev_row.addWidget(QLabel("Keyboard:"))
        self._device_combo = QComboBox()
        devices = self._hid.list_devices()
        current = self._config.get("product", "")
        if current and current not in devices:
            devices.insert(0, current)
        self._device_combo.addItems(devices)
        idx = self._device_combo.findText(current)
        if idx >= 0:
            self._device_combo.setCurrentIndex(idx)
        dev_row.addWidget(self._device_combo, 1)
        layout.addLayout(dev_row)

        # Poll interval
        poll_row = QHBoxLayout()
        poll_row.addWidget(QLabel("Poll interval (ms):"))
        self._poll_spin = QSpinBox()
        self._poll_spin.setRange(100, 5000)
        self._poll_spin.setSingleStep(100)
        self._poll_spin.setValue(self._config.get("poll_ms", POLL_DEFAULT_MS))
        poll_row.addWidget(self._poll_spin)
        poll_row.addStretch()
        layout.addLayout(poll_row)

        # Rules list
        layout.addWidget(QLabel("Rules (layer : app contains):"))
        self._rule_list = QListWidget()
        self._refresh_rules()
        layout.addWidget(self._rule_list)

        # Add / remove rule
        rule_edit_row = QHBoxLayout()
        self._rule_layer = QSpinBox()
        self._rule_layer.setRange(0, 9)
        self._rule_layer.setPrefix("Layer ")
        rule_edit_row.addWidget(self._rule_layer)
        self._rule_app = QLineEdit()
        self._rule_app.setPlaceholderText("app name (e.g. photoshop)")
        rule_edit_row.addWidget(self._rule_app, 1)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_rule)
        rule_edit_row.addWidget(add_btn)
        del_btn = QPushButton("Remove selected")
        del_btn.clicked.connect(self._remove_rule)
        rule_edit_row.addWidget(del_btn)
        layout.addLayout(rule_edit_row)

        # OK / Cancel
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

    def _refresh_rules(self):
        self._rule_list.clear()
        for rule in self._config.get("rules", []):
            layer = rule.get("layer", 0)
            conds = rule.get("conditions", [])
            desc  = " AND ".join(
                f"{c.get('field','app')} {c.get('type','contains')} '{c.get('value','')}'"
                for c in conds
            )
            self._rule_list.addItem(f"Layer {layer}: {desc}")

    def _add_rule(self):
        app_val = self._rule_app.text().strip().lower()
        if not app_val:
            return
        layer = self._rule_layer.value()
        new_rule = {
            "layer": layer,
            "conditions": [{"field": "app", "type": "contains", "value": app_val}]
        }
        self._config.setdefault("rules", []).append(new_rule)
        self._rule_app.clear()
        self._refresh_rules()

    def _remove_rule(self):
        row = self._rule_list.currentRow()
        if row >= 0:
            rules = self._config.get("rules", [])
            if row < len(rules):
                rules.pop(row)
            self._refresh_rules()

    def get_config(self) -> dict:
        self._config["product"]  = self._device_combo.currentText()
        self._config["poll_ms"]  = self._poll_spin.value()
        return self._config


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    AutoLayerApp().run()
