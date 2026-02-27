from traits.api import HasTraits, HTML, observe
from traitsui.api import UItem, View, HTMLEditor
from pyface.tasks.dock_pane import DockPane

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QApplication

from microdrop_style.helpers import is_dark_mode
from microdrop_style.colors import WHITE, GREY
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE
from microdrop_style.icons.icons import ICON_DROP_EC
from microdrop_utils.pyside_helpers import horizontal_spacer_widget

from .consts import (
    PKG, PKG_name, listener_name,
    disconnected_color, connected_no_device_color, connected_color,
)


class DropbotStatusAndControlsDockPane(DockPane):
    """
    A unified dock pane combining DropBot status display and manual controls.
    """

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    def create_contents(self, parent):
        from .model import DropbotStatusAndControlsModel
        from .message_handler import (
            DialogSignals,
            DropbotStatusAndControlsMessageHandler
        )
        from .dialog_views import DialogView
        from .controls import UnifiedView, ControlsController

        # 1. Shared model
        model = DropbotStatusAndControlsModel()

        # 2. Message handler (Dramatiq listener)
        dialog_signals = DialogSignals()
        self.message_handler = DropbotStatusAndControlsMessageHandler(
            model=model,
            dialog_signals=dialog_signals,
            name=listener_name
        )
        self.dialog_view = DialogView(
            dialog_signals=dialog_signals,
            message_handler=self.message_handler
        )

        # 3. Single unified TraitsUI view
        controls_controller = ControlsController(model)
        ui = model.edit_traits(
            view=UnifiedView,
            handler=controls_controller,
            kind='subpanel'
        )

        # Store model reference for statusbar icon color observation
        self._model = model

        return ui.control

    def show_help(self):
        sample_text = (
            """
            <html><body><h1>Dropbot Status And Controls Help Page</h1>
            """
            + self.__doc__
        )

        class HTMLEditorDemo(HasTraits):
            """Defines the main HTMLEditor demo class."""
            my_html_trait = HTML(sample_text)

            traits_view = View(
                UItem(
                    'my_html_trait',
                    editor=HTMLEditor(format_text=False),
                ),
                title='HTMLEditor',
                buttons=['OK'],
                width=800,
                height=600,
                resizable=True,
            )

        demo = HTMLEditorDemo()
        demo.configure_traits()

    @observe("task:window:status_bar_manager")
    def _setup_app_statusbar_with_dropbot_status_icon(self, event):
        dropbot_status = QLabel(ICON_DROP_EC)

        _font = QFont(ICON_FONT_FAMILY)
        _font.setPointSize(STATUSBAR_ICON_POINT_SIZE)
        dropbot_status.setFont(_font)
        dropbot_status.setStyleSheet(f"color: {disconnected_color}")

        self.task.window.status_bar_manager.status_bar.addPermanentWidget(horizontal_spacer_widget(10))
        self.task.window.status_bar_manager.status_bar.addPermanentWidget(dropbot_status)

        def set_status_color(event):
            dropbot_status.setStyleSheet(f"color: {event.new}")

        self._model.observe(set_status_color, "icon_color")

        self.status_bar_icon = dropbot_status

        def _apply_theme_style():
            self.status_bar_icon.setToolTip(get_status_icon_tooltip_themed())

        _apply_theme_style()
        QApplication.styleHints().colorSchemeChanged.connect(_apply_theme_style)


def get_status_icon_tooltip_themed():
    if is_dark_mode():
        title_color = WHITE
    else:
        title_color = GREY['dark']

    dropbot_status_icon_tooltip_html = f"""
    <div style="font-family: sans-serif; font-size: 10pt; line-height: 1;">
      <strong style="font-size: 1.1em; color: {title_color}">Dropbot Status:</strong>
      <ul style="margin-top: 1px; margin-bottom: 1px; padding-left: 20px;">
        <li><strong style="color: {disconnected_color};">Disconnected</strong></li>
        <li><strong style="color: {connected_no_device_color};">Connected (No Chip)</strong></li>
        <li><strong style="color: {connected_color};">Connected (Chip Detected)</strong></li>
      </ul>
    </div>
    """

    return dropbot_status_icon_tooltip_html
