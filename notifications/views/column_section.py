# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""One section of the drawer's column: its header over its contents, at
their natural height, folding open and closed."""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import Any, HasTraits, Instance, observe
from traits.observation.api import trait

# Microdrop utils imports.
from microdrop_utils.item_view_fitting import fit_item_views

# Local imports.
from ..consts import HISTORY_SECTION_ID, NotificationSection
from .card_column import CardColumn, is_card_list
from .section_header import SectionHeader
from .view_consts import SECTION_ANIMATION_MS

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The largest widget height Qt allows.
UNBOUNDED_HEIGHT = 16_777_215


def build_section_contents(section, pane_model, parent):
    """A section's contents for the column: cards for the drawer's own
    sections, else the contributor's own contents, grown to their natural
    height (or capped at the section's ``max_height``)."""

    if is_card_list(section):
        activity = section.id == HISTORY_SECTION_ID

        return CardColumn(section, pane_model, activity=activity, parent=parent)

    contents = section.factory(parent)
    widget = getattr(contents, "control", contents)

    if section.max_height:
        widget.setMaximumHeight(section.max_height)

    else:
        fit_item_views(widget)

    return contents


class _SectionBinding(HasTraits):
    """Shows the section model's changes in its column view."""

    section = Instance(NotificationSection)

    view = Any()

    @observe("section:[title, summary, glyph, accent, logo]")
    def _show_header(self, event):
        self.view.show_header()

    @observe("section:expanded")
    def _show_expanded(self, event):
        self.view.show_expanded(animate=True)

    # Only the drawer's own sections have ``available``.
    @observe(trait("section", notify=False).trait("available", optional=True))
    def _show_available(self, event):
        self.view.setVisible(event.new)
        self.view.header_changed.emit()


class ColumnSection(QtWidgets.QWidget):
    """A section's header over its contents, at their natural height."""

    #: The header was clicked.
    toggle_requested = QtCore.Signal(object)

    #: Its title, summary or state changed: a pinned copy must follow.
    header_changed = QtCore.Signal()

    def __init__(self, section, pane_model, parent=None):
        super().__init__(parent)

        self.section = section
        self.pane_model = pane_model

        #: What was built for it: a widget, or a TraitsUI UI around one.
        self.contents = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = SectionHeader(self)
        self.header.clicked.connect(lambda: self.toggle_requested.emit(self))
        layout.addWidget(self.header)

        self.body = QtWidgets.QWidget(self)
        body_layout = QtWidgets.QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.body)

        #: The fold animation, made on the first fold.
        self._fold = None

        self._binding = _SectionBinding(section=section, view=self)
        self.setVisible(getattr(section, "available", True))
        self.show_expanded(animate=False)

    @property
    def contents_widget(self):
        """The widget built for the section, or None."""
        return getattr(self.contents, "control", self.contents)

    def show_header(self):
        self.header.show_section(self.section, self.section.expanded, True)
        self.header_changed.emit()

    def show_expanded(self, animate):
        expanded = self.section.expanded

        if expanded and self.contents is None:
            self._build_contents()

        self.header.show_section(self.section, expanded, animate)
        self.header_changed.emit()

        if self._fold is not None:
            self._fold.stop()

        if not animate or not self.isVisible():
            self.body.setMaximumHeight(UNBOUNDED_HEIGHT)
            self.body.setVisible(expanded)

            return

        fold = self._fold_animation()
        natural = self.body.sizeHint().height()

        if expanded:
            self.body.setMaximumHeight(0)
            self.body.show()
            fold.setStartValue(0)
            fold.setEndValue(natural)

        else:
            fold.setStartValue(self.body.height())
            fold.setEndValue(0)

        fold.start()

    def dispose(self):
        """Stop following the section; dispose what was built for it."""
        self._binding.section = None
        dispose = getattr(self.contents, "dispose", None)

        if dispose is not None:
            dispose()

        self.contents = None

    def _fold_animation(self):

        if self._fold is None:
            self._fold = QtCore.QPropertyAnimation(self.body, b"maximumHeight", self)
            self._fold.setDuration(SECTION_ANIMATION_MS)
            self._fold.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
            self._fold.finished.connect(self._fold_finished)

        return self._fold

    def _fold_finished(self):
        self.body.setVisible(self.section.expanded)
        self.body.setMaximumHeight(UNBOUNDED_HEIGHT)

    def _build_contents(self):
        """Build the contents; a failure shows in place of them."""

        try:
            self.contents = build_section_contents(
                self.section, self.pane_model, self.body
            )

        except Exception as error:
            logger.exception(f"Notification section {self.section.id} failed")
            self.contents = QtWidgets.QLabel(f"Could not show this: {error}")

        self.body.layout().addWidget(self.contents_widget)


def card_column_of(view):
    """``view``'s CardColumn, if its contents are one."""
    widget = view.contents_widget

    return widget if isinstance(widget, CardColumn) else None
