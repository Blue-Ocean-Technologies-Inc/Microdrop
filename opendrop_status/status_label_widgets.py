from PySide6.QtGui import QPixmap, Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QWidget

from logger.logger_service import get_logger

logger = get_logger(__name__)

BORDER_RADIUS = 4


class OpenDropIconWidget(QLabel):
    """
    A scalable widget to display the OpenDrop icon and connection status color.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(60)
        self.setMaximumWidth(106)
        self.setFixedHeight(106)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._pixmap = QPixmap()

    def set_pixmap_from_path(self, path):
        self._pixmap = QPixmap(path)
        if self._pixmap.isNull():
            logger.warning(f"Failed to load image: {path}")
        self.update_scaled_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._pixmap.isNull():
            self.update_scaled_pixmap()

    def update_scaled_pixmap(self):
        scaled_pixmap = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled_pixmap)

    def set_status_color(self, color: str):
        self.setStyleSheet(f"background-color: {color}; border-radius: {BORDER_RADIUS}px;")


class OpenDropStatusGridWidget(QWidget):
    """Compact grid for OpenDrop status values."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(2)

        bold_font = self.font()
        bold_font.setBold(True)

        conn_label = QLabel("Connection:")
        conn_label.setFont(bold_font)
        self.connection_status = QLabel("Inactive")
        layout.addWidget(conn_label, 0, 0)
        layout.addWidget(self.connection_status, 0, 1)

        board_id_label = QLabel("Board ID:")
        board_id_label.setFont(bold_font)
        self.board_id = QLabel("-")
        layout.addWidget(board_id_label, 1, 0)
        layout.addWidget(self.board_id, 1, 1)

        t1_label = QLabel("Temp 1:")
        t1_label.setFont(bold_font)
        self.temperature_1 = QLabel("-")
        layout.addWidget(t1_label, 2, 0)
        layout.addWidget(self.temperature_1, 2, 1)

        t2_label = QLabel("Temp 2:")
        t2_label.setFont(bold_font)
        self.temperature_2 = QLabel("-")
        layout.addWidget(t2_label, 3, 0)
        layout.addWidget(self.temperature_2, 3, 1)

        t3_label = QLabel("Temp 3:")
        t3_label.setFont(bold_font)
        self.temperature_3 = QLabel("-")
        layout.addWidget(t3_label, 4, 0)
        layout.addWidget(self.temperature_3, 4, 1)

        feedback_label = QLabel("Feedback Ch:")
        feedback_label.setFont(bold_font)
        self.feedback_channels = QLabel("-")
        layout.addWidget(feedback_label, 5, 0)
        layout.addWidget(self.feedback_channels, 5, 1)

        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.setMaximumSize(self.sizeHint())
