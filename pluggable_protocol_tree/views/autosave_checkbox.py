# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The AutoSave checkbox beside the protocol tree's timeline checkboxes (#966).

Mirrors the status-bar glyph: both edit ``ProtocolAutosaveModel.enabled`` and
show ``model.tooltip``, so either one follows the other through the model. A
plain ``QCheckBox`` like its "Show full timeline" and "Phase navigation"
neighbours, so it looks and clicks the same.

Runs standalone against just the model:
``AutosaveCheckbox(model=ProtocolAutosaveModel()).control.show()``.
"""

# Enthought library imports.
from pyface.qt.QtWidgets import QCheckBox
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from pluggable_protocol_tree.models.protocol_autosave import ProtocolAutosaveModel


class AutosaveCheckbox(HasTraits):
    #: The AutoSave state this checkbox shows and toggles.
    model = Instance(ProtocolAutosaveModel)

    #: The checkbox the protocol tree pane lays out.
    control = Instance(QCheckBox)

    def traits_init(self):
        self.control = QCheckBox("AutoSave")
        self.control.toggled.connect(self._on_toggled)

        self._refresh()

    def _on_toggled(self, checked):
        self.model.enabled = checked

    @observe("model:[enabled, tooltip]", post_init=True)
    def _refresh(self, event=None):
        self.control.setChecked(self.model.enabled)
        self.control.setToolTip(self.model.tooltip)
