import json
from pathlib import Path

from pluggable_protocol_tree.services.logging.persistence import LoggingPersistence


def test_to_columnar_orders_and_fills():
    entries = [{"a": 1, "b": 2}, {"a": 3}]
    out = LoggingPersistence.to_columnar(entries, ["a", "b"])
    assert out == {"columns": ["a", "b"], "data": [[1, 3], [2, None]]}


def test_correct_rollover_adds_2_32_on_decrease():
    # uint32 wraps at 2**32; a decreasing instrument_time means a wrap.
    vals = [10, 20, 5, 15]           # wrap between index 1 and 2
    out = LoggingPersistence._correct_rollover(vals)
    assert out == [10, 20, 5 + 2**32, 15 + 2**32]


def test_correct_rollover_handles_none():
    assert LoggingPersistence._correct_rollover([10, None, 20]) == [10, None, 20]


def test_write_data_files_writes_json_and_csv(tmp_path):
    entries = [
        {"step_idx": 0, "instrument_time_us": 100, "Capacitance (pF)": 1.0},
        {"step_idx": 0, "instrument_time_us": 200, "Capacitance (pF)": 2.0},
    ]
    cols = ["step_idx", "instrument_time_us", "Capacitance (pF)"]
    json_path, csv_path = LoggingPersistence.write_data_files(
        tmp_path, "20260525_120000", entries, cols)
    assert json_path.exists() and json_path.suffix == ".json"
    assert csv_path.exists() and csv_path.suffix == ".csv"
    payload = json.loads(json_path.read_text())
    assert payload["columns"] == cols
    assert json_path.parent.name == "data"
    import pandas as pd
    df = pd.read_csv(csv_path)
    assert df.columns.tolist() == cols
    assert len(df) == 2


def test_correct_rollover_multiple_consecutive_wraps():
    vals = [4294967290, 5, 4294967200, 1]   # wraps at idx 1 and idx 3
    out = LoggingPersistence._correct_rollover(vals)
    assert out == [4294967290, 5 + 2**32, 4294967200 + 2**32, 1 + 2 * 2**32]


def test_write_data_files_rollover_corrects_instrument_time(tmp_path):
    entries = [
        {"instrument_time_us": 4000000000},
        {"instrument_time_us": 10},          # wrapped
    ]
    cols = ["instrument_time_us"]
    json_path, _ = LoggingPersistence.write_data_files(
        tmp_path, "t", entries, cols)
    payload = json.loads(json_path.read_text())
    col = payload["data"][0]
    assert col == [4000000000, 10 + 2**32]
