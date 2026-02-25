# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

from electrode_controller.models import ElectrodeStateChangePublisher

ELECTRODES_STATE_CHANGE = 'hardware/requests/electrodes_state_change'

electrode_state_change_publisher = ElectrodeStateChangePublisher(topic=ELECTRODES_STATE_CHANGE)