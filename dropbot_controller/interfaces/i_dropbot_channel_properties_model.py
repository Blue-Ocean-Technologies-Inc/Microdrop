import numpy as np
from traits.api import Instance, Interface, cached_property, Dict, Union, Float, Int, Bool, Array, Property, Str, observe, \
    Enum

from traits.trait_types import self


class IDropbotChannelsPropertiesModel(Interface):
    """Interface for a model containing information about dropbot channel properties."""

    num_available_channels = Int(desc="Number of available channels at maximum on the dropbot.")
    property_dtype = Enum(int, float, bool, desc="Property type for channel properties array")
    channels_properties_dict = Dict(Int, Union(Float, Int, Bool), desc="Dictionary of channel properties")
    channels_properties_mask = Property(Array, observe="channels_properties_dict", desc="boolean mask representing channel properties.")

    def _get_channels_properties_mask(self):
        """Return a boolean mask representing channel properties."""

class IDropbotChannelsPropertiesModelFromJSON(Interface):
    """
    Interface for a controller that validates a JSON string and uses it to update a
    DropbotChannelsPropertiesModel instance.
    """

    num_available_channels = Property(Int, observe='model')
    property_dtype = Property(Enum(bool, int, float), observe='model')

    channels_properties_json = Str(desc="JSON Message describing the channel_properties_dict")

    model = Instance(IDropbotChannelsPropertiesModel)

    ################################### Protected methods ####################################

    #-------------------------Trait default values--------------------------------
    def _model_default(self):
        """Return a default model instance"""

    #----------- Define class property getters and setters------------------------
    def _get_num_available_channels(self):
        """return dropbot number of available channels from the model."""

    def _get_property_dtype_channels(self):
        """return channel property dtype from the model"""

    # Define class property setters, which configures the model attributes
    def _set_num_available_channels(self, value):
        """Set model's num_available_channels to value"""

    def _set_property_dtype(self, value):
        """Set model's property dtype trait to value"""

    #--------------------------------------------------------------------------------

    def _update_model_from_json(self, json_msg):
        """
        Define routine to set the channel_properties_dict attribute using the new json string and
        create the dropbot channel properties model. Validate the JSON string here before setting the dict data.
        """

    ##########################################################################################

    def traits_init(self):
        """Initialize traits, create the model using JSON data"""

    @observe('channels_properties_json', post_init=True)
    def _channels_properties_json_changed(self, event):
        """
        Trigger this if the channel properties json is changed post init.
        Configure model accordingly.
        """