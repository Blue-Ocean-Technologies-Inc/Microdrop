"""
BaseStatusDockPane — orchestrates model + view + controller + message handler.

TraitsDockPane shows a HasTraits model through a TraitsUI View. The concrete
dock pane subclass declares the class-level ``view`` and implements the
per-instance factory hooks below; the base assembles everything in
traits_init and passes the controller explicitly to edit_traits, so no
mutable state is ever shared between pane instances (the old pattern built
model/controller at class-definition time and mutated the shared View via
``view.handler = controller``).

This base class provides:
  1. traits_init(): calls the factory hooks and assembles the pane.
  2. _create_model() / _create_controller() / _create_message_handler():
     per-instance factory hooks — subclass must implement.
  3. _setup_extras(): optional hook for device-specific additions such as
     dialog views or help pages.
  4. A generic status-bar icon: subclasses set ``status_bar_icon_glyph`` and
     may override _create_status_bar_icon(), _build_status_bar_tooltip(),
     or _create_status_bar_widgets() to customise / add widgets (see
     RealtimeModeIconMixin for an opt-in realtime-mode toggle).
"""
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.colors import WHITE, GREY
from microdrop_style.helpers import is_dark_mode
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE
from microdrop_utils.pyside_helpers import horizontal_spacer_widget
from pyface.tasks.api import TraitsDockPane
from pyface.qt.QtGui import QApplication, QLabel, QFont
from traits.api import Any, Instance, List, observe
from traitsui.api import Handler

from logger.logger_service import get_logger

from .interfaces import IMessageHandler

logger = get_logger(__name__)

#: Position in the status bar at which every pane widget is inserted.
STATUS_BAR_INSERT_INDEX = 2

#: Width (px) of the spacer inserted alongside each status-bar widget.
STATUS_BAR_SPACER_WIDTH = 10


def status_bar_icon_font() -> QFont:
    """The icon font, sized for status-bar icons."""
    font = QFont(ICON_FONT_FAMILY)
    font.setPointSize(STATUSBAR_ICON_POINT_SIZE)
    return font


def build_status_icon_tooltip(title, states, hint=None) -> str:
    """
    Render the status-icon hover tooltip: a colored legend of device states,
    plus an optional italic hint line.

    :param title: heading, e.g. "Device Status:".
    :param states: iterable of (color, label) pairs — one legend entry each.
    :param hint: optional italic line under the legend.
    """
    title_color = WHITE if is_dark_mode() else GREY["dark"]
    state_items = "".join(
        f'<li><strong style="color: {color};">{label}</strong></li>'
        for color, label in states
    )
    hint_html = (
        f'<div style="margin-top: 3px;"><em>{hint}</em></div>' if hint else ""
    )
    return f"""
    <div style="font-family: sans-serif; font-size: 10pt; line-height: 1;">
      <strong style="font-size: 1.1em; color: {title_color}">{title}</strong>
      <ul style="margin-top: 1px; margin-bottom: 1px; padding-left: 20px;">
        {state_items}
      </ul>
      {hint_html}
    </div>
    """


class BaseStatusDockPane(TraitsDockPane):
    """
    Base dock pane for device status-and-controls panels.

    Minimal subclass example
    ------------------------
    ::

        class MyDeviceDockPane(BaseStatusDockPane):
            id   = f"{PKG}.dock_pane"
            name = PKG_name

            view = MyDeviceView                    # TraitsUI View instance
            status_bar_icon_glyph = ICON_MY_DEVICE

            def _create_model(self):
                return MyDeviceModel()

            def _create_controller(self):
                return MyDeviceController(self.model)

            def _create_message_handler(self):
                return MyDeviceMessageHandler(
                    model=self.model,
                    name=f"{PKG}_listener",
                )
    """

    #: Icon-font glyph shown for this device in the app status bar.
    status_bar_icon_glyph = ""

    #: TraitsUI controller, built per instance by _create_controller().
    controller = Instance(Handler)

    #: Dramatiq-backed listener, built per instance by _create_message_handler().
    message_handler = Instance(IMessageHandler)

    #: Status-bar icon widget (built once the window's status bar appears).
    status_bar_icon = Any(None)

    #: Every widget this pane inserted into the status bar (icons AND their
    #: spacers), tracked so destroy() can remove exactly what was added —
    #: required for runtime hot unload of the pane.
    _status_bar_inserted_widgets = List()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                             #
    # ------------------------------------------------------------------ #

    def traits_init(self):
        """
        Assemble the pane after traits initialisation.

        Order matters: the message handler must be started before _setup_extras
        because extras (e.g. dialog views) may connect to handler signals.
        """
        self.model = self._create_model()
        self.controller = self._create_controller()
        self.message_handler = self._create_message_handler()
        self._setup_extras()

    def create_contents(self, parent):
        """
        Create the pane contents, passing the controller explicitly so the
        class-level View declaration is never mutated per instance.
        """
        self.ui = self.edit_traits(
            kind="subpanel", parent=parent, handler=self.controller
        )
        return self.ui.control

    def destroy(self):
        """Tear down everything this pane set up (inverse of traits_init +
        _populate_status_bar), then destroy the pane control.

        This is what makes the pane hot-unloadable at runtime: the status-bar
        widgets come out, the theme-change signal is disconnected, and the
        message handler releases its Dramatiq listener name so a re-mounted
        pane can register fresh. Also runs on normal app shutdown, so every
        step is guarded to be safe when only partially set up.
        """
        self._teardown_status_bar()
        if self.message_handler is not None:
            self.message_handler.teardown()
            self.message_handler = None
        super().destroy()

    def _teardown_status_bar(self):
        """Remove this pane's status-bar widgets and signal hookups."""
        if self._status_bar_inserted_widgets:
            try:
                QApplication.styleHints().colorSchemeChanged.disconnect(
                    self._refresh_status_bar_tooltip
                )
            except (RuntimeError, TypeError):
                pass                    # never connected / already gone
            try:
                status_bar = self.task.window.status_bar_manager.status_bar
            except Exception as e:      # window already torn down (app exit)
                logger.debug(f"Status bar gone before pane teardown: {e}")
                status_bar = None
            for widget in self._status_bar_inserted_widgets:
                if status_bar is not None:
                    status_bar.removeWidget(widget)
                widget.deleteLater()
            self._status_bar_inserted_widgets = []
        self.status_bar_icon = None

    # ------------------------------------------------------------------ #
    # Factory hooks — implement / override in subclass                     #
    # ------------------------------------------------------------------ #

    def _create_model(self):
        """Create and return the device-specific status model."""
        raise NotImplementedError(
            f"{type(self).__name__} must implement _create_model()"
        )

    def _create_controller(self):
        """Create and return the TraitsUI controller for self.model."""
        raise NotImplementedError(
            f"{type(self).__name__} must implement _create_controller()"
        )

    def _create_message_handler(self) -> IMessageHandler:
        """
        Create and return the device-specific message handler.

        The returned object must satisfy IMessageHandler (i.e. it must be a
        BaseMessageHandler subclass or equivalent HasTraits object whose
        traits_init() registers a Dramatiq actor).
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _create_message_handler()"
        )

    def _setup_extras(self):
        """
        Hook for device-specific one-time setup after the handler is running.

        Examples of what subclasses put here:
          - Dialog views (shorts detected, no-power, halted)
          - Help page action

        Default: no-op.
        """

    # ------------------------------------------------------------------ #
    # Status-bar icon                                                       #
    # ------------------------------------------------------------------ #

    @observe("model.icon_color", dispatch="ui")
    def _sync_model_icon_color(self, event):
        """Keep the icon color in sync with the model's connection state."""
        if self.status_bar_icon is not None:
            self.status_bar_icon.setStyleSheet(f"color: {event.new}")

    @observe("task:window:status_bar_manager")
    def _populate_status_bar(self, event):
        """Build the status-bar widgets and insert each (plus a spacer).

        Subclass overrides MUST re-apply the @observe decorator above —
        an undecorated override silently drops the observer registration."""
        self.status_bar_icon = self._create_status_bar_icon()
        self._refresh_status_bar_tooltip()
        QApplication.styleHints().colorSchemeChanged.connect(
            self._refresh_status_bar_tooltip
        )
        status_bar = self.task.window.status_bar_manager.status_bar
        for widget in self._create_status_bar_widgets():
            spacer = horizontal_spacer_widget(STATUS_BAR_SPACER_WIDTH)
            status_bar.insertPermanentWidget(STATUS_BAR_INSERT_INDEX, widget)
            status_bar.insertPermanentWidget(STATUS_BAR_INSERT_INDEX, spacer)
            # Track both so destroy() removes exactly what this pane added.
            self._status_bar_inserted_widgets.extend([widget, spacer])

    def _create_status_bar_icon(self):
        """
        Build the device's status-bar icon widget.

        Default: a plain QLabel showing ``status_bar_icon_glyph``. Override
        for interactive icons (e.g. the heater's click-to-scan label).
        """
        icon = QLabel(self.status_bar_icon_glyph)
        icon.setFont(status_bar_icon_font())
        icon.setStyleSheet(f"color: {self.model.DISCONNECTED_COLOR}")
        return icon

    def _create_status_bar_widgets(self):
        """
        The widgets to insert into the status bar, left to right.

        Override to add widgets alongside the device icon::

            return super()._create_status_bar_widgets() + [my_widget]
        """
        return [self.status_bar_icon]

    def _build_status_bar_tooltip(self) -> str:
        """Tooltip for the status-bar icon. Default: the four standard
        device states, colored from the model's class-level constants."""
        return build_status_icon_tooltip(
            "Device Status:",
            [
                (self.model.DISCONNECTED_COLOR, "Disconnected"),
                (self.model.CONNECTED_NO_DEVICE_COLOR, "Connected (No Chip)"),
                (self.model.CONNECTED_COLOR, "Connected (Chip Detected)"),
                (self.model.HALTED_COLOR, "Halted (Device Fault)"),
            ],
        )

    def _refresh_status_bar_tooltip(self, *args):
        """Re-apply the tooltip (``*args`` absorbs the colour-scheme arg when
        wired to QApplication's colorSchemeChanged)."""
        if self.status_bar_icon is not None:
            self.status_bar_icon.setToolTip(self._build_status_bar_tooltip())
