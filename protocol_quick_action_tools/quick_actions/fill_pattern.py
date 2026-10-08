# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""'Fill pattern' quick-action factory."""

# Microdrop package imports.
from pluggable_protocol_tree.consts import STEP_PATTERN_SHORTCUT
from pluggable_protocol_tree.models.quick_action import BaseQuickAction

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_STACKED_LINE_CHART

# Local imports.
from ..consts import ACTION_FILL_PATTERN


class _FillPatternAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.fill_pattern()

    def is_enabled(self, ctx):
        return not ctx.is_running


def make_fill_pattern_action():
    return _FillPatternAction(
        action_id=ACTION_FILL_PATTERN,
        icon_text=ICON_STACKED_LINE_CHART,
        tooltip=(
            "Fill a column with a ramp or alternating pattern "
            f"({STEP_PATTERN_SHORTCUT})"
        ),
        # Right after Add group (30).
        priority=35,
        # No shortcut here: the tree widget owns the tree-scoped binding, and
        # registering it twice would make Qt treat the key as ambiguous.
        shortcut="",
    )
