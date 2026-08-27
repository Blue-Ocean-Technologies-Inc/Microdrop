# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Execution-only lifecycle handlers.

These are IColumnHandler implementations with no column/view, attached to
the executor's ``lifecycle_handlers`` list. They run once-per-run policy
(via on_pre_protocol_start / on_post_protocol_end) at high priority so they
trail every real column's hooks.
"""
