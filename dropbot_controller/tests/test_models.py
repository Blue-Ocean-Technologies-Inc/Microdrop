import re

import numpy as np
import pytest
from traits.api import TraitError
from dropbot_controller.models.dropbot_channels_properties_model import DropbotChannelsPropertiesModelFromJSON


def test_message_model_success():
    """Test that JSON model controller accepts valid JSON string, validates it, and sets it to model. """
    json_data = '{"1": true, "2": false, "3": true}'
    parsed_data = {1: True, 2: False, 3: True}

    # Instantiate the model and validate
    model = DropbotChannelsPropertiesModelFromJSON(channels_properties_json=json_data).model
    assert model.channels_properties_dict == parsed_data

def test_message_model_failure_non_boolean_value():
    """Test that MessageModel raises TraitError for JSON with non-boolean values."""
    json_data = '{"1": true, "2": "false"}'  # Value "false" is a string, not a boolean

    with pytest.raises(TraitError,
                       match=re.escape("JSON Message input should be a dictionary with string representation of "
                                       "integer (numeric string) keys and Boolean values.")):
        DropbotChannelsPropertiesModelFromJSON(channels_properties_json=json_data)


def test_get_boolean_channels_states_mask():
    """Test that MessageModel returns the correct mask for the channels and states based on the input json string and
    max available channels specified
    """
    json_data = '{"0": true, "1": false, "9": true}'
    max_channels = 10

    # Instantiate the model and validate
    model = DropbotChannelsPropertiesModelFromJSON(channels_properties_json=json_data, num_available_channels=max_channels, property_dtype=bool).model
    assert np.all(
        model.channels_properties_mask ==
        np.array([True, False, False, False, False, False, False, False, False, True])
    )

def test_get_boolean_channels_states_mask_no_max_channel():
    """Test that MessageModel returns the correct mask for the channels and states based on the input json string and
    max available channels specified
    """
    json_data = '{"0": true, "1": false, "9": true}'
    max_channels = 10

    with pytest.raises(ValueError,
                       match=re.escape("Set num available channels.")):

        # Instantiate the model and validate
        model = DropbotChannelsPropertiesModelFromJSON(channels_properties_json=json_data).model
        mask = model.channels_properties_mask



def test_get_boolean_channels_states_mask_zero_on():
    """Test that MessageModel returns the correct mask for the channels and states based on the input json string and
    max available channels specified
    """
    json_data = '{"0": false, "1": false, "9": false}'
    max_channels = 10

    # Instantiate the model and validate
    model = DropbotChannelsPropertiesModelFromJSON(channels_properties_json=json_data, num_available_channels=max_channels, property_dtype=bool).model
    assert np.all(
        model.channels_properties_mask ==
        np.array([False, False, False, False, False, False, False, False, False, False])
    )

def test_model_from_changed_json():
    json_data_1 = '{"1": true, "2": false, "3": true}'
    json_data_2 = '{"1": false, "2": false, "3": false}'

    max_channels = 10

    json_model_factory = DropbotChannelsPropertiesModelFromJSON(channels_properties_json=json_data_1,
                                                   num_available_channels=max_channels, property_dtype=bool)

    model = json_model_factory.model

    assert np.all(
        model.channels_properties_mask ==
        np.array([False, True, False, True, False, False, False, False, False, False])
    )

    json_model_factory.channels_properties_json = json_data_2

    assert np.all(
        model.channels_properties_mask ==
        np.array([False, False, False, False, False, False, False, False, False, False])
    )
