# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""No connected device is its own exception, so a monitor can tell the idle
state from a real failure; it is still an Exception for older callers."""

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils import hardware_device_monitoring_helpers as helpers


def test_no_connected_device_raises_device_not_found(monkeypatch):
    monkeypatch.setattr(helpers, "check_connected_ports_hwid", lambda hwid: [])

    with pytest.raises(helpers.DeviceNotFoundError):
        helpers.check_devices_available(["VID:PID=16C0:0483"])

    assert issubclass(helpers.DeviceNotFoundError, Exception)
