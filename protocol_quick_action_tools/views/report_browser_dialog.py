"""File-manager-style dialog to browse and open session reports.

Ported from protocol_grid/extra_ui_elements.py:942-1064 (the legacy
class is fully decoupled from PGCWidget — only input is a list of path
strings). Kept verbatim except for the import path adjustments.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pyface.qt.QtCore import Qt, QUrl
from pyface.qt.QtGui import QDesktopServices
from pyface.qt.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)


class _ReportSortableTreeWidgetItem(QTreeWidgetItem):
    """QTreeWidgetItem subclass that sorts the Size column numerically
    and the Date column chronologically instead of lexicographically."""

    _SIZE_COL = 1
    _DATE_COL = 2

    def __lt__(self, other):
        col = self.treeWidget().sortColumn()
        if col == self._SIZE_COL:
            return ((self.data(col, Qt.UserRole) or 0)
                    < (other.data(col, Qt.UserRole) or 0))
        if col == self._DATE_COL:
            return ((self.data(col, Qt.UserRole) or 0)
                    < (other.data(col, Qt.UserRole) or 0))
        return super().__lt__(other)


class ReportBrowserDialog(QDialog):
    """Search-and-open dialog over a flat list of report HTML paths."""

    _COL_NAME = 0
    _COL_SIZE = 1
    _COL_DATE = 2

    def __init__(self, report_paths: List[str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Session Reports")
        self.setModal(True)
        self.setMinimumSize(650, 420)
        self._report_paths = report_paths
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- search bar ---
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Filter by file name...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._apply_filter)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self._search_box)
        layout.addLayout(search_layout)

        # --- file table ---
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Size", "Date Created"])
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSortingEnabled(True)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)

        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self._COL_NAME, QHeaderView.Stretch)
        header.setSectionResizeMode(self._COL_SIZE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self._COL_DATE, QHeaderView.ResizeToContents)

        for path_str in self._report_paths:
            p = Path(path_str)
            try:
                stat = os.stat(p)
                size_bytes = stat.st_size
                ctime = stat.st_ctime
            except OSError:
                size_bytes = 0
                ctime = 0.0

            item = _ReportSortableTreeWidgetItem([
                p.name,
                self._format_size(size_bytes),
                datetime.fromtimestamp(ctime).strftime("%Y-%m-%d  %H:%M:%S")
                if ctime else "",
            ])
            item.setToolTip(self._COL_NAME, str(p))
            item.setData(self._COL_NAME, Qt.UserRole, path_str)
            item.setData(self._COL_SIZE, Qt.UserRole, size_bytes)
            item.setData(self._COL_DATE, Qt.UserRole, ctime)
            self._tree.addTopLevelItem(item)

        self._tree.sortByColumn(self._COL_DATE, Qt.DescendingOrder)
        layout.addWidget(self._tree)

        # --- buttons ---
        button_layout = QHBoxLayout()
        open_btn = QPushButton("Open")
        open_btn.setDefault(True)
        open_btn.clicked.connect(self._open_selected)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(open_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

        self._tree.itemDoubleClicked.connect(self._open_item)

    def _apply_filter(self, text: str):
        text_lower = text.lower()
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            item.setHidden(text_lower not in item.text(self._COL_NAME).lower())

    def _open_selected(self):
        items = self._tree.selectedItems()
        if items:
            self._open_item(items[0])

    def _open_item(self, item):
        path_str = item.data(self._COL_NAME, Qt.UserRole)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path_str))

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.1f} MB"
