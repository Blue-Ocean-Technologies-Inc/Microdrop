from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import QColor
from pyface.tasks.task_pane import TaskPane
from traits.api import Instance, observe

from microdrop_application.preferences import MicrodropPreferences
from microdrop_style.helpers import is_dark_mode

from logger.logger_service import get_logger
logger = get_logger(__name__)

# Auto-mode backgrounds (used when canvas_background_use_custom is False).
# Stored as ints so we can feed them directly into `QColor(int)` — which
# accepts an RGB integer — without string parsing.
_AUTO_LIGHT_BG = 0xFFFFFF  # pure white
_AUTO_DARK_BG = 0x000000   # pure black


class MicrodropCentralCanvas(TaskPane):
    """Central canvas pane for the Microdrop task.

    Renders as a plain QWidget whose background is driven by the Microdrop
    General preferences:

    * `canvas_background_use_custom = False` (default) — follow the system
      color scheme: white in light mode, black in dark mode. Live-updates on
      `QApplication.styleHints().colorSchemeChanged`.
    * `canvas_background_use_custom = True` — use `canvas_background_color`
      (picked via a QColor dialog in the preferences view).

    In both modes, `canvas_background_opacity` (0–100 %) is applied on top
    and emitted as an `rgba(...)` Qt stylesheet.

    Preference changes are picked up live through an `@observe` on the
    composed `MicrodropPreferences` helper.
    """

    id = "white_canvas.pane"
    name = "White Canvas Pane"

    # A helper bound to the application's preferences scope. We create a
    # local helper here (rather than reusing the application's singleton)
    # so that `@observe("app_preferences:…")` fires as apptools propagates
    # node-level changes into this helper's mirrored traits.
    app_preferences = Instance(MicrodropPreferences)

    def create(self, parent):
        widget = QWidget(parent)
        self.control = widget

        self.app_preferences = MicrodropPreferences(
            preferences=self.task.window.application.preferences_helper.preferences
        )

        QApplication.styleHints().colorSchemeChanged.connect(self._apply_background_styling)

        self._apply_background_styling()

    @observe("app_preferences:canvas_background_use_custom,"
             "app_preferences:canvas_background_color,"
             "app_preferences:canvas_background_opacity")
    def _on_canvas_preferences_changed(self, event):
        """Re-style the canvas whenever any of the three canvas prefs change."""
        logger.debug(f"Canvas preference changed: {event.name} → {event.new}")
        self._apply_background_styling()

    def _apply_background_styling(self, *_args):
        """Compose the current preference state into an rgba stylesheet and
        push it onto the canvas widget.

        Safe to call from both preference-change and colorScheme-change paths:
        the `*_args` swallows whatever the caller passes (Qt signals emit a
        scheme enum; Traits observers emit an event object).
        """
        if self.control is None:
            return

        prefs = self.app_preferences
        use_custom = bool(prefs.canvas_background_use_custom) if prefs else False

        opacity_pct = int(prefs.canvas_background_opacity) if prefs else 100
        opacity_pct = max(0, min(100, opacity_pct))
        alpha = int(round(opacity_pct * 255 / 100))

        if use_custom and prefs.canvas_background_color is not None:
            color = prefs.canvas_background_color
        else:
            color = QColor(_AUTO_DARK_BG if is_dark_mode() else _AUTO_LIGHT_BG)

        self.control.setStyleSheet(
            f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {alpha});"
        )
