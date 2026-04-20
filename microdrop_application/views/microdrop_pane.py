from PySide6.QtWidgets import QWidget, QApplication
from pyface.tasks.task_pane import TaskPane
from traits.api import Instance, observe

from microdrop_application.preferences import MicrodropPreferences
from microdrop_style.helpers import is_dark_mode

from logger.logger_service import get_logger
logger = get_logger(__name__)

# UX-friendly auto-mode backgrounds. Dark value matches the VS Code
# "editor" default so the canvas doesn't feel jarringly black.
_AUTO_LIGHT_BG = "#FFFFFF"
_AUTO_DARK_BG = "#1E1E1E"


class MicrodropCentralCanvas(TaskPane):
    id = "white_canvas.pane"
    name = "White Canvas Pane"

    preferences = Instance(MicrodropPreferences)

    def create(self, parent):
        widget = QWidget(parent)
        self.control = widget

        try:
            self.preferences = MicrodropPreferences(
                preferences=self.task.window.application.preferences
            )
        except Exception as e:
            logger.warning(f"Canvas: could not attach preferences helper: {e}")
            self.preferences = None

        QApplication.styleHints().colorSchemeChanged.connect(self._apply_background_styling)

        self._apply_background_styling()

    @observe("preferences:canvas_background_use_custom,"
             "preferences:canvas_background_color,"
             "preferences:canvas_background_opacity")
    def _on_canvas_preferences_changed(self, event):
        self._apply_background_styling()

    def _apply_background_styling(self, *_args):
        if self.control is None:
            return
        prefs = self.preferences
        use_custom = bool(prefs.canvas_background_use_custom) if prefs else False
        opacity_pct = int(prefs.canvas_background_opacity) if prefs else 100
        opacity_pct = max(0, min(100, opacity_pct))
        alpha = int(round(opacity_pct * 255 / 100))

        if use_custom and prefs:
            color_hex = str(prefs.canvas_background_color or _AUTO_LIGHT_BG).strip()
        else:
            color_hex = _AUTO_DARK_BG if is_dark_mode() else _AUTO_LIGHT_BG

        r, g, b = self._parse_hex_color(color_hex)
        self.control.setStyleSheet(
            f"background-color: rgba({r}, {g}, {b}, {alpha});"
        )

    @staticmethod
    def _parse_hex_color(hex_str: str):
        """Return (r, g, b) from '#RRGGBB' / '#RGB' / 'RRGGBB'.
        Falls back to white on malformed input so the canvas never disappears."""
        s = (hex_str or "").lstrip("#").strip()
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        if len(s) != 6:
            return 255, 255, 255
        try:
            return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        except ValueError:
            return 255, 255, 255
