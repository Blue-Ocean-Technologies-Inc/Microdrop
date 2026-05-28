import pluggable_protocol_tree.services.logging.listener as L


class _Sink:
    def __init__(self):
        self.calls = []
    def on_capacitance(self, m): self.calls.append(("cap", m))
    def on_actuation(self, m): self.calls.append(("act", m))
    def on_media(self, m): self.calls.append(("media", m))


def test_route_to_active_sink_dispatches_by_topic():
    from dropbot_controller.consts import CAPACITANCE_UPDATED
    from pluggable_protocol_tree.consts import ELECTRODES_STATE_CHANGE
    from device_viewer.consts import DEVICE_VIEWER_MEDIA_CAPTURED
    sink = _Sink()
    L.set_active_logger(sink)
    try:
        L.route_to_active_logger(CAPACITANCE_UPDATED, "capmsg")
        L.route_to_active_logger(ELECTRODES_STATE_CHANGE, "actmsg")
        L.route_to_active_logger(DEVICE_VIEWER_MEDIA_CAPTURED, "mediamsg")
    finally:
        L.clear_active_logger()
    assert sink.calls == [("cap", "capmsg"), ("act", "actmsg"), ("media", "mediamsg")]


def test_route_with_no_active_logger_is_noop():
    L.clear_active_logger()
    L.route_to_active_logger("any/topic", "x")   # must not raise


def test_logging_topics_registered_in_consts():
    from pluggable_protocol_tree.consts import LOGGING_ACTOR_TOPIC_DICT, LOGGING_LISTENER_NAME
    from dropbot_controller.consts import CAPACITANCE_UPDATED
    topics = LOGGING_ACTOR_TOPIC_DICT[LOGGING_LISTENER_NAME]
    assert CAPACITANCE_UPDATED in topics


def test_route_calibration_dispatches_to_on_calibration():
    from device_viewer.consts import CALIBRATION_DATA

    class _CalSink:
        def __init__(self):
            self.got = None
        def on_calibration(self, m):
            self.got = m
    sink = _CalSink()
    L.set_active_logger(sink)
    try:
        L.route_to_active_logger(CALIBRATION_DATA, "calmsg")
    finally:
        L.clear_active_logger()
    assert sink.got == "calmsg"


def test_calibration_topic_registered_in_consts():
    from pluggable_protocol_tree.consts import LOGGING_ACTOR_TOPIC_DICT, LOGGING_LISTENER_NAME
    from device_viewer.consts import CALIBRATION_DATA
    assert CALIBRATION_DATA in LOGGING_ACTOR_TOPIC_DICT[LOGGING_LISTENER_NAME]
