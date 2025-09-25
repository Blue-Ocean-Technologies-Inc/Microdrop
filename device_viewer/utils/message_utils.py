from ..models.messages import DeviceViewerMessageModel
from ..models.route import RouteLayerManager
from ..models.electrodes import Electrodes
from ..models.main_model import DeviceViewMainModel

import copy

def gui_models_to_message_model(model: DeviceViewMainModel) -> DeviceViewerMessageModel:
    """Returns a deep-copied DeviceViewerMessageModel from our existing models"""
    channels_activated = model.electrodes.channels_states_map
    routes = [(layer.route.route, layer.color) for layer in model.routes.layers]
    id_to_channel = {}
    for electrode_id, electrode in model.electrodes.electrodes.items():
        id_to_channel[electrode_id] = electrode.channel

    return DeviceViewerMessageModel(channels_activated, routes, id_to_channel, {"step_id": model.step_id, "step_label": model.step_label}, editable=model.editable, uuid=model.uuid)