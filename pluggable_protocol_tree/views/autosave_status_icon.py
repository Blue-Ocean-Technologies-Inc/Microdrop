# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The AutoSave glyph for the app status bar (#966).

Built like the realtime-mode icon beside it: a ``ClickableToggleIcon``
showing the ``save_clock`` glyph in the status-bar icon font, green while
AutoSave is on and grey while it is off; a click toggles
``model.enabled``. The tooltip is ``model.tooltip``, shared with the
protocol tree's AutoSave checkbox: it carries the AutoSave state (no file
yet, last save failed, paused for a run).

Runs standalone against just the model:
``AutosaveStatusIcon(model=ProtocolAutosaveModel()).control.show()``.
"""

# Enthought library imports.
from pyface.qt.QtGui import QFont
from pyface.qt.QtWidgets import QLabel
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from pluggable_protocol_tree.consts import (
    PROTOCOL_AUTOSAVE_INACTIVE_TOOLTIP,
    PROTOCOL_AUTOSAVE_STATUS_BAR_PRIORITY,
)
from pluggable_protocol_tree.models.protocol_autosave import ProtocolAutosaveModel

# Microdrop style imports.
from microdrop_style.colors import GREY, SUCCESS_COLOR
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE
from microdrop_style.icons.icons import ICON_SAVE_CLOCK

# Microdrop utils imports.
from microdrop_utils.pyside_helpers import ClickableToggleIcon

#: The realtime-mode icon's on / off colours.
AUTOSAVE_ICON_ACTIVE_INACTIVE_STYLES = (
    f"QLabel {{color: {SUCCESS_COLOR};}}",
    f"QLabel {{color: {GREY['lighter']};}}",
)


class _AutosaveToggleIcon(ClickableToggleIcon):
    """A ``ClickableToggleIcon`` whose on-state tooltip can change.

    The base fixes its tooltips at construction and re-applies them on
    every restyle (colour-scheme changes included), so the current one is
    re-applied after it.
    """

    #: Tooltip shown while on; empty falls back to the base's.
    active_tooltip = ""

    def update_style(self):
        super().update_style()

        if self.is_active and self.active_tooltip:
            self.setToolTip(self.active_tooltip)


class AutosaveStatusIcon(HasTraits):
    #: The AutoSave state this glyph shows and toggles.
    model = Instance(ProtocolAutosaveModel)

    #: The glyph widget the status bar takes.
    control = Instance(QLabel)

    def traits_init(self):
        font = QFont(ICON_FONT_FAMILY)
        font.setPointSize(STATUSBAR_ICON_POINT_SIZE)

        self.control = _AutosaveToggleIcon(
            ICON_SAVE_CLOCK,
            AUTOSAVE_ICON_ACTIVE_INACTIVE_STYLES,
            (PROTOCOL_AUTOSAVE_INACTIVE_TOOLTIP, PROTOCOL_AUTOSAVE_INACTIVE_TOOLTIP),
        )
        self.control.setFont(font)
        self.control.status_bar_icon_priority = PROTOCOL_AUTOSAVE_STATUS_BAR_PRIORITY
        self.control.toggled.connect(self._on_toggled)

        self._refresh()

    def _on_toggled(self, is_active):
        self.model.enabled = is_active

    @observe("model:[enabled, tooltip]", post_init=True)
    def _refresh(self, event=None):
        self.control.is_active = self.model.enabled
        self.control.active_tooltip = self.model.tooltip
        self.control.update_style()
