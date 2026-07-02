"""Hardware-free tests for the Configure Sensors & Heaters parsing + model."""
import json

import pytest
from pydantic import ValidationError

from heater_controls_ui.sensor_config.parsing import (
    sensor_rows, heater_rows, thermistor_names, parse_board_config, RESERVED_OW_KEYS,
    split_sensor_names, build_board_config, scan_summary,
)
from heater_controls_ui.sensor_config.model import SensorConfigModel
from heater_controller.datamodels import HeaterConfigEdit, SensorNaming


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


def test_scan_summary_before_scan_is_blank():
    assert scan_summary(CONFIG, [], scan_done=False) == ""


def test_scan_summary_matched_new_and_missing():
    # inlet matched, outlet missing, one brand-new ROM on the bus.
    summary = scan_summary(
        CONFIG, ["28ff1111111111aa", "28ff9999999999cc"], scan_done=True)
    assert summary == (
        "Scan complete: 2 on bus (1 matched, 1 new). "
        "1 config entry not found on bus.")


def test_scan_summary_all_matched_no_missing():
    summary = scan_summary(
        CONFIG, ["28ff1111111111aa", "28ff2222222222bb"], scan_done=True)
    assert summary == "Scan complete: 2 on bus (2 matched, 0 new)."


def test_scan_summary_none_found_reports_all_missing():
    summary = scan_summary(CONFIG, [], scan_done=True)
    assert summary == (
        "Scan complete: 0 on bus (0 matched, 0 new). "
        "2 config entries not found on bus.")


def test_model_sets_and_clears_scan_summary():
    m = SensorConfigModel()
    assert m.load_config_text(json.dumps(CONFIG)) is True
    assert m.scan_summary == ""                       # no scan yet
    m.set_scanned_roms(["28ff1111111111aa", "28ff9999999999cc"])
    assert m.scan_summary.startswith("Scan complete: 2 on bus (1 matched, 1 new)")
    m.load_config_text(json.dumps(CONFIG))            # fresh config clears it
    assert m.scan_summary == ""


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


def test_model_available_sensor_names_live_updates():
    m = SensorConfigModel()
    m.load_config_text(json.dumps(CONFIG))
    assert set(m.available_sensor_names.split(", ")) == {"inlet", "outlet", "therm1"}
    # Editing a sensor name updates the reference list live.
    next(r for r in m.sensors if r.name == "inlet").name = "in2"
    names = set(m.available_sensor_names.split(", "))
    assert "in2" in names and "inlet" not in names
    # Clearing a name drops it.
    next(r for r in m.sensors if r.name == "outlet").name = ""
    assert "outlet" not in m.available_sensor_names


def test_refresh_updates_rows_in_place():
    m = SensorConfigModel()
    m.load_config_text(json.dumps(CONFIG))
    inlet = next(r for r in m.sensors if r.rom == "28ff1111111111aa")
    tec = next(r for r in m.heater_assignments if r.heater == "tec1")
    # Refresh with a changed config: same ROM/heater -> same row object, new value.
    changed = json.loads(json.dumps(CONFIG))
    changed["temperature_sensors"]["1-wire-sensors"].pop("inlet")
    changed["temperature_sensors"]["1-wire-sensors"]["probe"] = "28FF1111111111AA"
    changed["heaters"]["tec1"]["sensors"] = ["probe"]
    m.load_config_text(json.dumps(changed))
    assert m.sensors[0] is inlet or inlet in m.sensors          # reused, not replaced
    assert next(r for r in m.sensors if r.rom == "28ff1111111111aa").name == "probe"
    assert tec.sensors == "probe"                                # heater row updated in place


def test_refresh_resets_scan_status_to_in_config():
    # After a scan some sensors are "On bus..."; a refresh from the board clears
    # the scan so everything reverts to "In config" (matches the old UI).
    m = SensorConfigModel()
    m.load_config_text(json.dumps(CONFIG))
    m.set_scanned_roms(["28ff1111111111aa"])
    assert any(r.status == "On bus + in config" for r in m.sensors)
    m.load_config_text(json.dumps(CONFIG))           # refresh from board
    assert m.scan_done is False and m.scanned_roms == []
    assert all(r.status == "In config" for r in m.sensors)


def test_scan_preserves_name_edits():
    m = SensorConfigModel()
    m.load_config_text(json.dumps(CONFIG))
    inlet = next(r for r in m.sensors if r.rom == "28ff1111111111aa")
    inlet.name = "edited"                       # user is mid-edit
    m.set_scanned_roms(["28ff1111111111aa"])    # a scan happens
    assert inlet.name == "edited"               # name edit kept across the scan
    assert inlet.status == "On bus + in config"  # status still refreshed


def test_model_scan_updates_status():
    m = SensorConfigModel()
    m.load_config_text(json.dumps(CONFIG))
    m.set_scanned_roms(["28ff1111111111aa"])
    assert m.scan_done is True
    status = {r.name: r.status for r in m.sensors}
    assert status["inlet"] == "On bus + in config"
    assert status["outlet"] == "Missing from bus"


# --- edit validation (Phase 2) ----------------------------------------------

def _edit(sensors, assignments, therms=("therm1",)):
    return HeaterConfigEdit(
        sensors=[SensorNaming(rom=r, name=n) for r, n in sensors],
        assignments=assignments, thermistor_names=list(therms))


def test_valid_edit_passes():
    _edit([("28aa", "inlet")], {"tec1": ["inlet", "therm1"]})


def test_duplicate_names_rejected():
    with pytest.raises(ValidationError, match="Duplicate"):
        _edit([("28aa", "x"), ("28bb", "x")], {})


def test_reserved_name_rejected():
    with pytest.raises(ValidationError, match="reserved"):
        _edit([("28aa", "pin")], {})


def test_unknown_reference_rejected():
    with pytest.raises(ValidationError, match="undefined"):
        _edit([("28aa", "inlet")], {"tec1": ["ghost"]})


# --- config build (Phase 2) -------------------------------------------------

def test_split_sensor_names():
    assert split_sensor_names("a, b ,, c ") == ["a", "b", "c"]
    assert split_sensor_names("") == []


def test_build_board_config_renames_drops_and_preserves():
    named = [("28ff1111111111aa", "in1")]            # 'outlet' omitted -> removed
    assignments = {"tec1": ["in1", "therm1"], "res1": ["outlet"]}
    new = build_board_config(CONFIG, named, assignments)
    ow = new["temperature_sensors"]["1-wire-sensors"]
    assert ow["pin"] == 13 and ow["resolution"] == 16      # reserved keys kept
    assert "in1" in ow and "inlet" not in ow and "outlet" not in ow
    assert new["temperature_sensors"]["thermistors"] == {"therm1": {"beta": 3950}}
    assert new["heaters"]["tec1"]["type"] == "tec"         # type preserved
    assert new["heaters"]["tec1"]["sensors"] == ["in1", "therm1"]
    # original config object is not mutated
    assert "inlet" in CONFIG["temperature_sensors"]["1-wire-sensors"]
