"""Tests for the magnet compound column — model, custom view, factory."""

from unittest.mock import patch

from pyface.qt.QtCore import Qt
from traits.api import Bool, Float, HasTraits

from peripheral_controller.consts import (
    MIN_ZSTAGE_HEIGHT_MM, MAX_ZSTAGE_HEIGHT_MM,
)
from peripheral_protocol_controls.protocol_columns.magnet_column import (
    MagnetCompoundModel, MagnetHeightSpinBoxView, make_magnet_column,
)
from pluggable_protocol_tree.models.compound_column import (
    CompoundColumn,
)


def test_magnet_compound_model_field_specs():
    m = MagnetCompoundModel()
    specs = m.field_specs()
    assert [s.field_id for s in specs] == ["magnet_on", "magnet_height_mm"]
    assert [s.col_name for s in specs] == ["Magnet", "Magnet Height (mm)"]
    assert specs[0].default_value is False
    # Sentinel = MIN - 0.5 (the "Default" mode)
    assert specs[1].default_value == float(MIN_ZSTAGE_HEIGHT_MM - 0.5)


def test_magnet_compound_model_traits_are_bool_and_float():
    m = MagnetCompoundModel()
    enabled_trait = m.trait_for_field("magnet_on")
    height_trait = m.trait_for_field("magnet_height_mm")
    class Row(HasTraits):
        magnet_on = enabled_trait
        magnet_height_mm = height_trait
    r = Row()
    assert r.magnet_on is False
    assert r.magnet_height_mm == float(MIN_ZSTAGE_HEIGHT_MM - 0.5)
    r.magnet_on = True
    r.magnet_height_mm = 5.0
    assert r.magnet_on is True
    assert r.magnet_height_mm == 5.0


def test_magnet_height_view_displays_default_at_sentinel():
    """Below MIN_ZSTAGE_HEIGHT_MM is sentinel territory -> 'Default'."""
    v = MagnetHeightSpinBoxView(
        low=float(MIN_ZSTAGE_HEIGHT_MM - 0.5),
        high=float(MAX_ZSTAGE_HEIGHT_MM),
        decimals=2, single_step=0.1,
    )
    class Row(HasTraits):
        magnet_on = Bool(True)
    r = Row()
    assert v.format_display(0.0, r) == "Default"
    assert v.format_display(MIN_ZSTAGE_HEIGHT_MM - 0.1, r) == "Default"
    # >= MIN -> formatted float
    assert v.format_display(MIN_ZSTAGE_HEIGHT_MM, r) == "0.50"
    assert v.format_display(5.0, r) == "5.00"


def test_magnet_height_view_read_only_when_magnet_off():
    """Cross-cell editability via the canonical PPT-11 get_flags(row)
    pattern — height cell read-only when row.magnet_on is False."""
    v = MagnetHeightSpinBoxView(
        low=float(MIN_ZSTAGE_HEIGHT_MM - 0.5),
        high=float(MAX_ZSTAGE_HEIGHT_MM),
    )
    class Row(HasTraits):
        magnet_on = Bool(False)
        magnet_height_mm = Float(5.0)
    r = Row()
    flags = v.get_flags(r)
    assert not (flags & Qt.ItemIsEditable)


def test_magnet_height_view_editable_when_magnet_on():
    v = MagnetHeightSpinBoxView(
        low=float(MIN_ZSTAGE_HEIGHT_MM - 0.5),
        high=float(MAX_ZSTAGE_HEIGHT_MM),
    )
    class Row(HasTraits):
        magnet_on = Bool(True)
        magnet_height_mm = Float(5.0)
    r = Row()
    flags = v.get_flags(r)
    assert flags & Qt.ItemIsEditable


def test_make_magnet_column_returns_compound_with_two_fields():
    cc = make_magnet_column()
    assert isinstance(cc, CompoundColumn)
    ids = [s.field_id for s in cc.model.field_specs()]
    assert ids == ["magnet_on", "magnet_height_mm"]


import json
from unittest.mock import MagicMock

from peripheral_controller.consts import (
    PROTOCOL_SET_MAGNET, MAGNET_APPLIED,
)


def test_magnet_handler_priority_20():
    from peripheral_protocol_controls.protocol_columns.magnet_column import (
        MagnetHandler,
    )
    handler = MagnetHandler()
    assert handler.priority == 20


def test_magnet_handler_wait_for_topics_includes_magnet_applied():
    from peripheral_protocol_controls.protocol_columns.magnet_column import (
        MagnetHandler,
    )
    handler = MagnetHandler()
    assert MAGNET_APPLIED in handler.wait_for_topics


def test_magnet_handler_on_step_publishes_engage_payload():
    """magnet_on=True, magnet_height_mm=5.0 -> JSON
    {'on': True, 'height_mm': 5.0}; wait_for(MAGNET_APPLIED, timeout=10.0)."""
    from peripheral_protocol_controls.protocol_columns.magnet_column import (
        MagnetHandler,
    )
    handler = MagnetHandler()
    row = MagicMock()
    row.magnet_on = True
    row.magnet_height_mm = 5.0
    ctx = MagicMock()

    published = []
    with patch(
        "peripheral_protocol_controls.protocol_columns.magnet_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert len(published) == 1
    assert published[0]["topic"] == PROTOCOL_SET_MAGNET
    payload = json.loads(published[0]["message"])
    assert payload == {"on": True, "height_mm": 5.0}
    ctx.wait_for.assert_called_once_with(MAGNET_APPLIED, timeout=10.0)


def test_magnet_handler_on_step_publishes_retract_payload():
    """magnet_on=False -> JSON {'on': False, 'height_mm': X} (height
    included but ignored backend-side)."""
    from peripheral_protocol_controls.protocol_columns.magnet_column import (
        MagnetHandler,
    )
    handler = MagnetHandler()
    row = MagicMock()
    row.magnet_on = False
    row.magnet_height_mm = 0.0
    ctx = MagicMock()

    published = []
    with patch(
        "peripheral_protocol_controls.protocol_columns.magnet_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    payload = json.loads(published[0]["message"])
    assert payload == {"on": False, "height_mm": 0.0}


def test_magnet_handler_on_step_publishes_default_sentinel_payload():
    """magnet_on=True with sentinel height -> JSON has the sentinel
    value verbatim; backend interprets it (handler does NOT pre-resolve
    to the live pref)."""
    from peripheral_protocol_controls.protocol_columns.magnet_column import (
        MagnetHandler,
    )
    handler = MagnetHandler()
    row = MagicMock()
    row.magnet_on = True
    row.magnet_height_mm = float(MIN_ZSTAGE_HEIGHT_MM - 0.5)
    ctx = MagicMock()

    published = []
    with patch(
        "peripheral_protocol_controls.protocol_columns.magnet_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    payload = json.loads(published[0]["message"])
    assert payload["on"] is True
    assert payload["height_mm"] == float(MIN_ZSTAGE_HEIGHT_MM - 0.5)
