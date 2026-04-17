from PySide6.QtGui import QPixmap, Qt
from PySide6.QtWidgets import QLabel, QSizePolicy
from pyface.qt import QtWidgets
from traits.api import Int, Property, HasTraits, Range, Str
from traitsui.api import Item, View
from traitsui.basic_editor_factory import BasicEditorFactory
from traitsui.qt.editor import Editor as QtEditor

from dropbot_status_and_controls.consts import BORDER_RADIUS
from logger.logger_service import get_logger

logger = get_logger(__name__)


class _ScalingPixmapLabel(QLabel):
    """QLabel that auto-scales its pixmap to fill available space on resize.

    Uses ``Ignored`` vertical policy so the grid sibling drives the
    HGroup height.  On every resize the max-width is clamped to the
    current height, keeping the icon square.
    """

    def __init__(self):
        super().__init__()
        self._source_pixmap = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Ignored vertically → the grid determines the row height.
        # Preferred horizontally → width is governed by maxWidth set in resizeEvent.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(120, 120)
        self.setStyleSheet("padding: 5px;")
    def set_source_pixmap(self, pixmap):
        self._source_pixmap = pixmap
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep the icon square: max width tracks the actual height
        h = self.height()
        self.setMaximumWidth(h)
        self._rescale()

    def _rescale(self):
        if not self._source_pixmap.isNull():
            scaled = self._source_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)


class StatusIconEditor(QtEditor):
    """Custom TraitsUI editor that displays a DropBot icon with colored background.

    The editor value is bound to `icon_path` (str path to the image).
    It also observes `icon_color` on the model to update the background color.
    """

    def init(self, parent):
        self.control = _ScalingPixmapLabel()

        # Load initial image
        self._load_pixmap(self.value)

        # Observe icon_color on the model for background color updates
        self.object.observe(self._on_icon_color_changed, "icon_color")
        self._apply_background_color(self.object.icon_color)

    def _load_pixmap(self, path):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            logger.error(f"Failed to load image: {path}")
        self.control.set_source_pixmap(pixmap)

    def _apply_background_color(self, color):
        self.control.setStyleSheet(
            f"background-color: {color}; border-radius: {BORDER_RADIUS}px;"
        )

    def _on_icon_color_changed(self, event):
        self._apply_background_color(event.new)

    def update_editor(self):
        """Called when icon_path trait changes."""
        self._load_pixmap(self.value)

    def dispose(self):
        self.object.observe(self._on_icon_color_changed, "icon_color", remove=True)
        super().dispose()


class StatusIconEditorFactory(BasicEditorFactory):
    klass = StatusIconEditor

# ---------------------------------------------------------
# 1. The Qt Backend Editor
# ---------------------------------------------------------
class _SteppedSpinEditor(QtEditor):
    """The actual Qt implementation of the spin box."""

    def init(self, parent):
        """Initializes the editor by creating the underlying toolkit widget."""
        # Use QDoubleSpinBox for floats. (Use QSpinBox for ints).
        self.control = QtWidgets.QSpinBox()

        # Configure range bounds from the factory
        self.control.setMinimum(self.factory.low)
        self.control.setMaximum(self.factory.high)

        if self.factory.suffix:
            self.control.setSuffix(self.factory.suffix)

        self.control.setSingleStep(self.factory.step)

        # Connect the Qt signal to update the Trait value
        self.control.valueChanged.connect(self.update_object)

    def update_object(self, value):
        """Handles the user changing the value in the GUI."""
        self.value = value

    def update_editor(self):
        """Updates the GUI when the Trait changes externally."""
        if self.control is not None:
            # Block signals temporarily to prevent an infinite update loop
            self.control.blockSignals(True)
            self.control.setValue(self.value)
            self.control.blockSignals(False)


class SteppedSpinEditor(BasicEditorFactory):
    """The factory class passed into the Item's editor parameter."""

    klass = Property

    # Expose custom parameters to the TraitsUI Item
    step = Int(1)
    suffix = Str("")
    low = Int(-1000000)  # Default arbitrary low bound
    high = Int(1000000)  # Default arbitrary high bound

    def _get_klass(self):
        return _SteppedSpinEditor

class RangeWithCustomViewHints(Range):
    def create_editor(self):
        """ Returns the default UI editor for the trait.
        """
        return SteppedSpinEditor(
            low=self._low,
            high=self._high,
            step=self._metadata.get("step", 1),
            suffix=self._metadata.get("suffix", ""),
        )


if __name__ == "__main__":
    # ---------------------------------------------------------
    # Example Usage
    # ---------------------------------------------------------
    class MyDeviceController(HasTraits):
        fine_voltage = RangeWithCustomViewHints(10, 1000000, step=1)
        coarse_voltage = RangeWithCustomViewHints(10, 1000000, step=10000, suffix=" V")

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
