import json

from pluggable_protocol_tree.services.logging.ingestion import LoggingIngestion


def test_log_data_tracks_columns_in_order():
    ing = LoggingIngestion()
    ing.log_data({"a": 1, "b": 2})
    ing.log_data({"a": 3, "c": 4})
    assert ing.columns == ["a", "b", "c"]
    assert ing.entries == [{"a": 1, "b": 2}, {"a": 3, "c": 4}]


def test_log_metadata_merges():
    ing = LoggingIngestion()
    ing.log_metadata({"x": 1})
    ing.log_metadata({"y": 2, "x": 9})
    assert ing.metadata == {"x": 9, "y": 2}


def test_calculate_force_formula():
    ing = LoggingIngestion()
    ing.update_capacitance_per_unit_area(2.0)
    # 0.5 * 2.0 * 10**2 = 100.0
    assert ing._calculate_force(10.0) == 100.0


def test_calculate_force_none_without_cpa_or_nonpositive_voltage():
    ing = LoggingIngestion()
    assert ing._calculate_force(10.0) is None       # no c-per-area
    ing.update_capacitance_per_unit_area(2.0)
    assert ing._calculate_force(0.0) is None         # voltage <= 0


def test_log_media_buckets_by_type():
    ing = LoggingIngestion()

    class _M:
        def __init__(self, path, type_):
            self.path = path
            self.type = type_

    class _T:
        value = "video"
    ing.log_media(_M("a.mp4", _T()))
    assert ing.media["video"] == ["a.mp4"]


def test_log_media_accepts_plain_string_type():
    ing = LoggingIngestion()

    class _M:
        path = "b.png"
        type = "IMAGE"          # plain string, not an enum
    ing.log_media(_M())
    assert ing.media["image"] == ["b.png"]


def _msg(cap="12.5pF", volt="100V", instr=1000, recv=1700000000):
    return json.dumps({"capacitance": cap, "voltage": volt,
                       "instrument_time_us": instr, "reception_time": recv})


def test_log_capacitance_stamps_step_and_phase_and_force():
    ing = LoggingIngestion()
    ing.update_capacitance_per_unit_area(2.0)
    ing.set_step(step_id="uuid-1", step_idx=3)
    ing.set_actuation(actuated_channels=[5, 6], actuated_area=4.0)
    assert ing.log_capacitance(_msg()) is True
    e = ing.entries[-1]
    assert e["step_id"] == "uuid-1"
    assert e["step_idx"] == 3
    assert e["Capacitance (pF)"] == 12.5
    assert e["Voltage (V)"] == 100.0
    assert e["Force Over Unit Area (mN/mm^2)"] == round(0.5 * 2.0 * 100.0**2, 6)
    assert e["Actuated Area (mm^2)"] == 4.0
    assert e["actuated_channels"] == [5, 6]
    assert e["instrument_time_us"] == 1000
    assert e["utc_time"] == 1700000000


def test_log_capacitance_per_phase_attribution():
    ing = LoggingIngestion()
    ing.set_step(step_id="s", step_idx=1)
    ing.set_actuation(actuated_channels=[1], actuated_area=1.0)
    ing.log_capacitance(_msg())
    ing.set_actuation(actuated_channels=[2, 3], actuated_area=2.0)   # next phase
    ing.log_capacitance(_msg())
    assert ing.entries[0]["actuated_channels"] == [1]
    assert ing.entries[1]["actuated_channels"] == [2, 3]


def test_log_capacitance_bare_numbers_and_invalid():
    ing = LoggingIngestion()
    ing.set_step(step_id="s", step_idx=1)
    assert ing.log_capacitance(_msg(cap="9.0", volt="50")) is True
    assert ing.entries[-1]["Capacitance (pF)"] == 9.0
    assert ing.log_capacitance(_msg(cap="-", volt="-")) is False   # skipped
    assert ing.log_capacitance("not json") is False


def test_log_capacitance_requires_step_set():
    ing = LoggingIngestion()
    assert ing.log_capacitance(_msg()) is False    # no step set yet


def test_log_capacitance_force_none_without_cpa():
    ing = LoggingIngestion()
    ing.set_step(step_id="s", step_idx=1)
    ing.set_actuation(actuated_channels=[1], actuated_area=1.0)
    assert ing.log_capacitance(_msg()) is True
    assert ing.entries[-1]["Force Over Unit Area (mN/mm^2)"] is None
