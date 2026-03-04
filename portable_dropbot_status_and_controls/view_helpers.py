from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor

from traitsui.basic_editor_factory import BasicEditorFactory

from dropbot_status_and_controls.view_helpers import StatusIconEditor
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import TOGGLE_DROPBOT_LOADING

from logger.logger_service import get_logger

logger = get_logger(__name__)

ICON_DISABLE_TIMEOUT_S = 10


class ClickableStatusIconEditor(StatusIconEditor):
    """StatusIconEditor that supports clicking to toggle the tray.

    On click, publishes TOGGLE_DROPBOT_LOADING and temporarily disables
    itself. Re-enabled when chip_inserted or tray_operation_failed changes,
    or after a timeout.
    """

    def init(self, parent):
        super().init(parent)

        # Make the label clickable
        self.control.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.control.mousePressEvent = self._on_icon_clicked

        # Fail-safe timer to re-enable icon if no response arrives
        self._timeout_timer = QTimer()
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

        # Observe model traits that should re-enable the icon
        self.object.observe(self._on_re_enable_trigger, "chip_inserted")
        self.object.observe(self._on_re_enable_trigger, "tray_operation_failed")

    def _on_icon_clicked(self, event):
        if not self.object.connected:
            return
        logger.info("Toggling portable dropbot tray")
        publish_message(topic=TOGGLE_DROPBOT_LOADING, message="")
        self.control.setEnabled(False)
        self._timeout_timer.start(ICON_DISABLE_TIMEOUT_S * 1000)

    def _on_re_enable_trigger(self, event):
        self._timeout_timer.stop()
        self.control.setEnabled(True)
        # Reset the flag if it was a tray failure
        if event.trait.name == "tray_operation_failed" and event.new:
            self.object.tray_operation_failed = False

    def _on_timeout(self):
        if self.object.connected:
            self.control.setEnabled(True)

    def dispose(self):
        self.object.observe(
            self._on_re_enable_trigger, "chip_inserted", remove=True
        )
        self.object.observe(
            self._on_re_enable_trigger, "tray_operation_failed", remove=True
        )
        self._timeout_timer.stop()
        super().dispose()


class ClickableStatusIconEditorFactory(BasicEditorFactory):
    klass = ClickableStatusIconEditor
