# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""ZoneTargetHandler.on_pre_step and the compound model, with the broker,
the zones snapshot and the detection reply faked — no Redis, no hardware."""

# Standard library imports.
import json

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Enum, HasTraits, Str

# Microdrop package imports.
from dropbot_controller.consts import DETECT_DROPLETS, DROPLETS_DETECTED
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.routes_column import (
    EXTRA_STATIC_ELECTRODES_KEY,
)
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.models.row_manager import RowManager
from zone_protocol_controls.consts import (
    ZONE_CRITERIA,
    ZONE_TARGET_CRITERION_FIELD_ID,
    ZONE_TARGET_FIELD_ID,
    ZoneCriterion,
)
from zone_protocol_controls.protocol_columns import zone_target_column
from zone_protocol_controls.protocol_columns.zone_target_column import (
    ZoneTargetCompoundModel,
    ZoneTargetHandler,
)

SNAPSHOT = {
    "storage": {
        "name": "storage",
        "color": "#f5e050",
        "regions": [
            {"id": "storage-1", "electrode_ids": ["a1"], "channels": [1]},
            {"id": "storage-2", "electrode_ids": ["b1", "b2"], "channels": [2, 3]},
        ],
    }
}

MAPPING = {"a1": 1, "b1": 2, "b2": 3}


class _FakeRow(HasTraits):
    zone_target = Str("storage")
    zone_target_criterion = Enum(*ZONE_CRITERIA)

    def dotted_path(self):
        return "1"


class _FakeProtocolCtx:
    def __init__(self, preview_mode=False):
        self.preview_mode = preview_mode
        self.scratch = {"electrode_to_channel": MAPPING}


class _FakeStepCtx:
    def __init__(self, reply=None, preview_mode=False):
        self.protocol = _FakeProtocolCtx(preview_mode)
        self.scratch = {}
        self.reply = reply
        self.waits = []

    def wait_for(self, topic, timeout=5.0, predicate=None):
        self.waits.append(topic)

        return json.dumps(self.reply)


@pytest.fixture
def published(monkeypatch):
    """Capture detection requests and report contributions; serve SNAPSHOT."""
    calls = []

    monkeypatch.setattr(
        zone_target_column,
        "publish_message",
        lambda topic, message: calls.append((topic, json.loads(message))),
    )
    monkeypatch.setattr(
        zone_target_column.protocol_logging_data_contribution_publisher,
        "publish",
        lambda payload: calls.append(("report", payload)),
    )
    monkeypatch.setattr(zone_target_column, "read_zones_snapshot", lambda: SNAPSHOT)

    return calls


def _reply(*channels, success=True, error=""):
    return {"success": success, "detected_channels": list(channels), "error": error}


def test_step_without_zone_target_requests_nothing(published):
    ctx = _FakeStepCtx()

    ZoneTargetHandler().on_pre_step(_FakeRow(zone_target=""), ctx)

    assert published == []
    assert ctx.waits == []
    assert EXTRA_STATIC_ELECTRODES_KEY not in ctx.scratch


def test_preview_mode_skips_detection(published):
    ctx = _FakeStepCtx(preview_mode=True)

    ZoneTargetHandler().on_pre_step(_FakeRow(), ctx)

    assert published == []
    assert EXTRA_STATIC_ELECTRODES_KEY not in ctx.scratch


def test_first_matching_region_is_added_to_the_step(published):
    ctx = _FakeStepCtx(reply=_reply(3))

    ZoneTargetHandler().on_pre_step(_FakeRow(), ctx)

    assert published[0] == (DETECT_DROPLETS, [1, 2, 3])
    assert ctx.waits == [DROPLETS_DETECTED]
    assert ctx.scratch[EXTRA_STATIC_ELECTRODES_KEY] == ["b1", "b2"]
    assert published[1] == (
        "report",
        {
            "Zone Target": "storage",
            "Zone Target Criterion": ZoneCriterion.HAS_DROPLET,
            "Zone Target Region": "storage-2",
        },
    )


def test_no_droplet_criterion_picks_the_first_free_region(published):
    ctx = _FakeStepCtx(reply=_reply(1))
    row = _FakeRow(zone_target_criterion=ZoneCriterion.NO_DROPLET)

    ZoneTargetHandler().on_pre_step(row, ctx)

    assert ctx.scratch[EXTRA_STATIC_ELECTRODES_KEY] == ["b1", "b2"]


def test_no_matching_region_fails_the_step(published):
    ctx = _FakeStepCtx(reply=_reply())

    with pytest.raises(RuntimeError, match="no region of zone type 'storage'"):
        ZoneTargetHandler().on_pre_step(_FakeRow(), ctx)

    assert EXTRA_STATIC_ELECTRODES_KEY not in ctx.scratch


def test_missing_zone_type_fails_before_detection(published):
    ctx = _FakeStepCtx()

    with pytest.raises(RuntimeError, match="not defined on the loaded device"):
        ZoneTargetHandler().on_pre_step(_FakeRow(zone_target="gone"), ctx)

    assert published == []


def test_detection_error_fails_the_step(published):
    ctx = _FakeStepCtx(reply=_reply(success=False, error="no proxy"))

    with pytest.raises(RuntimeError, match="no proxy"):
        ZoneTargetHandler().on_pre_step(_FakeRow(), ctx)


def test_model_loads_stale_values():
    model = ZoneTargetCompoundModel()

    assert model.deserialize(ZONE_TARGET_FIELD_ID, None) == ""
    assert model.deserialize(ZONE_TARGET_FIELD_ID, "gone") == "gone"
    assert (
        model.deserialize(ZONE_TARGET_CRITERION_FIELD_ID, "Maybe")
        == ZoneCriterion.HAS_DROPLET
    )
    assert (
        model.deserialize(ZONE_TARGET_CRITERION_FIELD_ID, ZoneCriterion.NO_DROPLET)
        == ZoneCriterion.NO_DROPLET
    )


def _build_columns():
    return [
        make_type_column(),
        make_id_column(),
        make_name_column(),
        *_expand_compound(zone_target_column.make_zone_target_column()),
    ]


def test_values_round_trip_through_the_protocol_file():
    rm = RowManager(columns=_build_columns())
    rm.add_step(
        values={
            "name": "S1",
            ZONE_TARGET_FIELD_ID: "deleted zone",
            ZONE_TARGET_CRITERION_FIELD_ID: ZoneCriterion.NO_DROPLET,
        }
    )
    rm.add_step(values={"name": "S2"})

    payload = json.loads(json.dumps(rm.to_json()))
    steps = RowManager.from_json(payload, columns=_build_columns()).root.children

    assert steps[0].zone_target == "deleted zone"
    assert steps[0].zone_target_criterion == ZoneCriterion.NO_DROPLET
    assert steps[1].zone_target == ""
    assert steps[1].zone_target_criterion == ZoneCriterion.HAS_DROPLET


def test_zone_picker_offers_the_snapshot_and_keeps_a_missing_value(published):
    from pyface.qt.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    view = zone_target_column.ZoneTypeComboBoxView()
    editor = view.create_editor(None, None)

    assert [editor.itemData(i) for i in range(editor.count())] == ["", "storage"]

    view.set_editor_data(editor, "storage")
    assert view.get_editor_data(editor) == "storage"

    view.set_editor_data(editor, "gone")
    assert view.get_editor_data(editor) == "gone"

    assert "storage-1, storage-2" in view.get_tooltip(_FakeRow())
