import json

import numpy as np
from traits.api import provides, Int, Dict, Union, Float, Bool, cached_property, Enum, Property, Array, HasTraits, \
    Str, Instance, TraitError, observe, DelegatesTo

from dropbot_controller.interfaces.i_dropbot_channel_properties_model import IDropbotChannelsPropertiesModel, \
    IDropbotChannelsPropertiesModelFromJSON


@provides(IDropbotChannelsPropertiesModel)
class DropbotChannelsPropertiesModel(IDropbotChannelsPropertiesModel):
    """
    Implementation for dropbot channel properties model.
    """

    num_available_channels = Int(desc="Number of available channels at maximum on the dropbot.")
    channels_properties_dict = Dict(Int, Union(Float, Int, Bool), desc="Dictionary of channel properties")
    channels_properties_boolean_mask = Property(Array, observe="channels_properties_dict", desc="boolean mask representing channel properties.")
    property_dtype = Enum(int, float, bool, desc="Property type for channel properties array")

    @cached_property
    def _get_channels_properties_boolean_mask(self):
        mask = np.zeros(self.num_available_channels, dtype=self.property_dtype)

        for key, value in self.channels_properties_dict.items():
            mask[key] = value

        return mask


@provides(IDropbotChannelsPropertiesModelFromJSON)
class DropbotChannelsPropertiesModelFromJSON(HasTraits):
    """
        Implementation for dropbot channel properties model from a JSON string
    """

    num_available_channels = Int(desc="Number of available channels at maximum on the dropbot.")
    property_dtype = Enum(int, float, bool, desc="Property type for channel properties array")

    model = Instance(IDropbotChannelsPropertiesModel)

    channels_properties_json = Str(desc="JSON Message describing the channel_properties_dict")

    def traits_init(self):
        self.model = DropbotChannelsPropertiesModel(num_available_channels=self.num_available_channels, channels_properties_json=self.channels_properties_json)
        self.set_dropbot_properties_model_data(self.channels_properties_json)


    def set_dropbot_properties_model_data(self, json_msg):
        json_data_items = json.loads(json_msg).items()
        if all(k.isdigit() and isinstance(v, (int, float, bool)) for k, v in json_data_items):
            self.model.channels_properties_dict = {int(key): value for key, value in json_data_items}
        else:
            raise TraitError("JSON Message input should be a dictionary with string representation of "
                             "integer (numeric string) keys and Boolean values.")

    @observe('channels_properties_json', post_init=True)
    def _channels_properties_json_changed(self, event):
        """
        Trigger this if the channel properties json is changed.
        """
        # Add some extra functionality
        self.set_dropbot_properties_model_data(event.new)