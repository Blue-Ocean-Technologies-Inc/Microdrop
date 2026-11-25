# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""The News section's contents in the drawer's column: the feed's status
line, then one sub-section per group (Top stories, What's new,
Newsletters, Announcements, Updates), at natural height."""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import Any, HasTraits, Instance, observe
from traitsui.api import UItem, View

# Local imports.
from ..models.news_section import NewsSection
from .feed_subsection import FeedSubsection
from .status_banner import StatusBannerEditor

#: The feed's status line ("Pushed 1 new post"), as its own view shows it.
FeedStatusView = View(
    UItem(
        "status_text",
        editor=StatusBannerEditor(error_name="status_is_error"),
        visible_when="status_text",
    ),
)


class _FeedBinding(HasTraits):
    """Rebuilds the sub-sections when the feed's groups change, and the
    "new" marks when the alerts do."""

    section = Instance(NewsSection)

    view = Any()

    @observe("section:controller:model:groups")
    def _rebuild(self, event):
        self.view.schedule_rebuild()

    @observe("section:alerts:items:[unread, is_new]")
    def _show_new(self, event):
        self.view.show_new()


class FeedColumn(QtWidgets.QWidget):
    """The feed's status line over its sub-sections, at natural height."""

    def __init__(self, section, parent=None):
        super().__init__(parent)

        self.section = section
        self.controller = section.controller
        self._subsections = []
        self._rebuild_queued = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 8, 6)
        layout.setSpacing(0)

        self._status_ui = self.controller.edit_traits(
            view=FeedStatusView, kind="subpanel", parent=self
        )
        layout.addWidget(self._status_ui.control)

        self._groups = QtWidgets.QVBoxLayout()
        self._groups.setSpacing(2)
        layout.addLayout(self._groups)

        self._binding = _FeedBinding(section=section, view=self)
        self.rebuild()

    def new_ids(self):
        """Ids of the posts marked new."""
        return self.section.new_post_ids()

    def schedule_rebuild(self):

        if not self._rebuild_queued:
            self._rebuild_queued = True
            QtCore.QTimer.singleShot(0, self.rebuild)

    def rebuild(self):
        """A sub-section per group; the model leaves empty groups out."""
        self._rebuild_queued = False
        self._dispose_subsections()

        for group in self.controller.model.groups:
            subsection = FeedSubsection(group, self, self)
            self._groups.addWidget(subsection)
            self._subsections.append(subsection)

    def show_new(self):

        for subsection in self._subsections:
            subsection.show_new()

    def frame_for(self, post_id):
        """The frame of the post with ``post_id``, its sub-section opened."""

        if self._rebuild_queued:
            self.rebuild()

        for subsection in self._subsections:
            frame = subsection.frame_for(post_id)

            if frame is not None:
                return frame

        return None

    def _dispose_subsections(self):

        for subsection in self._subsections:
            subsection.dispose()
            subsection.hide()
            subsection.deleteLater()

        self._subsections = []

    def dispose(self):
        self._binding.section = None
        self._dispose_subsections()
        self._status_ui.dispose()
