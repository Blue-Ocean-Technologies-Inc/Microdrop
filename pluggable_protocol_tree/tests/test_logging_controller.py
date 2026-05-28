import json

from pluggable_protocol_tree.services.logging.controller import ProtocolLoggingController
from pluggable_protocol_tree.services.logging.models import LoggingDeviceContext
import pluggable_protocol_tree.services.logging.listener as L


class _FakeRow:
    uuid = "row-uuid"
    name = "Step A"
    path = (0,)


def _ctx(tmp_path):
    return LoggingDeviceContext(
        experiment_directory=tmp_path,
        device_svg_path=None,
        channel_areas={5: 2.0, 6: 3.0},
        capacitance_per_unit_area=2.0,
    )


def _immediate(controller):
    controller._flush()


def test_start_logging_preview_is_noop(tmp_path):
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=True)
    assert c._ingestion is None
    assert L.get_active_logger() is None


def test_actuation_area_summed_from_channel_areas(tmp_path):
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    c._on_step_started(_FakeRow())
    c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [5, 6]}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    e = c._ingestion.entries[-1]
    assert e["Actuated Area (mm^2)"] == 5.0      # 2.0 + 3.0
    assert e["actuated_channels"] == [5, 6]
    c.stop_logging()


def test_flush_writes_artifacts_and_clears_sink(tmp_path):
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    assert L.get_active_logger() is c
    c._on_step_started(_FakeRow())
    c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [5]}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    c.stop_logging()
    assert list((tmp_path / "data").glob("data_*.json"))
    assert list((tmp_path / "data").glob("data_*.csv"))
    assert list((tmp_path / "reports").glob("report_*.html"))
    assert L.get_active_logger() is None


def test_on_actuation_ignores_non_dict_json(tmp_path):
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    c._on_step_started(_FakeRow())
    c.on_actuation("[1, 2, 3]")        # valid JSON, but a list -> must not raise
    c.on_actuation("not json")          # malformed -> must not raise
    # capacitance still logs with whatever actuation state exists (empty)
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    assert c._ingestion.entries[-1]["actuated_channels"] == []
    c.stop_logging()


def _ctx_no_cpa(tmp_path):
    return LoggingDeviceContext(
        experiment_directory=tmp_path, device_svg_path=None,
        channel_areas={5: 2.0}, capacitance_per_unit_area=None)


def test_on_calibration_populates_force(tmp_path):
    """CALIBRATION_DATA → capacitance-per-unit-area = liquid - filler, so
    subsequent capacitance rows get a real force (legacy parity)."""
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx_no_cpa(tmp_path), n_steps=1, preview_mode=False)
    c._on_step_started(_FakeRow())
    c.on_calibration(json.dumps({"liquid_capacitance_over_area": 5.0,
                                 "filler_capacitance_over_area": 3.0}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    # cpa = 5 - 3 = 2.0 ; force = 0.5 * 2 * 100^2
    assert c._ingestion.entries[-1]["Force Over Unit Area (mN/mm^2)"] == \
        round(0.5 * 2.0 * 100.0 ** 2, 6)
    c.stop_logging()


def test_on_calibration_ignores_invalid_liquid_le_filler(tmp_path):
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx_no_cpa(tmp_path), n_steps=1, preview_mode=False)
    c._on_step_started(_FakeRow())
    c.on_calibration(json.dumps({"liquid_capacitance_over_area": 2.0,
                                 "filler_capacitance_over_area": 5.0}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    assert c._ingestion.entries[-1]["Force Over Unit Area (mN/mm^2)"] is None
    c.stop_logging()


def test_attach_only_wires_step_started():
    """attach must wire ONLY step_started — start/stop are pane-driven so a
    whole-protocol repeat run is one log, not stopped after rep 1."""
    class _FakeSig:
        def __init__(self):
            self.slots = []
        def connect(self, fn):
            self.slots.append(fn)

    class _FakeQSignals:
        def __init__(self):
            self.step_started = _FakeSig()
            self.protocol_finished = _FakeSig()
            self.protocol_aborted = _FakeSig()
            self.protocol_error = _FakeSig()

    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=lambda ctrl: None)
    q = _FakeQSignals()
    c.attach(q)
    assert len(q.step_started.slots) == 1
    assert q.protocol_finished.slots == []
    assert q.protocol_aborted.slots == []
    assert q.protocol_error.slots == []


def test_logging_spans_multiple_reps_one_log(tmp_path):
    """One start_logging + many step_started (across simulated reps) + one
    stop_logging => a single artifact set with continuous step_idx."""
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=2, preview_mode=False)
    for _ in range(4):                       # 2 steps x 2 reps
        c._on_step_started(_FakeRow())
        c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [5]}))
        c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                     "instrument_time_us": 1, "reception_time": 2}))
    # not stopped between reps -> all four samples in one ingestion
    assert len(c._ingestion.entries) == 4
    step_idxs = [e["step_idx"] for e in c._ingestion.entries]
    assert step_idxs == [1, 2, 3, 4]         # continuous across reps
    c.stop_logging()
    assert list((tmp_path / "data").glob("data_*.json"))


def test_stop_logging_generate_report_false_writes_data_no_report(tmp_path):
    captured = []
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate,
                                  completion_callback=captured.append)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    c._on_step_started(_FakeRow())
    c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [5]}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    c.stop_logging(generate_report=False)
    assert list((tmp_path / "data").glob("data_*.json"))
    assert not list((tmp_path / "reports").glob("report_*.html"))
    assert captured == [None]


def test_stop_logging_generate_report_true_invokes_callback_with_path(tmp_path):
    captured = []
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate,
                                  completion_callback=captured.append)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    c._on_step_started(_FakeRow())
    c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [5]}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    c.stop_logging()            # generate_report defaults True
    assert len(captured) == 1 and captured[0] is not None
    assert captured[0].name.startswith("report_")


def test_stop_logging_overwrites_steps_metadata_with_actual_count(tmp_path):
    """The 'Steps' metadata row seeded as '0 / n' must be overwritten with
    the real completed-step count (self._step_idx) on stop, so the report's
    Metadata section doesn't show 0/n forever."""
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=3, preview_mode=False)
    assert c._ingestion.metadata["Steps"] == "0 / 3"
    c._on_step_started(_FakeRow())
    c._on_step_started(_FakeRow())                # 2 of 3 steps actually ran
    # Snapshot metadata BEFORE stop (which clears self._ingestion); the
    # report builder will read the same dict from ing.metadata at flush time.
    metadata = c._ingestion.metadata
    c.stop_logging()
    assert metadata["Steps"] == "2 / 3"
    assert "Completed Steps" not in metadata


def test_stop_logging_adds_start_stop_elapsed_time_metadata(tmp_path):
    """Legacy parity: the report metadata table includes Start Time, Stop
    Time, and Elapsed Time once a run stops."""
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    c._on_step_started(_FakeRow())
    meta = c._ingestion.metadata
    c.stop_logging()
    for key in ("Start Time", "Stop Time", "Elapsed Time"):
        assert key in meta
    assert meta["Elapsed Time"].count(":") == 2          # "H:MM:SS"


def test_flush_drains_app_globals_media_captures_into_ingestion(tmp_path, monkeypatch):
    """Mirror legacy parity: the camera widget caches captures into
    app_globals["media_captures"] but doesn't publish the topic our
    listener subscribes to. The controller must drain the bucket at
    flush time so the report's Media Captures section sees them."""
    from pluggable_protocol_tree.services.logging import controller as ctrl_mod

    # In-memory stand-in for the Redis-backed app_globals dict.
    fake_globals = {}
    monkeypatch.setattr(ctrl_mod, "_get_app_globals", lambda: fake_globals)

    img_path = tmp_path / "captures" / "img.png"
    vid_path = tmp_path / "captures" / "vid.mkv"
    img_path.parent.mkdir(parents=True)
    img_path.write_bytes(b"")
    vid_path.write_bytes(b"")
    # Each entry is a JSON-serialised MediaCaptureMessageModel — same shape
    # the camera widget's _cache_media_capture actor stores.
    seed = [
        '{"path":"' + str(img_path).replace("\\", "/") + '","type":"image"}',
        '{"path":"' + str(vid_path).replace("\\", "/") + '","type":"video"}',
    ]

    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    # start_logging cleared the bucket — seed it after start, the same way
    # captures land asynchronously during a real run.
    fake_globals["media_captures"] = list(seed)
    assert fake_globals["media_captures"] == seed
    # Snapshot the ingestion media dict before flush clears the ingestion.
    media = c._ingestion.media
    c._on_step_started(_FakeRow())
    c.stop_logging()
    assert str(img_path) in media["image"][0]
    assert str(vid_path) in media["video"][0]


def test_start_logging_resets_app_globals_media_bucket(tmp_path, monkeypatch):
    """Each run's report must only show that run's captures — start_logging
    clears the shared bucket before the run begins."""
    from pluggable_protocol_tree.services.logging import controller as ctrl_mod
    fake_globals = {"media_captures": ["leftover-from-previous-run"]}
    monkeypatch.setattr(ctrl_mod, "_get_app_globals", lambda: fake_globals)

    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    assert fake_globals["media_captures"] == []


def test_log_metadata_forwards_to_ingestion_and_is_noop_without(tmp_path):
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    c.log_metadata({"Protocol Path": "<a>x</a>"})
    assert c._ingestion.metadata["Protocol Path"] == "<a>x</a>"
    c._ingestion = None
    c.log_metadata({"k": "v"})                   # must not raise
