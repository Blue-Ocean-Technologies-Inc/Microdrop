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

def visualize_protocol_with_swimlanes(protocol_sequence, base_name="protocol_chain", max_nodes_per_column=5):
    G = pgv.AGraph(directed=True, rankdir="TB", strict=False)
    node_counter = [0]

    def add_sequence(seq, parent_graph, parent_subgraph=None, group_name=None, parent_last_node=None, depth=0):
        n = len(seq)
        columns = [seq[i:i+max_nodes_per_column] for i in range(0, n, max_nodes_per_column)]
        col_first_nodes = []
        col_last_nodes = []

        prev_col_last_node = parent_last_node

        for col_idx, chunk in enumerate(columns):
            col_nodes = []
            col_nodes_last = []  # track last node for each element
            for obj in chunk:
                
                if isinstance(obj, ProtocolGroup):
                    group_id = f"group_{node_counter[0]}"
                    
                    with parent_graph.subgraph(name=f"cluster_{group_id}") as sub:
                        sub.graph_attr.update(style="dashed", label="Group", fontsize="12")
                        
                        first_in_group, last_in_group = add_sequence(
                            obj.elements, sub, parent_subgraph=sub, group_name=group_id, depth=depth+1
                        )
                        
                        col_nodes.append(first_in_group)
                        col_nodes_last.append(last_in_group)
                        # Only connect to the group's first node if previous node exists
                        if len(col_nodes) > 1 and col_nodes[-2] is not None and first_in_group is not None:
                            parent_graph.add_edge(col_nodes_last[-2], first_in_group)
                
                else:  # ProtocolStep
                    step_id = f"step_{node_counter[0]}"
                    node_counter[0] += 1
                    label = f"{obj.name}\n" + "\n".join(f"{k}: {v}" for k, v in obj.parameters.items())
                    parent_graph.add_node(step_id, label=label, shape="box", style="filled", fillcolor="#e0f7fa", fontname="Helvetica")
                    col_nodes.append(step_id)
                    col_nodes_last.append(step_id)
                    
                    if len(col_nodes) > 1:
                        parent_graph.add_edge(col_nodes_last[-2], step_id)

            if prev_col_last_node and col_nodes and col_nodes[0] is not None:
                parent_graph.add_edge(prev_col_last_node, col_nodes[0], color="#1976d2", penwidth=2, arrowhead="normal", constraint=False, minlen=2)
            # Store first/last for arrows
            if col_nodes and col_nodes[0]:
                col_first_nodes.append(col_nodes[0])
            if col_nodes_last and col_nodes_last[-1]:
                col_last_nodes.append(col_nodes_last[-1])
            prev_col_last_node = col_nodes_last[-1] if col_nodes_last else prev_col_last_node

        # For outer recursion, return first and last actual nodes in this sequence
        first_node = col_first_nodes[0] if col_first_nodes else None
        last_node = col_last_nodes[-1] if col_last_nodes else None
        return first_node, last_node

    add_sequence(protocol_sequence, G)
    G.layout(prog="dot")
    G.draw(f"{base_name}_swimlanes.png")
    G.write(f"{base_name}_swimlanes.dot")