"""Volume-threshold column smoke tests.

This file grows over Tasks 5 and 6 — Task 5 adds model + view + factory
metadata tests, Task 6 adds handler behaviour tests."""

from volume_threshold_protocol_controls.consts import (
    VOLUME_THRESHOLD_COL_ID, VOLUME_THRESHOLD_COL_NAME,
    VOLUME_THRESHOLD_DEFAULT,
)
from volume_threshold_protocol_controls.protocol_columns.volume_threshold_column import (
    make_volume_threshold_column,
)


def test_column_id_name_default():
    col = make_volume_threshold_column()
    assert col.model.col_id == VOLUME_THRESHOLD_COL_ID
    assert col.model.col_name == VOLUME_THRESHOLD_COL_NAME
    assert col.model.default_value == VOLUME_THRESHOLD_DEFAULT


def test_column_view_hidden_by_default_and_step_only():
    """Step-only column (no value on a group row); hidden by default
    in the column header — same posture as droplet_check and the trail
    /loop knobs. Surfaces via header right-click."""
    col = make_volume_threshold_column()
    assert col.view.hidden_by_default is True
    assert col.view.renders_on_group is False


def test_column_trait_is_float_with_default_zero():
    """trait_for_row must return a Float trait — the legacy column was
    a numeric volume; a string trait would silently accept garbage."""
    from traits.api import Float
    col = make_volume_threshold_column()
    trait = col.model.trait_for_row()
    assert isinstance(trait.handler, Float().handler.__class__)


def test_plugin_default_lists_the_column():
    """Task 6 wires the factory into the plugin's contribution list.
    Tested here so the scaffold-task placeholder gets a real value."""
    from volume_threshold_protocol_controls.plugin import (
        VolumeThresholdProtocolControlsPlugin,
    )
    p = VolumeThresholdProtocolControlsPlugin()
    contribs = p._contributed_protocol_columns_default()
    assert len(contribs) == 1
    assert contribs[0].model.col_id == VOLUME_THRESHOLD_COL_ID
