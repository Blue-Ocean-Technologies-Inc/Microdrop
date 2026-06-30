"""Hardware-free tests for the Configure Sensors & Heaters parsing + model."""
import json

from heater_controls_ui.sensor_config.parsing import (
    sensor_rows, heater_rows, thermistor_names, parse_board_config, RESERVED_OW_KEYS,
)
from heater_controls_ui.sensor_config.model import SensorConfigModel


CONFIG = {
    "temperature_sensors": {
        "1-wire-sensors": {"pin": 13, "conv_mode": 4, "resolution": 16,
                           "inlet": "28FF1111111111AA", "outlet": "28FF2222222222BB"},
        "thermistors": {"therm1": {"beta": 3950}},
    },
    "heaters": {
        "tec1": {"type": "tec", "sensors": ["inlet", "therm1"]},
        "res1": {"type": "resistive", "sensors": ["outlet"]},
    },
}


# --- parsing ----------------------------------------------------------------

def test_parse_board_config_rejects_non_json():
    assert parse_board_config("not json") is None
    assert parse_board_config("[1, 2]") is None       # not a dict
    assert parse_board_config(json.dumps(CONFIG))["heaters"]["tec1"]["type"] == "tec"


def test_sensor_rows_excludes_reserved_bus_keys():
    rows = sensor_rows(CONFIG, scanned_roms=[], scan_done=False)
    names = {r["name"] for r in rows}
    assert names == {"inlet", "outlet"}
    assert not (names & RESERVED_OW_KEYS)


def test_sensor_rows_status_logic():
    rows = {r["rom"]: r["status"] for r in sensor_rows(
        CONFIG, scanned_roms=["28ff2222222222bb", "28ff9999999999cc"], scan_done=True)}
    assert rows["28ff1111111111aa"] == "Missing from bus"   # in config, off bus
    assert rows["28ff2222222222bb"] == "On bus + in config"  # both
    assert rows["28ff9999999999cc"] == "New (on bus)"        # bus only


def test_sensor_rows_in_config_before_scan():
    rows = {r["rom"]: r["status"] for r in sensor_rows(CONFIG, [], scan_done=False)}
    assert rows["28ff1111111111aa"] == "In config"


def test_heater_rows():
    rows = {r["heater"]: r for r in heater_rows(CONFIG)}
    assert set(rows) == {"tec1", "res1"}
    assert rows["tec1"]["type"] == "tec"
    assert rows["tec1"]["sensors"] == "inlet, therm1"


def test_thermistor_names():
    assert thermistor_names(CONFIG) == ["therm1"]


def test_empty_config_yields_no_rows():
    assert sensor_rows({}, [], False) == []
    assert heater_rows({}) == []


# --- model ------------------------------------------------------------------

def test_model_load_config_builds_rows():
    m = SensorConfigModel()
    assert m.load_config_text(json.dumps(CONFIG)) is True
    assert {r.name for r in m.sensors} == {"inlet", "outlet"}
    assert {r.heater for r in m.heater_assignments} == {"tec1", "res1"}
    assert m.source.startswith("Live from board")


def test_model_load_bad_config_returns_false():
    m = SensorConfigModel()
    assert m.load_config_text("nope") is False


def test_model_scan_updates_status():
    m = SensorConfigModel()
    m.load_config_text(json.dumps(CONFIG))
    m.set_scanned_roms(["28ff1111111111aa"])
    assert m.scan_done is True
    status = {r.name: r.status for r in m.sensors}
    assert status["inlet"] == "On bus + in config"
    assert status["outlet"] == "Missing from bus"
