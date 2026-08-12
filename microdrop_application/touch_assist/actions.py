"""The Tools -> Touch Assist menu: three independent checkbox
actions, one per floating tool. No mode switch and no detection —
the user decides what is on screen."""
from pyface.action.api import Action
from pyface.tasks.action.api import SMenu
from traits.api import Str

from .consts import PKG, TOOL_KEYBOARD, TOOL_MOUSE, TOOL_NUMPAD
from .manager import touch_assist_manager


class TouchAssistAction(Action):
    """One checkbox: show/hide one Touch Assist tool."""

    style = "toggle"

    #: Which tool this checkbox drives (consts.TOOL_*).
    tool = Str()

    def perform(self, event):
        # Registered here rather than at construction so the manager
        # only ever holds actions that reached a live menu.
        touch_assist_manager.register_action(self.tool, self)
        touch_assist_manager.set_visible(self.tool, self.checked)


def touch_assist_menu():
    """The Touch Assist submenu, built fresh per menu bar (pyface
    actions bind to the window that renders them)."""
    return SMenu(
        TouchAssistAction(id=f"{PKG}.virtual_numpad",
                          name="Virtual &Numpad", tool=TOOL_NUMPAD),
        TouchAssistAction(id=f"{PKG}.virtual_keyboard",
                          name="Virtual &Keyboard", tool=TOOL_KEYBOARD),
        TouchAssistAction(id=f"{PKG}.virtual_mouse",
                          name="Virtual &Mouse", tool=TOOL_MOUSE),
        id="TouchAssist", name="Touch &Assist",
    )
