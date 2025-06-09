import json
from .protocol_visualization_helpers import (
    visualize_protocol_graph,
    get_protocol_graph,
    convert_json_protocol_to_graph,
)
from protocol_grid.model.tree_data import ProtocolGroup, ProtocolStep


def build_sample_protocol_tree() -> ProtocolGroup:
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

    new_step3 = ProtocolStep(name="NewStep3", parameters={"Newparam3": "Newvalue3"}) # [0,1,1,1]
    root.get_element(element_idx=[0, 1, 1]).add_element(new_step3)

    # Add multiple groups at same level
    level2_group2 = ProtocolGroup(name="Level 2, group 2")
    level2_group2.add_element(step1.model_copy(update={"name": step1.name + "_copy"}))
    level2_group2.add_element(new_step1.model_copy(update={"name": new_step1.name + "_copy"}))
    root.get_element([0, 1]).add_element(level2_group2)

    check_group = root.get_element([0, 1, 3])

    assert check_group.name == level2_group2.name

    return root


def save_protocol_tree_to_json(root: ProtocolGroup, filename: str = "tree_data_save.json"):
    json_model = root.model_dump_json(indent=4)
    with open(filename, 'w') as outfile:
        outfile.write(json_model)
    return json_model


def load_protocol_tree_from_json(filename: str) -> ProtocolGroup:
    with open(filename, 'r') as infile:
        json_model_loaded = json.load(infile)
    return ProtocolGroup.model_validate(json_model_loaded)


def protocol_model_serialization(json_model: str):
    json_string_loaded = json.dumps(json.loads(json_model))
    test_group = ProtocolGroup.model_validate_json(json_string_loaded)
    assert test_group.model_dump_json(indent=4) == json_model
    return test_group


def visualize_protocol_from_model(protocol_group: ProtocolGroup, base_name: str = "tree_data"):
    protocol_graph = get_protocol_graph(protocol_group)
    visualize_protocol_graph(protocol_graph, f"{base_name}.png")
    protocol_graph.write(f"{base_name}.dot")


def visualize_protocol_from_json(json_input: str | dict, base_name: str):
    G = convert_json_protocol_to_graph(json_input)
    visualize_protocol_graph(G, f"{base_name}.png")


def main():
    # Build and visualize the tree
    root = build_sample_protocol_tree()
    visualize_protocol_from_model(root, "tree_data")

    # Save and reload JSON
    json_model = save_protocol_tree_to_json(root)
    loaded_group = load_protocol_tree_from_json("tree_data_save.json")

    # Verify serialization
    test_group = protocol_model_serialization(json_model)

    # Visualize from JSON string
    visualize_protocol_from_json(json_model, "tree_data_from_json_string")

    # Visualize from JSON file
    visualize_protocol_from_json("tree_data_save.json", "tree_data_from_json_file")


if __name__ == "__main__":
    main()
