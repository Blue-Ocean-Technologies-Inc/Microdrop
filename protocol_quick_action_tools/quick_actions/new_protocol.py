# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""'New protocol' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_NEW_PROTOCOL


class _NewProtocolAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.new_protocol()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_new_protocol_action() -> _NewProtocolAction:
    return _NewProtocolAction(
        action_id=ACTION_NEW_PROTOCOL,
        icon_text="new_window",
        tooltip="New protocol",
        priority=70,
        shortcut="Ctrl+N"
    )
