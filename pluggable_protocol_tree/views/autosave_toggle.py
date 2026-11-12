# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""AutoSave on/off switch for the protocol tree's quick-actions toolbar.

A checkable tool button bound to a ``ProtocolAutosaveModel``: its checked
state is ``model.enabled``, its text the short state and its tooltip the
full one. Instantiable standalone against just the model.
"""

# Enthought library imports.
from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QToolButton
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from pluggable_protocol_tree.models.protocol_autosave import ProtocolAutosaveModel


class AutosaveToggle(HasTraits):
    #: The AutoSave state this switch shows and edits.
    model = Instance(ProtocolAutosaveModel)

    #: The tool button placed on the toolbar.
    control = Instance(QToolButton)

    def traits_init(self):
        self.control = QToolButton()
        self.control.setCheckable(True)
        self.control.setCursor(Qt.PointingHandCursor)
        self.control.toggled.connect(self._on_toggled)

        self._refresh()

    def _on_toggled(self, checked):
        self.model.enabled = checked

    @observe("model:[enabled, label_text, status_text]", post_init=True)
    def _refresh(self, event=None):
        self.control.blockSignals(True)
        self.control.setChecked(self.model.enabled)
        self.control.blockSignals(False)

        self.control.setText(self.model.label_text)
        self.control.setToolTip(self.model.status_text)
