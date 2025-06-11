import json
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

def get_protocol_graph(protocol_sequence):
    G = pgv.AGraph(directed=True, rankdir="TB")

    node_id = [0]
    prev_node = None

    def add_seq(seq, graph, parent_cluster=None):
        local_prev = None
        for obj in seq:
            if isinstance(obj, ProtocolGroup):
                cluster_name = f"cluster_{id(obj)}"
                with graph.subgraph(name=cluster_name) as c:
                    c.graph_attr.update(style="dashed", label=f"Group: {obj.name}")
                    first_in_group = add_seq(obj.elements, c, parent_cluster=cluster_name) # recursion here
                    # return the FIRST AND LAST node id in the group
                    if first_in_group is not None:
                        if local_prev is not None:
                            graph.add_edge(local_prev, first_in_group)
                        local_prev = get_last_node(obj.elements, c)
            elif isinstance(obj, ProtocolStep):
                step_id = f"step_{node_id[0]}"
                node_id[0] += 1
                label = f"{obj.name}\n" + "\n".join(f"{k}: {v}" for k, v in obj.parameters.items())
                graph.add_node(step_id, label=label, shape="box", style="filled")
                if local_prev is not None:
                    graph.add_edge(local_prev, step_id)
                local_prev = step_id
                if parent_cluster is None and prev_node is not None:
                    graph.add_edge(prev_node, step_id)
        return get_first_node(seq, graph)

    def get_first_node(seq, graph):
        for obj in seq:
            if isinstance(obj, ProtocolGroup):
                return get_first_node(obj.elements, graph) # recursion: to find first node inside a group
            elif isinstance(obj, ProtocolStep):
                return [n for n in graph.nodes() if graph.get_node(n).attr['label'].startswith(obj.name)][0]
        return None

    def get_last_node(seq, graph):
        for obj in reversed(seq):
            if isinstance(obj, ProtocolGroup):
                return get_last_node(obj.elements, graph) # recursion: to find first node inside a group
            elif isinstance(obj, ProtocolStep):
                return [n for n in graph.nodes() if graph.get_node(n).attr['label'].startswith(obj.name)][0]
        return None

    add_seq(protocol_sequence, G)
    return G

def visualize_protocol_from_model(protocol_sequence, base_name = "protocol_chain"):
    G = get_protocol_graph(protocol_sequence)
    G.layout(prog="dot")
    G.draw(f"{base_name}.png")
    G.write(f"{base_name}.dot")

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

def save_protocol_sequence_to_json(seq, filename="protocol_seq.json"):
    with open(filename, "w") as f:
        json.dump([item.dict() for item in seq], f, indent=4)
