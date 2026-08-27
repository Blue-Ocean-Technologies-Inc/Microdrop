# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

DARK_MODE_STYLESHEET = """
        QLabel {
            color: #e0e0e0;
        }
        /* Example: Create a specific class for headers if needed */
        QLabel[class="header"] {
            color: #ffffff;
        }
        """

LIGHT_MODE_STYLESHEET = """
        QLabel {
            color: #333333;
        }
        QLabel[class="header"] {
            color: #000000;
        }
        """

def get_label_style(theme):
    """Specific overrides for QLabels (headers, etc)."""
    if theme == "dark":
        return DARK_MODE_STYLESHEET
    else:
        return LIGHT_MODE_STYLESHEET