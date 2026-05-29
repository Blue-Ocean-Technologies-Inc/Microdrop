"""IQuickAction is the contract any contributed quick-action button
implements. This file pins the trait shape and the two-method surface
so future refactors can't silently break plugin contributions."""

from traits.api import HasStrictTraits, provides

from pluggable_protocol_tree.consts import PROTOCOL_QUICK_ACTIONS
from pluggable_protocol_tree.interfaces.i_quick_action import IQuickAction


def test_extension_point_id_is_namespaced():
    assert PROTOCOL_QUICK_ACTIONS == (
        "pluggable_protocol_tree.protocol_quick_actions"
    )


def test_iquick_action_required_traits_exist():
    """Trait names + default values are part of the public contract —
    plugins read action_id/icon_text/tooltip directly.

    Concrete providers inherit from both HasStrictTraits and IQuickAction
    so that the interface's trait definitions are picked up by the MRO
    (standard Traits Interface pattern; @provides alone is insufficient).
    """

    @provides(IQuickAction)
    class _Stub(HasStrictTraits, IQuickAction):
        pass

    s = _Stub()
    # Every trait declared on IQuickAction must be readable on a provider
    # (proves the interface itself declares them).
    for name in ("action_id", "icon_text", "tooltip",
                 "priority", "shortcut"):
        assert hasattr(s, name), f"missing trait: {name}"
    assert s.priority == 50
    assert s.shortcut == ""


def test_iquick_action_methods_are_callable_with_ctx():
    """The interface defines on_execute_action(ctx) and is_enabled(ctx)
    -> bool; defaults are no-op / True."""

    @provides(IQuickAction)
    class _Stub(HasStrictTraits, IQuickAction):
        action_id = "x"
        icon_text = ""
        tooltip = ""

    s = _Stub()
    # Default implementations don't raise; is_enabled defaults to True.
    s.on_execute_action(ctx=None)
    assert s.is_enabled(ctx=None) is True
