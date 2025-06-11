from PySide6.QtWidgets import QWidget
from pyface.tasks.task_pane import TaskPane


class MicrodropCentralCanvas(TaskPane):
    id = "white_canvas.pane"
    name = "White Canvas Pane"

    def create(self, parent):
        widget = QWidget(parent)
        widget.setStyleSheet("background-color: white;")  # white background
        self.control = widget