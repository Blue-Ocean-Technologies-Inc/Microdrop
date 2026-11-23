# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Droplet detection threshold defaults."""

#: Default capacitance (pF) a channel must read to count as holding liquid
#: (Portable DropBot Settings preference), the driver's own drop default.
#: Per channel, the driver's saved overrides and a fresh baseline still
#: replace it and the active chip's electrode weights scale it.
DROPLET_DETECTION_THRESHOLD_PF = 5.0

#: Bounds of the droplet detection threshold preference (pF); the driver
#: refuses anything above 1000 pF.
DROPLET_DETECTION_THRESHOLD_PF_BOUNDS = (0.1, 1000.0)
