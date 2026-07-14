"""BaseQuickAction is a thin HasStrictTraits convenience base so
plugins don't have to redeclare the IQuickAction trait set. The
QuickActionCtx is the value object passed to every action callback."""

from unittest.mock import MagicMock

from pluggable_protocol_tree.interfaces.i_quick_action import IQuickAction
from pluggable_protocol_tree.models.quick_action import (
    BaseQuickAction, QuickActionCtx,
)


def test_base_quick_action_provides_iquick_action_interface():
    a = BaseQuickAction(action_id="x", icon_text="add", tooltip="t",
                        priority=10, shortcut="Ctrl+X")
    # Traits 7 uses ABC-based registration; has_traits_interface is the
    # correct check (replaces Traits 4's __implements__.getInterfaces()).
    assert a.has_traits_interface(IQuickAction)
    assert a.action_id == "x"
    assert a.icon_text == "add"
    assert a.priority == 10
    assert a.shortcut == "Ctrl+X"


def test_base_quick_action_defaults():
    a = BaseQuickAction(action_id="x")
    assert a.priority == 50
    assert a.shortcut == ""
    assert a.is_enabled(ctx=None) is True


def test_quick_action_ctx_carries_dock_pane_selection_running():
    dock_pane = MagicMock()
    ctx = QuickActionCtx(
        dock_pane=dock_pane,
        selected_paths=((0,), (1, 2)),
        is_running=True,
    )
    assert ctx.dock_pane is dock_pane
    # The tree pane is reached through the dock pane.
    assert ctx.pane is dock_pane._pane
    assert ctx.selected_paths == ((0,), (1, 2))
    assert ctx.is_running is True


def test_quick_action_ctx_pane_is_none_without_dock_pane():
    ctx = QuickActionCtx()
    assert ctx.dock_pane is None
    assert ctx.pane is None
    assert ctx.selected_paths == ()
    assert ctx.is_running is False


def test_subclass_can_add_extra_trait():
    """Plugin authors will subclass BaseQuickAction and frequently add
    their own bookkeeping traits (e.g. cached state). Catch the
    HasStrictTraits regression: subclassing must remain open."""
    from traits.api import Str

    class _MyAction(BaseQuickAction):
        label = Str("default")

    a = _MyAction(action_id="a", label="hello")
    assert a.label == "hello"
    assert a.action_id == "a"
