from ..models.messages import DeviceViewerMessageModel
from ..models.route import RouteLayerManager
from ..models.electrodes import Electrodes
from ..models.main_model import MainModel

import copy

def gui_models_to_message_model(model: MainModel) -> DeviceViewerMessageModel:
    """Returns a deep-copied DeviceViewerMessageModel from our existing models"""
    channels_activated = model.channels_states_map
    routes = [(layer.route.route, layer.color) for layer in model.layers]
    id_to_channel = {}
    for electrode_id, electrode in model.electrodes.items():
        id_to_channel[electrode_id] = electrode.channel

    return DeviceViewerMessageModel(channels_activated, routes, id_to_channel, model.step_id)