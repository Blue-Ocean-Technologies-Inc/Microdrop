# enthought imports
from traits.api import observe
from pyface.tasks.dock_pane import DockPane

from pyface.qt.QtGui import QFont, Qt
from pyface.qt.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QLabel, QApplication

from microdrop_style.button_styles import get_tooltip_style
from microdrop_style.general_style import get_general_style
from microdrop_style.helpers import is_dark_mode, QT_THEME_NAMES
from microdrop_style.colors import GREY, WHITE
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE
from microdrop_style.icons.icons import ICON_STAIRS
from microdrop_style.label_style import get_label_style
from microdrop_utils.pyside_helpers import horizontal_spacer_widget
from .consts import PKG, PKG_name,DEVICE_NAME

from dropbot_status.displayed_UI import disconnected_color, connected_color


class PeripheralStatusDockPane(DockPane):
    """
    A dock pane to view the status of the dropbot.
    """
    #### 'ITaskPane' interface ################################################

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    def create_contents(self, parent):
        # Import all the components from your module
        from .z_stage.view_model import ZStageViewModel, ZStageViewModelSignals
        from .z_stage.view import ZStageView
        from .model import PeripheralModel
        from .dramatiq_view_model import DramatiqStatusViewModel
        from .dramatiq_status_controller import DramatiqStatusController

        model = PeripheralModel(device_name=DEVICE_NAME)

        # initialize dramatiq controller for the UI
        dramatiq_view_model = DramatiqStatusViewModel(model=model)
        # store controller and view in dock pane
        self.dramatiq_controller = DramatiqStatusController(ui=dramatiq_view_model,
                                                                   listener_name=dramatiq_view_model.__class__.__module__.split(".")[0] + "_listener")

        # initialize displayed UI
        view_signals = ZStageViewModelSignals()
        view_model = ZStageViewModel(
            model=model,
            view_signals=view_signals
        )

        _view = ZStageView(view_model=view_model)

        view_model.force_initial_update()

        ### Make pane scrollable:

        # The scroll area needs an intermediate QWidget to hold the layout
        # This is what allows you to use 'addStretch'
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)  # Pass content widget to layout constructor
        layout.addWidget(_view)
        layout.addStretch()

        # Create the scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_content)

        # ---------------------------------- Theme aware styling ----------------------------------#
        def _apply_theme_style(theme: 'Qt.ColorScheme'):
            """Handle application level theme updates"""
            theme = QT_THEME_NAMES[theme]

            general = get_general_style(theme)
            labels = get_label_style(theme)
            tooltips = get_tooltip_style(theme)

            # Order matters slightly: General generic rules first, specific widgets last.
            stylesheet = f"{general}\n{labels}\n{tooltips}"

            self.control.setStyleSheet(stylesheet)

        # Apply initial theme styling
        _apply_theme_style(theme=Qt.ColorScheme.Dark if is_dark_mode() else Qt.ColorScheme.Light)

        # Call theme application method whenever global theme changes occur as well
        QApplication.styleHints().colorSchemeChanged.connect(_apply_theme_style)

        # Return the scroll area directly
        return scroll_area

    @observe("task:window:status_bar_manager")
    def _setup_app_statusbar_with_device_status_icon(self, event):

        _model = self.dramatiq_controller.ui.model

        device_status = QLabel(ICON_STAIRS)

        _font = QFont(ICON_FONT_FAMILY)
        _font.setPointSize(STATUSBAR_ICON_POINT_SIZE)
        device_status.setFont(_font)
        device_status.setStyleSheet(f"color: {disconnected_color};")

        self.task.window.status_bar_manager.status_bar.addPermanentWidget(horizontal_spacer_widget(10))
        self.task.window.status_bar_manager.status_bar.addPermanentWidget(device_status)

        def set_status_color(event):
            color = connected_color if event.new else disconnected_color
            device_status.setStyleSheet(f"color: {color}")

        _model.observe(set_status_color, "status")

        self.status_bar_icon = device_status

        ### update tooltip based on dark / light mode
        def _apply_theme_style():
            self.status_bar_icon.setToolTip(get_status_icon_tooltip_themed())

        _apply_theme_style()  # initial setting
        QApplication.styleHints().colorSchemeChanged.connect(_apply_theme_style)  # track theme changes

def get_status_icon_tooltip_themed():
    if is_dark_mode():
        title_color = WHITE
    else:
        title_color = GREY['dark']

    z_stage_status_icon_tooltip_html = f"""
    <div style="font-family: sans-serif; font-size: 10pt; line-height: 1;">
      <strong style="font-size: 1.1em; color: {title_color}">Z-Stage Status:</strong>
      <ul style="margin-top: 1px; margin-bottom: 0; padding-left: 20px;">
        <li><strong style="color: {disconnected_color};">Disconnected</strong></li>
        <li><strong style="color: {connected_color};">Connected</strong></li>
      </ul>
    </div>
    """
    return z_stage_status_icon_tooltip_html


