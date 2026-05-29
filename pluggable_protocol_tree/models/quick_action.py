"""Default ``IQuickAction`` provider + ``QuickActionCtx`` value object.

Plugins are free to subclass ``BaseQuickAction`` (recommended — gets
the trait set and default ``is_enabled`` for free) or write a fresh
``HasStrictTraits`` class decorated with ``@provides(IQuickAction)``.
"""

from traits.api import (
    Any, Bool, HasStrictTraits, Tuple, provides,
)

from pluggable_protocol_tree.interfaces.i_quick_action import IQuickAction


@provides(IQuickAction)
class BaseQuickAction(HasStrictTraits, IQuickAction):
    """Concrete IQuickAction provider with the default trait set.

    Subclasses override ``on_execute_action`` (and optionally
    ``is_enabled``). Trait fields can be set positionally / by kwarg
    in factory functions — see protocol_quick_action_tools.quick_actions.

    Inherits from IQuickAction so the trait declarations (action_id,
    icon_text, tooltip, priority, shortcut) come along automatically.
    The @provides decorator separately registers the interface so
    isinstance/adaptation checks work.
    """

    def on_execute_action(self, ctx):
        """Default no-op. Subclasses override."""

    def is_enabled(self, ctx) -> bool:
        return True


class QuickActionCtx(HasStrictTraits):
    """Value object handed to every action callback.

    Built fresh by the controller on each click / refresh — never
    cached on the action. ``pane`` is the live ``ProtocolTreePane``
    (so contributions can reach ``pane.manager``, ``pane.widget.tree``,
    ``pane.application``, ``pane.experiment_manager``, etc.).
    """
    pane = Any
    selected_paths = Tuple()
    is_running = Bool(False)
