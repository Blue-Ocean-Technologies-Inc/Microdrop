# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

from electrode_controller.models import ElectrodeStateChangePublisher, ElectrodeDisableRequestPublisher

ELECTRODES_STATE_CHANGE = 'hardware/requests/electrodes_state_change'
ELECTRODES_DISABLE_REQUEST = 'hardware/requests/electrodes_disable'

electrode_state_change_publisher = ElectrodeStateChangePublisher(topic=ELECTRODES_STATE_CHANGE)
electrode_disable_request_publisher = ElectrodeDisableRequestPublisher(topic=ELECTRODES_DISABLE_REQUEST)