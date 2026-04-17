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
