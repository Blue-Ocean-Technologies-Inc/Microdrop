# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from traits.api import HasTraits, Str, Range, Bool

class AlphaValue(HasTraits):
    """A class to represent an alpha value with a key."""
    key = Str()  # The key for the alpha value
    alpha = Range(0, 100, mode="spinner")  # The alpha value associated with the key
    visible = Bool(True)  # Whether the alpha value is visible in the UI