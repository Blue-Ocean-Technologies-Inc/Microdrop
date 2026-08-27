# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""'Open Protocol' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_OPEN_PROTOCOL


class _OpenProtocolAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.load_protocol_dialog()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_open_protocol_action() -> _OpenProtocolAction:
    return _OpenProtocolAction(
        action_id=ACTION_OPEN_PROTOCOL,
        icon_text="file_open",
        tooltip="Open Protocol",
        priority=50,
        shortcut="Ctrl+O"
    )
