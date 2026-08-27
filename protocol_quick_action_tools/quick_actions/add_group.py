# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""'Add group' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_ADD_GROUP


class _AddGroupAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.add_group_after_selection()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_add_group_action() -> _AddGroupAction:
    return _AddGroupAction(
        action_id=ACTION_ADD_GROUP,
        icon_text="playlist_add",
        tooltip="Add group",
        priority=30,
        # Ctrl+Shift+Return (main Enter, mirroring add_step's Ctrl+Return) frees
        # Ctrl+Shift+G for the tree's Unfold Group shortcut (#529).
        shortcut="Ctrl+Shift+Return",
    )
