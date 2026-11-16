# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Standalone visual demo of Touch mode: no plugins, no Redis.

The Touch mode box at the top switches the touch stylesheet block and the
touch event filter live, and the colour scheme switches light/dark. Below
is a gallery of what Touch mode changes:

  * steppers: TraitsUI spinners (one with a negative range), the shared
    SteppedSpinEditor (with a suffix) and DoubleSpinBoxEditor (decimals) —
    tap a value to type it on the number pad;
  * sliders (TraitsUI and the shared SteppedSliderEditor), check boxes,
    radio buttons, a combo box, a text field, tabs, a menu bar and a
    scrolling list;
  * tables: a TraitsUI table with spinner cells, the DictFloatTableEditor,
    and a tree whose numeric cells use the protocol tree's spin-box column
    views — their number pad opens straight away and OK commits through
    the delegate (each commit is printed);
  * Help mode: the ? toggle beside the switches (as in the status bar)
    turns it on; then touching any control, a disabled one included,
    shows its help bubble instead of operating it. Esc or Done ends it.

Run:
    pixi run python -m examples.demos.touch_mode_demo
"""

# Standard library imports.
import sys

# Enthought library imports.
from pyface.qt import QtGui, QtWidgets
from pyface.qt.QtCore import Qt
from traits.api import (
    Bool,
    Button,
    Dict,
    Enum,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Range,
    Str,
    observe,
)
from traitsui.api import (
    CustomEditor,
    HGroup,
    Item,
    ObjectColumn,
    RangeEditor,
    TableEditor,
    VGroup,
    View,
)

# Microdrop package imports.
from microdrop_application.touch_mode.controller import TouchModeController
from microdrop_application.touch_mode.help_controls import make_help_toggle_button
from pluggable_protocol_tree.views.columns.spinbox import (
    DoubleSpinBoxColumnView,
    IntSpinBoxColumnView,
)

# Microdrop style imports.
from microdrop_style.helpers import apply_color_scheme, style_app

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    DictFloatTableEditor,
    DoubleSpinBoxEditor,
    SteppedSliderEditor,
    SteppedSpinEditor,
)

#: (step, repeats, duration) rows of the protocol-style tree.
TREE_ROWS = (("Mix", 3, 1.5), ("Split", 1, 0.75), ("Merge", 2, 2.0))

#: Tooltips of the tree's columns, on their cells and header sections.
TREE_COLUMN_TOOLTIPS = (
    "The step's name",
    "How many times the step runs",
    "How long one run of the step lasts, in seconds",
)

#: (tab, tooltip) of the tab bar.
TABS = (
    ("Protocol", "The steps of the experiment"),
    ("Device", "The electrode layout"),
    ("Camera", "The live camera view"),
)


class DemoStep(HasTraits):
    """A row of the TraitsUI table."""

    name = Str()
    repeats = Range(1, 20)


class ColumnViewDelegate(QtWidgets.QStyledItemDelegate):
    """Edits numeric columns through the protocol tree's column views, as
    ProtocolItemDelegate does, and prints every commit."""

    def __init__(self, views, parent=None):
        super().__init__(parent)
        self._views = views

    def createEditor(self, parent, option, index):
        editor = self._views[index.column()].create_editor(parent, None)
        editor.setAutoFillBackground(True)

        return editor

    def setEditorData(self, editor, index):
        self._views[index.column()].set_editor_data(editor, index.data(Qt.EditRole))

    def setModelData(self, editor, model, index):
        value = self._views[index.column()].get_editor_data(editor)
        model.setData(index, value, Qt.EditRole)
        print(f"tree commit: row {index.row()} column {index.column()} -> {value}")


def build_qt_gallery(parent, editor):
    """Raw-Qt widgets TraitsUI has no editor for: a protocol-style tree,
    tabs, a menu bar and a scrolling list."""
    gallery = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(gallery)
    layout.setContentsMargins(0, 0, 0, 0)

    menu_bar = QtWidgets.QMenuBar()

    for title in ("File", "Edit", "Tools"):
        menu = menu_bar.addMenu(title)
        menu.addAction(f"{title} something")
        menu.addAction(f"{title} something else")

    layout.addWidget(menu_bar)

    tabs = QtWidgets.QTabBar()

    for title, tooltip in TABS:
        tabs.setTabToolTip(tabs.addTab(title), tooltip)

    layout.addWidget(tabs)

    model = QtGui.QStandardItemModel(0, 3)
    model.setHorizontalHeaderLabels(["Step", "Repeats", "Duration (s)"])

    for column, tooltip in enumerate(TREE_COLUMN_TOOLTIPS):
        model.setHeaderData(
            column, Qt.Orientation.Horizontal, tooltip, Qt.ItemDataRole.ToolTipRole
        )

    for name, repeats, duration in TREE_ROWS:
        step = QtGui.QStandardItem(name)
        step.setEditable(False)
        cells = [QtGui.QStandardItem(), QtGui.QStandardItem()]
        cells[0].setData(repeats, Qt.EditRole)
        cells[1].setData(duration, Qt.EditRole)
        row = [step, *cells]

        for item, tooltip in zip(row, TREE_COLUMN_TOOLTIPS):
            item.setToolTip(tooltip)

        model.appendRow(row)

    tree = QtWidgets.QTreeView()
    tree.setModel(model)
    tree.setRootIsDecorated(False)
    tree.setItemDelegateForColumn(
        1, ColumnViewDelegate({1: IntSpinBoxColumnView(low=1, high=100)}, tree)
    )
    tree.setItemDelegateForColumn(
        2, ColumnViewDelegate({2: DoubleSpinBoxColumnView(high=60.0)}, tree)
    )
    tree.setEditTriggers(
        QtWidgets.QAbstractItemView.DoubleClicked
        | QtWidgets.QAbstractItemView.SelectedClicked
    )
    layout.addWidget(tree)

    log = QtWidgets.QListWidget()
    log.setToolTip("What happened so far, newest last")
    log.addItems([f"Log line {number}" for number in range(1, 41)])
    log.setMaximumHeight(160)
    layout.addWidget(log)

    return gallery


class TouchModeDemo(HasTraits):
    """The gallery; every trait is edited by a different kind of editor."""

    #: Drives the TouchModeController, as the app preference does.
    touch_mode = Bool(False)

    color_scheme = Enum("light", "dark")

    voltage = Range(30, 200, 100)
    offset = Range(-50, 50, 0)
    frequency = Int(10000)
    duration = Float(1.5)
    brightness = Range(0.0, 1.0, 0.5)
    gain = Range(0, 100, 40)

    record = Bool(True)
    loop = Bool(False)
    direction = Enum("Forward", "Backward")
    mode = Enum("Fast", "Balanced", "Accurate")
    note = Str("Tap to type")

    #: Always disabled, to show Help mode describing a disabled control.
    calibrate = Button("Calibrate")

    thresholds = Dict(Str, Float, {"Electrode A": 1.5, "Electrode B": 2.25})
    steps = List(Instance(DemoStep))

    _controller = Instance(TouchModeController, ())

    def _steps_default(self):
        return [DemoStep(name="Mix", repeats=3), DemoStep(name="Split", repeats=1)]

    @observe("touch_mode")
    def _touch_mode_updated(self, event):
        self._controller.enabled = self.touch_mode

    @observe("color_scheme")
    def _color_scheme_updated(self, event):
        apply_color_scheme(self.color_scheme)

    @observe("voltage, offset, frequency, duration, thresholds, steps:items:repeats")
    def _value_updated(self, event):
        print(f"{event.name} -> {event.new}")


switches_group = HGroup(
    Item("touch_mode", label="Touch mode"),
    Item("color_scheme", label="Colour scheme"),
    Item(
        "_controller",
        show_label=False,
        editor=CustomEditor(lambda parent, editor: make_help_toggle_button()),
    ),
)

fields_group = VGroup(
    Item(
        "voltage",
        label="Voltage (spinner)",
        editor=RangeEditor(low=30, high=200, mode="spinner"),
        tooltip="High voltage applied to the actuated electrodes",
    ),
    Item(
        "offset",
        label="Offset (negative)",
        editor=RangeEditor(low=-50, high=50, mode="spinner"),
        tooltip="Offset added to the reading",
    ),
    Item(
        "frequency",
        editor=SteppedSpinEditor(low=100, high=10000, step=100, suffix=" Hz"),
        tooltip="Frequency of the actuation voltage",
    ),
    Item(
        "duration",
        label="Duration (s)",
        editor=DoubleSpinBoxEditor(low=0.0, high=60.0, decimals=2, step=0.25),
    ),
    Item("brightness", editor=SteppedSliderEditor(low=0.0, high=1.0, step=0.1)),
    Item("gain", editor=RangeEditor(low=0, high=100, mode="slider")),
    Item("record", tooltip="Record a video of the run"),
    Item("loop"),
    Item("direction", style="custom"),
    Item("mode"),
    Item("note"),
    Item(
        "calibrate",
        show_label=False,
        enabled_when="False",
        tooltip="Calibrates the capacitance reading; needs a connected DropBot",
    ),
    label="Fields",
    show_border=True,
)

tables_group = VGroup(
    Item(
        "thresholds",
        show_label=False,
        editor=DictFloatTableEditor(
            key_label="Electrode",
            value_label="Threshold (pF)",
            low=0.0,
            high=10.0,
            decimals=2,
        ),
    ),
    Item(
        "steps",
        show_label=False,
        editor=TableEditor(
            columns=[
                ObjectColumn(name="name", editable=False),
                ObjectColumn(
                    name="repeats", editor=RangeEditor(low=1, high=20, mode="spinner")
                ),
            ],
        ),
    ),
    Item("_controller", show_label=False, editor=CustomEditor(build_qt_gallery)),
    label="Tables and lists",
    show_border=True,
)

touch_mode_demo_view = View(
    VGroup(switches_group, HGroup(fields_group, tables_group)),
    title="Touch mode demo",
    width=1100,
    height=760,
    resizable=True,
    scrollable=True,
)


if __name__ == "__main__":
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    style_app(app)

    demo = TouchModeDemo()
    demo.touch_mode = True
    demo.configure_traits(view=touch_mode_demo_view)
