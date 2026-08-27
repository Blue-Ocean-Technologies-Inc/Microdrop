# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Owner of the Touch Assist floating widgets: creates each lazily on
first show, shows/hides on menu toggles, and pushes a widget's own
close button back into the menu checkbox so the two never disagree.
GUI-thread only; no Redis or dramatiq involvement."""
from traits.api import Dict, HasTraits, Str

from logger.logger_service import get_logger

from .consts import TOOL_KEYBOARD, TOOL_MOUSE, TOOL_NUMPAD

logger = get_logger(__name__)


class TouchAssistManager(HasTraits):

    #: tool name -> the created widget (absent until first shown).
    _widgets = Dict(Str)

    #: tool name -> the menu action, registered by the action itself
    #: on its first toggle, so a widget closed from its own ✕ can
    #: uncheck the menu.
    _actions = Dict(Str)

    def register_action(self, tool, action):
        self._actions[tool] = action

    def set_visible(self, tool, visible):
        widget = self._widgets.get(tool)
        if widget is None:
            if not visible:
                return
            widget = self._create(tool)
            if widget is None:
                return
            self._widgets[tool] = widget
        widget.setVisible(visible)
        if visible:
            widget.raise_()
        logger.info(f"Touch Assist {tool}: "
                    f"{'shown' if visible else 'hidden'}")

    def widget_closed(self, tool):
        """The widget's own close button: mirror it into the menu."""
        action = self._actions.get(tool)
        if action is not None:
            action.checked = False

    def _create(self, tool):
        # Imported here so headless code paths (backend, tests) never
        # pay for Qt widget imports they will not show.
        from .input_pads import VirtualKeyboard, VirtualNumpad
        from .virtual_mouse import VirtualMouse
        factories = {TOOL_NUMPAD: VirtualNumpad,
                     TOOL_KEYBOARD: VirtualKeyboard,
                     TOOL_MOUSE: VirtualMouse}
        factory = factories.get(tool)
        if factory is None:
            logger.warning(f"Unknown Touch Assist tool: {tool}")
            return None
        widget = factory()
        widget.closed_by_user = lambda: self.widget_closed(tool)
        return widget


#: The one manager the menu actions talk to.
touch_assist_manager = TouchAssistManager()
