import sys
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMainWindow,
    QGroupBox,
    QDoubleSpinBox,
)
from PySide6.QtCore import Slot

from microdrop_utils.pyside_helpers import CollapsibleVStackBox
from peripheral_controller.consts import MIN_ZSTAGE_HEIGHT_MM, MAX_ZSTAGE_HEIGHT_MM
from peripherals_ui.z_stage.view_model import ZStageViewModel


class ZStageView(QWidget):
    """
    The View. Manages UI widgets only.
    Binds to the ViewModel's commands and its signals.
    """

    def __init__(self, view_model: ZStageViewModel, parent=None):
        super().__init__(parent)
        self.view_model = view_model
        # Get the signal bridge from the ViewModel
        self.view_signals = view_model.view_signals

        # --- Create Widgets ---
        # Read-only labels
        self.status_label = QLabel("Status: ...")
        self.current_position_label = QLabel("Position: ...")

        # Color box for status
        self.status_color_box = QLabel()
        # control buttons
        self.up_button = QPushButton("Up")
        self.down_button = QPushButton("Down")
        self.home_button = QPushButton("Home")

        # Position control spinbox
        self.set_position_label = QLabel("Set Position:")
        self.position_spinbox = QDoubleSpinBox()
        self.position_spinbox.setSingleStep(0.5)
        self.position_spinbox.setRange(MIN_ZSTAGE_HEIGHT_MM, MAX_ZSTAGE_HEIGHT_MM)
        self.position_spinbox.setDecimals(2)
        self.position_spinbox.setSuffix(" mm")

        # --- Layout ---
        main_layout = QVBoxLayout(self)

        ################### Status display group ######################
        # Create a container widget for all the contents of the group
        status_contents_container = QWidget()

        status_layout = QHBoxLayout(status_contents_container)  # Set layout on container

        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.current_position_label)
        status_layout.addStretch()  # Add stretch to keep them to the left

        status_group = CollapsibleVStackBox("Status", [status_contents_container])

        ###################### Control group ##########################

        # Create a container widget for all the contents of the group
        self.control_contents_container = QWidget()

        # Set the layout on the container widget
        controls_layout = QVBoxLayout(self.control_contents_container)
        controls_buttons_layout = QHBoxLayout()
        position_controls_layout = QHBoxLayout()

        # display buttons horizontally
        controls_buttons_layout.addWidget(self.up_button)
        controls_buttons_layout.addWidget(self.down_button)
        controls_buttons_layout.addWidget(self.home_button)

        # display position label and spin box horizontally aligned
        position_controls_layout.addWidget(self.set_position_label)
        position_controls_layout.addWidget(self.position_spinbox)

        controls_layout.addLayout(controls_buttons_layout)
        controls_layout.addLayout(position_controls_layout)

        control_group = CollapsibleVStackBox("Controls", [self.control_contents_container])

        #############################################################

        main_layout.addWidget(status_group)
        main_layout.addWidget(control_group)
        main_layout.addStretch()

        # --- Data Binding ---

        # Connect buttons (View) -> commands (ViewModel)
        self.up_button.clicked.connect(self.view_model.move_up)
        self.down_button.clicked.connect(self.view_model.move_down)
        self.home_button.clicked.connect(self.view_model.go_home)
        self.position_spinbox.valueChanged.connect(self.view_model.set_position)

        # Connect signals (ViewModel) -> slots (View widgets)
        self.view_signals.status_text_changed.connect(self.status_label.setText)

        # Connect the formatted text signal to our new display label
        self.view_signals.position_text_changed.connect(self.current_position_label.setText)

        # Connect the float value signal to our custom slot to update the spinbox
        self.view_signals.position_value_changed.connect(self.on_position_value_changed)

        self.view_signals.controls_enabled_changed.connect(self.set_controls_enabled)

    @Slot(float)
    def on_position_value_changed(self, value: float):
        """Slot to update the spinbox value from the ViewModel."""
        # Block signals to prevent an infinite feedback loop
        # (setValue -> valueChanged -> set_position -> model change -> signal -> setValue)
        self.position_spinbox.blockSignals(True)
        self.position_spinbox.setValue(value)
        self.position_spinbox.blockSignals(False)

    @Slot(bool)
    def set_controls_enabled(self, enabled: bool):
        """
        Enables or disables the motion controls (buttons and spinbox).
        The Connect/Disconnect button is excluded as it needs to be always active.
        """
        self.up_button.setEnabled(enabled)
        self.down_button.setEnabled(enabled)
        self.home_button.setEnabled(enabled)
        self.position_spinbox.setEnabled(enabled)
        self.set_position_label.setEnabled(enabled)

# ----------------------------------------------------------------------------
# 5. Main Application / Test Harness
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    from peripherals_ui.model import PeripheralModel

    from logger.logger_service import init_logger, get_logger
    logger = get_logger(__name__)
    init_logger()

    logger.info("Starting")

    app = QApplication(sys.argv)

    # 1. Create the Model
    the_model = PeripheralModel(device_name="ZStage")

    # 2. Create the ViewModel
    the_view_model = ZStageViewModel(model=the_model)

    # 3. Create the View
    the_view = ZStageView(view_model=the_view_model)

    # 4. Force initial state sync *after* bindings are set up
    the_view_model.force_initial_update()

    the_model.status = True
    the_model.realtime_mode = True

    # 5. Show the UI
    window = QMainWindow()
    window.setWindowTitle("Positioner MVVM Example")
    window.setCentralWidget(the_view)
    window.show()

    sys.exit(app.exec())