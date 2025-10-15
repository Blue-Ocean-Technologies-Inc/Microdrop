import json
import pytest
import numpy as np
from traits.trait_errors import TraitError

from device_viewer.models.electrodes import Electrodes
from device_viewer.utils.dmf_utils_helpers import channels_to_svg
from .common import TEST_PATH
from pathlib import Path

correct_path_array = np.array(

    [
        [[29.03221, 74.702264]],
        [[23.051897, 74.702264]],
        [[23.051897, 80.861713]],
        [[29.03221, 80.861713]]
    ]
)

sample_svg_path = Path(TEST_PATH) / "device_svg_files" / "2x3device.svg"
sample_svg_path_with_scale = Path(TEST_PATH) / "device_svg_files" / "2x3device_with_scale.svg"
sample_svg_valid_channels_states_map = Path(TEST_PATH) / "valid_2x3_device_electrodes_states_map.json"
sample_svg_valid_channels_electrode_ids_map = Path(TEST_PATH) / "valid_2x3_device_channels_electrode_ids_map.json"


@pytest.fixture
def valid_electrodes_model_from_svg():
    from device_viewer.models.electrodes import Electrodes
    # Initialize an instance of Electrodes and load the SVG file
    electrodes = Electrodes()
    electrodes.set_electrodes_from_svg_file(sample_svg_path)
    return electrodes

@pytest.fixture
def valid_electrodes_model_from_svg_with_scale():
    from device_viewer.models.electrodes import Electrodes
    # Initialize an instance of Electrodes and load the SVG file
    electrodes = Electrodes()
    electrodes.set_electrodes_from_svg_file(sample_svg_path_with_scale)
    return electrodes


def test_electrodes_initialization():
    from device_viewer.models.electrodes import Electrodes
    # Initialize an instance of Electrodes and load the SVG file
    electrodes = Electrodes()
    electrodes.set_electrodes_from_svg_file(sample_svg_path)
    assert electrodes.svg_model.area_scale == 1.0

    # Initialize an instance of electrode, load with svg file with scale metadata.
    electrodes_with_scale = Electrodes()
    electrodes_with_scale.set_electrodes_from_svg_file(sample_svg_path_with_scale)

    assert electrodes_with_scale.svg_model.area_scale == 0.34

    # Add an assertion to validate successful setup.
    # Check if 92 electrodes initialized here which is true for the sample device
    assert len(electrodes) == 92
    assert len(electrodes_with_scale) == 92


def test_electrode_creation_traits_check_fail():
    try:
        from device_viewer.models.electrodes import Electrode
        Electrode(channel=1, path=[[1, 1], [2, 2], [3, 3]])
    except Exception as e:
        assert isinstance(e, TraitError)

    try:
        Electrode(channel="1", path=correct_path_array)
    except Exception as e:
        assert isinstance(e, TraitError)


def test_electrode_creation_traits_check_path_pass():
    from device_viewer.models.electrodes import Electrode
    test_electrode = Electrode(channel=1, path=correct_path_array)

    assert test_electrode.channel == 1 and np.array_equal(test_electrode.path, correct_path_array)


def test_electrodes_creation_traits_check_fail():
    from device_viewer.models.electrodes import Electrode, Electrodes
    try:
        Electrodes(electrodes={"1": Electrode(channel=1, path=correct_path_array),
                               "2": Electrode(channel=2, path=[[1, 1], [2, 2], [3, 3]])})
    except Exception as e:
        assert isinstance(e, TraitError)

    try:
        Electrodes(electrodes={"1": Electrode(channel=1, path=correct_path_array),
                               "2": Electrode(channel="2", path=correct_path_array)})
    except Exception as e:
        assert isinstance(e, TraitError)


def test_electrodes_creation_traits_check_pass():
    from device_viewer.models.electrodes import Electrode, Electrodes

    electrodes = Electrodes(electrodes={"1": Electrode(channel=1, path=correct_path_array),
                                        "2": Electrode(channel=2, path=correct_path_array)})
    assert isinstance(electrodes.electrodes, dict) and len(electrodes.electrodes) == 2


def test_get_channels_electrode_ids_map(valid_electrodes_model_from_svg):
    """
    Test method to get map of channels to electrode ids that have this channel associated with them.
    Some channels should have multiple electrode ids (like channel 30 for the example device svg).
    """

    #: get valid json file
    with open(sample_svg_valid_channels_electrode_ids_map) as f:
        valid_electrodes_model = json.load(f)

    #: check electrodes_states_map
    for channel in valid_electrodes_model.keys():
        #: since json loading, this will have string keys
        assert valid_electrodes_model[channel] == valid_electrodes_model_from_svg.channels_electrode_ids_map[int(channel)]


def test_electrodes_states_map(valid_electrodes_model_from_svg):
    """
    Test getting map of electrodes actuation states from model as a property.
    If this property is accurate then the individual electrodes and states properties should be ok too since this is a
    composite of those two.
    """

    #: get valid json file
    with open(sample_svg_valid_channels_states_map) as f:
        valid_electrodes_model = json.load(f)

    #: check electrodes_states_map
    for channel in valid_electrodes_model.keys():
        #: since json loading, this will have string keys
        assert valid_electrodes_model[channel] == valid_electrodes_model_from_svg.channels_states_map[int(channel)]

    # check if traits listening works. so upon setting state of one of the channels, the channels states map should
    # update accordingly

    change_key = list(valid_electrodes_model_from_svg.electrodes.keys())[0]
    change_electrode = valid_electrodes_model_from_svg[change_key]
    change_electrode.state = not change_electrode.state

    # obtain new channels_states_map
    new_channels_states_map = valid_electrodes_model_from_svg.channels_states_map

    assert new_channels_states_map[change_electrode.channel] == True

def test_save_svg_file_init_scale_metadata(valid_electrodes_model_from_svg):
    # save file that initially does not have a scale, with a scale

    from device_viewer.utils.dmf_utils_helpers import channels_to_svg

    new_filename = Path(TEST_PATH) / "test_svg_model_save_init_scale.svg"
    new_pixel_scale = 0.55

    channels_to_svg(valid_electrodes_model_from_svg.svg_model.filename,
                    new_filename,
                    valid_electrodes_model_from_svg.electrode_ids_channels_map,
                    new_pixel_scale)

    test_saved_electrode = Electrodes()
    test_saved_electrode.set_electrodes_from_svg_file(new_filename)

    assert test_saved_electrode.svg_model.area_scale == new_pixel_scale

def test_save_svg_file_edit_scale_metadata(valid_electrodes_model_from_svg_with_scale):
    # save file that initially does have a scale, with a new scale

    from device_viewer.utils.dmf_utils_helpers import channels_to_svg

    # check that the loaded file is as expected
    assert valid_electrodes_model_from_svg_with_scale.svg_model.area_scale == 0.34

    new_filename = Path(TEST_PATH) / "test_svg_model_save_edit_scale.svg"
    new_pixel_scale = 0.55

    channels_to_svg(valid_electrodes_model_from_svg_with_scale.svg_model.filename,
                    new_filename,
                    valid_electrodes_model_from_svg_with_scale.electrode_ids_channels_map,
                    new_pixel_scale)

    test_saved_electrode = Electrodes()
    test_saved_electrode.set_electrodes_from_svg_file(new_filename)

    assert test_saved_electrode.svg_model.area_scale == new_pixel_scale