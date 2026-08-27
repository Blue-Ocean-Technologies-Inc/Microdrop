# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

from electrode_controller.models import ElectrodeStateChangePublisher, ElectrodeDisableRequestPublisher, DisabledChannelsChangedPublisher
from dropbot_controller.consts import DISABLED_CHANNELS_CHANGED

ELECTRODES_STATE_CHANGE = 'hardware/requests/electrodes_state_change'
ELECTRODES_DISABLE_REQUEST = 'hardware/requests/electrodes_disable'
ELECTRODES_STATE_APPLIED = 'hardware/electrodes_state_applied'

electrode_state_change_publisher = ElectrodeStateChangePublisher(topic=ELECTRODES_STATE_CHANGE)
electrode_disable_request_publisher = ElectrodeDisableRequestPublisher(topic=ELECTRODES_DISABLE_REQUEST)
disabled_channels_changed_publisher = DisabledChannelsChangedPublisher(topic=DISABLED_CHANNELS_CHANGED)