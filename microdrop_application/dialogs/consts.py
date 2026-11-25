# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])

# Default WebViewDialog size. Kept here (Qt-free) so callers can reference
# them without importing the dialog module, which pulls in QtWebEngine.
DEFAULT_WEB_VIEW_DIALOG_WIDTH = 1024
DEFAULT_WEB_VIEW_DIALOG_HEIGHT = 768

# ---------------------------------------------------------------------------
# Dialogs recorded in the notifications drawer (dialog_records.py)
# ---------------------------------------------------------------------------
#: Who raised a recorded dialog, when its caller does not say.
DIALOG_SOURCE = "MicroDrop"

#: The same dialog shown again within this many seconds is one burst from
#: one cause: one entry counted xN. Later, it is a new entry.
DIALOG_REPEAT_WINDOW_S = 2.0

#: Titles saying nothing the severity does not: the entry takes its title
#: from the dialog's first line instead.
GENERIC_DIALOG_TITLES = ("Error", "Warning", "Information", "Success")

#: Most characters of a dialog's text and details kept in its entry.
DIALOG_DETAIL_MAX_CHARS = 4000
