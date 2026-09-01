# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the magnet compound column — model, custom views, handler,
and factory. Hardware-free: publish_message is patched, no Redis/proxy
needed. GUI imports require QT_QPA_PLATFORM=offscreen."""

import json
from unittest.mock import MagicMock, patch

from pyface.qt.QtCore import Qt
from traits.api import Bool, Float, HasTraits

from pluggable_protocol_tree.models.compound_column import CompoundColumn
from portable_dropbot_controller.consts import (
    MAGNET_APPLIED,
    MAGNET_HEIGHT_MM_BOUNDS,
    PROTOCOL_SET_MAGNET,
)
from portable_dropbot_protocol_controls.consts import SET_MAGNET_FIELD_ID
from portable_dropbot_protocol_controls.protocol_columns.magnet_column import (
    MagnetCompoundModel,
    MagnetHandler,
    MagnetHeightSpinBoxView,
    MagnetOnCheckboxView,
    make_magnet_column,
)

_SENTINEL = float(MAGNET_HEIGHT_MM_BOUNDS[0] - 0.5)


def test_magnet_compound_model_field_specs():
    m = MagnetCompoundModel()
    specs = m.field_specs()
    assert [s.field_id for s in specs] == [
        SET_MAGNET_FIELD_ID,
        "magnet_on",
        "magnet_height_mm",
    ]
    assert [s.col_name for s in specs] == [
        "Set Magnet",
        "Magnet",
        "Magnet Height (mm)",
    ]
    assert specs[0].default_value is False
    assert specs[1].default_value is False
    # Sentinel = MIN - 0.5 (the "Default" mode)
    assert specs[2].default_value == _SENTINEL


def test_magnet_compound_model_traits_are_bool_and_float():
    m = MagnetCompoundModel()
    enabled_trait = m.trait_for_field("magnet_on")
    height_trait = m.trait_for_field("magnet_height_mm")

    class Row(HasTraits):
        magnet_on = enabled_trait
        magnet_height_mm = height_trait

    r = Row()
    assert r.magnet_on is False
    assert r.magnet_height_mm == _SENTINEL
    r.magnet_on = True
    r.magnet_height_mm = 5.0
    assert r.magnet_on is True
    assert r.magnet_height_mm == 5.0


def test_magnet_compound_model_trait_for_field_unknown_raises():
    m = MagnetCompoundModel()
    try:
        m.trait_for_field("nope")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for unknown field_id")


def test_magnet_height_view_displays_default_at_sentinel():
    """Below MAGNET_HEIGHT_MM_BOUNDS[0] is sentinel territory -> 'Default'."""
    v = MagnetHeightSpinBoxView(
        low=_SENTINEL,
        high=float(MAGNET_HEIGHT_MM_BOUNDS[1]),
        decimals=2,
        single_step=0.1,
    )

    class Row(HasTraits):
        magnet_on = Bool(True)

    r = Row()
    assert v.format_display(0.0, r) == "Default"
    assert v.format_display(MAGNET_HEIGHT_MM_BOUNDS[0] - 0.1, r) == "Default"
    # >= MIN -> formatted float
    assert v.format_display(MAGNET_HEIGHT_MM_BOUNDS[0], r) == "0.50"
    assert v.format_display(5.0, r) == "5.00"


def test_magnet_height_view_read_only_when_magnet_off():
    """Cross-cell editability via the canonical PPT-11 get_flags(row)
    pattern — height cell read-only when row.magnet_on is False."""
    v = MagnetHeightSpinBoxView(low=_SENTINEL, high=float(MAGNET_HEIGHT_MM_BOUNDS[1]))

    class Row(HasTraits):
        set_magnet = Bool(True)
        magnet_on = Bool(False)
        magnet_height_mm = Float(5.0)

    r = Row()
    flags = v.get_flags(r)
    assert not (flags & Qt.ItemIsEditable)


def test_magnet_height_view_editable_when_magnet_on():
    v = MagnetHeightSpinBoxView(low=_SENTINEL, high=float(MAGNET_HEIGHT_MM_BOUNDS[1]))

    class Row(HasTraits):
        set_magnet = Bool(True)
        magnet_on = Bool(True)
        magnet_height_mm = Float(5.0)

    r = Row()
    flags = v.get_flags(r)
    assert flags & Qt.ItemIsEditable


def test_cells_locked_until_set_magnet_checked():
    """set_magnet off = the engage checkbox is not checkable and the
    height cell is read-only even with magnet_on True."""
    height_view = MagnetHeightSpinBoxView(
        low=_SENTINEL, high=float(MAGNET_HEIGHT_MM_BOUNDS[1])
    )
    on_view = MagnetOnCheckboxView()

    class Row(HasTraits):
        set_magnet = Bool(False)
        magnet_on = Bool(True)
        magnet_height_mm = Float(5.0)

    r = Row()
    assert not (height_view.get_flags(r) & Qt.ItemIsEditable)
    assert not (on_view.get_flags(r) & Qt.ItemIsUserCheckable)
    r.set_magnet = True
    assert on_view.get_flags(r) & Qt.ItemIsUserCheckable


def test_make_magnet_column_returns_compound_with_three_fields():
    cc = make_magnet_column()
    assert isinstance(cc, CompoundColumn)
    ids = [s.field_id for s in cc.model.field_specs()]
    assert ids == [SET_MAGNET_FIELD_ID, "magnet_on", "magnet_height_mm"]


def test_magnet_handler_priority_20():
    handler = MagnetHandler()
    assert handler.priority == 20


def test_magnet_handler_wait_for_topics_includes_magnet_applied():
    handler = MagnetHandler()
    assert MAGNET_APPLIED in handler.wait_for_topics


def test_magnet_handler_default_ack_time_is_40s():
    """The portable's magnet Z move blocks up to ~30s in the driver, so
    the provider default needs real headroom beyond an RPC round-trip."""
    handler = MagnetHandler()
    assert handler.default_ack_time_s == 40.0
    assert handler.ack_time_s == 40.0


def test_magnet_handler_on_step_publishes_engage_payload():
    """magnet_on=True, magnet_height_mm=5.0 -> JSON
    {'on': True, 'height_mm': 5.0}; wait_for(MAGNET_APPLIED, timeout=40.0)."""
    handler = make_magnet_column().handler
    row = MagicMock()
    row.set_magnet = True
    row.magnet_on = True
    row.magnet_height_mm = 5.0
    ctx = MagicMock()
    ctx.protocol.preview_mode = False

    published = []
    with patch(
        "portable_dropbot_protocol_controls.protocol_columns.magnet_column"
        ".publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert len(published) == 1
    assert published[0]["topic"] == PROTOCOL_SET_MAGNET
    payload = json.loads(published[0]["message"])
    assert payload == {"on": True, "height_mm": 5.0}
    ctx.wait_for.assert_called_once_with(MAGNET_APPLIED, timeout=40.0)


def test_magnet_handler_skips_ack_wait_when_ack_time_zero():
    """ack_time_s=0 (the grid's "don't wait") still publishes the magnet
    state but does NOT block on the hardware ack."""
    handler = make_magnet_column().handler
    handler.ack_time_s = 0.0
    row = MagicMock()
    row.set_magnet = True
    row.magnet_on = True
    row.magnet_height_mm = 5.0
    ctx = MagicMock()
    ctx.protocol.preview_mode = False

    published = []
    with patch(
        "portable_dropbot_protocol_controls.protocol_columns.magnet_column"
        ".publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert len(published) == 1  # still publishes the state
    ctx.wait_for.assert_not_called()  # but does not block on ack


def test_magnet_handler_on_step_publishes_disengage_payload():
    """magnet_on=False -> JSON {'on': False, 'height_mm': X} (height
    included but ignored backend-side)."""
    handler = MagnetHandler()
    row = MagicMock()
    row.set_magnet = True
    row.magnet_on = False
    row.magnet_height_mm = 0.0
    ctx = MagicMock()
    ctx.protocol.preview_mode = False

    published = []
    with patch(
        "portable_dropbot_protocol_controls.protocol_columns.magnet_column"
        ".publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    payload = json.loads(published[0]["message"])
    assert payload == {"on": False, "height_mm": 0.0}


def test_magnet_handler_on_step_publishes_default_sentinel_payload():
    """magnet_on=True with sentinel height -> JSON has the sentinel
    value verbatim; backend interprets it (handler does NOT pre-resolve
    it to an absolute position)."""
    handler = MagnetHandler()
    row = MagicMock()
    row.set_magnet = True
    row.magnet_on = True
    row.magnet_height_mm = _SENTINEL
    ctx = MagicMock()
    ctx.protocol.preview_mode = False

    published = []
    with patch(
        "portable_dropbot_protocol_controls.protocol_columns.magnet_column"
        ".publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    payload = json.loads(published[0]["message"])
    assert payload["on"] is True
    assert payload["height_mm"] == _SENTINEL


def test_magnet_handler_unchecked_step_leaves_magnet_untouched():
    """set_magnet off = no engage/disengage publish and no ack wait."""
    handler = make_magnet_column().handler
    row = MagicMock()
    row.set_magnet = False
    row.magnet_on = True
    row.magnet_height_mm = 5.0
    ctx = MagicMock()
    ctx.protocol.preview_mode = False

    published = []
    with patch(
        "portable_dropbot_protocol_controls.protocol_columns.magnet_column"
        ".publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert published == []
    ctx.wait_for.assert_not_called()


def test_magnet_handler_preview_mode_skips_publish_and_wait():
    handler = make_magnet_column().handler
    row = MagicMock()
    row.set_magnet = True
    row.magnet_on = True
    row.magnet_height_mm = 5.0
    ctx = MagicMock()
    ctx.protocol.preview_mode = True

    published = []
    with patch(
        "portable_dropbot_protocol_controls.protocol_columns.magnet_column"
        ".publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert published == []
    ctx.wait_for.assert_not_called()
