"""Tests for the droplet-check column — model factory, view class
attributes, handler declarations. Handler behavior (publish + wait_for)
is in test_droplet_check_handler.py."""

import pytest
from traits.api import HasTraits

from pluggable_protocol_tree.models.column import Column

from dropbot_controller.consts import DROPLETS_DETECTED
from dropbot_protocol_controls.consts import DROPLET_CHECK_DECISION_RESPONSE
from dropbot_protocol_controls.protocol_columns.droplet_check_column import (
    DropletCheckColumnModel,
    DropletCheckColumnView,
    DropletCheckHandler,
    make_droplet_check_column,
)


def test_make_droplet_check_column_returns_column_with_check_droplets_id():
    col = make_droplet_check_column()
    assert isinstance(col, Column)
    assert col.model.col_id == "check_droplets"
    assert col.model.col_name == "Check Droplets"


def test_default_value_is_true():
    model = DropletCheckColumnModel()
    assert model.default_value is True


def test_trait_for_row_returns_bool_trait_with_true_default():
    # The trait that goes onto each row's dynamic class.
    model = DropletCheckColumnModel()
    trait = model.trait_for_row()
    # Build a tiny class that uses the trait, instantiate, check default.
    Row = type("Row", (HasTraits,), {"check_droplets": trait})
    row = Row()
    assert row.check_droplets is True


def test_serialize_and_deserialize_roundtrip_true_and_false():
    model = DropletCheckColumnModel()
    assert model.serialize(True)  is True
    assert model.serialize(False) is False
    assert model.deserialize(True)  is True
    assert model.deserialize(False) is False


def test_view_class_attributes():
    view = DropletCheckColumnView()
    assert view.hidden_by_default is True   # follows trail/loop precedent
    assert view.renders_on_group  is False


def test_handler_priority_is_80_post_step_late():
    # Priority 80 — droplet check is the only on_post_step hook today,
    # so 80 is conventional rather than load-bearing. (Lower priorities
    # like routes(30) are on_step hooks, not on_post_step — different
    # bucket.) See spec § 4.
    handler = DropletCheckHandler()
    assert handler.priority == 80


def test_handler_declares_both_response_topics_in_wait_for():
    handler = DropletCheckHandler()
    assert DROPLETS_DETECTED in handler.wait_for_topics
    assert DROPLET_CHECK_DECISION_RESPONSE in handler.wait_for_topics


def test_factory_wires_model_view_handler_together():
    col = make_droplet_check_column()
    assert isinstance(col.model,   DropletCheckColumnModel)
    assert isinstance(col.view,    DropletCheckColumnView)
    assert isinstance(col.handler, DropletCheckHandler)
