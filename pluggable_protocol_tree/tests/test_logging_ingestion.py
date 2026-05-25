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
