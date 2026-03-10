"""
BaseStatusDockPane — orchestrates model + view + controller + message handler.

TraitsDockPane wires a HasTraits model to a TraitsUI View through a Controller
(Handler). The concrete dock pane subclass sets the class-level model, view,
and controller attributes that TraitsDockPane expects, then calls super().

This base class provides:
  1. traits_init(): calls the two factory hooks and assembles the pane.
  2. _create_message_handler(): factory hook — subclass must implement.
  3. _setup_extras(): optional hook for device-specific additions such as
     status-bar icons, dialog views, or help pages.

Design notes:
  - We use factory *methods* (not class-level attributes) for the message
    handler and extras so that each pane *instance* gets its own objects —
    the existing code had a subtle bug where class-level model/controller
    were shared across instances.
  - Subclasses that need a status-bar icon or dialog popups override
    _setup_extras(); this keeps the base class free of device-specific code.
"""
from dropbot_status_and_controls.consts import connected_no_device_color, halted_color
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.colors import WHITE, GREY
from microdrop_style.helpers import is_dark_mode
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE
from microdrop_style.icons.icons import ICON_DROP_EC
from microdrop_utils.pyside_helpers import horizontal_spacer_widget
from pyface.tasks.api import TraitsDockPane
from pyface.qt.QtGui import QApplication, QLabel, QFont
from traits.api import observe

from logger.logger_service import get_logger

from .interfaces import IMessageHandler

logger = get_logger(__name__)


class BaseStatusDockPane(TraitsDockPane):
    """
    Base dock pane for device status-and-controls panels.

    Minimal subclass example
    ------------------------
    ::

        class MyDeviceDockPane(BaseStatusDockPane):
            id   = f"{PKG}.dock_pane"
            name = PKG_name

            # TraitsDockPane class-level attributes
            model      = MyDeviceModel()
            view       = MyDeviceView
            controller = MyDeviceController(model)
            view.handler = controller

            def _create_message_handler(self) -> IMessageHandler:
                return MyDeviceMessageHandler(
                    model=self.model,
                    name=f"{PKG}_listener",
                )
    """

    # ------------------------------------------------------------------ #
    # Lifecycle                                                             #
    # ------------------------------------------------------------------ #

    def traits_init(self):
        """
        Assemble the pane after traits initialisation.

        Order matters: the message handler must be started before _setup_extras
        because extras (e.g. dialog views) may connect to handler signals.
        """
        self.message_handler = self._create_message_handler()
        self._setup_extras()

    # ------------------------------------------------------------------ #
    # Factory hooks — implement / override in subclass                     #
    # ------------------------------------------------------------------ #

    def _create_message_handler(self) -> IMessageHandler:
        """
        Create and return the device-specific message handler.

        The returned object must satisfy IMessageHandler (i.e. it must be a
        BaseMessageHandler subclass or equivalent HasTraits object whose
        traits_init() registers a Dramatiq actor).

        Raises NotImplementedError if not overridden.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _create_message_handler()"
        )

    def _setup_extras(self):
        """
        Hook for device-specific one-time setup after the handler is running.

        Examples of what subclasses put here:
          - Dialog views (shorts detected, no-power, halted)
          - Status-bar icon widget and colour observer
          - Help page action

        Default: no-op.
        """

    # ------------------------------------------------------------------ #
    # Status-bar icon                                                       #
    # ------------------------------------------------------------------ #
    @observe("task:window:status_bar_manager")
    def _setup_statusbar_icon(self, event):
        icon = QLabel(ICON_DROP_EC)
        font = QFont(ICON_FONT_FAMILY)
        font.setPointSize(STATUSBAR_ICON_POINT_SIZE)
        icon.setFont(font)
        icon.setStyleSheet(f"color: {self.model.DISCONNECTED_COLOR}")

        self.task.window.status_bar_manager.status_bar.addPermanentWidget(
            horizontal_spacer_widget(10)
        )
        self.task.window.status_bar_manager.status_bar.addPermanentWidget(icon)

        # Keep the icon color in sync with the model's connection state.
        self.model.observe(lambda e: icon.setStyleSheet(f"color: {e.new}"), "icon_color")

        self.status_bar_icon = icon

        def _apply_tooltip():
            self.status_bar_icon.setToolTip(_build_status_icon_tooltip(
                self.model.DISCONNECTED_COLOR,
                self.model.CONNECTED_COLOR,
                self.model.CONNECTED_NO_DEVICE_COLOR,
                self.model.HALTED_COLOR)
            )

        _apply_tooltip()
        QApplication.styleHints().colorSchemeChanged.connect(_apply_tooltip)


def _build_status_icon_tooltip(
        disconnected_color,
        connected_color,
        connected_no_device_color,
        halted_color) -> str:
    title_color = WHITE if is_dark_mode() else GREY["dark"]
    return f"""
    <div style="font-family: sans-serif; font-size: 10pt; line-height: 1;">
      <strong style="font-size: 1.1em; color: {title_color}">Device Status:</strong>
      <ul style="margin-top: 1px; margin-bottom: 1px; padding-left: 20px;">
        <li><strong style="color: {disconnected_color};">Disconnected</strong></li>
        <li><strong style="color: {connected_no_device_color};">Connected (No Chip)</strong></li>
        <li><strong style="color: {connected_color};">Connected (Chip Detected)</strong></li>
        <li><strong style="color: {halted_color};">Halted (Device Fault)</strong></li>
      </ul>
    </div>
    """
