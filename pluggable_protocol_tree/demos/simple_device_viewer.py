"""5x5 grid widget for the demo. NOT the production device viewer.

Two modes:
  Static: clicks toggle electrode IDs into row.electrodes
  Route:  clicks append electrode IDs to an in-progress route;
          Finish Route commits to row.routes; Clear discards.

Live actuation overlay: set_actuated() is called by an external
listener (the demo's actuation subscription) and paints those cells
bright green. Wired in run_widget.py.
"""

from typing import Iterable, Optional, Set

from pyface.qt.QtCore import QPoint, QRect, Qt, Signal, Slot
from pyface.qt.QtGui import QBrush, QColor, QPainter, QPen
from pyface.qt.QtWidgets import (
    QButtonGroup, QGridLayout, QHBoxLayout, QPushButton, QRadioButton,
    QVBoxLayout, QWidget,
)


GRID_W = 5
GRID_H = 5
CELL_PX = 60
GRID_PADDING = 6


def _electrode_id(i: int) -> str:
    return f"e{i:02d}"


class SimpleDeviceViewer(QWidget):
    """Exposes set_active_row(row) and set_actuated(electrode_ids).
    Mutates row.electrodes / row.routes directly when the user clicks."""

    GRID_W = GRID_W
    GRID_H = GRID_H

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._active_row = None
        self._actuated: Set[str] = set()
        self._mode = "static"
        self._in_progress_route: list = []

        # Toolbar
        self._mode_static = QRadioButton("Static")
        self._mode_static.setChecked(True)
        self._mode_route = QRadioButton("Route")
        mode_group = QButtonGroup(self)
        mode_group.addButton(self._mode_static)
        mode_group.addButton(self._mode_route)
        self._mode_static.toggled.connect(self._on_mode_changed)

        self._finish_btn = QPushButton("Finish Route")
        self._clear_btn = QPushButton("Clear")
        self._finish_btn.clicked.connect(self._finish_route)
        self._clear_btn.clicked.connect(self._clear_route)
        self._finish_btn.setEnabled(False)
        self._clear_btn.setEnabled(False)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._mode_static)
        toolbar.addWidget(self._mode_route)
        toolbar.addWidget(self._finish_btn)
        toolbar.addWidget(self._clear_btn)
        toolbar.addStretch()

        outer = QVBoxLayout(self)
        outer.addLayout(toolbar)
        outer.addStretch()

        self.setMinimumSize(
            GRID_W * CELL_PX + 2 * GRID_PADDING,
            GRID_H * CELL_PX + 2 * GRID_PADDING + 40,
        )

    # ---------- public API ----------

    def set_active_row(self, row):
        """Called when the tree's selection changes AND when the
        executor's step_started fires."""
        self._active_row = row
        self._in_progress_route = []
        self._update_route_button_state()
        self.update()

    def set_actuated(self, electrode_ids: Iterable[str]):
        """Called by the actuation subscription with the current phase's
        electrode set. Paints those cells green on top of the static /
        route layers."""
        self._actuated = set(electrode_ids or [])
        self.update()

    @Slot(object)
    def set_actuated_qt_safe(self, electrode_ids):
        """Qt-decorated slot — the actuation listener calls this via
        QMetaObject.invokeMethod with QueuedConnection so the actual
        widget mutation runs on the GUI thread."""
        self.set_actuated(electrode_ids)

    # ---------- mode ----------

    def _on_mode_changed(self, _checked):
        self._mode = "static" if self._mode_static.isChecked() else "route"
        self._update_route_button_state()

    def _update_route_button_state(self):
        in_route_mode = self._mode == "route"
        self._finish_btn.setEnabled(in_route_mode and bool(self._in_progress_route))
        self._clear_btn.setEnabled(in_route_mode and bool(self._in_progress_route))

    # ---------- grid geometry ----------

    def _grid_origin(self) -> QPoint:
        return QPoint(GRID_PADDING, 40 + GRID_PADDING)

    def _cell_rect(self, idx: int) -> QRect:
        col = idx % GRID_W
        row = idx // GRID_W
        origin = self._grid_origin()
        return QRect(origin.x() + col * CELL_PX,
                     origin.y() + row * CELL_PX,
                     CELL_PX - 2, CELL_PX - 2)

    def _cell_center(self, idx: int) -> QPoint:
        r = self._cell_rect(idx)
        return QPoint(r.x() + r.width() // 2, r.y() + r.height() // 2)

    def _hit_cell(self, pt: QPoint) -> Optional[int]:
        for i in range(GRID_W * GRID_H):
            if self._cell_rect(i).contains(pt):
                return i
        return None

    # ---------- click handling ----------

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._active_row is None:
            return
        idx = self._hit_cell(event.position().toPoint())
        if idx is None:
            return
        eid = _electrode_id(idx)
        if self._mode == "static":
            current = list(self._active_row.electrodes)
            if eid in current:
                current.remove(eid)
            else:
                current.append(eid)
            self._active_row.electrodes = current
        else:
            self._in_progress_route.append(eid)
            self._update_route_button_state()
        self.update()

    def _finish_route(self):
        if self._active_row is not None and self._in_progress_route:
            self._active_row.routes = list(self._active_row.routes) + [
                list(self._in_progress_route),
            ]
        self._in_progress_route = []
        self._update_route_button_state()
        self.update()

    def _clear_route(self):
        self._in_progress_route = []
        self._update_route_button_state()
        self.update()

    # ---------- painting ----------

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        statics = set(getattr(self._active_row, "electrodes", []) or [])
        routes = list(getattr(self._active_row, "routes", []) or [])

        # 1. Cells
        for i in range(GRID_W * GRID_H):
            eid = _electrode_id(i)
            r = self._cell_rect(i)
            if eid in self._actuated:
                p.setBrush(QBrush(QColor(40, 220, 80)))    # bright green
            elif eid in statics:
                p.setBrush(QBrush(QColor(255, 230, 90)))   # yellow
            else:
                p.setBrush(QBrush(QColor(220, 220, 220)))  # light gray
            p.setPen(QPen(QColor(80, 80, 80), 1))
            p.drawRect(r)
            p.drawText(r, Qt.AlignCenter, eid)

        # 2. Route lines (solid)
        p.setPen(QPen(QColor(60, 60, 200), 3))
        for route in routes:
            for a, b in zip(route, route[1:]):
                ai = _id_to_idx(a)
                bi = _id_to_idx(b)
                if ai is None or bi is None:
                    continue
                p.drawLine(self._cell_center(ai), self._cell_center(bi))

        # 3. In-progress route (dashed)
        if self._in_progress_route:
            p.setPen(QPen(QColor(60, 60, 200), 2, Qt.DashLine))
            for a, b in zip(self._in_progress_route, self._in_progress_route[1:]):
                ai = _id_to_idx(a)
                bi = _id_to_idx(b)
                if ai is None or bi is None:
                    continue
                p.drawLine(self._cell_center(ai), self._cell_center(bi))
            # Outline the in-progress cells
            for eid in self._in_progress_route:
                idx = _id_to_idx(eid)
                if idx is not None:
                    p.setPen(QPen(QColor(60, 60, 200), 2, Qt.DashLine))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(self._cell_rect(idx))

        p.end()


def _id_to_idx(eid: str) -> Optional[int]:
    """'e07' -> 7. Returns None if the id isn't in this grid's namespace."""
    if not eid.startswith("e"):
        return None
    try:
        idx = int(eid[1:])
    except ValueError:
        return None
    if 0 <= idx < GRID_W * GRID_H:
        return idx
    return None
