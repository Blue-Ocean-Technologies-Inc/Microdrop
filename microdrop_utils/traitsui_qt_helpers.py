from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QColor, QFont, QShortcut, QKeySequence, QPixmap
from pyface.qt.QtWidgets import QStyledItemDelegate, QDoubleSpinBox
from pyface.qt import QtWidgets

from traits.api import Instance, Any, Bool, Range, List, Str, Int, Property, Float
from traitsui.api import (ObjectColumn as ObjectTableColumn_, TableColumn as TableColumn_,
                          UIInfo, Handler, RangeEditor, BasicEditorFactory)
from traitsui.qt.editor import Editor as QtEditor

from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_style.colors import WHITE, BLACK
from microdrop_style.helpers import is_dark_mode
from microdrop_style.icons.icons import ICON_VISIBILITY, ICON_VISIBILITY_OFF, ICON_SELECT_All, ICON_DESELECT
from microdrop_utils.pyside_helpers import _ScalingPixmapLabel, MarqueeComboBox

from logger.logger_service import get_logger
logger = get_logger(__name__)


class TableColumn(TableColumn_):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.cell_color = None
        self.read_only_cell_color = None

    def get_text_color(self, object):
        """Returns the text color for the column for a specified object."""
        return WHITE if is_dark_mode() else BLACK


class ObjectColumn(ObjectTableColumn_):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.cell_color = None
        self.read_only_cell_color = None

    def get_text_color(self, object):
        """Returns the text color for the column for a specified object."""
        return "white" if is_dark_mode() else "black"


class ColorRenderer(QStyledItemDelegate):
    def paint(self, painter, option, index):
        value = index.data()
        color = QColor(value)

        painter.save()

        # Draw the rectangle with the given color
        rect = option.rect
        painter.setBrush(color)
        painter.setPen(color)
        painter.drawRect(rect)

        painter.restore()


class ColorColumn(ObjectColumn):
    def __init__(self, **traits):  # Stolen from traitsui/extra/checkbox_column.py
        """Initializes the object."""
        super().__init__(**traits)

        # force the renderer to be our color renderer
        self.renderer = ColorRenderer()


class CustomCheckboxColumn(ObjectColumn):
    def __init__(self, **traits: Any):
        super().__init__(**traits)
        self.format_func = self.formatter
        self.text_font = QFont(ICON_FONT_FAMILY, 15)

    def formatter(self, value):  # No self since were just passing it as a function
        return ICON_SELECT_All if value else ICON_DESELECT

    def on_click(self, object):
        current_val = object.trait_get(self.name)[self.name]
        object.trait_set(**{self.name: not current_val})


class VisibleColumn(CustomCheckboxColumn):
    def formatter(self, value):
        return ICON_VISIBILITY if value else ICON_VISIBILITY_OFF


######## We have to define a new range column to properly handle range traits with spin boxes ########
class RangeColumn(ObjectColumn):
    editing_object_key = Str

    def __init__(self, **traits):
        super().__init__(**traits)
        self.editing_object_key = ""

        ### traitsui renders the static read-mode label and the editor labels
        ### when in edit-mode we have to check which row is edited and remove the static read-mode text
        self.format_func = self.formatter

    def formatter(
        self, value, object
    ):  # No self since were just passing it as a function
        if object.key == self.editing_object_key:
            return ""
        return value

    def get_editor(self, object):
        """Gets the editor for the column of a specified object."""

        # get the editor returned by super class to obtain some trait values for modified editor.
        _editor = super().get_editor(object)

        ### the current edited row object key is set here
        self.editing_object_key = object.key

        ### We have to override the del method of the range editor so when the edit mode is exited and del is called,
        ### we indicate that none of the rows are edited by setting the editing_object_key to "".
        ### to do this we need to apss the reference of this "parent_column" object to the range editor

        ### This is a major hack!
        ### TODO: Figure out better way to do this.

        class _RangeEditor(RangeEditor):
            parent_column = Instance(RangeColumn)

            def __del__(self):
                self.parent_column.editing_object_key = ""

        editor = _RangeEditor(
            low=_editor.low, high=_editor.high, mode=_editor.mode, parent_column=self
        )

        return editor

    def get_value(self, object):
        """Gets the formatted value of the column for a specified object."""
        try:
            if self.format_func is not None:
                return self.format_func(self.get_raw_value(object), object)

            return self.format % (self.get_raw_value(object),)
        except:
            logger.error(
                "Error occurred trying to format a %s value" % self.__class__.__name__
            )
            return "Format!"

## --------------------------------------------------------
# Range editing spinner box with custom increments
## --------------------------------------------------------

class _SteppedSpinEditor(QtEditor):
    """The actual Qt implementation of the spin box."""

    def init(self, parent):
        """Initializes the editor by creating the underlying toolkit widget."""
        # Use QDoubleSpinBox for floats. (Use QSpinBox for ints).
        self.control = QtWidgets.QSpinBox()

        # Configure range bounds from the factory
        self.control.setMinimum(self.factory.low)
        self.control.setMaximum(self.factory.high)

        if self.factory.suffix:
            self.control.setSuffix(self.factory.suffix)

        self.control.setSingleStep(self.factory.step)

        # Connect the Qt signal to update the Trait value
        self.control.valueChanged.connect(self.update_object)

    def update_object(self, value):
        """Handles the user changing the value in the GUI."""
        self.value = value

    def update_editor(self):
        """Updates the GUI when the Trait changes externally."""
        if self.control is not None:
            # Block signals temporarily to prevent an infinite update loop
            self.control.blockSignals(True)
            self.control.setValue(self.value)
            self.control.blockSignals(False)


class SteppedSpinEditor(BasicEditorFactory):
    """The factory class passed into the Item's editor parameter."""

    klass = Property

    # Expose custom parameters to the TraitsUI Item
    step = Int(1)
    suffix = Str("")
    low = Int(-1000000)  # Default arbitrary low bound
    high = Int(1000000)  # Default arbitrary high bound

    def _get_klass(self):
        return _SteppedSpinEditor


class RangeWithSteppedSpinViewHint(Range):
    def create_editor(self):
        """ Returns the default UI editor for the trait.
        """
        return SteppedSpinEditor(
            low=self._low,
            high=self._high,
            step=self._metadata.get("step", 1),
            suffix=self._metadata.get("suffix", ""),
        )


class RangeWithViewHints(Range):
    def create_editor(self):
        """ Returns the default UI editor for the trait.
        """
        # fixme: Needs to support a dynamic range editor.

        auto_set = self.auto_set
        if auto_set is None:
            auto_set = True

        from traitsui.api import RangeEditor

        return RangeEditor(
            self,
            mode=self.mode or "auto",
            cols=self.cols or 3,
            auto_set=auto_set,
            enter_set=self.enter_set or False,
            low_label=self.low or "",
            high_label=self.high or "",
            low_name=self._low_name,
            high_name=self._high_name,
            format_str='%.2f',
            is_float=True
        )


class _DoubleSpinBoxEditor(QtEditor):
    def init(self, parent):
        """ This method builds the native Qt widget. """
        self.control = QDoubleSpinBox()
        self.control.setMinimum(self.factory.low)
        self.control.setMaximum(self.factory.high)
        self.control.setDecimals(self.factory.decimals)
        self.control.setSingleStep(self.factory.step)

        # When the user clicks the arrows, update the Trait
        self.control.valueChanged.connect(self.update_object)

    def update_object(self, value):
        """ Sync UI changes back to the Python model. """
        self.value = value

    def update_editor(self):
        """ Sync Python model changes back to the UI. """
        self.control.setValue(self.value)


class DoubleSpinBoxEditor(BasicEditorFactory):
    # Link the factory to the Editor class we just made
    klass = _DoubleSpinBoxEditor

    # Define the arguments we can pass to the editor in the View
    low = Float(0.0)
    high = Float(100.0)
    decimals = Int(1)
    step = Float(0.1)  # How much it increments when arrows are clicked


class _SentinelDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox whose minimum is a sentinel value displayed as text
    (Qt's specialValueText mechanism — applies exactly at the minimum).
    Stepping snaps between the sentinel and the real range instead of
    passing through the values in between, and any typed value below the
    real range lands on the sentinel."""

    def __init__(self, sentinel_value, real_low, parent=None):
        super().__init__(parent)
        self._sentinel_value = sentinel_value
        self._real_low = real_low

    def stepBy(self, steps):
        if steps < 0 and self.value() <= self._real_low:
            self.setValue(self._sentinel_value)
        elif steps > 0 and self.value() < self._real_low:
            self.setValue(self._real_low)
        else:
            super().stepBy(steps)

    def value(self):
        raw = super().value()
        return self._sentinel_value if raw < self._real_low else raw


class _DictFloatTableEditor(QtEditor):
    """Two-column table over a Dict(Str, Float) trait: read-only keys in
    the first column, a float spinbox per value in the second. Keys come
    from the dict itself; the editor only changes values."""

    def init(self, parent):
        self.control = QtWidgets.QTableWidget()
        self.control.setColumnCount(2)
        self.control.setHorizontalHeaderLabels(
            [self.factory.key_label, self.factory.value_label])
        self.control.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch)
        self.control.verticalHeader().setVisible(False)
        self._updating_object = False
        # No update_editor() call here — TraitsUI invokes it right after
        # init. A manual extra pass left the replaced cell spinboxes
        # orphaned (undeleted, stacked over the first cell).

    def update_object(self, key, spinbox_value):
        """Sync one spinbox change back to the dict trait (re-assigned
        whole so trait observers and preference persistence fire)."""
        updated = dict(self.value or {})
        updated[key] = float(spinbox_value)
        self._updating_object = True
        try:
            self.value = updated
        finally:
            self._updating_object = False

    def update_editor(self):
        """Rebuild the table from the dict trait."""
        if self._updating_object:
            return   # echo of our own update_object write — widgets are current
        entries = dict(self.value or {})
        self.control.clearContents()   # drops stale items AND cell widgets
        self.control.setRowCount(len(entries))
        for row, (key, value) in enumerate(entries.items()):
            key_item = QtWidgets.QTableWidgetItem(str(key))
            key_item.setFlags(Qt.ItemIsEnabled)   # visible, not editable
            self.control.setItem(row, 0, key_item)

            if self.factory.allow_infinity:
                spinbox = _SentinelDoubleSpinBox(
                    sentinel_value=self.factory.infinity_value,
                    real_low=self.factory.low,
                )
                spinbox.setMinimum(self.factory.infinity_value)
                spinbox.setSpecialValueText(self.factory.infinity_text)
            else:
                spinbox = QDoubleSpinBox()
                spinbox.setMinimum(self.factory.low)
            spinbox.setMaximum(self.factory.high)
            spinbox.setDecimals(self.factory.decimals)
            spinbox.setSingleStep(self.factory.step)
            spinbox.setValue(float(value))
            spinbox.valueChanged.connect(
                lambda new_value, k=key: self.update_object(k, new_value))
            self.control.setCellWidget(row, 1, spinbox)
        # Size the table to its rows — no dead scroll area below the last
        # entry when embedded in a preferences pane.
        rows_height = sum(self.control.rowHeight(r)
                          for r in range(self.control.rowCount()))
        self.control.setFixedHeight(
            self.control.horizontalHeader().height() + rows_height
            + 2 * self.control.frameWidth())


class DictFloatTableEditor(BasicEditorFactory):
    """Editor factory for Dict(Str, Float) traits — declare directly in
    a View: Item("my_dict", editor=DictFloatTableEditor(...))."""
    klass = _DictFloatTableEditor

    key_label = Str("Key")
    value_label = Str("Value")
    low = Float(0.0)
    high = Float(100.0)
    decimals = Int(1)
    step = Float(0.5)
    #: When True, the spinbox accepts one extra position below ``low`` —
    #: the finite ``infinity_value`` sentinel, rendered as
    #: ``infinity_text`` (float("inf") itself can't be stored: apptools
    #: preference round-trips go through literal_eval). Spinning down
    #: from ``low`` snaps onto the sentinel; consumers translate it to
    #: an unbounded wait.
    allow_infinity = Bool(False)
    infinity_value = Float(-1.0)
    infinity_text = Str("∞")

class SafeCancelTableHandler(Handler):
    """
    In tables, we want the cancel event not to close the view. Instead it should deselect all elements.
    """
    escape_shortcut = Any()

    def init(self, info: UIInfo):
        """Runs once when the UI is generated."""

        # 1. Create a shortcut that intercepts the Escape key
        self.escape_shortcut = QShortcut(QKeySequence.Cancel, info.ui.control)

        # 2. Ensure it captures the key even if the user is clicked inside the table
        self.escape_shortcut.setContext(Qt.WidgetWithChildrenShortcut)

        # 3. Route it to a custom method instead of closing the window
        self.escape_shortcut.activated.connect(lambda: self.handle_escape(info))

        return True

    def handle_escape(self, info: UIInfo):
        """Swallows the Escape key press so the table doesn't hide."""
        pass


class StatusIconEditor(QtEditor):
    """Custom TraitsUI editor that displays an icon with colored background.

    The editor value is bound to `icon_path` (str path to the image).
    It also observes `icon_color` on the model to update the background color.
    """

    def init(self, parent):
        self.control = _ScalingPixmapLabel()

        # Load initial image
        self._load_pixmap(self.value)

        # Observe icon_color on the model for background color updates
        self.object.observe(self._on_icon_color_changed, "icon_color")
        self._apply_background_color(self.object.icon_color)

    def _load_pixmap(self, path):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            logger.error(f"Failed to load image: {path}")
        self.control.set_source_pixmap(pixmap)

    def _apply_background_color(self, color):
        self.control.setStyleSheet(
            f"background-color: {color}; border-radius: {self.factory.border_radius}px;"
        )

    def _on_icon_color_changed(self, event):
        self._apply_background_color(event.new)

    def update_editor(self):
        """Called when icon_path trait changes."""
        self._load_pixmap(self.value)

    def dispose(self):
        self.object.observe(self._on_icon_color_changed, "icon_color", remove=True)
        super().dispose()


class StatusIconEditorFactory(BasicEditorFactory):
    klass = StatusIconEditor

    border_radius = Int(4)


class _HoverScrollEnumEditor(QtEditor):
    """Qt editor that renders an Enum trait via :class:`MarqueeComboBox`.

    The combo box uses ``AdjustToMinimumContentsLengthWithIcon`` so it doesn't
    expand to fit the widest item; overflow text marquee-scrolls on hover (see
    :class:`MarqueeComboBox`). The dropdown list still renders full names.
    """

    def init(self, parent):
        self.control = MarqueeComboBox()
        self.control.addItems(list(self.factory.values))

        self.control.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )

        self.control.currentTextChanged.connect(self.update_object)

    def update_object(self, value):
        self.value = value

    def update_editor(self):
        if self.control is not None:
            # Block signals so programmatic updates don't re-fire update_object.
            self.control.blockSignals(True)
            self.control.setCurrentText(str(self.value))
            self.control.blockSignals(False)


class HoverScrollEnumEditor(BasicEditorFactory):
    """Factory for an Enum combo box that marquee-scrolls overflow text on hover."""

    klass = Property

    values = List(Str)

    def _get_klass(self):
        return _HoverScrollEnumEditor
