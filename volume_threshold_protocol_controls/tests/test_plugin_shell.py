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


def test_plugin_default_contributions_is_empty_until_task_6():
    """Column factory ships in Task 6. Scaffold must boot cleanly
    with no contributions so the rest of the plan can land in any
    order without breaking Envisage load."""
    p = VolumeThresholdProtocolControlsPlugin()
    assert isinstance(p.contributed_protocol_columns, list)
