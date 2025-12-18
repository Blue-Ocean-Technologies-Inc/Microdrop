import logging
import sys
import os
import re
from multiprocessing import Process, Queue
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QMainWindow, QTextEdit, QToolBar,
                               QColorDialog, QWidget, QVBoxLayout,
                               QPushButton, QSizePolicy, QLabel)
from PySide6.QtGui import QAction, QIcon, QFont, QColor, QTextListFormat, QKeySequence
from PySide6.QtCore import Qt, QTimer

from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_style.colors import GREY, SECONDARY_SHADE, WHITE
from microdrop_style.font_paths import load_material_symbols_font, load_inter_font

from logger.logger_service import get_logger
logger = get_logger(__name__)


def get_readable_text_color(hex_bg):
    """
    Returns strictly Black or White based on background brightness.
    """
    bg = QColor(hex_bg)
    # Calculate luminance (standard formula)
    lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()

    # If bright (>128), text is Black. If dark, text is White.
    return "#000000" if lum > 128 else "#FFFFFF"


def _spacer():
    widget = QWidget()
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    widget.setStyleSheet(f"background: transparent; border: none;")

    return widget


# ===========================================================================
# 2. MODEL (Data Persistence)
# ===========================================================================
class StickyModel:
    def __init__(self, base_dir="Notes", experiment_name="None"):
        self.base_dir = Path(base_dir) / 'Notes'
        self.experiment = experiment_name

        self.current_filename = None

        self.current_color = "#FFF7D1"  # Default Yellow

        self.base_dir.mkdir(exist_ok=True)

    def _get_next_filename(self):
        existing_files = os.listdir(self.base_dir)
        max_index = 0
        pattern = re.compile(r"(\d+)\.html")
        for f in existing_files:
            match = pattern.match(f)
            if match:
                index = int(match.group(1))
                if index > max_index:
                    max_index = index
        return f"{max_index + 1}"

    def save_note(self, html_content):
        if not self.current_filename:
            self.current_filename = self._get_next_filename()

        full_path = (self.base_dir / self.current_filename).with_suffix(".html")
        try:
            # We save the div with the specific color context
            full_html = f"<div style='background-color:{self.current_color}; height:100%;'>{html_content}</div>"
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(full_html)
            return True, full_path
        except Exception as e:
            return False, str(e)

    def set_color(self, hex_color):
        self.current_color = hex_color


# ===========================================================================
# 3. VIEW (Frameless Window)
# ===========================================================================
class StickyView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.resize(320, 320)

        self.setWindowIcon(QIcon.fromTheme("sticky_note"))

        if parent is None:
            self.setWindowFlags(Qt.WindowStaysOnTopHint)

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.setLayout(self.main_layout)

        self.file_save_label = QLabel("Unsaved")

        # --- ACTIONS, SHORTCUTS & TOOLTIPS ---

        # 1. Close
        self.act_close = QAction("close", self)
        self.act_close.setShortcut(QKeySequence.Close)  # Standard Close (Ctrl+W)
        self.act_close.setToolTip("Close Note (Ctrl+W)")
        self.addAction(self.act_close)

        # 2. Save
        self.act_save = QAction("save", self)
        self.act_save.setShortcut(QKeySequence.Save)  # Standard Save (Ctrl+S)
        self.act_save.setToolTip("Save Note (Ctrl+S)")
        self.addAction(self.act_save)

        # 3. Formatting
        self.act_bold = QAction("format_bold", self)
        self.act_bold.setCheckable(True)
        self.act_bold.setShortcut(QKeySequence.Bold)  # Standard Bold (Ctrl+B)
        self.act_bold.setToolTip("Bold (Ctrl+B)")
        self.addAction(self.act_bold)

        self.act_italic = QAction("format_italic", self)
        self.act_italic.setCheckable(True)
        self.act_italic.setShortcut(QKeySequence.Italic)  # Standard Italic (Ctrl+I)
        self.act_italic.setToolTip("Italic (Ctrl+I)")
        self.addAction(self.act_italic)

        self.act_underline = QAction("format_underlined", self)
        self.act_underline.setCheckable(True)
        self.act_underline.setShortcut(QKeySequence.Underline)  # Standard Underline (Ctrl+U)
        self.act_underline.setToolTip("Underline (Ctrl+U)")
        self.addAction(self.act_underline)

        self.act_strike = QAction("strikethrough_s", self)
        self.act_strike.setCheckable(True)
        self.act_strike.setShortcut("Ctrl+Shift+S")
        self.act_strike.setToolTip("Strikethrough (Ctrl+Shift+S)")
        self.addAction(self.act_strike)

        self.act_list = QAction("format_list_bulleted", self)
        self.act_list.setCheckable(True)
        self.act_list.setShortcut("Ctrl+Shift+L")
        self.act_list.setToolTip("Bullet List (Ctrl+Shift+L)")
        self.addAction(self.act_list)

        self.act_color = QAction("format_color_fill", self)
        self.act_color.setToolTip("Change Background Color")

        # --- TOOLBAR SETUP ---

        # 1. Top Draggable Toolbar
        self.top_bar = QToolBar()
        self.top_bar.addAction(self.act_save)
        self.top_bar.addWidget(self.file_save_label)
        self.top_bar.addWidget(_spacer())
        self.top_bar.addAction(self.act_color)
        self.top_bar.addAction(self.act_close)

        # 2. Editor Area
        self.editor = QTextEdit()
        self.editor.setFont(QFont("Comic Sans MS", 12))
        self.editor.setFrameStyle(0)

        # 3. Bottom Toolbar
        self.bottom_bar = QToolBar()
        self.bottom_bar.addAction(self.act_bold)
        self.bottom_bar.addAction(self.act_italic)
        self.bottom_bar.addAction(self.act_underline)
        self.bottom_bar.addAction(self.act_strike)
        self.bottom_bar.addAction(self.act_list)

        self.main_layout.addWidget(self.top_bar)
        self.main_layout.addWidget(self.editor)
        self.main_layout.addWidget(self.bottom_bar)

        self.set_background_color("#FFF7D1")

    def set_background_color(self, hex_bg):
        text_color = get_readable_text_color(hex_bg)
        self.setStyleSheet(f"""
            QWidget {{ background-color: {hex_bg}; border: 1px solid #999; }}
            QLabel {{ color: {text_color}; }}
            /* Ensure tooltips are readable regardless of theme */
            QToolTip {{ color: #000000; background-color: #FFFFE0; border: 1px solid #888; }}
        """)
        self.editor.setStyleSheet(f"background-color: transparent; color: {text_color};")

        style = f"""
        QToolBar {{background: transparent; border: none;}}
        QToolButton {{
            font-family: {ICON_FONT_FAMILY};
            font-size: 18px;
            width: 24px; height: 24px;
            border: none; background: transparent; color: {text_color};
        }}
        QToolButton:checked {{
            background-color: {SECONDARY_SHADE[800]};
            border-color: {SECONDARY_SHADE[900]}; color: {WHITE};
        }}
        QToolButton:pressed {{background-color: {GREY['dark']};}}
        QLabel {{border: none; color: {text_color};}}
        """
        self.top_bar.setStyleSheet(style)
        self.bottom_bar.setStyleSheet(style)

    def get_html(self):
        return self.editor.toHtml()


# ===========================================================================
# 4. CONTROLLER & LAUNCHER
# ===========================================================================
class StickyController:
    def __init__(self, model: 'StickyModel', view: 'StickyView'):
        self.model = model
        self.view = view

        self._connect_signals()

        self.view.set_background_color(self.model.current_color)
        self.view.setWindowTitle(f"Exp: {self.model.experiment}")

    def _connect_signals(self):
        self.view.act_bold.triggered.connect(self.toggle_bold)
        self.view.act_italic.triggered.connect(self.toggle_italic)
        self.view.act_underline.triggered.connect(self.toggle_underline)
        self.view.act_strike.triggered.connect(self.toggle_strike)
        self.view.act_list.triggered.connect(self.toggle_list)

        self.view.act_save.triggered.connect(self.save_note)
        self.view.act_color.triggered.connect(self.pick_color)
        self.view.editor.cursorPositionChanged.connect(self.update_ui_state)
        self.view.editor.textChanged.connect(self.text_changed)

    def text_changed(self, *args, **kwargs):
        if self.model.current_filename:
            self.view.editor.setPlaceholderText(f"Unsaved changes ({self.model.current_filename})")
            self.view.file_save_label.setText(f"Unsaved changes ({self.model.current_filename})")

    def save_note(self):
        success, result = self.model.save_note(self.view.get_html())
        if success:
            self.view.editor.setPlaceholderText(f"Saved ({self.model.current_filename})")
            self.view.file_save_label.setText(f"Saved ({self.model.current_filename})")
            logger.info(f"Saved to {result}")
        else:
            logger.error("Error saving")

    def pick_color(self):
        color = QColorDialog.getColor(initial=QColor(self.model.current_color))
        if color.isValid():
            hex_color = color.name()
            self.model.set_color(hex_color)
            self.view.set_background_color(hex_color)
            self.save_note()

    def toggle_bold(self):
        self._fmt(lambda f: f.setFontWeight(QFont.Normal if f.fontWeight() > QFont.Normal else QFont.Bold))

    def toggle_italic(self):
        self._fmt(lambda f: f.setFontItalic(not f.fontItalic()))

    def toggle_underline(self):
        self._fmt(lambda f: f.setFontUnderline(not f.fontUnderline()))

    def toggle_strike(self):
        self._fmt(lambda f: f.setFontStrikeOut(not f.fontStrikeOut()))

    def toggle_list(self):
        cursor = self.view.editor.textCursor()
        cursor.beginEditBlock()

        if cursor.currentList():
            # If currently in a list, remove list formatting by setting standard block formatting
            block_fmt = cursor.blockFormat()
            block_fmt.setObjectIndex(-1)  # Detaches block from list
            cursor.setBlockFormat(block_fmt)
        else:
            # Create a standard bullet list
            list_fmt = QTextListFormat()
            list_fmt.setStyle(QTextListFormat.Style.ListDisc)
            cursor.createList(list_fmt)

        cursor.endEditBlock()
        self.view.editor.setFocus()

    def _fmt(self, func):
        fmt = self.view.editor.currentCharFormat()
        func(fmt)
        self.view.editor.setCurrentCharFormat(fmt)

    def update_ui_state(self):
        fmt = self.view.editor.currentCharFormat()
        self.view.act_bold.setChecked(fmt.fontWeight() == QFont.Bold)
        self.view.act_italic.setChecked(fmt.fontItalic())
        self.view.act_underline.setChecked(fmt.fontUnderline())
        self.view.act_strike.setChecked(fmt.fontStrikeOut())
        self.view.act_list.setChecked(bool(self.view.editor.textCursor().currentList()))


class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sticky Manager")
        self.resize(300, 100)
        self.active_notes = []

        central = QWidget()
        layout = QVBoxLayout()

        btn = QPushButton("＋ New Desktop Note")
        btn.setFont(QFont("Segoe UI", 12))
        btn.setMinimumHeight(40)
        btn.clicked.connect(self.launch_note)

        layout.addWidget(btn)
        central.setLayout(layout)
        self.setCentralWidget(central)

    def launch_note(self):
        model = StickyModel()
        view = StickyView()
        ctrl = StickyController(model, view)
        view.show()
        self.active_notes.append(ctrl)

class QueueLogHandler(logging.Handler):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        try:
            # Format the message (adds timestamp, level, etc.)
            msg = self.format(record)
            # Send string to Main Process
            self.queue.put(msg)
        except Exception:
            self.handleError(record)

def run_sticky_manager(command_queue, log_queue):
    """
    Runs in a SEPARATE process.
    Loads Qt once, then waits for commands.
    """
    # 1. Initialize Qt (Heavy lifting happens only once here)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # --- SETUP LOGGING FOR DAEMON ---
    # This redirects all logs in this process to the queue
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Create our custom handler
    queue_handler = QueueLogHandler(log_queue)
    root_logger.addHandler(queue_handler)

    # 2. Load heavy resources
    load_material_symbols_font()
    QIcon.setThemeName("Material Symbols Outlined")

    # 3. Keep references to prevent Garbage Collection
    active_notes = []

    def check_queue():
        """Polled by QTimer to check for new requests"""
        while not command_queue.empty():
            command_data = command_queue.get()
            cmd_type = command_data[0]

            if cmd_type == "NEW":
                _, base_dir, exp_name = command_data

                # --- NEW LOGIC: Check for existing window ---
                existing_ctrl = None

                # Filter out closed windows first (optional cleanup)
                active_notes[:] = [c for c in active_notes if c.view.isVisible()]

                for ctrl in active_notes:
                    # Check if model matches the requested parameters
                    # We compare string paths to be safe
                    if (str(ctrl.model.base_dir) == str(Path(base_dir) / 'Notes') and
                            ctrl.model.experiment == exp_name):
                        existing_ctrl = ctrl
                        break

                if existing_ctrl:
                    logger.info(f"Daemon: Note for {exp_name} already exists. Showing it.")
                    # Bring existing window to front
                    if existing_ctrl.view.isMinimized():
                        existing_ctrl.view.showNormal()
                    existing_ctrl.view.show()
                    existing_ctrl.view.raise_()
                    existing_ctrl.view.activateWindow()
                else:
                    logger.info(f"Daemon: Creating note for {exp_name} in {base_dir}")
                    # Create MVP
                    model = StickyModel(base_dir, exp_name)
                    view = StickyView()  # Top level
                    ctrl = StickyController(model, view)
                    view.show()
                    active_notes.append(ctrl)
                # ---------------------------------------------

            elif cmd_type == "TERMINATE":
                logger.info("Daemon: Shutting down.")
                app.quit()

    # 4. QTimer polls the queue efficiently
    timer = QTimer()
    timer.timeout.connect(check_queue)
    timer.start(500)  # Check every 500ms (Changed from 1000 for better responsiveness)

    logger.info("Sticky Note Daemon Started. Waiting for commands...")
    sys.exit(app.exec())


# ===========================================================================
# 3. THE LAUNCHER (Your API)
# ===========================================================================
class NoteLauncher:
    """
    A helper class you can use anywhere in your main app.
    It manages the connection to the background daemon.
    """

    def __init__(self):
        self.daemon_process = None

    def start_daemon(self):
        if self.daemon_process and self.daemon_process.is_alive():
            logger.info("Daemon already running.")
            return

        # Create Queue
        self.command_queue = Queue()
        self.log_queue = Queue()

        # Start Process
        self.daemon_process = Process(target=run_sticky_manager,
                                      args=(self.command_queue, self.log_queue))

        self.daemon_process.start()
        logger.info("Launcher: Daemon process started.")

    def request_new_note(self, base_dir="Notes", experiment_name="General"):
        if not (self.command_queue and self.daemon_process and self.daemon_process.is_alive()):
            logger.error("Launcher Error: Daemon is not running. Starting it now...")
            self.start_daemon()

        # Send tuple safely (No string parsing needed!)
        self.command_queue.put(("NEW", base_dir, experiment_name))

    def shutdown(self):
        if self.command_queue:
            self.command_queue.put(("TERMINATE",))
        if self.daemon_process:
            self.daemon_process.join()


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)

    # Load the Material Symbols font
    load_material_symbols_font()
    # load inter font and set with some size
    LABEL_FONT_FAMILY = load_inter_font()

    app.setFont(QFont(LABEL_FONT_FAMILY, 11))
    QIcon.setThemeName("Material Symbols Outlined")

    launcher = LauncherWindow()
    launcher.launch_note()
    sys.exit(app.exec())