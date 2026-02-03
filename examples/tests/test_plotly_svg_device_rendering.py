import pytest
import numpy as np
from pathlib import Path

from microdrop_utils.plotly_helpers import create_plotly_svg_dropbot_device_heatmap
from .common import TEST_PATH

sample_svg_path = Path(TEST_PATH) / "device_svg_files" / "2x3device.svg"

@pytest.fixture
def valid_electrodes_model_from_svg():
    from device_viewer.models.electrodes import Electrodes
    # Initialize an instance of Electrodes and load the SVG file
    electrodes = Electrodes()
    electrodes.set_electrodes_from_svg_file(sample_svg_path)
    return electrodes

def test_create_plotly_svg_dropbot_device_heatmap(valid_electrodes_model_from_svg):
    """
    Generates a Plotly heatmap with 'Invisible Polygon Hitboxes'.

    Architecture:
    1. Visual Layer: layout.shapes (Colored SVG Paths).
    2. Interaction Layer: go.Scatter traces with opacity=0 and fill="toself".
       - This creates a transparent "hitbox" covering the entire electrode.
       - Hovering anywhere on the electrode triggers the tooltip.
    """

    # --- 1. Setup Data ---

    # Dummy Data
    channels = list(valid_electrodes_model_from_svg.channels_electrode_ids_map.keys())
    np.random.seed(42)
    channel_frequencies = {c: np.random.randint(0, 1000) for c in channels}

    fig = create_plotly_svg_dropbot_device_heatmap(sample_svg_path, channel_frequencies)

    output_path = Path(TEST_PATH) / "plotly_heatmap.html"
    fig.write_html(output_path)

    print(f"\nReport saved: {output_path.absolute()}")
    fig.show()
    assert output_path.exists()

def test_create_plotly_svg_dropbot_device_heatmap_missing_channels_frequencies(valid_electrodes_model_from_svg):
    """
    Generates a Plotly heatmap with 'Invisible Polygon Hitboxes'.

    Architecture:
    1. Visual Layer: layout.shapes (Colored SVG Paths).
    2. Interaction Layer: go.Scatter traces with opacity=0 and fill="toself".
       - This creates a transparent "hitbox" covering the entire electrode.
       - Hovering anywhere on the electrode triggers the tooltip.
    """

    # --- 1. Setup Data ---

    # Dummy Data
    channels = list(valid_electrodes_model_from_svg.channels_electrode_ids_map.keys())
    np.random.seed(42)
    channel_frequencies = {c: np.random.randint(0, 1000) for c in channels if c%2} # only feed odd channels in

    fig = create_plotly_svg_dropbot_device_heatmap(sample_svg_path, channel_frequencies)

    output_path = Path(TEST_PATH) / "plotly_heatmap.html"
    fig.write_html(output_path)

    print(f"\nReport saved: {output_path.absolute()}")
    fig.show()
    assert output_path.exists()

