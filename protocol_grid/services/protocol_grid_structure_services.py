import json
import os
import time
from collections import OrderedDict

import dramatiq
import h5py
from traits.api import Dict, HasTraits, provides
from traits.trait_types import Str, List

from protocol_grid_controller.interfaces.i_protocol_grid_controller_service import IPGSService
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)


@provides(IPGSService)
class ProtocolGridStructureService(HasTraits):
    id = "app.protocol_grid_structure_services"
    name = "Protocol Grid Structure Services"
    steps = List(default_value=[])
    electrodes_on = Dict(key_trait=Str(), value_trait=List(Str), default_value={})
    file_save_dir = Str(default_value=f"{os.getcwd()}{os.sep}Protocol_Saves")
    file_name = Str(default_value="")
    selected_step = 0
    protocol_data = List(default_value=[])

    def add_step(self, step: str, electrodes_on: list[str]):
        self.steps.append(step)
        self.electrodes_on[step] = electrodes_on

    @staticmethod
    def save_ordered_dict_to_hdf5(ordered_dict, file_name):
        def recursively_save_dict_to_group(group, dict_to_save):
            for key, item in dict_to_save.items():
                if isinstance(item, dict):
                    subgroup = group.create_group(key)
                    recursively_save_dict_to_group(subgroup, item)
                else:
                    group.attrs[key] = item
            group.attrs['order'] = list(dict_to_save.keys())  # Save the order of keys

        with h5py.File(file_name, 'w') as h5file:
            recursively_save_dict_to_group(h5file, ordered_dict)

    @staticmethod
    def load_ordered_dict_from_hdf5(file_name):
        def recursively_load_dict_from_group(group):
            result = OrderedDict()
            if 'order' in group.attrs:
                order = group.attrs['order']
                for key in order:
                    if key in group.attrs:
                        result[key] = group.attrs[key]
                    else:
                        result[key] = recursively_load_dict_from_group(group[key])
            else:
                for key, item in group.attrs.items():
                    result[key] = item
                for key, subgroup in group.items():
                    result[key] = recursively_load_dict_from_group(subgroup)
            return result

        with h5py.File(file_name, 'r') as h5file:
            return recursively_load_dict_from_group(h5file)

    @staticmethod
    def generate_steps_list(protocol):
        steps_list = []

        def recursively_add_steps(step_dict, parent_key=''):
            if 'Type' in step_dict and step_dict['Type'] == 'Group':
                repetitions = step_dict.get('Repetitions', 1)
                for _ in range(repetitions):
                    for key, value in step_dict.items():
                        if key not in ['Type', 'Repetitions']:
                            recursively_add_steps(value, key)
            else:
                steps_list.append({parent_key: step_dict})

        for key, value in protocol.items():
            recursively_add_steps(value, key)

        return steps_list

    @staticmethod
    def extract_commands(protocol_data):
        commands = []

        def recursively_extract_commands(step_dict):
            if 'Description' in step_dict:  # This is a single step
                commands.append(step_dict)
            elif 'Type' in step_dict and step_dict['Type'] == 'Group':  # This is a step group
                repetitions = step_dict.get('Repetitions', 1)
                for _ in range(repetitions):
                    for key, value in step_dict.items():
                        if key not in ['Type', 'Repetitions']:
                            recursively_extract_commands(value)

        for key, value in protocol_data.items():
            recursively_extract_commands(value)

        return commands

    @staticmethod
    def execute_step(step):
        description = step['Description']
        duration = step['Duration']
        voltage = step['Voltage']
        frequency = step['Frequency']

        logger.info(f"Executing {description}: Duration={duration}s, Voltage={voltage}V, Frequency={frequency}Hz")
        time.sleep(duration)  # Simulating execution with sleep

    def execute_protocol(self, protocol):
        """ Execute the protocol in the order they appear in the protocol data. """
        steps_by_order = self.extract_commands(protocol)  # gets list of unique command rows in the protocol
        logger.info(steps_by_order)

        for step in steps_by_order:
            print(step)
            self.execute_step(step)  # execute the command

    def on_cell_changed(self, message):
        """
        example:
        '{
        1: {"Description": "this is description 1", "Duration": 30, "Voltage": 100, "Frequency": 10000},
        2: {"Description": "this is description 2", "Duration": 20, "Voltage": 50, "Frequency": 10000},
        3: {"Description": "this is description 3", "Duration": 10, "Voltage": 60, "Frequency": 10000},
        }'

        json.loads turns it to dictionary
        """

        temp_protocol_data = json.loads(message)
        for key, value in temp_protocol_data.items():
            self.protocol_data[key] = value


if __name__ == '__main__':
    example_protocol = OrderedDict([
        ("Step 1", {"Description": "Monkas1",
                    "Duration": 2,
                    "Voltage": 15,
                    "Frequency": 10000,
                    "electrode_channels_on": [1, 2, 3]}),
        ("Step-Group[2-4]", {
            "Type": "Group",
            "Repetitions": 5,
            "Step 2": {"Description": "Monkas2",
                       "Duration": 4,
                       "Voltage": 25,
                       "Frequency": 20000,
                       "electrode_channels_on": [1, 2, 3]},
            "Step 3": {"Description": "Monkas3",
                       "Duration": 6,
                       "Voltage": 35,
                       "Frequency": 30000,
                       "electrode_channels_on": [1, 2, 3]},
            "Step 4": {"Description": "Monkas4",
                       "Duration": 8,
                       "Voltage": 45,
                       "Frequency": 40000,
                       "electrode_channels_on": [1, 2, 3]}
        }),
        ("Step 5", {"Description": "Monkas5",
                    "Duration": 10,
                    "Voltage": 55,
                    "Frequency": 50000,
                    "electrode_channels_on": [1, 2, 3]})

    ])

    filename = "test_protocol.h5"
    ProtocolGridStructureService.save_ordered_dict_to_hdf5(example_protocol, filename)
    protocol = ProtocolGridStructureService.load_ordered_dict_from_hdf5(filename)
    print(f"protocol: {protocol}")
    order = ProtocolGridStructureService.generate_steps_list(protocol)
    print(f"Step List: {order}")
