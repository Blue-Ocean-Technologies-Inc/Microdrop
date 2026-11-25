# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The sections' alerts (``SectionAlert``, e.g. a new news post) as toasts,
bell counts and "new" marks, like a notification's, never listed in
Activity. Qt-free.

Each alert a section gains gets a stand-in entry in the pane model's
``section_alerts``, offered to the toasts. It is seen once the drawer is
open with its section expanded: off the bell, marked new until the drawer
closes, then let go of. The alert's own ``unread`` and ``is_new`` follow
its stand-in's, for the contributor's marks.
"""

# Enthought library imports.
from traits.api import Callable, Dict, HasTraits, Instance, observe

# Local imports.
from ..consts import SEVERITY_INFO
from ..models.notification import Notification
from ..models.notifications_pane_model import NotificationsPaneModel

#: The first part of a stand-in's key: ``(ALERT_KEY, section id, alert key)``.
ALERT_KEY = "alert"


class SectionAlertWatcher(HasTraits):
    """Turns the sections' new alerts into stand-in entries."""

    #: The drawer's model: its sections and their alerts' stand-ins.
    pane_model = Instance(NotificationsPaneModel)

    #: ``offer(entry)``: the toast controller's, to pop an alert up.
    offer = Callable()

    #: Each alert's stand-in, by the alert's id().
    _stand_ins = Dict()

    @observe("pane_model.sections.items.alerts.items")
    def _follow_alerts(self, event):
        sections = self.pane_model.sections
        current = {id(alert) for section in sections for alert in section.alerts}

        for section in sections:
            for alert in section.alerts:
                if id(alert) not in self._stand_ins:
                    self._stand_ins[id(alert)] = self._add(section, alert)

        gone = [key for key in self._stand_ins if key not in current]

        for key in gone:
            entry = self._stand_ins.pop(key)

            if entry in self.pane_model.section_alerts:
                self.pane_model.section_alerts.remove(entry)

    @observe("pane_model:is_open")
    @observe("pane_model:sections:items:expanded")
    def _see_alerts(self, event):
        """Alerts are seen once the drawer is open on their expanded
        section: off the bell, still marked new; closing the drawer lets go
        of them."""
        model = self.pane_model

        if not model.is_open:
            for entry in model.section_alerts:
                entry.is_new = False

            model.section_alerts = [e for e in model.section_alerts if e.unread]

            return

        expanded = {section.id for section in model.sections if section.expanded}

        for entry in model.section_alerts:
            if entry.unread and entry.section_id in expanded:
                entry.trait_set(unread=False, is_new=True)

    @observe("pane_model:section_alerts:items:[unread, is_new]")
    def _mirror_state(self, event):
        alert = event.object.alert

        if alert is not None:
            setattr(alert, event.name, event.new)

    def _add(self, section, alert):
        """The alert's stand-in, listed and offered; None when its category
        is kept out of the drawer."""
        kind = self.pane_model.center.settings.category(alert.category_id)

        if kind is not None and not kind.in_drawer:
            return None

        entry = Notification(
            key=(ALERT_KEY, section.id, alert.key),
            title=alert.title,
            detail=alert.detail,
            severity=SEVERITY_INFO,
            source=alert.source,
            category_id=alert.category_id,
            section_id=section.id,
            alert=alert,
            accent=alert.accent or section.accent,
        )
        self.pane_model.section_alerts.append(entry)

        if self.offer is not None:
            self.offer(entry)

        return entry
