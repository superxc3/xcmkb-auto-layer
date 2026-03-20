# xcmkb Auto-Layer

System tray companion app for xcmkb keyboards. Detects the active application and automatically switches the keyboard to a configured layer.

## Requirements

- Python 3.11+
- xcmkb keyboard flashed with a `tps43-600` or `tps65-600` keymap (or any keymap with Auto-Layer Raw HID support)

## Installation

```bash
pip install -r requirements.txt
```

### Windows
No extra steps — `pywin32` installs automatically.

### macOS
`pyobjc-framework-Cocoa` installs automatically. You must grant **Accessibility** permission to the terminal / Python binary so it can read the active application:

> System Settings → Privacy & Security → Accessibility → add Terminal (or Python)

## Usage

```bash
python main.py
```

A coloured dot appears in the system tray:

| Colour | Meaning |
|--------|---------|
| 🟢 Green  | Running — keyboard connected, monitoring active |
| 🟠 Orange | Paused   — user-paused via tray menu |
| 🔴 Red    | Error    — keyboard not found / disconnected |
| 🔵 Blue   | Grabbing — waiting for you to switch app |

### First-time setup

1. Open **Settings…** from the tray menu.
2. Select your keyboard from the **Keyboard** dropdown.
3. Click **OK**.

### Adding rules

**Via Grab (recommended)**

1. Click **Grab (assign current app → layer)** in the tray menu.
2. Switch to the app you want to map (you have 4 seconds).
3. The keyboard layer active at that moment is recorded automatically.

**Via Settings**

1. Open **Settings…**.
2. In the **Rules** section, enter the app name (e.g. `photoshop`) and choose a layer number.
3. Click **Add**, then **OK**.

### Configuration file

Stored at `~/.xcmkb-auto-layer/config.json`:

```json
{
  "product": "SoflePLUS2 v6.00 TPS43",
  "poll_ms": 500,
  "block_list": ["vial", "via"],
  "rules": [
    {
      "layer": 2,
      "conditions": [
        {"field": "app", "type": "contains", "value": "photoshop"}
      ]
    },
    {
      "layer": 3,
      "operator": "and",
      "conditions": [
        {"field": "app",   "type": "equals",   "value": "code"},
        {"field": "title", "type": "contains", "value": "python"}
      ]
    }
  ]
}
```

| Field | Options |
|-------|---------|
| `field` | `app` \| `title` |
| `type` | `equals` \| `contains` \| `starts` \| `ends` |
| `operator` | `or` (default) \| `and` |

Rules are evaluated top-to-bottom; the first match wins. Layer `0` is the fallback when no rule matches.

The `block_list` prevents layer switching while Vial / VIA configurator is in the foreground.

## Firmware

Compatible keymaps live in the [superxc3/vial-qmk](https://github.com/superxc3/vial-qmk) repository under:

```
keyboards/xcmkb/sofleplus2/keymaps/tps43-600/
keyboards/xcmkb/sofleplus2/keymaps/tps65-600/
```

These keymaps expose Raw HID commands `0x30`–`0x40` for layer switching and query.

## License

MIT
