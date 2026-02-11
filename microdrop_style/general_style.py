# A selector string that targets common UI elements but avoids QMenu/Popups
# .QWidget matches exact QWidget instances (often used as containers) but not subclasses
TARGET_WIDGETS = (
    "QMainWindow, QDialog, QDockWidget, "
    ".QWidget, QFrame, QGroupBox, QScrollArea, "
    "QLabel, QRadioButton, QLineEdit, QTextEdit, "
    "QAbstractSpinBox, QProgressBar, QComboBox, QTabWidget, "
    "QTableView, QToolButton, QPushButton"
)

DARK_MODE_STYLESHEET = f"""
        {TARGET_WIDGETS} {{
            background-color: #2b2b2b;
            color: #ffffff;
            font-family: "Inter", sans-serif;
        }}

        """

LIGHT_MODE_STYLESHEET = f"""
        {TARGET_WIDGETS} {{
            background-color: #f0f0f0;
            color: #000000;
            font-family: "Inter", sans-serif;
        }}
        """

def get_general_style(theme):
    """Defines the base background and text color for the window/container."""
    if theme == "dark":
        return DARK_MODE_STYLESHEET
    else:
        return LIGHT_MODE_STYLESHEET
