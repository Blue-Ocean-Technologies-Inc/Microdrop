# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""'Undo' / 'Redo' quick-action factories for protocol edits (#967).

The buttons drive the tree pane's edit history. Their shortcuts are bound
once on the pane itself, so here they only appear in the tooltips, which
name the edit the button would act on ("Undo Delete Step (Ctrl+Z)").
"""

# Microdrop package imports.
from pluggable_protocol_tree.consts import (
    PROTOCOL_REDO_SHORTCUTS,
    PROTOCOL_UNDO_SHORTCUT,
)
from pluggable_protocol_tree.models.quick_action import BaseQuickAction

# Local imports.
from ..consts import ACTION_REDO, ACTION_UNDO


def _history(ctx):
    """The pane's ``ProtocolHistory``, or None without a mounted pane."""
    return getattr(ctx.pane, "protocol_history", None)


class _UndoAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.undo()

    def is_enabled(self, ctx):
        history = _history(ctx)

        return history is not None and bool(history.undo_name)

    def tooltip_for(self, ctx):
        history = _history(ctx)
        name = history.undo_name if history is not None else ""
        label = f"Undo {name}" if name else "Nothing to undo"

        return f"{label} ({PROTOCOL_UNDO_SHORTCUT})"


class _RedoAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.redo()

    def is_enabled(self, ctx):
        history = _history(ctx)

        return history is not None and bool(history.redo_name)

    def tooltip_for(self, ctx):
        history = _history(ctx)
        name = history.redo_name if history is not None else ""
        label = f"Redo {name}" if name else "Nothing to redo"

        return f"{label} ({' / '.join(PROTOCOL_REDO_SHORTCUTS)})"


def make_undo_action():
    return _UndoAction(
        action_id=ACTION_UNDO,
        icon_text="undo",
        tooltip="Undo",
        # Right after Fill Pattern (35), closing the editing cluster.
        priority=36,
        # Bound on the pane (see ProtocolTreePane._install_history_shortcuts);
        # a second registration would make the key ambiguous (#961).
        shortcut="",
    )


def make_redo_action():
    return _RedoAction(
        action_id=ACTION_REDO,
        icon_text="redo",
        tooltip="Redo",
        priority=37,
        shortcut="",
    )
