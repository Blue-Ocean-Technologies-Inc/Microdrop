# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for the Help-menu document actions."""

# Standard library imports.
import re

# Microdrop package imports.
from image_viewer.consts import ANALYSIS_HELP_HTML_PATH

# Local imports.
from ..menus import OpenWebViewDialogAction, menu_factory

#: A tag attribute that would make the page fetch something at load time.
NETWORK_RESOURCE_PATTERN = re.compile(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""")


def _analysis_help_action():
    actions = [
        item
        for item in menu_factory().items
        if isinstance(item, OpenWebViewDialogAction)
        and item.source == ANALYSIS_HELP_HTML_PATH
    ]

    return actions[0] if actions else None


def test_help_menu_offers_the_analysis_guide():
    action = _analysis_help_action()

    assert action is not None
    assert action.window_title == "Image Analysis Tutorial"


def test_analysis_guide_is_bundled_and_self_contained():
    html = ANALYSIS_HELP_HTML_PATH.read_text(encoding="utf-8")

    assert ANALYSIS_HELP_HTML_PATH.is_file()
    assert NETWORK_RESOURCE_PATTERN.search(html) is None
