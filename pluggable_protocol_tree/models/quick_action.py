"""Default ``IQuickAction`` provider + ``QuickActionCtx`` value object.

Plugins are free to subclass ``BaseQuickAction`` (recommended — gets
the trait set and default ``is_enabled`` for free) or write a fresh
``HasTraits`` class decorated with ``@provides(IQuickAction)``.
"""

from traits.api import (
    Any, Bool, HasStrictTraits, Property, Tuple, provides,
)

from pluggable_protocol_tree.interfaces.i_quick_action import IQuickAction


@provides(IQuickAction)
class BaseQuickAction(IQuickAction):
    """Concrete IQuickAction provider with the default trait set.

    Subclasses override ``on_execute_action`` (and optionally
    ``is_enabled``). Trait fields can be set positionally / by kwarg
    in factory functions — see protocol_quick_action_tools.quick_actions.

    Inherits from IQuickAction so the trait declarations (action_id,
    icon_text, tooltip, priority, shortcut) come along automatically.
    The @provides decorator separately registers the interface so
    isinstance/adaptation checks work.

    Inherits ``IQuickAction`` directly (which chains to ``Interface`` -->
    ``HasTraits``, not ``HasStrictTraits``) so plugin authors can freely
    add their own traits when subclassing without hitting a ``TraitError``
    at class-definition time.
    """

    def on_execute_action(self, ctx):
        """Default no-op. Subclasses override."""

    def is_enabled(self, ctx) -> bool:
        """Default: always True. Override to gate on selection or protocol state."""
        return True


class QuickActionCtx(HasStrictTraits):
    """Value object handed to every action callback.

    Built fresh by the controller on each click / refresh — never cached
    on the action. ``dock_pane`` is the live ``PluggableProtocolDockPane``
    — the composition root that owns run control and the logging
    controller. The tree pane (``pane`` methods, selection, widgets) is
    reached through it via the ``pane`` convenience property
    (``dock_pane._pane``). Typed lazily by qualified name to avoid a
    models -> views import cycle; None in demo / headless contexts that
    mount the tree pane without a dock pane.
    """
    #: The live ``PluggableProtocolDockPane``. Typed ``Any`` (not
    #: ``Instance``) to avoid a models -> views import cycle and to keep
    #: duck-typed test stand-ins usable.
    dock_pane = Any
    #: The ProtocolTreePane owned by the dock pane, or None.
    pane = Property()
    selected_paths = Tuple(
        desc="Tuple of 0-indexed path tuples (matching RowManager.selection) "
             "currently highlighted in the tree.")
    is_running = Bool(False)

    def _get_pane(self):
        return getattr(self.dock_pane, "_pane", None)
