# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Package-level constants for zone_protocol_controls.

The plugin owns no topics: the Zone Target column uses the DropBot's
DETECT_DROPLETS / DROPLETS_DETECTED round trip (dropbot_controller.consts)
and reads the device viewer's zones snapshot (device_viewer.consts.ZONES_KEY).
"""

PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

ACTOR_TOPIC_DICT = {}

#: Compound base id — the persistence discriminator of the Zone Target column.
ZONE_TARGET_BASE_ID = "zone_target"

#: Row traits / cell col_ids: the zone type id ("" = off for the step) and
#: the criterion the chosen region must meet.
ZONE_TARGET_FIELD_ID = "zone_target"
ZONE_TARGET_CRITERION_FIELD_ID = "zone_target_criterion"

#: Default wait (seconds) for the DROPLETS_DETECTED reply; matches the
#: Check Droplets column's window, the detection backend retries internally.
ZONE_TARGET_DEFAULT_ACK_TIME_S = 12.0

#: Handler priority: on_pre_step runs ahead of the routes/V-F on_step hooks
#: anyway; 25 keeps it out of the 30 (volume threshold) and 80 (droplet
#: check) buckets that also wait on DROPLETS_DETECTED.
ZONE_TARGET_PRIORITY = 25


class ZoneCriterion:
    """Values of the per-step criterion cell. Plain str constants, NOT a
    Python enum — they are persisted in protocol JSON and compared as bare
    strings."""

    HAS_DROPLET = "Has Droplet"
    NO_DROPLET = "No Droplet"


#: The selectable criteria, in display order; the first is the default.
ZONE_CRITERIA = (ZoneCriterion.HAS_DROPLET, ZoneCriterion.NO_DROPLET)
