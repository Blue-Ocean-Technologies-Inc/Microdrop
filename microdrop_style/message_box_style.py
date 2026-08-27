# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

message_box_style = """

QMessageBox QPushButton {
    font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
"""

def get_message_box_style(theme):
    return message_box_style