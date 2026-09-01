# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Package-level constants for portable_dropbot_protocol_controls.

Topic constants and hardware bounds live in portable_dropbot_controller/
consts.py — this plugin imports them (the same layering as
dropbot_protocol_controls over dropbot_controller).
"""

PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

#: Checkbox field (row trait) of the magnet compound column: command the
#: magnet on this step, or leave it untouched (no engage/disengage
#: publish, no applied-ack wait). Referenced by the handler gate and the
#: cross-cell editability views.
SET_MAGNET_FIELD_ID = "set_magnet"

#: Checkbox field (row trait) of the temperature compound column: drive
#: the heater on this step, or leave it untouched (no setpoint publish,
#: no reached-ack wait).
SET_TEMPERATURE_FIELD_ID = "set_temperature"
