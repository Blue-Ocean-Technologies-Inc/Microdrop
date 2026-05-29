"""Traits interface for protocol-tree quick-action buttons.

Each contribution is a button on the toolbar mounted under the tree.
Mirrors the IColumn pattern: tree plugin owns the contract, other
plugins contribute implementations. Two hooks:

* ``on_execute_action(ctx)`` — fired on click (or keyboard shortcut).
* ``is_enabled(ctx) -> bool`` — queried by the controller on selection
  / protocol-running changes; default ``True``.

The ``ctx`` is a :class:`QuickActionCtx` carrying the pane, current
selection, and is_running flag. Contributions stay Qt-free where they
can by delegating Qt work to pane helper methods.
"""

from traits.api import Bool, Int, Interface, Str


class IQuickAction(Interface):
    action_id = Str(
        desc="Stable identifier (e.g. 'add_step'). Used in logging, "
             "tests, and shortcut-conflict messages.")
    icon_text = Str(
        desc="Material-symbol name rendered as the button's text under "
             "ICON_FONT_FAMILY (e.g. 'add', 'delete', 'playlist_add').")
    tooltip = Str(desc="Button tooltip.")
    priority = Int(50,
        desc="Lower runs first; controls left-to-right order in the bar.")
    shortcut = Str(default_value="",
        desc="QKeySequence string ('R', 'Ctrl+S', ...). Empty = no "
             "shortcut. Registered widget-scoped to the pane.")

    def on_execute_action(self, ctx):
        """Called when the button is clicked or its shortcut fires.
        ctx is a QuickActionCtx. Return value is ignored."""

    def is_enabled(self, ctx) -> bool:
        """Return True if the button should be clickable. Queried by
        the controller on selection / protocol-running changes.
        Default: always True."""
        return True
