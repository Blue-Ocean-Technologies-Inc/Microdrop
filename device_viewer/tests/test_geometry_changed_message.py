"""Tests for GeometryChangedMessage Pydantic model + topic constant."""

from device_viewer.consts import (
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    ACTOR_TOPIC_DICT,
    listener_name,
)
from device_viewer.models.messages import GeometryChangedMessage


def test_topic_constant_value():
    assert DEVICE_VIEWER_GEOMETRY_CHANGED == "ui/device_viewer/geometry_changed"


def test_dv_does_not_subscribe_to_its_own_geometry_publishes():
    """The DV publishes DEVICE_VIEWER_GEOMETRY_CHANGED but does not
    consume it. Subscribing would create a no-op handler-not-found
    log on every chip-insert. The pluggable_protocol_tree controller
    is the only consumer (via SYNC_ACTOR_TOPIC_DICT)."""
    assert DEVICE_VIEWER_GEOMETRY_CHANGED not in ACTOR_TOPIC_DICT[listener_name]


def test_round_trip():
    msg = GeometryChangedMessage(id_to_channel={"e00": 0, "e01": 1, "e02": None})
    rt = GeometryChangedMessage.deserialize(msg.serialize())
    assert rt.id_to_channel == {"e00": 0, "e01": 1, "e02": None}


def test_empty_mapping_round_trip():
    msg = GeometryChangedMessage(id_to_channel={})
    rt = GeometryChangedMessage.deserialize(msg.serialize())
    assert rt.id_to_channel == {}
