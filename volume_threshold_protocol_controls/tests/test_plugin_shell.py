"""Plugin scaffold smoke tests."""

import volume_threshold_protocol_controls
from volume_threshold_protocol_controls.consts import PKG, PKG_name
from volume_threshold_protocol_controls.plugin import (
    VolumeThresholdProtocolControlsPlugin,
)


def test_package_importable():
    assert volume_threshold_protocol_controls is not None


def test_consts_derived_from_package_name():
    assert PKG == "volume_threshold_protocol_controls"
    assert PKG_name == "Volume Threshold Protocol Controls"


def test_plugin_id_and_name():
    p = VolumeThresholdProtocolControlsPlugin()
    assert p.id == "volume_threshold_protocol_controls.plugin"
    assert p.name == "Volume Threshold Protocol Controls Plugin"


def test_plugin_default_contributions_lists_volume_threshold_column():
    """Task 5 wired the column factory into the plugin's contributions."""
    from volume_threshold_protocol_controls.consts import (
        VOLUME_THRESHOLD_COL_ID,
    )
    p = VolumeThresholdProtocolControlsPlugin()
    contribs = p.contributed_protocol_columns
    assert len(contribs) == 1
    assert contribs[0].model.col_id == VOLUME_THRESHOLD_COL_ID
