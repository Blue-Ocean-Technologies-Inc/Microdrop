import json

class DeviceViewerMessageModel():
    '''A minimal model for device viewer such that there is enough info to:
    - Combine with protocol_grid to generate electrode states
    - Construct a message to display the routes/electrodes when a protocol is playing
    - Save/Load device_viewer state from/to a file
    The actual models are way too large and contain lots of GUI-specific values that don't really need to be saved/transmitted
    '''
    def __init__(self, channels_activated: dict[int, bool], routes: list[tuple[list[str], str]], 
                 id_to_channel: dict[str, int], step_info: dict[str, str], editable: bool=True):
        # A map from channel number to whether it is activated (not as part of a route) 
        self.channels_activated = channels_activated
        # An in-order list of tuples (route, color), where route is a list of electrode ids in the path
        # and color is a QColor-compatible color for the route
        self.routes = routes
        # A dict that takes electrode ids as a key and gives the relevant channel
        self.id_to_channel = id_to_channel
        # A dict containing step information
        self.step_info = step_info or None
        if self.step_info is not None:  
            self.step_id = step_info.get("step_id", None)
            self.step_label = step_info.get("step_label", None)
        self.editable = editable # True (editing) or False (running)
 
    def get_routes_with_ids(self) -> list[list[str]]:
        """Returns a list of just the electrode_id parts of each route"""
        return [routedata[0] for routedata in self.routes]
    
    def get_routes_with_channels(self) -> list[list[int]]:
        """Takes get_routes_with_ids and maps the electrode_ids to thier respective channels"""
        return [[self.id_to_channel[electrode_id] for electrode_id in route ] for route in self.get_routes_with_ids()]
    
    def serialize(self) -> str:
        return json.dumps(self.to_dict())
    
    def to_dict(self) -> dict:
        return {
            "channels_activated": self.channels_activated,
            "routes": self.routes,
            "id_to_channel": self.id_to_channel,
            "step_info": self.step_info,
            "editable": self.editable
        }
    
    @staticmethod
    def deserialize(string: str) -> 'DeviceViewerMessageModel':
        obj = json.loads(string)

        channels_activated_with_int_keys = {int(k): v for k, v in obj["channels_activated"].items()}
        obj["channels_activated"] = channels_activated_with_int_keys # Convert keys to int for consistency with the constructor

        try:
            return DeviceViewerMessageModel(
                obj["channels_activated"], 
                obj["routes"], 
                obj["id_to_channel"], 
                obj["step_info"], 
                obj.get("editable", True)
            )
        except KeyError:
            raise ValueError("Provided string is not a valid Device Viewer message")
        
    def __repr__(self):
        number_of_channels_activated = 0
        for _, activated in self.channels_activated.items():
            if activated:
                number_of_channels_activated += 1
        return f"<DeviceViewerMessageModel len(routes)={len(self.routes)} number_of_channels_activated={number_of_channels_activated}>"

if __name__ == "__main__":
    test_step_info = {"step_id": "1", "step_label": "Test Step 1"}
    test = DeviceViewerMessageModel({1: True}, [(["a", "a"], "red")], {"a": 1}, test_step_info, True)
    print(test.get_routes_with_channels())
    print(test.get_routes_with_ids())
    print(test.serialize())
    print(DeviceViewerMessageModel.deserialize(test.serialize()).serialize())