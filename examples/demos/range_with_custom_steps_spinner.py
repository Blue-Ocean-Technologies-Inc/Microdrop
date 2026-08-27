# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from traits.api import HasTraits
from traitsui.api import Item, View

from logger.logger_service import get_logger
from microdrop_utils.traitsui_qt_helpers import RangeWithSteppedSpinViewHint

logger = get_logger(__name__)

if __name__ == "__main__":
    # ---------------------------------------------------------
    # Example Usage
    # ---------------------------------------------------------
    class MyDeviceController(HasTraits):
        fine_voltage = RangeWithSteppedSpinViewHint(10, 1000000, step=1)
        coarse_voltage = RangeWithSteppedSpinViewHint(10, 1000000, step=10000, suffix=" V")

        traits_view = View(
            Item(
                "fine_voltage",
                label="Fine Tune (1 step)",
                # Use our custom editor with a 0.01 step
            ),
            Item(
                "coarse_voltage",
                label="Coarse Tune (5 step)",
                # Use our custom editor with a 0.5 step
            ),
            title="Custom Spinbox Step Example",
            width=300,
            resizable=True,
        )

    controller = MyDeviceController()
    controller.configure_traits()
