import plotly.graph_objects as go
import numpy as np
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from pathlib import Path
from device_viewer.utils.dmf_utils_helpers import SVGProcessor


def format_time_tooltip(quant):
    """
    Formats a duration in seconds into sec, min, or hours
    based on its magnitude.

    Args:
        quant (float): The time duration in seconds.

    Returns:
        str: The formatted time string with units.

    Examples:
        >>> format_time_tooltip(45.123)
        '45.12 sec'
        >>> format_time_tooltip(150)
        '2.50 min'
        >>> format_time_tooltip(7500)
        '2.08 hours'
    """
    if quant < 60:
        return f"{quant:.2f} sec"
    elif quant < 3600:
        return f"{quant / 60:.2f} min"
    else:
        return f"{quant / 3600:.2f} hours"


def create_plotly_svg_dropbot_device_heatmap(
    svg_file: Path | str,
    channel_quantity_dict: dict,
    quant_title="Actuation Times",
    quant_units="seconds",
) -> go.Figure:
    """
    Generates a Plotly heatmap with 'Invisible Polygon Hitboxes'.

    The heatmap intensity is based on the channel quantities provided in channel_quantity_dict.

    We expect it to be time values by default (actuation duration). They will be auto formatted.

    Architecture:
    1. Visual Layer: layout.shapes (Colored SVG Paths).
    2. Interaction Layer: go.Scatter traces with opacity=0 and fill="toself".
       - This creates a transparent "hitbox" covering the entire electrode.
       - Hovering anywhere on the electrode triggers the tooltip.
    """

    # --- 1. Setup Data ---
    processor = SVGProcessor(filename=svg_file)

    device_electrodes = {}
    for child in processor.root:
        if "Device" in child.attrib.values():
            device_electrodes = processor.svg_to_electrodes(child)
            break

    if not channel_quantity_dict.values():
        channel_quant = [0]

    else:
        channel_quant = channel_quantity_dict.values()

    max_time = max(channel_quant)

    # Colors
    norm = mcolors.Normalize(vmin=0, vmax=max_time)
    cmap = plt.get_cmap("Reds")

    # --- 2. Build Layers ---
    plotly_shapes = []  # VISIBLE Layer (Colors)
    hitbox_traces = []  # INTERACTIVE Layer (Tooltips)
    all_points_list = []  # For auto-scaling bounds

    for elec_id, elec_data in device_electrodes.items():
        points = elec_data.path
        if len(points) >= 3:
            all_points_list.append(points)

            # Resolve ID & Frequency
            chan_id = elec_data.channel
            quant = channel_quantity_dict.get(chan_id, 0)
            fill_color = mcolors.to_hex(cmap(norm(quant)))

            # --- VISIBLE LAYER (layout.shapes) ---
            # Reconstruct SVG path string for the visual fill
            path_str = f"M {points[0, 0]} {points[0, 1]}"
            for pt in points[1:]:
                path_str += f" L {pt[0]} {pt[1]}"
            path_str += " Z"

            plotly_shapes.append(
                dict(
                    type="path",
                    path=path_str,
                    fillcolor=fill_color,
                    line=dict(color="#444444", width=0.5),
                    layer="below",  # Draw shapes below the interactive traces
                )
            )

            # --- INTERACTIVE LAYER Hitbox ---
            # Close the loop explicitly for the Scatter trace
            x_hitbox = np.append(points[:, 0], points[0, 0])
            y_hitbox = np.append(points[:, 1], points[0, 1])

            quant = (
                format_time_tooltip(quant)
                if quant_units in ["seconds", "minutes", "hours", "days"]
                else quant
            )

            # Pre-format the tooltip text
            tooltip_text = (
                f"<b>Electrode ID:</b> {elec_id}<br>"
                f"<b>Channel ID:</b> {chan_id}<br>"
                f"<b>{quant_title}:</b> {quant}"
            )

            hitbox_traces.append(
                go.Scatter(
                    x=x_hitbox,
                    y=y_hitbox,
                    fill="toself",  # Fills the polygon to capture hover events
                    mode="lines",  # Required to define boundary
                    opacity=0,  # <--- INVISIBLE (The Magic)
                    name=elec_id,  # Trace name (hidden but good for debugging)
                    text=tooltip_text,  # The tooltip string
                    hoverinfo="text",  # Only show the 'text' string
                    showlegend=False,
                )
            )

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

    fig.add_trace(
        go.Scatter(
            x=[0],
            y=[0],
            mode="markers",
            opacity=0,
            marker=dict(
                size=0,
                color=[0, max_time],  # Range
                colorscale="Reds",
                showscale=True,
                colorbar=dict(title="Time (s)"),
            ),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    fig.update_layout(
        title=quant_title,
        width=1000,
        height=800,
        plot_bgcolor="white",
        shapes=plotly_shapes,  # Add the visible colored shapes
        xaxis=dict(range=x_range, showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(
            range=y_range,
            scaleanchor="x",
            scaleratio=1,
            showgrid=False,
            zeroline=False,
            showticklabels=False,
        ),
    )

    return fig
