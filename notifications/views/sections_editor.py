# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The contributed sections above the notifications, each a header that
expands to its contents.

A section's contents are whatever its contributor's factory builds, which
TraitsUI cannot lay out from a trait, hence this small editor. Contents are
built the first time the section expands, and its expanded flag is the
section's own ``expanded`` trait, so a request can open it.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import Any, HasTraits, Instance, List, observe
from traitsui.api import BasicEditorFactory
from traitsui.qt.editor import Editor

# Local imports.
from ..consts import SECTION_MAX_HEIGHT, NotificationSection

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Style of a section header: a flat, full-width, left-aligned button.
HEADER_STYLE_SHEET = "QPushButton { border: none; padding: 4px 6px; text-align: left; }"


class SectionPanel(HasTraits):
    """One section's header and, once expanded, its contents."""

    #: The section shown.
    section = Instance(NotificationSection)

    #: The panel: the header over the contents.
    control = Any()

    #: The header button.
    _header = Any()

    #: The factory's result: a QWidget, or a TraitsUI UI around one.
    _contents = Any()

    def create(self):
        """Build the panel, collapsed or expanded as the section is."""
        self.control = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.control)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = header = QtWidgets.QPushButton(self.control)
        header.setFlat(True)
        header.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        header.setStyleSheet(HEADER_STYLE_SHEET)
        header.clicked.connect(self._toggle)
        layout.addWidget(header)

        self._show_header()
        self._show_expanded()

        return self.control

    def dispose(self):
        """Dispose the contents' TraitsUI UI, if they have one."""
        dispose = getattr(self._contents, "dispose", None)

        if dispose is not None:
            dispose()

        self._contents = None
        self.section = None

    def _toggle(self):
        self.section.expanded = not self.section.expanded

    @observe("section:[title, summary, expanded]", post_init=True)
    def _show_header(self, event=None):
        if self._header is None or self.section is None:
            return

        section = self.section
        arrow = "▾" if section.expanded else "▸"
        # Expanded, the contents say it themselves.
        shown = section.summary and not section.expanded
        summary = f"  —  {section.summary}" if shown else ""

        self._header.setText(f"{arrow}  {section.title}{summary}")
        self._header.setToolTip(
            f"{'Hide' if section.expanded else 'Show'} {section.title.lower()}"
        )

    @observe("section:expanded", post_init=True)
    def _show_expanded(self, event=None):
        if self.control is None or self.section is None:
            return

        if self.section.expanded and self._contents is None:
            self._build_contents()

        widget = self._contents_widget()

        if widget is not None:
            widget.setVisible(self.section.expanded)

    def _build_contents(self):
        """Run the section's factory; a failure shows in place of it."""

        try:
            self._contents = self.section.factory(self.control)

        except Exception as error:
            logger.exception(f"Notification section {self.section.id} failed")
            self._contents = QtWidgets.QLabel(f"Could not show this: {error}")

        widget = self._contents_widget()
        widget.setMaximumHeight(SECTION_MAX_HEIGHT)
        self.control.layout().addWidget(widget)

    def _contents_widget(self):
        return getattr(self._contents, "control", self._contents)


class _SectionsEditor(Editor):
    """Shows the edited list of NotificationSections as SectionPanels."""

    #: One panel per section, top first.
    _panels = List(Instance(SectionPanel))

    def init(self, parent):
        self.control = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.control)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

    def update_editor(self):
        """Rebuild the panels for the current sections."""
        self._dispose_panels()

        for section in self.value:
            panel = SectionPanel(section=section)
            self.control.layout().addWidget(panel.create())
            self._panels.append(panel)

        self.control.setVisible(bool(self.value))

    def dispose(self):
        self._dispose_panels()
        super().dispose()

    def _dispose_panels(self):
        for panel in self._panels:
            panel.dispose()

            # At app exit the window may already have deleted the panel.
            try:
                panel.control.hide()
                panel.control.deleteLater()

            except RuntimeError as error:
                logger.debug(f"Notification section panel already deleted: {error}")

        self._panels = []


class SectionsEditor(BasicEditorFactory):
    """Edit a list of NotificationSections as expandable panels."""

    klass = _SectionsEditor
