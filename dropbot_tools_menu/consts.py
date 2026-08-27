# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from dropbot_controller.consts import SELF_TESTS_PROGRESS, CHIP_INSERTED, DROPBOT_DISCONNECTED
# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

from microdrop_application.consts import PKG as microdrop_application_package

# Topics this plugin wants some actors to subscribe to:
ACTOR_TOPIC_DICT = {
    f"{microdrop_application_package}_listener": [ SELF_TESTS_PROGRESS], # This adds the listener to the microdrop application task, not itself
    f"{PKG}_listener": [ 
                                 CHIP_INSERTED,
                                 DROPBOT_DISCONNECTED,
                                 SELF_TESTS_PROGRESS
    ]}

