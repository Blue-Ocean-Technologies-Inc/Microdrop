# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for Help mode: where the bubble goes, and what help a point on
screen resolves to."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtCore import QPoint, QRect, QRectF, QSize, Qt
from pyface.qt.QtGui import QStandardItem, QStandardItemModel
from pyface.qt.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabBar,
    QTableView,
    QWidget,
)

# Microdrop package imports.
from microdrop_application.touch_mode.consts import (
    HELP_BUBBLE_ARROW_PX,
    HELP_BUBBLE_FINGER_CLEARANCE_PX,
)
from microdrop_application.touch_mode.help_bubble import place_bubble
from microdrop_application.touch_mode.help_resolver import resolve_help

# Microdrop style imports.
from microdrop_style.touch_style import TOUCH_RADIUS_PX

SCREEN = QRect(0, 0, 1280, 800)
BUBBLE = QSize(260, 90)


def test_bubble_goes_above_the_finger_and_points_at_it():
    anchor = QRect(600, 400, 160, 44)
    finger = QPoint(700, 420)

    top_left, arrow_x, below = place_bubble(BUBBLE, anchor, finger, SCREEN)
    bubble = QRect(top_left, BUBBLE)

    assert not below
    assert bubble.bottom() < finger.y() - HELP_BUBBLE_FINGER_CLEARANCE_PX
    assert top_left.x() + arrow_x == finger.x()


def test_bubble_flips_below_at_the_top_of_the_screen():
    anchor = QRect(600, 10, 160, 44)
    finger = QPoint(650, 30)

    top_left, _arrow_x, below = place_bubble(BUBBLE, anchor, finger, SCREEN)

    assert below
    assert top_left.y() > finger.y() + HELP_BUBBLE_FINGER_CLEARANCE_PX


def test_bubble_stays_on_screen_and_keeps_its_arrow_off_the_corners():
    anchor = QRect(1250, 500, 30, 30)
    finger = QPoint(1275, 510)

    top_left, arrow_x, _below = place_bubble(BUBBLE, anchor, finger, SCREEN)

    assert SCREEN.contains(QRect(top_left, BUBBLE))
    assert arrow_x <= BUBBLE.width() - TOUCH_RADIUS_PX - HELP_BUBBLE_ARROW_PX


def test_bubble_for_a_tall_control_stays_near_the_finger():
    anchor = QRect(100, 50, 400, 700)
    finger = QPoint(300, 600)

    top_left, _arrow_x, below = place_bubble(BUBBLE, anchor, finger, SCREEN)

    assert not below
    assert finger.y() - (top_left.y() + BUBBLE.height()) < 4 * (
        HELP_BUBBLE_FINGER_CLEARANCE_PX
    )


@pytest.fixture
def window(qapp):
    window = QWidget()
    window.resize(600, 400)
    grid = QGridLayout(window)

    label = QLabel("Voltage:")
    label.setToolTip("Specifies the voltage")
    spin_box = QSpinBox()
    spin_box.setToolTip("High voltage on the actuated electrodes")
    grid.addWidget(label, 0, 0)
    grid.addWidget(spin_box, 0, 1)

    button = QPushButton("Calibrate")
    button.setToolTip("Needs a connected DropBot")
    button.setEnabled(False)
    grid.addWidget(button, 1, 1)

    tabs = QTabBar()
    tabs.setTabToolTip(tabs.addTab("Device"), "The electrode layout")
    grid.addWidget(tabs, 2, 1)

    model = QStandardItemModel(1, 1)
    model.setHorizontalHeaderLabels(["Duration"])
    cell = QStandardItem("1.0")
    cell.setToolTip("Seconds one run lasts")
    model.setItem(0, 0, cell)
    table = QTableView()
    table.setModel(model)
    grid.addWidget(table, 3, 1)

    scene = QGraphicsScene(0, 0, 100, 100)
    electrode = QGraphicsRectItem(QRectF(0, 0, 100, 100))
    electrode.setToolTip("Electrode 7")
    scene.addItem(electrode)
    view = QGraphicsView(scene)
    grid.addWidget(view, 4, 1)

    window.show()
    qapp.processEvents()

    widgets = {
        "label": label,
        "spin_box": spin_box,
        "button": button,
        "tabs": tabs,
        "table": table,
        "view": view,
    }

    yield window, widgets

    window.close()


def help_at(window, widget, point=None):
    point = widget.rect().center() if point is None else point

    return resolve_help(widget.mapToGlobal(point), window)


def test_editor_takes_its_label_as_title(window):
    window, widgets = window

    topic = help_at(window, widgets["spin_box"])

    assert topic.title == "Voltage"
    assert topic.text == "High voltage on the actuated electrodes"


def test_label_speaks_for_its_editor(window):
    window, widgets = window

    topic = help_at(window, widgets["label"])

    assert topic.text == "High voltage on the actuated electrodes"


def test_disabled_button_resolves_by_position(window):
    window, widgets = window

    topic = help_at(window, widgets["button"])

    assert (topic.title, topic.text) == ("Calibrate", "Needs a connected DropBot")


def test_tab_cell_and_graphics_item_tooltips(window):
    window, widgets = window
    tabs, table, view = widgets["tabs"], widgets["table"], widgets["view"]

    tab_topic = help_at(window, tabs, tabs.tabRect(0).center())
    cell_rect = table.visualRect(table.model().index(0, 0))
    cell_topic = help_at(window, table.viewport(), cell_rect.center())
    item_topic = help_at(window, view.viewport())

    assert (tab_topic.title, tab_topic.text) == ("Device", "The electrode layout")
    assert (cell_topic.title, cell_topic.text) == ("Duration", "Seconds one run lasts")
    assert item_topic.text == "Electrode 7"


def test_control_without_any_tooltip_has_no_text(qapp):
    window = QWidget()
    button = QPushButton("Mystery", window)
    window.show()
    qapp.processEvents()

    topic = help_at(window, button)

    assert topic.title == "Mystery"
    assert topic.text == ""

    window.close()


def test_header_section_tooltip(window):
    window, widgets = window
    table = widgets["table"]
    table.model().setHeaderData(
        0, Qt.Orientation.Horizontal, "How long it lasts", Qt.ItemDataRole.ToolTipRole
    )
    header = table.horizontalHeader()

    topic = help_at(window, header.viewport(), QPoint(5, header.height() // 2))

    assert (topic.title, topic.text) == ("Duration", "How long it lasts")
