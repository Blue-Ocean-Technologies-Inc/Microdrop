from typing import Optional
from pydantic import BaseModel, computed_field, UUID4

class DeviceViewerMessageModel(BaseModel):
    # A map from channel number to activation status
    # Pydantic handles the int/str key conversion automatically during JSON loading
    channels_activated: dict[int, bool]

    # List of (electrode_ids, color_string)
    routes: list[tuple[list[str], str]]

    # Map electrode ID to channel number
    id_to_channel: dict[str, int]

    # Raw step info dictionary
    step_info: Optional[dict] = None

    editable: bool = True

    activated_electrodes_area_mm2: Optional[float] = 0

    uuid: UUID4

    @computed_field
    @property
    def step_id(self) -> Optional[str]:
        return self.step_info.get("step_id") if self.step_info else None

    @computed_field
    @property
    def step_label(self) -> Optional[str]:
        return self.step_info.get("step_label") if self.step_info else None

    @computed_field
    @property
    def free_mode(self) -> bool:
        return self.step_info.get("free_mode", False) if self.step_info else False

    def get_routes_with_ids(self) -> list[list[str]]:
        return [route[0] for route in self.routes]

    def get_routes_with_channels(self) -> list[list[int]]:
        return [
            [self.id_to_channel[electrode_id] for electrode_id in route_ids]
            for route_ids in self.get_routes_with_ids()
        ]

    def serialize(self) -> str:
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, json_str: str) -> "DeviceViewerMessageModel":
        # Pydantic automatically handles the dict[int, bool] conversion from JSON strings
        return cls.model_validate_json(json_str)

    def __repr__(self):
        count = sum(1 for v in self.channels_activated.values() if v)
        return f"<DeviceViewerMessageModel len(routes)={len(self.routes)} activated={count}>"


if __name__ == "__main__":
    import uuid

    test_step_info = {"step_id": "1", "step_label": "Test Step 1", "free_mode": False}
    test = DeviceViewerMessageModel(
        channels_activated={1: True},
        routes=[(["a", "a"], "red")],
        id_to_channel={"a": 1},
        step_info=test_step_info,
        uuid=uuid.uuid4(),
        activated_electrodes_area_mm2=1324.314
    )

    print(f"Routes as Channels: {test.get_routes_with_channels()}")
    print(f"Serialized: {test.serialize()}")

    # Proof of round-trip
    new_obj = DeviceViewerMessageModel.deserialize(test.serialize())
    print(f"Deserialized step_id: {new_obj.step_id}")
