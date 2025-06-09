import pygraphviz as pgv
from typing import Union

from microdrop_utils.json_helpers import load_python_object_from_json
from protocol_grid.model.tree_data import ProtocolGroup,ProtocolStep

# Custom colors by type
color_map = {
    "root": "#56e7ff",
    "group": "#80deea",
    "step": "#e0f7fa"
}

base_node_attr = {
    "shape": "box",
    "style": "filled",
    "fillcolor": "#e0f7fa",
    "fontname": "Helvetica",
    "fontsize": "10",
    "width": "0",
    "height": "0",
    "fixedsize": "false",
    "labelloc": "t",
    "labeljust": "l"
}


def add_nodes_edges(graph, parent):
    # Add steps
    for element in parent.elements:
        if isinstance(element, ProtocolStep):
            step = element

            params_string = format_steps_param_as_string(step)

            step_label = (f"IDX: {str(step.idx)}\n"
                          f"Name: {step.name}\n"
                          f"{params_string}")

            graph.add_node(str(step.idx), label=step_label, type="step")
            graph.add_edge(str(parent.idx), str(step.idx))

        # Add subgroups recursively
        elif isinstance(element, ProtocolGroup):
            sub_group = element

            group_label = f"IDX: {str(sub_group.idx)}\nName: {sub_group.name}"
            graph.add_node(str(sub_group.idx), label=group_label, type="group")
            graph.add_edge(str(parent.idx), str(sub_group.idx))
            add_nodes_edges(graph, sub_group)


def format_steps_param_as_string(step):
    # get the params information formated into a string to add as a node label
    params_string = ""
    for param in step.parameters:
        param_line = f"{param} = {step.parameters[param]}"

        params_string += param_line + "\n"
    return params_string


def get_protocol_graph(ProtocolGroup) -> pgv.AGraph:
    G = pgv.AGraph(
        directed=True,
        strict=True,
        rankdir="TB",
    )

    G.add_node(ProtocolGroup.idx, label=f"IDX: {str(ProtocolGroup.idx)}\nName: {ProtocolGroup.name}", type="root")
    add_nodes_edges(G, ProtocolGroup)

    return G


def visualize_protocol_graph(protocol_graph, save_file_name="tree_data.png") -> pgv.AGraph:
    # Base styles
    protocol_graph.node_attr.update(base_node_attr)

    protocol_graph.edge_attr.update(arrowsize=0.8)

    # Apply per-node styling
    for node in protocol_graph.nodes():
        node_type = node.attr.get("type", "step")
        node.attr["fillcolor"] = color_map.get(node_type, "#ffffff")

    # Layout and render
    protocol_graph.layout(prog="dot")
    protocol_graph.draw(save_file_name)


def convert_json_protocol_to_graph(json_input: Union[str, dict]) -> pgv.AGraph:
    # Construct the ProtocolGroup object
    protocol_dict = load_python_object_from_json(json_input)
    protocol_group = ProtocolGroup.model_validate(protocol_dict)

    # Generate and visualize the graph
    protocol_graph = get_protocol_graph(protocol_group)

    return protocol_graph
