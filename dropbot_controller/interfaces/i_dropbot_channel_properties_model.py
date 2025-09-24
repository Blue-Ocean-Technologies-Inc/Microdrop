import numpy as np
from traits.api import Instance, Interface, cached_property, Dict, Union, Float, Int, Bool, Array, Property, Str, observe, \
    Enum
from traits.trait_types import self


class IDropbotChannelsPropertiesModel(Interface):
    """
    Model for information about dropbot channel properties.
    """
    num_available_channels = Int(desc="Number of available channels at maximum on the dropbot.")
    property_dtype = Enum(int, float, bool, desc="Property type for channel properties array")
    channels_properties_dict = Dict(Int, Union(Float, Int, Bool), desc="Dictionary of channel properties")
    channels_properties_boolean_mask = Property(Array, observe="channels_properties_dict", desc="boolean mask representing channel properties.")

    @cached_property
    def _get_channels_properties_boolean_mask(self) -> Array:
        """
        Create a Boolean mask array indicating dropbot channels properties (area, actuation status etc).
        Returns:
            np.ndarray: A array of size `max_size`.
        """
        pass


class IDropbotChannelsPropertiesModelFromJSON(Interface):
    """
    Model for the JSON string containing information about dropbot electrode properties.
    """
    num_available_channels = Int(desc="Number of available channels at maximum on the dropbot.")
    property_dtype = Enum(int, float, bool, desc="Property type for channel properties array")

    model = Instance(IDropbotChannelsPropertiesModel)

    channels_properties_json = Str(desc="JSON Message describing the channel_properties_dict")

    def set_dropbot_properties_model_data(self, json_msg):
        """
        Define routine to set the channel_properties_dict attribute using the new json string and
        create the dropbot channel properties model.
        """

    def traits_init(self):
        """
        Initialize traits, create the model.
        """
        # Create Model
        # self.set_dropbot_properties_model_data(self.channels_properties_json)

    @observe('channels_properties_json', post_init=True)
    def _channels_properties_json_changed(self):
        """
        Trigger this if the channel properties json is changed post init.
        """
         # Add some extra functionality
        # self.set_dropbot_properties_model_data(self)