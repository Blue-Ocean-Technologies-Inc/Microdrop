from unittest.mock import patch

import pytest
import os
from collections import OrderedDict

from microdrop_utils._logger import get_logger
from protocol_grid_controller.services.protocol_grid_structure_services import ProtocolGridStructureService

logger = get_logger(__name__)


@pytest.fixture
def protocol_service():
    return ProtocolGridStructureService()


@pytest.fixture
def example_protocol():
    return OrderedDict([
        ("Step 1", {"Order": 1, "Description": "Monkas1", "Duration": 2, "Voltage": 15, "Frequency": 10000}),
        ("Step-Group[2-4]", {
            "Order": -1,
            "Repetitions": 5,
            "Step 2": {"Order": 2, "Description": "Monkas2", "Duration": 4, "Voltage": 25, "Frequency": 20000},
            "Step 3": {"Order": 3, "Description": "Monkas3", "Duration": 6, "Voltage": 35, "Frequency": 30000},
            "Step 4": {"Order": 4, "Description": "Monkas4", "Duration": 8, "Voltage": 45, "Frequency": 40000}
        }),
        ("Step 5", {"Order": 5, "Description": "Monkas5", "Duration": 10, "Voltage": 55, "Frequency": 50000})
    ])


def test_add_step(protocol_service):
    protocol_service.add_step("Step 1", ["Electrode 1", "Electrode 2"])
    assert protocol_service.steps == ["Step 1"]
    assert protocol_service.electrodes_on == {"Step 1": ["Electrode 1", "Electrode 2"]}


def test_save_and_load_protocol(protocol_service, example_protocol, tmpdir):
    def remove_is_json_keys(protocol):
        def remove_keys(d):
            if isinstance(d, dict):
                return {k: remove_keys(v) for k, v in d.items() if not k.endswith("_is_json")}
            return d

        return remove_keys(protocol)

    filename = os.path.join(tmpdir, "test_protocol.h5")
    ProtocolGridStructureService.save_protocol_to_hdf5(example_protocol, filename)
    loaded_protocol = ProtocolGridStructureService.load_protocol_from_hdf5(filename)
    loaded_protocol = remove_is_json_keys(loaded_protocol)

    assert example_protocol.keys() == loaded_protocol.keys()
    for key in example_protocol.keys():
        assert example_protocol[key] == loaded_protocol[key]


def test_create_execution_order(protocol_service, example_protocol):
    order = ProtocolGridStructureService.create_execution_order(example_protocol)
    expected_order = [1, 2, 3, 4, 2, 3, 4, 2, 3, 4, 2, 3, 4, 2, 3, 4, 5]
    assert order == expected_order


def test_extract_commands(protocol_service, example_protocol):
    commands = ProtocolGridStructureService.extract_commands(example_protocol)
    expected_commands = [
        {'Description': 'Monkas1', 'Duration': 2, 'Voltage': 15, 'Frequency': 10000},
        {'Description': 'Monkas2', 'Duration': 4, 'Voltage': 25, 'Frequency': 20000},
        {'Description': 'Monkas3', 'Duration': 6, 'Voltage': 35, 'Frequency': 30000},
        {'Description': 'Monkas4', 'Duration': 8, 'Voltage': 45, 'Frequency': 40000},
        {'Description': 'Monkas5', 'Duration': 10, 'Voltage': 55, 'Frequency': 50000}
    ]
    assert commands == expected_commands
