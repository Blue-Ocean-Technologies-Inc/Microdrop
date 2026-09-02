# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for the Qt-free electrode zones model."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
# Microdrop package imports.
from device_viewer.consts import ZONES_KEY
from device_viewer.default_settings import alpha_keys, default_alphas, zones_key

BUNDLED_2X3 = (
    Path(__file__).resolve().parents[1] / "resources" / "devices" / "2x3device.svg"
)


def test_zones_alpha_key_registered():
    assert zones_key == "Zones"
    assert zones_key in alpha_keys
    assert default_alphas[zones_key] == 100
    assert ZONES_KEY == "microdrop.device.zones"
