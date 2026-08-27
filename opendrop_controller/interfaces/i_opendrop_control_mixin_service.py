# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from traits.api import Interface, Str


class IOpenDropControlMixinService(Interface):
    """
    Interface for OpenDrop mixin services that expose topic-based request handlers.
    """

    id = Str
    name = Str

    def on_topic_request(self, message):
        """
        Naming convention for exposed methods:
        `on_<topic-name>_request(message)`.
        """
        pass
