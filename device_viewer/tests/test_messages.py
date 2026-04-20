from device_viewer.models.messages import DeviceViewerMessageModel


def _base_kwargs():
    return dict(
        channels_activated=set(),
        routes=[],
        id_to_channel={},
    )


def test_execution_params_defaults_to_none():
    msg = DeviceViewerMessageModel(**_base_kwargs())
    assert msg.execution_params is None


def test_execution_params_roundtrip():
    params = {
        "duration": 1.5,
        "repetitions": 3,
        "repeat_duration": 0.0,
        "trail_length": 2,
        "trail_overlay": 1,
        "soft_start": True,
        "soft_terminate": False,
    }
    msg = DeviceViewerMessageModel(**_base_kwargs(), execution_params=params)

    rebuilt = DeviceViewerMessageModel.deserialize(msg.serialize())
    assert rebuilt.execution_params == params


def test_execution_params_none_roundtrip():
    msg = DeviceViewerMessageModel(**_base_kwargs())
    rebuilt = DeviceViewerMessageModel.deserialize(msg.serialize())
    assert rebuilt.execution_params is None
