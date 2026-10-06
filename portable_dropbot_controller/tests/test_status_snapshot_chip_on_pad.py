# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The signal board reports chip_on_pad as a 3-bit contact mask (debounced
presence, left pogo, right pogo); the status snapshot publishes a chip only
when all three are set. Hardware-free, no Redis."""

# Standard library imports.
import json

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Dict

# Microdrop package imports.
from portable_dropbot_controller import portable_dropbot_controller_base
from portable_dropbot_controller.portable_dropbot_controller_base import (
    PortableDropbotControllerBase,
)


class _Harness(PortableDropbotControllerBase):
    #: What the driver's status read answers.
    status = Dict()

    def traits_init(self):
        pass

    def _proxy_call(self, context, call):
        return True, self.status

    def _publish_motors(self, mechanisms=None, poll=True):
        pass


@pytest.mark.parametrize(
    ("chip_on_pad", "expected"),
    [(0, False), (3, False), (5, False), (7, True)],
)
def test_chip_on_pad_needs_every_contact_bit(monkeypatch, chip_on_pad, expected):
    published = []
    monkeypatch.setattr(
        portable_dropbot_controller_base,
        "publish_message",
        lambda topic, message: published.append(json.loads(message)),
    )

    harness = _Harness()
    harness.status = {"signal": {"chip_on_pad": chip_on_pad}}

    harness._publish_status_snapshot()

    assert published == [{"chip_on_pad": expected}]
