import functools

from traits.api import observe, Dict
from traitsui.api import (
    View,
    HGroup,
    Item,
    BasicEditorFactory,
    Controller,
    VGroup,
    VGrid,
    HSplit,
    UItem,
    Spring,
)
from traitsui.qt.editor import Editor as QtEditor
from PySide6.QtGui import Qt, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy

from logger.logger_service import get_logger
from manual_controls.MVC import ToggleEditorFactory
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.decorators import debounce

from dropbot_controller.consts import (
    SET_VOLTAGE,
    SET_FREQUENCY,
    SET_REALTIME_MODE,
)

from .consts import PKG_name, BORDER_RADIUS

logger = get_logger(__name__)


# ─── Scaling pixmap label ─────────────────────────────────────────────────────


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


# ─── StatusIconEditor ──────────────────────────────────────────────────────────


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

    # ─── Unified View ──────────────────────────────────────────────────────────────


left = HGroup(
    Item(
        "icon_path",
        editor=StatusIconEditorFactory(),
        show_label=False,
    ),
    Spring("8"),
    VGroup(
        Spring("8"),
        VGroup(
            Item("connection_status_text", style="readonly", label="Connection"),
            Item("chip_status_text", style="readonly", label="Chip Status"),
        ),
        Spring("25"),
        UItem(
            "realtime_mode",
            style="custom",
            editor=ToggleEditorFactory(),
            enabled_when="connected",
        ),
    ),
)


pluggable_grid_layout = VGrid(
    Item("voltage_readback_display", style="readonly", label="Voltage"),
    UItem("voltage", label="Voltage"),
    Item("frequency", label="Frequency", style="readonly"),
    UItem("frequency", label="Frequency"),
    Item("capacitance_display", style="readonly", label="  Capacitance"),
    UItem(""),
    Item("pressure_display", style="readonly", label="c_device"),
    UItem(""),
    Item("force_display", style="readonly", label="Force"),
    UItem(""),
    show_left=True,
    springy=False,
)

UnifiedView = View(
    HSplit(
        left,
        pluggable_grid_layout,
        springy=False,
        show_border=True,
    ),
    title=PKG_name,
    resizable=True,
)


class ControlsController(Controller):
    # Use a dict to store the *latest* task for each topic
    message_dict = Dict()

    def init(self, info):
        info.ui.control.setStyleSheet(
            """
                            QSplitter::handle:horizontal {
                                /* 1. Add more spacing (Total distance between panes) */
                                width: 5px;               

                                /* 2. Transparent color (Red, Green, Blue, Alpha/Opacity) 
                                      0 opacity = completely invisible. 
                                      40 opacity = very faint/transparent grey. */
                                background-color: rgba(150, 150, 150, 40); 

                                /* 3. Make it very thin by squishing the visible area 
                                      40px total - 19px left - 19px right = 2px thin line */
                                margin-left: 200px;          
                                margin-right: 200px;         
                            }

                            QSplitter::handle:horizontal:hover {
                                /* Slightly more opaque blue when the user hovers over the gap */
                                background-color: rgba(52, 152, 219, 100); 
                            }

                            QSplitter::handle:horizontal:pressed {
                                background-color: rgba(28, 89, 128, 180); 
                            }
                        """
        )
        return True

    def _publish_message_if_realtime(self, topic: str, message: str) -> bool:
        if self.model.realtime_mode:
            publish_message(topic=topic, message=message)
            return True
        else:
            # Create the task "snapshot"
            task = functools.partial(publish_message, topic=topic, message=message)
            logger.debug(
                f"QUEUEING Topic='{topic}, message={message}' when realtime mode on"
            )
            # Store the task, overwriting any previous task for this topic
            self.message_dict[topic] = task

        return False

    def publish_queued_messages(self):
        """Processes the most recent message for each topic."""
        logger.info(
            "\n--- Dropbot Controls: Publishing Queued Messages (Last Value Only) ---"
        )

        if not self.message_dict:
            logger.info("--- Dropbot Controls Queue empty ---")
            return

        # Get all the "latest" tasks that are waiting
        tasks_to_run = list(self.message_dict.values())
        # Clear the dict for the next batch
        self.message_dict.clear()

        for task in tasks_to_run:
            try:
                task()  # This executes: publish_message(topic=..., message=...)
            except Exception as e:
                logger.warning(f"Error publishing queued message: {e}")

    ###################################################################################
    # Controller interface — debounced setattr
    ###################################################################################

    @debounce(wait_seconds=0.3)
    def voltage_setattr(self, info, object, traitname, value):
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=0.3)
    def frequency_setattr(self, info, object, traitname, value):
        return super().setattr(info, object, traitname, value)

    # This callback will not call update_editor() when it is not debounced!
    # This is likely because update_editor is only called by 'external' trait changes, and the new thread spawned by the decorator appears as such
    @debounce(wait_seconds=1)
    def realtime_mode_setattr(self, info, object, traitname, value):
        logger.debug(f"Set realtime mode to {value}")
        info.realtime_mode.control.setChecked(value)
        return super().setattr(info, object, traitname, value)

    ###################################################################################
    # Trait notification handlers
    ###################################################################################

    @observe("model:realtime_mode")
    def _realtime_mode_changed(self, event):
        publish_message(topic=SET_REALTIME_MODE, message=str(event.new))

        if event.new:
            self.publish_queued_messages()

    @observe("model:voltage")
    def _voltage_changed(self, event):
        if self._publish_message_if_realtime(topic=SET_VOLTAGE, message=str(event.new)):
            logger.debug(f"Requesting Voltage change to {event.new} V")

    @observe("model:frequency")
    def _frequency_changed(self, event):
        if self._publish_message_if_realtime(
            topic=SET_FREQUENCY, message=str(event.new)
        ):
            logger.debug(f"Requesting Frequency change to {event.new} Hz")
