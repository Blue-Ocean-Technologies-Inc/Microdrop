"""Pure helpers that turn the board's ``dump_config`` JSON and 1-Wire scan
results into the two configurator tables. No Qt / traits here, so these are
straightforward to unit-test.

Config document shape (from the firmware ``dump_config``)::

    {
      "temperature_sensors": {
        "1-wire-sensors": {"pin": 13, "conv_mode": 4, "resolution": 16,
                           "<name>": "<rom-hex>", ...},
        "thermistors":    {"<name>": {...}, ...}
      },
      "heaters": {"<heater>": {"type": "...", "sensors": ["<name>", ...]}, ...}
    }
"""
import json

# Bus-level keys inside ``1-wire-sensors`` that are NOT sensor name->ROM entries.
RESERVED_OW_KEYS = {"pin", "conv_mode", "resolution"}


def parse_board_config(config_text):
    """Parse a ``dump_config`` JSON document into a dict, or None if invalid."""
    try:
        config = json.loads(config_text)
    except Exception:
        return None
    return config if isinstance(config, dict) else None


def _ow_name_to_rom(config):
    """``{rom_lower: name}`` for the 1-Wire sensors defined in the config
    (excluding the reserved bus-level keys)."""
    ow = ((config.get("temperature_sensors") or {}).get("1-wire-sensors") or {})
    return {
        rom.lower(): name
        for name, rom in ow.items()
        if name not in RESERVED_OW_KEYS and isinstance(rom, str)
    }


def thermistor_names(config):
    """Names of the thermistors defined in the config (used as valid sensor
    references for heater assignments)."""
    thermistors = ((config.get("temperature_sensors") or {}).get("thermistors") or {})
    return list(thermistors.keys()) if isinstance(thermistors, dict) else []


def _sensor_status(in_config, on_bus, scan_done):
    if in_config and on_bus:
        return "On bus + in config"
    if in_config and not on_bus:
        return "Missing from bus" if scan_done else "In config"
    if on_bus and not in_config:
        return "New (on bus)"
    return ""


def sensor_rows(config, scanned_roms, scan_done):
    """Rows for the Sensors table: the union of 1-Wire sensors defined in the
    config and ROMs seen on the last bus scan. Each row is
    ``{"rom", "name", "status"}`` (ROM lower-cased)."""
    by_rom = _ow_name_to_rom(config)
    scanned = {r.lower() for r in (scanned_roms or []) if isinstance(r, str)}
    rows = []
    for rom in sorted(set(by_rom) | scanned):
        rows.append({
            "rom": rom,
            "name": by_rom.get(rom, ""),
            "status": _sensor_status(rom in by_rom, rom in scanned, scan_done),
        })
    return rows


def heater_rows(config):
    """Rows for the Heater Assignments table: one per heater channel, with its
    type and a comma-joined list of assigned sensor names. Each row is
    ``{"heater", "type", "sensors"}``."""
    heaters = config.get("heaters") or {}
    rows = []
    if isinstance(heaters, dict):
        for name, cfg in heaters.items():
            if not isinstance(cfg, dict):
                continue
            sensors = cfg.get("sensors") or []
            joined = ", ".join(s for s in sensors if isinstance(s, str))
            rows.append({"heater": name, "type": str(cfg.get("type", "")), "sensors": joined})
    return rows
