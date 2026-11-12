# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The AutoSave checkbox on the protocol tree's navigation bar (#966).

Mirrors the status-bar glyph: both edit ``ProtocolAutosaveModel.enabled`` and
show ``model.tooltip``, so either one follows the other through the model.
Standalone panes, which have no status bar, get AutoSave through this one.

Runs standalone against just the model:
``AutosaveCheckbox(model=ProtocolAutosaveModel()).control.show()``.
"""

# Enthought library imports.
from pyface.qt.QtWidgets import QWidget
from traits.api import HasTraits, Instance, observe
from traitsui.api import UI, Group, Item, View

# Microdrop package imports.
from pluggable_protocol_tree.models.protocol_autosave import ProtocolAutosaveModel

#: The toggle, labelled on its right like a plain checkbox.
autosave_checkbox_view = View(
    Group(Item("enabled", label="AutoSave"), show_left=False),
)


class AutosaveCheckbox(HasTraits):
    #: The AutoSave state this checkbox shows and toggles.
    model = Instance(ProtocolAutosaveModel)

    #: The TraitsUI panel holding the checkbox.
    ui = Instance(UI)

    #: The panel widget the navigation bar takes.
    control = Instance(QWidget)

    def traits_init(self):
        self.ui = self.model.edit_traits(view=autosave_checkbox_view, kind="subpanel")
        self.control = self.ui.control

        self._refresh_tooltip()

    # The checkbox and its label set no tooltip of their own, so Qt shows
    # the panel's for both.
    @observe("model:tooltip", post_init=True)
    def _refresh_tooltip(self, event=None):
        self.control.setToolTip(self.model.tooltip)
