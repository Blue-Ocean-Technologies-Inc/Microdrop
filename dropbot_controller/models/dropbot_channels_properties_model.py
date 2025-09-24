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
        if self.num_available_channels == 0:
            raise ValueError("Set num available channels.")

        mask = np.zeros(self.num_available_channels, dtype=self.property_dtype)

        for key, value in self.channels_properties_dict.items():
            mask[key] = value

        return mask


@provides(IDropbotChannelsPropertiesModelFromJSON)
class DropbotChannelsPropertiesModelFromJSON(HasTraits):
    """
        Implementation for dropbot channel properties model from a JSON string
    """

    num_available_channels = Property(Int, observe='model')
    property_dtype = Property(Enum(bool, int, float), observe='model')

    channels_properties_json = Str(desc="JSON Message describing the channel_properties_dict")

    model = Instance(IDropbotChannelsPropertiesModel)

    ################################### Protected methods ####################################

    # -------------------------Trait default values--------------------------------
    def _model_default(self):
        """Return a default model instance"""
        return DropbotChannelsPropertiesModel()

    # ----------- Define class property getters and setters------------------------
    def _get_num_available_channels(self):
        return self.model.num_available_channels

    def _get_property_dtype_channels(self):
        return self.model.property_dtype

    # Define class property setters, which configures the model attributes
    def _set_num_available_channels(self, value):
        self.model.num_available_channels = value

    def _set_property_dtype(self, value):
        self.model.property_dtype = value

    def _update_model_from_json(self, json_msg):
        json_data_items = json.loads(json_msg).items()
        if all(k.isdigit() and isinstance(v, (int, float, bool)) for k, v in json_data_items):
            self.model.channels_properties_dict = {int(key): value for key, value in json_data_items}
        else:
            raise TraitError("JSON Message input should be a dictionary with string representation of "
                             "integer (numeric string) keys and Boolean values.")

    # --------------------------------------------------------------------------------

    def traits_init(self):
        self._update_model_from_json(self.channels_properties_json)

    @observe('channels_properties_json', post_init=True)
    def _channels_properties_json_changed(self, event):
        """
        Trigger this if the channel properties json is changed post init.
        Configure model accordingly.
        """
        self._update_model_from_json(event.new)