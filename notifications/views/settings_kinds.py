# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The settings' "By kind" tab: a filter box over one scrolling column of
collapsible sections, one per owner (``settings_kind_section``).

Sections start as ``sections_expanded_at_first`` says (all of them when the
kinds are few, else the first), then as the user leaves them, for the
session (``SettingsWindowState.expanded``). Typing in the filter shows only
the kinds whose names match and unfolds the sections that have some;
clearing it folds them back as they were. Runs standalone::

    KindsPanel(settings, SettingsWindowState()).show()
"""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import Any, Bool, HasTraits, Instance, observe

# Local imports.
from ..consts import PKG
from ..models.settings import NotificationSettings
from ..models.settings_window import sections_expanded_at_first
from .settings_kind_section import KindSection

#: Object names, under the settings window's isolated root.
FILTER_OBJECT_NAME = f"{PKG}KindsFilter"
COLUMN_OBJECT_NAME = f"{PKG}KindsColumn"


class _KindsBinding(HasTraits):
    """Shows each choice as it changes, and rebuilds the sections once per
    burst of kinds being declared."""

    settings = Instance(NotificationSettings)

    panel = Any()

    #: Whether a rebuild is queued.
    _queued = Bool(False)

    @observe("settings:groups:items:categories:items:[in_drawer, popup, tone]")
    def _choice_changed(self, event):
        self.panel.show_choices(event.object)

    @observe("settings:groups.items")
    @observe("settings:groups:items:categories.items")
    def _kinds_changed(self, event):

        if not self._queued:
            self._queued = True
            QtCore.QTimer.singleShot(0, self._rebuild)

    def release(self):
        """Stop following the settings: the panel is gone."""
        self.settings = None

    def _rebuild(self):
        self._queued = False

        if self.settings is not None:
            self.panel.show_sections()


class KindsPanel(QtWidgets.QWidget):
    """The filter, then every group's section in a scrolling column; or only
    the group ``group_name``, with no filter."""

    def __init__(self, settings, window, group_name="", parent=None):
        super().__init__(parent)

        self.settings = settings
        self.window_state = window
        self.group_name = group_name
        self.sections = []

        #: Each section's state before the user expanded or collapsed it.
        self._at_first = {}

        # Fills its tab: TraitsUI tops-and-lefts a page's layout, which
        # leaves a widget that does not expand at its size hint.
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(6)

        self.filter = None

        if not group_name:
            self.filter = QtWidgets.QLineEdit(self)
            self.filter.setObjectName(FILTER_OBJECT_NAME)
            self.filter.setPlaceholderText("Filter kinds…")
            self.filter.setClearButtonEnabled(True)
            self.filter.setToolTip("Show only the kinds whose names contain this")
            self.filter.textChanged.connect(self._apply_filter)
            layout.addWidget(self.filter)

        self.scroll = QtWidgets.QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        layout.addWidget(self.scroll, 1)

        self._column = QtWidgets.QWidget()
        self._column.setObjectName(COLUMN_OBJECT_NAME)
        self._column_layout = QtWidgets.QVBoxLayout(self._column)
        self._column_layout.setContentsMargins(0, 0, 4, 0)
        self._column_layout.setSpacing(4)

        self._no_match = QtWidgets.QLabel("No kinds match the filter.", self._column)
        self._no_match.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._no_match.hide()
        self._column_layout.addWidget(self._no_match)
        self._column_layout.addStretch(1)
        self.scroll.setWidget(self._column)

        self._binding = _KindsBinding(settings=settings, panel=self)
        self.destroyed.connect(lambda *args, binding=self._binding: binding.release())

        self.show_sections()

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def show_sections(self):
        """One section per group with kinds, built afresh."""

        for section in self.sections:
            self._column_layout.removeWidget(section)
            section.hide()
            section.deleteLater()

        groups = [
            group
            for group in self.settings.groups
            if group.categories and self.group_name in ("", group.name)
        ]
        at_first = sections_expanded_at_first([len(g.categories) for g in groups])

        self._at_first = {
            group.name: expanded for group, expanded in zip(groups, at_first)
        }
        self.sections = []

        # Before the "no match" note and the stretch, in the Tab order too.
        for index, group in enumerate(groups):
            section = KindSection(group, self._column)
            section.header_clicked.connect(
                lambda section=section: self._toggle(section)
            )
            self._column_layout.insertWidget(index, section)
            self.sections.append(section)

        self._apply_filter(self.filter.text() if self.filter else "")

    def show_choices(self, category):
        """Show ``category``'s choices in its section."""

        for section in self.sections:
            if section.group.name == category.group:
                section.show_choices(category)

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _remembered(self, section):
        name = section.group.name

        return self.window_state.expanded.get(name, self._at_first.get(name, True))

    def _toggle(self, section):
        expanded = not section.expanded

        self.window_state.expanded[section.group.name] = expanded
        section.show_expanded(expanded, True)

    def _apply_filter(self, text):
        """Filtering, only the sections with matches, unfolded; else each as
        the user left it."""
        filtering = bool(text.strip())
        matches = 0

        for section in self.sections:
            shown = section.apply_filter(text)
            matches += shown
            section.setVisible(shown > 0 or not filtering)
            expanded = shown > 0 if filtering else self._remembered(section)
            section.show_expanded(expanded, False)

        self._no_match.setVisible(filtering and matches == 0)


def kinds_panel(parent, editor, window, group_name):
    """A TraitsUI ``CustomEditor`` factory: the panel over the settings the
    editor's item belongs to."""
    return KindsPanel(editor.object, window, group_name, parent)
