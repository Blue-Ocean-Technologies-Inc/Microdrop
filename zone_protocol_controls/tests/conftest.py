# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pre-wire the dramatiq broker before the column module builds its module
level app_globals proxy (no Redis connection is made until a read)."""

# Microdrop utils imports.
from microdrop_utils.broker_server_helpers import configure_dramatiq_broker

configure_dramatiq_broker()
