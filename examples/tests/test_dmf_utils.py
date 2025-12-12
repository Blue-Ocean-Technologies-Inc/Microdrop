import os
import tempfile
import shutil
import pytest
from pathlib import Path
from xml.etree import ElementTree as ET


@pytest.fixture
def clean_svg():
    from .common import TEST_PATH
    with tempfile.TemporaryDirectory() as tmpdir:
        shutil.copy(f"{TEST_PATH}{os.sep}device_svg_files{os.sep}90_pin_array.svg", tmpdir)
        yield Path(tmpdir) / '90_pin_array.svg'


@pytest.fixture
def svg_root(clean_svg):
    tree = ET.parse(clean_svg)
    return tree.getroot()


@pytest.fixture
def svg_shape(svg_root):
    return svg_root[4][0]


@pytest.fixture
def svg_electrode_layer(svg_root):
    return svg_root[4]

@pytest.fixture
def SvgUtil():
    from device_viewer.utils.dmf_utils import SvgUtil
    return SvgUtil

@pytest.fixture
def SVGProcessor():
    from device_viewer.utils.dmf_utils_helpers import SVGProcessor
    return SVGProcessor

def test_svg_util(clean_svg, SvgUtil):

    SvgUtil(filename=clean_svg)


def test_filename(clean_svg, SvgUtil):

    svg = SvgUtil()
    svg.filename = clean_svg
    assert svg.filename == clean_svg


def test_set_fill_black(svg_electrode_layer, SvgUtil):

    SvgUtil.set_fill_black(svg_electrode_layer)
    assert svg_electrode_layer[0].attrib['style'] == 'fill:#000000'


def test_svg_to_electrodes(clean_svg, SVGProcessor):
    svg_processor = SVGProcessor(filename=str(clean_svg))
    for child in svg_processor.root:
        if "Device" in child.attrib.values():
            electrodes = svg_processor.svg_to_electrodes(child)
            assert len(electrodes) == 84

def test_extract_connections(clean_svg, SVGProcessor):
    svg_processor = SVGProcessor(filename=str(clean_svg))
    for child in svg_processor.root:
        if "Connections" in child.attrib.values():
            connection_lines = svg_processor.extract_connections(child)

            assert len(connection_lines) == 125

def test_get_connection_lines(clean_svg, SvgUtil):
    svg = SvgUtil(filename=clean_svg)
    assert (len(svg.get_connection_lines())) == 125