"""Peripheral (Z-Stage) status dock pane, on the status-and-controls template.

The pane contents stay a hand-built Qt view (ZStageView in a scroll area) —
create_contents is overridden instead of using the base's TraitsUI path, so
there is no TraitsUI controller. Everything else comes from the template:
per-instance model/message-handler assembly, the status-bar icon with theme-
tracked tooltip, and destroy() teardown for runtime hot unload.
"""
from traits.api import observe
from pyface.qt.QtGui import Qt
from pyface.qt.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QApplication

from template_status_and_controls.base_dock_pane import (
    BaseStatusDockPane, build_status_icon_tooltip, status_bar_icon_font)
from microdrop_style.button_styles import get_tooltip_style
from microdrop_style.general_style import get_general_style
from microdrop_style.helpers import is_dark_mode, QT_THEME_NAMES
from microdrop_style.icons.icons import ICON_STAIRS
from microdrop_style.label_style import get_label_style
from microdrop_utils.pyside_helpers import ClickableLabel
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger

from .consts import PKG, PKG_name, DEVICE_NAME, START_DEVICE_MONITORING, listener_name
from .model import PeripheralModel
from .message_handler import PeripheralMessageHandler

logger = get_logger(__name__)


class PeripheralStatusDockPane(BaseStatusDockPane):
    """Dock pane showing the Z-Stage status and manual controls."""

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    status_bar_icon_glyph = ICON_STAIRS

    # ------------------------------------------------------------------ #
    # BaseStatusDockPane factory hooks                                     #
    # ------------------------------------------------------------------ #
    def _create_model(self):
        return PeripheralModel(device_name=DEVICE_NAME)

    def _create_controller(self):
        # Contents are a hand-built Qt view (see create_contents), not a
        # TraitsUI View — there is no TraitsUI controller.
        return None

    def _create_message_handler(self) -> PeripheralMessageHandler:
        return PeripheralMessageHandler(model=self.model, name=listener_name)

    # ------------------------------------------------------------------ #
    # Contents — hand-built Qt Z-Stage view in a scroll area               #
    # ------------------------------------------------------------------ #
    def create_contents(self, parent):
        from .z_stage.view_model import ZStageViewModel, ZStageViewModelSignals
        from .z_stage.view import ZStageView

        view_signals = ZStageViewModelSignals()
        view_model = ZStageViewModel(model=self.model, view_signals=view_signals)
        _view = ZStageView(view_model=view_model)
        view_model.force_initial_update()

        # The scroll area needs an intermediate QWidget to hold the layout
        # (this is what allows 'addStretch').
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.addWidget(_view)
        layout.addStretch()

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_content)

        # Theme-aware styling, re-applied on every app theme change. The
        # connection is undone in destroy() so a hot-unloaded pane doesn't
        # leave a dangling slot firing into a destroyed widget.
        self._apply_theme_style(
            Qt.ColorScheme.Dark if is_dark_mode() else Qt.ColorScheme.Light)
        QApplication.styleHints().colorSchemeChanged.connect(
            self._apply_theme_style)

        return scroll_area

    def _apply_theme_style(self, theme: 'Qt.ColorScheme'):
        """Restyle the pane contents for the given application theme."""
        if self.control is None:
            return
        theme = QT_THEME_NAMES[theme]
        general = get_general_style(theme)
        labels = get_label_style(theme)
        tooltips = get_tooltip_style(theme)
        # Order matters slightly: generic rules first, specific widgets last.
        self.control.setStyleSheet(f"{general}\n{labels}\n{tooltips}")

    def destroy(self):
        try:
            QApplication.styleHints().colorSchemeChanged.disconnect(
                self._apply_theme_style)
        except (RuntimeError, TypeError):
            pass                        # never connected / already gone
        super().destroy()

    # ------------------------------------------------------------------ #
    # Status-bar icon — stairs glyph, clickable to trigger a connection scan
    # ------------------------------------------------------------------ #
    # Overrides of @observe-decorated methods MUST re-apply the decorator:
    # an undecorated override silently drops the base registration.
    @observe("task:window:status_bar_manager")
    def _populate_status_bar(self, event):
        super()._populate_status_bar(event)
        self._sync_search_affordance()  # initial cursor for the search state

    def _create_status_bar_icon(self):
        # Clickable: triggers a Z-Stage connection scan (same as Tools ▸
        # Peripherals ▸ Z-Stage ▸ Search Connection), ignored while one is
        # already running (see model.searching).
        icon = ClickableLabel(self.status_bar_icon_glyph)
        icon.setFont(status_bar_icon_font())
        icon.setStyleSheet(f"color: {self.model.DISCONNECTED_COLOR}")
        icon.clicked.connect(self._search_connection)
        return icon

    def _build_status_bar_tooltip(self) -> str:
        return build_status_icon_tooltip(
            "Z-Stage Status:",
            [
                (self.model.DISCONNECTED_COLOR, "Disconnected"),
                (self.model.CONNECTED_COLOR, "Connected"),
            ],
            hint="Searching for device…" if self.model.searching
                 else "Click to search for a connection.",
        )

    def _search_connection(self):
        """Ask the backend to start a connection scan, unless one is already
        running. The backend acknowledges by publishing its searching state,
        which disables the icon (see _sync_search_affordance)."""
        if self.model.searching:
            logger.debug("Z-Stage search already active; ignoring status-icon click")
            return
        publish_message(message="", topic=START_DEVICE_MONITORING)

    @observe("model:searching", dispatch="ui")
    def _sync_search_affordance(self, event=None):
        """Pointing-hand cursor only when a click would do something — i.e.
        when no scan is currently active — and flip the tooltip to match."""
        if self.status_bar_icon is not None:
            self.status_bar_icon.setCursor(
                Qt.CursorShape.ArrowCursor if self.model.searching
                else Qt.CursorShape.PointingHandCursor)
        self._refresh_status_bar_tooltip()
