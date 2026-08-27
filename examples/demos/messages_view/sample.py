# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QDialog, QVBoxLayout, QTextBrowser, QHBoxLayout
from PySide6.QtCore import QFile, QTextStream

class HtmlPopup(QDialog):
    def __init__(self, file_path):
        super().__init__()

        self.setWindowTitle("HTML Popup")

        # Create a QTextBrowser widget
        self.browser = QTextBrowser()

        # Load the HTML file
        self.load_html(file_path)

        # Create a close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)

        # Set layout
        layout = QVBoxLayout()
        layout.addWidget(self.browser)
        layout.addWidget(close_button)
        self.setLayout(layout)

    def load_html(self, file_path):
        file = QFile(file_path)
        if file.open(QFile.ReadOnly | QFile.Text):
            stream = QTextStream(file)
            self.browser.setHtml(stream.readAll())
        file.close()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Create a button
        self.button = QPushButton("Show HTML Popup")
        self.button.clicked.connect(self.show_popup)

        # Set the button as the central widget
        self.setCentralWidget(self.button)

    def show_popup(self):
        popup = HtmlPopup('sample.html')
        popup.exec()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
