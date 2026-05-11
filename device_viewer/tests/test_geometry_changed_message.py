"""Tests for GeometryChangedMessage Pydantic model + topic constant."""

from device_viewer.consts import (
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    ACTOR_TOPIC_DICT,
    listener_name,
)
from device_viewer.models.messages import GeometryChangedMessage


def test_topic_constant_value():
    assert DEVICE_VIEWER_GEOMETRY_CHANGED == "ui/device_viewer/geometry_changed"


def test_topic_in_actor_topic_dict():
    assert DEVICE_VIEWER_GEOMETRY_CHANGED in ACTOR_TOPIC_DICT[listener_name]


def test_round_trip():
    msg = GeometryChangedMessage(id_to_channel={"e00": 0, "e01": 1, "e02": None})
    rt = GeometryChangedMessage.deserialize(msg.serialize())
    assert rt.id_to_channel == {"e00": 0, "e01": 1, "e02": None}


def test_empty_mapping_round_trip():
    msg = GeometryChangedMessage(id_to_channel={})
    rt = GeometryChangedMessage.deserialize(msg.serialize())
    assert rt.id_to_channel == {}
