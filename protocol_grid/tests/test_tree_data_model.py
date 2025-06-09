import json
import pytest
from .common import VALID_OUTPUTS

from protocol_grid_controller.model.tree_data import ProtocolGroup, ProtocolStep


@pytest.fixture
def protocol_tree():
    root = ProtocolGroup(name="Root Group")  # [0]
    step1 = ProtocolStep(name="Step1", parameters={"param1": "value1"})  # [0, 0]
    root.add_element(step1)

    # Level 1
    sub_group = ProtocolGroup(name="Level 1")  # [0, 1]
    step2 = ProtocolStep(name="Step2", parameters={"param2": "value2"})  # [0, 1, 0]
    sub_group.add_element(step2)
    root.add_element(sub_group)

    # Level 2
    sub_sub_group = ProtocolGroup(name="Level 2")  # [0, 1, 1]
    step3 = ProtocolStep(name="Step3", parameters={"param3": "value3"})  # [0, 1, 1, 0]
    sub_group.add_element(sub_sub_group)
    sub_sub_group.add_element(step3)

    # Add additional steps
    new_step1 = ProtocolStep(name="newStep1", parameters={"newparam2": "value2", "newparam3": "value3"})
    root.add_element(new_step1)  # [0, 2]

    new_step2 = ProtocolStep(name="NewStep2", parameters={"Newparam2": "Newvalue2"})
    sub_group.add_element(new_step2)  # [0, 1, 2]

    new_step3 = ProtocolStep(name="NewStep3", parameters={"Newparam3": "Newvalue3"})  # [0,1,1,1]
    root.get_element(element_idx=[0, 1, 1]).add_element(new_step3)

    # Add multiple groups at same level
    level2_group2 = ProtocolGroup(name="Level 2, group 2")
    level2_group2.add_element(step1.model_copy(update={"name": step1.name + "_copy"}))
    level2_group2.add_element(new_step1.model_copy(update={"name": new_step1.name + "_copy"}))
    root.get_element([0, 1]).add_element(level2_group2)

    return root


def test_json_serialization_matches_snapshot(protocol_tree):
    json_model = protocol_tree.model_dump_json(indent=4)
    with open(VALID_OUTPUTS / "tree_data_save.json") as f:
        expected = json.load(f)
    actual = json.loads(json_model)
    assert actual == expected

def test_tree_traversal(protocol_tree):
    check_group = protocol_tree.get_element([0, 1, 3])

    assert check_group.name == "Level 2, group 2"


if __name__ == "__main__":
    pytest.main([__file__])
