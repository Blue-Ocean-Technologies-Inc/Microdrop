# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Microdrop utils imports.
from microdrop_utils.source_update_startup import AUTO_UPDATE_PREFERENCE_PATH

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

ACTOR_TOPIC_DICT = {}

#: The node of this plugin's preferences. Derived from the path the startup
#: step reads before the application exists, so the two cannot drift.
PREFERENCES_PATH = AUTO_UPDATE_PREFERENCE_PATH.rpartition(".")[0]

#: Update policies: move to the newest release at startup, or stay put.
POLICY_LATEST = "latest"
POLICY_STAY = "stay"

#: Shown in place of a changelog section the selected release does not have.
NO_CHANGELOG_TEXT = "No changelog for this version."

#: The running version when the source is not a git checkout.
UNKNOWN_VERSION_TEXT = "unknown (not a git checkout)"

#: The answers to the warning for a release that pulls at every start.
SET_AND_SWITCH = "Set it and switch"
SWITCH_WITHOUT_IT = "Switch without it"
