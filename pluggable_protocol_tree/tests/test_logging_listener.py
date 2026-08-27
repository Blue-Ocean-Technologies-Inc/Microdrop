# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

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
    from pluggable_protocol_tree.consts import ACTOR_TOPIC_DICT, LOGGING_LISTENER_NAME
    from dropbot_controller.consts import CAPACITANCE_UPDATED
    topics = ACTOR_TOPIC_DICT[LOGGING_LISTENER_NAME]
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
    from pluggable_protocol_tree.consts import ACTOR_TOPIC_DICT, LOGGING_LISTENER_NAME
    from device_viewer.consts import CALIBRATION_DATA
    assert CALIBRATION_DATA in ACTOR_TOPIC_DICT[LOGGING_LISTENER_NAME]


def test_route_contribution_topics_dispatch():
    from pluggable_protocol_tree.consts import (
        PROTOCOL_LOGGING_DATA_CONTRIBUTION,
        PROTOCOL_LOGGING_METADATA_CONTRIBUTION,
    )

    class _ContribSink:
        def __init__(self):
            self.calls = []
        def on_metadata_contribution(self, m): self.calls.append(("meta", m))
        def on_data_contribution(self, m): self.calls.append(("data", m))

    sink = _ContribSink()
    L.set_active_logger(sink)
    try:
        L.route_to_active_logger(PROTOCOL_LOGGING_METADATA_CONTRIBUTION, "metamsg")
        L.route_to_active_logger(PROTOCOL_LOGGING_DATA_CONTRIBUTION, "datamsg")
    finally:
        L.clear_active_logger()
    assert sink.calls == [("meta", "metamsg"), ("data", "datamsg")]


def test_contribution_topics_registered_in_consts():
    from pluggable_protocol_tree.consts import (
        ACTOR_TOPIC_DICT, LOGGING_LISTENER_NAME,
        PROTOCOL_LOGGING_DATA_CONTRIBUTION,
        PROTOCOL_LOGGING_METADATA_CONTRIBUTION,
    )
    topics = ACTOR_TOPIC_DICT[LOGGING_LISTENER_NAME]
    assert PROTOCOL_LOGGING_METADATA_CONTRIBUTION in topics
    assert PROTOCOL_LOGGING_DATA_CONTRIBUTION in topics
