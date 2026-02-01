import pytest
from .common import TEST_PATH
from pathlib import Path
sample_svg_path = Path(TEST_PATH) / "device_svg_files" / "2x3device.svg"

import plotly.graph_objects as go
import numpy as np
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from pathlib import Path
from device_viewer.utils.dmf_utils_helpers import SVGProcessor

@pytest.fixture
def valid_electrodes_model_from_svg():
    from device_viewer.models.electrodes import Electrodes
    # Initialize an instance of Electrodes and load the SVG file
    electrodes = Electrodes()
    electrodes.set_electrodes_from_svg_file(sample_svg_path)
    return electrodes

def test_plotly_heatmap_invisible_polygon_hitboxes(valid_electrodes_model_from_svg):
    """
    Generates a Plotly heatmap with 'Invisible Polygon Hitboxes'.

    Architecture:
    1. Visual Layer: layout.shapes (Colored SVG Paths).
    2. Interaction Layer: go.Scatter traces with opacity=0 and fill="toself".
       - This creates a transparent "hitbox" covering the entire electrode.
       - Hovering anywhere on the electrode triggers the tooltip.
    """

    # --- 1. Setup Data ---
    model = valid_electrodes_model_from_svg
    processor = SVGProcessor(filename=str(model.svg_model.filename))

    device_electrodes = {}
    for child in processor.root:
        if "Device" in child.attrib.values():
            device_electrodes = processor.svg_to_electrodes(child)
            break

    # Dummy Data
    channels = list(model.channels_electrode_ids_map.keys())
    np.random.seed(42)
    channel_frequencies = {c: np.random.randint(0, 1000) for c in channels}

    # Colors
    norm = mcolors.Normalize(vmin=0, vmax=1000)
    cmap = plt.get_cmap('Reds')

    # --- 2. Build Layers ---
    plotly_shapes = []  # VISIBLE Layer (Colors)
    hitbox_traces = []  # INTERACTIVE Layer (Tooltips)
    all_points_list = []  # For auto-scaling bounds

    for elec_id, elec_data in device_electrodes.items():
        points = elec_data.path
        if len(points) < 3: continue
        all_points_list.append(points)

        # Resolve ID & Frequency

        chan_id = elec_data.channel
        freq = channel_frequencies[chan_id]
        fill_color = mcolors.to_hex(cmap(norm(freq)))

        # --- A. VISIBLE LAYER (layout.shapes) ---
        # Reconstruct SVG path string for the visual fill
        path_str = f"M {points[0, 0]} {points[0, 1]}"
        for pt in points[1:]:
            path_str += f" L {pt[0]} {pt[1]}"
        path_str += " Z"

        plotly_shapes.append(dict(
            type="path",
            path=path_str,
            fillcolor=fill_color,
            line=dict(color="#444444", width=0.5),
            layer="below"  # Draw shapes below the interactive traces
        ))

        # --- B. INTERACTIVE LAYER (Invisible Hitbox Trace) ---
        # Close the loop explicitly for the Scatter trace
        x_hitbox = np.append(points[:, 0], points[0, 0])
        y_hitbox = np.append(points[:, 1], points[0, 1])

        # Pre-format the tooltip text
        tooltip_text = (
            f"<b>Electrode ID:</b> {elec_id}<br>"
            f"<b>Channel ID:</b> {chan_id}<br>"
            f"<b># Actuations:</b> {freq}"
        )

        hitbox_traces.append(go.Scatter(
            x=x_hitbox,
            y=y_hitbox,
            fill="toself",  # Fills the polygon to capture hover events
            mode='lines',  # Required to define boundary
            opacity=0,  # <--- INVISIBLE (The Magic)
            name=elec_id,  # Trace name (hidden but good for debugging)
            text=tooltip_text,  # The tooltip string
            hoverinfo='text',  # Only show the 'text' string
            showlegend=False
        ))

    # --- 3. Auto-Scaling ---
    all_coords = np.vstack(all_points_list)
    min_x, min_y = np.min(all_coords, axis=0)
    max_x, max_y = np.max(all_coords, axis=0)

    # Add 5% padding
    pad_x = (max_x - min_x) * 0.05
    pad_y = (max_y - min_y) * 0.05

    x_range = [min_x - pad_x, max_x + pad_x]
    y_range = [max_y + pad_y, min_y - pad_y]  # Inverted Y for SVG origin

    # --- 4. Assemble Figure ---
    fig = go.Figure()

    # Add all invisible hitbox traces
    for trace in hitbox_traces:
        fig.add_trace(trace)

    fig.add_trace(go.Scatter(
        x=[0],
        y=[0],
        mode='markers',
        opacity=0,
        marker=dict(
            size=0,
            color=[0, 1000],  # Range
            colorscale='Reds',
            showscale=True,
            colorbar=dict(title="Frequency")
        ),
        hoverinfo='skip',
        showlegend=False
    ))

    fig.update_layout(
        title="Actuation Frequency Heatmap",
        width=1000, height=800,
        plot_bgcolor="white",

        shapes=plotly_shapes,  # Add the visible colored shapes

        xaxis=dict(range=x_range, showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(range=y_range, scaleanchor="x", scaleratio=1,
                   showgrid=False, zeroline=False, showticklabels=False)
    )

    output_path = Path(TEST_PATH) / "plotly_heatmap_hitboxes.html"
    fig.write_html(output_path)

    print(f"\nReport saved: {output_path.absolute()}")
    fig.show()
    assert output_path.exists()