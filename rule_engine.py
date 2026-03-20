"""
Rule engine: given (app_name, window_title), return which layer to activate.

Config format (config.json):
{
  "product": "SoflePLUS2 v6.00 TPS43",
  "poll_ms": 500,
  "block_list": ["vial", "via"],
  "rules": [
    {
      "layer": 2,
      "conditions": [
        {"field": "app",   "type": "contains", "value": "photoshop"}
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

Fields  : "app" | "title"
Types   : "equals" | "contains" | "starts" | "ends"
Operator: "or" (default) | "and"
Layer 0 is the implicit fallback when no rule matches.
"""

import json
import os
from pathlib import Path

DEFAULT_CONFIG = {
    "product": "",
    "poll_ms": 500,
    "block_list": ["vial", "via"],
    "rules": []
}

CONFIG_PATH = Path.home() / ".xcmkb-auto-layer" / "config.json"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                # merge with defaults for any missing keys
                return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def is_blocked(app_name: str | None, block_list: list[str]) -> bool:
    """Return True if the current app matches any entry in the block list."""
    if app_name is None:
        return False
    app_lower = app_name.lower()
    return any(b.lower() in app_lower for b in block_list)


def evaluate(app_name: str | None, title: str | None, rules: list[dict]) -> int:
    """
    Evaluate rules top-to-bottom; return the layer of the first match.
    Returns 0 (base layer) if no rule matches.
    """
    app   = (app_name or "").lower()
    title = (title    or "").lower()

    for rule in rules:
        conditions = rule.get("conditions", [])
        operator   = rule.get("operator", "or").lower()
        layer      = rule.get("layer", 0)

        results = [_match_condition(c, app, title) for c in conditions]

        if not results:
            continue
        if operator == "and":
            matched = all(results)
        else:   # "or"
            matched = any(results)

        if matched:
            return int(layer)

    return 0   # fallback: base layer


def _match_condition(cond: dict, app: str, title: str) -> bool:
    field  = cond.get("field", "app").lower()
    kind   = cond.get("type",  "contains").lower()
    value  = cond.get("value", "").lower()
    target = app if field == "app" else title

    if kind == "equals":
        return target == value
    elif kind == "contains":
        return value in target
    elif kind == "starts":
        return target.startswith(value)
    elif kind == "ends":
        return target.endswith(value)
    return False
