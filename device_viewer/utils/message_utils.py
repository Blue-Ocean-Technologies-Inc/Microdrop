from ..models.messages import DeviceViewerMessageModel
from ..models.main_model import DeviceViewMainModel

def gui_models_to_message_model(model: DeviceViewMainModel) -> DeviceViewerMessageModel:
    """Returns a deep-copied DeviceViewerMessageModel from our existing models"""

    id_to_channel = {}
    for electrode_id, electrode in model.electrodes.electrodes.items():
        id_to_channel[electrode_id] = electrode.channel

    # In free mode, carry the sidebar's current execution params so the grid
    # can seed them into a newly-created step. With a step selected, the grid
    # already owns those values — don't round-trip them.
    exec_params = None
    if not model.step_id:
        exec_params = model.routes._current_params()

    return DeviceViewerMessageModel(
        channels_activated=model.electrodes.actuated_channels,
        routes=[(layer.route.route, layer.color) for layer in model.routes.layers],
        id_to_channel=id_to_channel,
        step_info={"step_id": model.step_id, "step_label": model.step_label},
        uuid=model.uuid,
        editable=model.editable,
        activated_electrodes_area_mm2=model.electrodes.get_activated_electrode_area_mm2(),
        svg_file=model.electrodes.svg_model.filename,
        execution_params=exec_params,
    )