# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unused-columns notice lifecycle handler.

The executor skips the protocol start/end hooks of every column no step in
the run has a value for (``ProtocolContext.skipped_column_ids``) and logs
each one. This handler also tells the operator, once per run, through an
information dialog whose "Do not show again" checkbox writes
``suppress_unused_column_hooks_information``. Preview runs show it too: the
skip applies to them as well, and the notice touches no hardware.
"""

# Enthought library imports.
from traits.api import Instance

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import information
from pluggable_protocol_tree.models.column import BaseColumnHandler
from pluggable_protocol_tree.services.preferences import ProtocolPreferences


class UnusedColumnsNoticeHandler(BaseColumnHandler):
    """Tells the operator which columns' protocol hooks a run skips."""

    #: After every real column's start hooks (one may still cancel the run),
    #: before realtime-mode prep (900).
    priority = 800

    #: Holds the "Do not show again" flag.
    preferences = Instance(ProtocolPreferences)

    def on_pre_protocol_start(self, ctx):
        if (
            not ctx.skipped_column_ids
            or self.preferences.suppress_unused_column_hooks_information
        ):
            return

        names = self._skipped_column_names(ctx)
        result = ctx.prompt_gui(lambda: self._show_notice(names))

        # None: the wait ended without an answer (e.g. an external resume).
        if result is None:
            return

        _, checked = result
        self.preferences.suppress_unused_column_hooks_information = checked

    @staticmethod
    def _skipped_column_names(ctx):
        """Return the display names of the skipped columns, in column order.

        A column's ``preference_display_name`` wins over its header label
        (``col_name``); a compound's field cells share one id and arrive
        owner-first, so the owner's label names the compound.
        """
        names = {}

        for column in ctx.columns:
            if column.id in ctx.skipped_column_ids:
                names.setdefault(
                    column.id,
                    getattr(column, "preference_display_name", "")
                    or column.model.col_name
                    or column.id,
                )

        return list(names.values())

    @staticmethod
    def _show_notice(names):
        """Runs on the GUI thread via ctx.prompt_gui. Returns (result, checked)."""
        return information(
            None,
            title="Protocol Columns Not Used",
            message=(
                "No step in this run uses these columns, so their protocol "
                f"start/end actions were skipped: {', '.join(names)}."
            ),
            cancel=False,
            checkbox_text="Do not show again (can be undone from preferences)",
        )
