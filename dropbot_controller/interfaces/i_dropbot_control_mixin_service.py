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


class IDropbotControlMixinService(Interface):
    """
    An interface for a dropbot control mixin that provides certain methods for a dropbot controller
    """

    id = Str
    name = Str

    ################################### Exposed Methods ###############################

    def on_topic_request(self, message):
        """
        A method that is called when a dropbot topic request is received. This naming convention is to be followed
        for methods to be exposed. While calling it one would send a message to a topic that is
        something/dropbot/topic
        """
        pass

    ####################################################################################


