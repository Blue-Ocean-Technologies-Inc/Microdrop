from ..models.messages import DeviceViewerMessageModel
from ..models.main_model import DeviceViewMainModel

def gui_models_to_message_model(model: DeviceViewMainModel) -> DeviceViewerMessageModel:
    """Returns a deep-copied DeviceViewerMessageModel from our existing models"""

    id_to_channel = {}
    for electrode_id, electrode in model.electrodes.electrodes.items():
        id_to_channel[electrode_id] = electrode.channel

    return DeviceViewerMessageModel(
        channels_activated=model.electrodes.channels_states_map,
        routes=[(layer.route.route, layer.color) for layer in model.routes.layers],
        id_to_channel=id_to_channel,
        step_info={"step_id": model.step_id, "step_label": model.step_label},
        uuid=model.uuid,
        editable=model.editable,
        activated_electrodes_area_mm2=model.electrodes.get_activated_electrode_area_mm2(),
    )