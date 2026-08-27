# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Package-level constants for protocol_quick_action_tools.

Follows the MicroDrop convention: PKG derived from __name__, PKG_name
title-cased for display.
"""

PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

# Stable action_id strings. Tests assert against these constants so
# the legacy ids remain accessible by name from outside the plugin.
ACTION_ADD_STEP        = "add_step"
ACTION_DELETE_ROW      = "delete_row"
ACTION_ADD_GROUP       = "add_group"
ACTION_IMPORT_PROTOCOL = "import_protocol"
ACTION_OPEN_PROTOCOL   = "open_protocol"
ACTION_SAVE_PROTOCOL   = "save_protocol"
ACTION_NEW_PROTOCOL    = "new_protocol"
ACTION_BROWSE_REPORTS  = "browse_reports"
