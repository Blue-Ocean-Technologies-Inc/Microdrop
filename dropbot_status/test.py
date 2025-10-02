import sys
import random
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QHBoxLayout
from PySide6.QtCore import QTimer

# Import all the components from your module
from displayed_UI import (
    DropbotStatusViewModelSignals,
    DropBotStatusViewModel,
    DropBotStatusView
)
from dropbot_status.model import DropBotStatusModel


class Window(QMainWindow):
    """
    A window that wraps the DropBotStatusView and provides controls
    to manipulate the underlying Model, demonstrating the reactive UI.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dropbot Status")
        self.resize(400, 150)

        # 1. --- Instantiate the MVVM components in order ---
        self.model = DropBotStatusModel()
        self.view_signals = DropbotStatusViewModelSignals()
        self.view_model = DropBotStatusViewModel(
            model=self.model,
            view_signals=self.view_signals
        )

        # The View is the UI component we are testing
        self.status_view = DropBotStatusView(view_signals=self.view_signals)

        # 2. --- Create controls that will ONLY interact with the model ---
        self.connect_button = QPushButton("Toggle Connection")
        self.chip_button = QPushButton("Toggle Chip Inserted")

        # 3. --- Connect controls to methods that change the model ---
        self.connect_button.clicked.connect(self._toggle_connection)
        self.chip_button.clicked.connect(self._toggle_chip)

        # 4. --- Set up a timer to simulate backend sensor updates ---
        self.simulation_timer = QTimer(self)
        self.simulation_timer.setInterval(1500)  # Update every 1.5 seconds
        self.simulation_timer.timeout.connect(self._simulate_backend_updates)
        self.simulation_timer.start()

        # 5. --- Lay out the window ---
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)

        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.addWidget(self.connect_button)
        controls_layout.addWidget(self.chip_button)

        main_layout.addWidget(self.status_view)
        main_layout.addWidget(controls_widget)

        self.setCentralWidget(main_widget)

    def _toggle_connection(self):
        """Changes the connection state on the model."""
        self.model.connected = not self.model.connected
        print(f"HARNESS: Set model.connected = {self.model.connected}")

    def _toggle_chip(self):
        """Changes the chip state on the model."""
        self.model.chip_inserted = not self.model.chip_inserted
        print(f"HARNESS: Set model.chip_inserted = {self.model.chip_inserted}")

    def _simulate_backend_updates(self):
        """Simulates receiving new sensor data from a backend."""
        if self.model.connected:
            cap = f"{random.uniform(10, 50):.2f} pF"
            volt = f"{random.uniform(3.0, 3.3):.2f} V"
            self.model.capacitance = cap
            self.model.voltage = volt
            print(f"HARNESS: Simulating backend update. Capacitance: {cap}")
        else:
            # If not connected, reset to default values
            self.model.capacitance = "-"
            self.model.voltage = "-"
            print("HARNESS: Simulating backend update (disconnected).")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())