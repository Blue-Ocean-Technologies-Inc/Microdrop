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
        self.disconnect_button = QPushButton("Connect/Disconnect")  # Add disconnect button

        # Position control spinbox
        self.set_position_label = QLabel("Set Position:")
        self.position_spinbox = QDoubleSpinBox()
        self.position_spinbox.setRange(0, 500)
        self.position_spinbox.setDecimals(2)
        self.position_spinbox.setSuffix(" mm")

        # --- Layout ---
        main_layout = QVBoxLayout(self)

        ################### Status display group ######################
        self.status_group = QGroupBox("Status")  # Store as self.status_group

        status_layout = QHBoxLayout()

        status_layout.addWidget(self.status_color_box)

        # We will now use a single QHBoxLayout for all status info
        status_text_layout = QVBoxLayout()

        # Add the read only labels
        status_text_layout.addWidget(self.status_label)
        status_text_layout.addWidget(self.current_position_label)

        status_layout.addLayout(status_text_layout)

        self.status_group.setLayout(status_layout)

        ###################### Control group ##########################
        control_group = QGroupBox("Controls")
        controls_layout = QVBoxLayout()
        controls_buttons_layout = QHBoxLayout()
        position_controls_layout = QHBoxLayout()

        # display buttons horizontally
        controls_buttons_layout.addWidget(self.up_button)
        controls_buttons_layout.addWidget(self.down_button)
        controls_buttons_layout.addWidget(self.home_button)
        controls_buttons_layout.addWidget(self.disconnect_button)  # Add button to layout

        # display position label and spin box horizontally aligned
        position_controls_layout.addWidget(self.set_position_label)
        position_controls_layout.addWidget(self.position_spinbox)

        controls_layout.addLayout(controls_buttons_layout)
        controls_layout.addLayout(position_controls_layout)
        control_group.setLayout(controls_layout)

        #############################################################

        main_layout.addWidget(self.status_group)
        main_layout.addWidget(control_group)

        # --- Data Binding ---

        # Connect buttons (View) -> commands (ViewModel)
        self.up_button.clicked.connect(self.view_model.move_up)
        self.down_button.clicked.connect(self.view_model.move_down)
        self.home_button.clicked.connect(self.view_model.go_home)
        self.disconnect_button.clicked.connect(self.view_model.disconnect_device)  # Connect button
        self.position_spinbox.valueChanged.connect(self.view_model.set_position)

        # Connect signals (ViewModel) -> slots (View widgets)
        self.view_signals.status_text_changed.connect(self.status_label.setText)

        # Connect the formatted text signal to our new display label
        self.view_signals.position_text_changed.connect(self.current_position_label.setText)

        # Connect the float value signal to our custom slot to update the spinbox
        self.view_signals.position_value_changed.connect(self.on_position_value_changed)

        # Connect the color signal to our new slot
        self.view_signals.status_color_changed.connect(self.on_status_color_changed)

    @Slot(float)
    def on_position_value_changed(self, value: float):
        """Slot to update the spinbox value from the ViewModel."""
        # Block signals to prevent an infinite feedback loop
        # (setValue -> valueChanged -> set_position -> model change -> signal -> setValue)
        self.position_spinbox.blockSignals(True)
        self.position_spinbox.setValue(value)
        self.position_spinbox.blockSignals(False)

    @Slot(str)
    def on_status_color_changed(self, color: str):
        """Updates the border color of the status group box."""
        # This CSS sets a border and ensures the groupbox title is visible
        self.status_group.setStyleSheet(f"""
            QGroupBox {{
                border: 2px solid {color};
                border-radius: 5px;
                margin-top: 6px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 7px;
                padding: 0px 5px 0px 5px;
            }}
        """)

        # Set the background color of the new status box
        self.status_color_box.setStyleSheet(f"""
                    QLabel {{
                        background-color: {color};
                        border: 1px solid #555;
                        border-radius: 5px;
                    }}
                """)


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

    # 5. Show the UI
    window = QMainWindow()
    window.setWindowTitle("Positioner MVVM Example")
    window.setCentralWidget(the_view)
    window.show()

    sys.exit(app.exec())