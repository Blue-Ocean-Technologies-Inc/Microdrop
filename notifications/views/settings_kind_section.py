# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""One owner's kinds of notification on the settings' "By kind" tab: a
drawer-style header that folds the section, over a grid of real controls,
one row per kind::

    (◉) Protocol  [ 4 kinds · 1 changed ]                      ⌄
        Kind                         Drawer  Pop-up  Sound
        Step completed                 ☑       ☑     [Soft     ▾]
        ...                                         Reset to defaults

A grid, not a TraitsUI table: it takes its rows' natural height, so the
tab's column is the one thing that scrolls, and its controls take part in
the Tab order. A group of more than MAX_VISIBLE_KIND_ROWS kinds scrolls
inside its section. Runs standalone::

    section = KindSection(settings.groups[0])
    section.show_expanded(True, False)
    section.show()
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.panel_theme import muted_text, theme_palette
from microdrop_style.typography import CHIP, role_font

# Local imports.
from ..consts import PKG, TONE_LABELS, TONE_NONE, NotificationSection
from ..models.settings_window import MAX_VISIBLE_KIND_ROWS, kind_matches, kinds_summary
from .section_header import SectionHeader

#: The grid's columns, and their titles.
COLUMN_NAME, COLUMN_DRAWER, COLUMN_POPUP, COLUMN_SOUND = range(4)
COLUMN_TITLES = ("Kind", "Drawer", "Pop-up", "Sound")

#: Object names, under the settings window's isolated root.
SECTION_OBJECT_NAME = f"{PKG}KindSection"
RESET_OBJECT_NAME = f"{PKG}KindsReset"

_ALIGN = QtCore.Qt.AlignmentFlag
_KEY = QtCore.Qt.Key


class KindSectionHeader(SectionHeader):
    """The drawer's section header, reached with Tab and folded with Enter
    or Space, with a focus ring while it has the keyboard."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Tab, not a click: a click would leave the ring drawn.
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.TabFocus)

    def keyPressEvent(self, event):

        if event.key() in (_KEY.Key_Return, _KEY.Key_Enter):
            self.click()

            return

        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)

        if not self.hasFocus():
            return

        ring = QtGui.QPen(theme_palette().color(QtGui.QPalette.ColorRole.Highlight))
        ring.setWidthF(1.5)

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(ring)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(1, 4, -1, -4), 7, 7)
        painter.end()


class _KindRow:
    """One kind's name and its three choices, in its section's grid."""

    def __init__(self, category, grid, row, parent):
        self.category = category

        self.name = QtWidgets.QLabel(parent)
        self.name.setWordWrap(True)
        self.name.setToolTip(category.description)

        self.drawer = QtWidgets.QCheckBox(parent)
        self.drawer.setAccessibleName(f"Keep {category.label} in the drawer")
        self.drawer.setToolTip("Kept in the drawer; off, it is not recorded")

        self.popup = QtWidgets.QCheckBox(parent)
        self.popup.setAccessibleName(f"Pop up {category.label}")
        self.popup.setToolTip("Pops up as a toast; off, it goes straight to the drawer")

        self.sound = QtWidgets.QComboBox(parent)
        self.sound.setAccessibleName(f"Sound for {category.label}")

        for tone, label in TONE_LABELS.items():
            self.sound.addItem(label, tone)

        grid.addWidget(self.name, row, COLUMN_NAME)
        grid.addWidget(self.drawer, row, COLUMN_DRAWER, _ALIGN.AlignCenter)
        grid.addWidget(self.popup, row, COLUMN_POPUP, _ALIGN.AlignCenter)
        grid.addWidget(self.sound, row, COLUMN_SOUND)

        self.show_choices()

        self.drawer.toggled.connect(self._take_drawer)
        self.popup.toggled.connect(self._take_popup)
        self.sound.currentIndexChanged.connect(self._take_tone)

    @property
    def widgets(self):
        return self.name, self.drawer, self.popup, self.sound

    def show_choices(self):
        """Show the category's choices: a critical one's drawer locked on,
        and no pop-up or sound to choose while it is not kept."""
        category = self.category
        kept = category.in_drawer
        tone = category.tone if kept else TONE_NONE

        for widget in self.widgets:
            widget.blockSignals(True)

        self.name.setText(category.row_label)
        self.drawer.setChecked(kept)
        self.drawer.setEnabled(not category.critical)
        self.popup.setChecked(category.popup)
        self.popup.setEnabled(kept)
        self.sound.setCurrentIndex(self.sound.findData(tone))
        self.sound.setEnabled(kept)

        for widget in self.widgets:
            widget.blockSignals(False)

    def set_shown(self, shown):

        for widget in self.widgets:
            widget.setVisible(shown)

    def _take_drawer(self, checked):
        self.category.in_drawer = checked

    def _take_popup(self, checked):
        self.category.popup = checked

    def _take_tone(self, index):
        self.category.tone = self.sound.itemData(index)


class KindSection(QtWidgets.QWidget):
    """A collapsible section of one group's kinds, with its own reset."""

    #: The header was clicked: the panel decides what that unfolds.
    header_clicked = QtCore.Signal()

    def __init__(self, group, parent=None):
        super().__init__(parent)

        self.group = group
        self.expanded = False
        self.setObjectName(SECTION_OBJECT_NAME)

        #: Shown filtered: how many rows pass, or None for no filter.
        self._shown = None

        # The header paints the drawer's look from a section's traits.
        self._look = NotificationSection(title=group.name)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = KindSectionHeader(self)
        self.header.clicked.connect(self.header_clicked)
        layout.addWidget(self.header)

        self.body = QtWidgets.QWidget(self)
        body_layout = QtWidgets.QVBoxLayout(self.body)
        body_layout.setContentsMargins(12, 2, 6, 6)
        body_layout.setSpacing(4)
        layout.addWidget(self.body)

        self._table = QtWidgets.QWidget()
        self._grid = QtWidgets.QGridLayout(self._table)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(4)
        self._grid.setColumnStretch(COLUMN_NAME, 1)

        self._titles = [self._add_title(column) for column in range(4)]
        self.rows = [
            _KindRow(category, self._grid, row, self._table)
            for row, category in enumerate(group.categories, start=1)
        ]

        self._scroll = None

        if len(self.rows) > MAX_VISIBLE_KIND_ROWS:
            self._scroll = QtWidgets.QScrollArea(self.body)
            self._scroll.setWidget(self._table)
            self._scroll.setWidgetResizable(True)
            self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            self._scroll.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            body_layout.addWidget(self._scroll)

        else:
            self._table.setParent(self.body)
            body_layout.addWidget(self._table)

        self.reset_button = QtWidgets.QToolButton(self.body)
        self.reset_button.setObjectName(RESET_OBJECT_NAME)
        self.reset_button.setText("Reset to defaults")
        self.reset_button.setAutoRaise(True)
        self.reset_button.setToolTip(f"Restore the {group.name} kinds' defaults")
        self.reset_button.clicked.connect(group.reset)
        body_layout.addWidget(self.reset_button, 0, _ALIGN.AlignRight)

        self._style_titles()
        self.show_summary()

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def show_expanded(self, expanded, animate):
        """Unfold or fold the section, the header's chevron turning."""
        self.expanded = expanded
        self.body.setVisible(expanded)
        self.header.show_section(self._look, expanded, animate)

    def show_choices(self, category):
        """Show ``category``'s choices again, and the summary they change."""

        for row in self.rows:
            if row.category is category:
                row.show_choices()

        self.show_summary()

    def show_summary(self):
        """The header's count of kinds and of those changed; the reset only
        while something is changed."""
        changed = self.group.changed_count

        self._look.summary = kinds_summary(len(self.rows), changed, self._shown)
        self.header.show_section(self._look, self.expanded, False)
        self.reset_button.setEnabled(changed > 0)

    def apply_filter(self, text):
        """Show only the rows whose names pass ``text``; returns how many."""
        shown = 0

        for row in self.rows:
            passes = kind_matches(row.category.label, text)
            row.set_shown(passes)
            shown += passes

        self._shown = shown if text.strip() else None
        self.show_summary()
        self._fit_scroll()

        return shown

    # ------------------------------------------------------------------ #
    # Qt                                                                  #
    # ------------------------------------------------------------------ #

    def showEvent(self, event):
        super().showEvent(event)

        # Sized once polished: the panel's font is handed down then.
        self._fit_scroll()

    def changeEvent(self, event):
        super().changeEvent(event)

        if event.type() == QtCore.QEvent.Type.ApplicationPaletteChange:
            self._style_titles()

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _add_title(self, column):
        title = QtWidgets.QLabel(COLUMN_TITLES[column], self._table)
        title.setFont(role_font(CHIP))
        centred = column in (COLUMN_DRAWER, COLUMN_POPUP)
        alignment = _ALIGN.AlignCenter if centred else _ALIGN.AlignLeft

        self._grid.addWidget(title, 0, column, alignment | _ALIGN.AlignBottom)

        return title

    def _style_titles(self):
        muted = muted_text(theme_palette()).name()

        for title in self._titles:
            title.setStyleSheet(f"color: {muted};")

    def _fit_scroll(self):
        """A long group's rows scroll inside, MAX_VISIBLE_KIND_ROWS at a time;
        fewer shown, the scroll area shrinks to them."""

        if self._scroll is None or not self.rows:
            return

        spacing = self._grid.verticalSpacing()
        row = self.rows[0].sound.sizeHint().height() + spacing
        titles = self._titles[0].sizeHint().height() + spacing
        most = titles + MAX_VISIBLE_KIND_ROWS * row

        self._scroll.setFixedHeight(min(self._table.sizeHint().height(), most))
