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
    QDoubleSpinBox
)
from PySide6.QtCore import QObject, Signal, Slot
from traits.api import HasTraits, Instance, Str, Float, observe


# ----------------------------------------------------------------------------
# 1. The Model
# Holds the raw state of the positioner. It is UI-agnostic.
# ----------------------------------------------------------------------------
class PositionerModel(HasTraits):
    """Holds the raw state of the positioner device."""
    status = Str("Idle")
    position = Float(0.0)  # Position in mm


# ----------------------------------------------------------------------------
# 2. The ViewModel's Signal Bridge
# A dedicated QObject to hold Qt signals for thread-safe communication.
# ----------------------------------------------------------------------------
class PositionerViewModelSignals(QObject):
    """Holds Qt signals for the ViewModel to communicate with the View."""
    status_text_changed = Signal(str)
    position_text_changed = Signal(str)
    position_value_changed = Signal(float)  # Signal for the raw float value
    status_color_changed = Signal(str)  # Signal for the group box color


# ----------------------------------------------------------------------------
# 3. The ViewModel (The Logic)
# Contains all presentation logic. It knows the Model, but not the View.
# ----------------------------------------------------------------------------
class PositionerViewModel(HasTraits):
    """Manages the logic for the Positioner View."""
    model = Instance(PositionerModel)
    view_signals = Instance(PositionerViewModelSignals, ())  # Auto-creates an instance

    # --- Commands (for the View's buttons to call) ---

    def move_up(self):
        """Command to move the positioner up by 10mm."""
        if self.model.status == "Disconnected": return
        print("VIEWMODEL: 'Up' command received.")
        # In a real app, this would publish a message.
        # For this example, we modify the model directly.
        self.model.status = "Moving Up"
        self.model.position += 10.0
        self.model.status = "Idle"  # This will fire a second signal

    def move_down(self):
        """Command to move the positioner down by 10mm."""
        if self.model.status == "Disconnected": return
        print("VIEWMODEL: 'Down' command received.")
        self.model.status = "Moving Down"
        if self.model.position >= 10.0:
            self.model.position -= 10.0
        else:
            self.model.position = 0.0
        self.model.status = "Idle"

    def go_home(self):
        """Command to send the positioner to the home position."""
        if self.model.status == "Disconnected": return
        print("VIEWMODEL: 'Home' command received.")
        self.model.status = "Homing"
        self.model.position = 0.0
        self.model.status = "Homed"

    def set_position(self, value: float):
        """Command to set the positioner to a specific value."""
        if self.model.status == "Disconnected": return
        print(f"VIEWMODEL: 'set_position' command received: {value}")
        # The check to prevent loops is handled in the View
        self.model.status = "Moving to Position"
        self.model.position = value
        self.model.status = "Idle"

    def disconnect_device(self):
        """Command to simulate disconnecting the device."""
        print("VIEWMODEL: 'disconnect_device' command received.")
        if self.model.status == "Disconnected":
            self.model.status = "Idle"  # Reconnect
        else:
            self.model.status = "Disconnected"

    # --- Logic Methods ---
    # These contain the formatting logic, so observers are simple.

    def _update_status_display(self):
        """Formats and emits the current status."""
        new_status = self.model.status
        display_text = f"Status: {new_status}"
        print(f"VIEWMODEL: Updating status. Emitting: '{display_text}'")
        self.view_signals.status_text_changed.emit(display_text)

    def _update_position_display(self):
        """Formats and emits the current position as a string."""
        new_pos = self.model.position
        display_text = f"Position: {new_pos:.2f} mm"
        print(f"VIEWMODEL: Updating position text. Emitting: '{display_text}'")
        self.view_signals.position_text_changed.emit(display_text)

    # --- Observers (React to Model changes) ---

    @observe("model:status")
    def _on_status_changed(self, event):
        """Fires when model.status changes."""
        self._update_status_display()

        # Update color based on status
        if event.new == "Disconnected":
            self.view_signals.status_color_changed.emit("red")
        else:
            self.view_signals.status_color_changed.emit("green")

    @observe("model:position")
    def _on_position_changed(self, event):
        """Fires when model.position changes."""
        self._update_position_display()
        # Also emit the raw float value for the spin box
        print(f"VIEWMODEL: Emitting position value: {event.new}")
        self.view_signals.position_value_changed.emit(event.new)

    # --- Initializer ---

    def force_initial_update(self):
        """Pushes the current model state to the view's signals."""
        print("VIEWMODEL: Forcing initial update.")
        self._update_status_display()
        self._update_position_display()
        self.view_signals.position_value_changed.emit(self.model.position)


# ----------------------------------------------------------------------------
# 4. The View (The UI)
# Manages UI widgets only. Binds to the ViewModel and its signals.
# ----------------------------------------------------------------------------
class PositionerView(QWidget):
    """
    The View. Manages UI widgets only.
    Binds to the ViewModel's commands and its signals.
    """

    def __init__(self, view_model: PositionerViewModel, parent=None):
        super().__init__(parent)
        self.view_model = view_model
        # Get the signal bridge from the ViewModel
        self.view_signals = view_model.view_signals

        # --- Create Widgets ---
        self.status_label = QLabel("Status: ...")

        # Read-only label for displaying the current position
        self.current_position_label = QLabel("Position: ...")
        self.current_position_label.setMinimumWidth(120)  # Give it some space
        self.current_position_label.setContentsMargins(5, 2, 5, 2)  # Add padding

        # control buttons
        self.up_button = QPushButton("Up")
        self.down_button = QPushButton("Down")
        self.home_button = QPushButton("Home")

        # Position control spinbox
        self.set_position_label = QLabel("Set Position:")
        self.position_spinbox = QDoubleSpinBox()
        self.position_spinbox.setRange(0, 500)
        self.position_spinbox.setDecimals(2)
        self.position_spinbox.setSuffix(" mm")

        # --- Layout ---
        main_layout = QVBoxLayout(self)

        ################### Status display group ######################
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout()

        # Position layout (Display Label, Set Label, Spinbox)
        position_layout = QHBoxLayout()
        position_layout.addWidget(self.current_position_label)  # Add the new display label
        position_layout.addSpacing(10)  # Add some space

        status_layout.addWidget(self.status_label)
        status_layout.addLayout(position_layout)
        status_group.setLayout(status_layout)

        ###################### Control group ##########################
        control_group = QGroupBox("Controls")
        controls_layout = QVBoxLayout()
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
        control_group.setLayout(controls_layout)

        #############################################################

        main_layout.addWidget(status_group)
        main_layout.addWidget(control_group)

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

    @Slot(float)
    def on_position_value_changed(self, value: float):
        """Slot to update the spinbox value from the ViewModel."""
        # Block signals to prevent an infinite feedback loop
        # (setValue -> valueChanged -> set_position -> model change -> signal -> setValue)
        self.position_spinbox.blockSignals(True)
        self.position_spinbox.setValue(value)
        self.position_spinbox.blockSignals(False)


# ----------------------------------------------------------------------------
# 5. Main Application / Test Harness
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 1. Create the Model
    the_model = PositionerModel()

    # 2. Create the ViewModel
    the_view_model = PositionerViewModel(model=the_model)

    # 3. Create the View
    the_view = PositionerView(view_model=the_view_model)

    # 4. Force initial state sync *after* bindings are set up
    the_view_model.force_initial_update()

    # 5. Show the UI
    window = QMainWindow()
    window.setWindowTitle("Positioner MVVM Example")
    window.setCentralWidget(the_view)
    window.show()

    sys.exit(app.exec())