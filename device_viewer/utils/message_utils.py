from ..models.messages import DeviceViewerMessageModel
from ..models.route import RouteLayerManager
from ..models.electrodes import Electrodes

import copy

def gui_models_to_message_model(electrodes: Electrodes, route_manager: RouteLayerManager) -> DeviceViewerMessageModel:
    """Returns a deep-copied DeviceViewerMessageModel from our existing models"""
    channels_activated = electrodes.channels_states_map
    routes = [(layer.route.route, layer.color) for layer in route_manager.layers]
    id_to_channel = {}
    for electrode_id, electrode_dict in electrodes.svg_model.electrodes.items():
        id_to_channel[electrode_id] = electrode_dict["channel"]
    
    return DeviceViewerMessageModel(channels_activated, routes, id_to_channel)