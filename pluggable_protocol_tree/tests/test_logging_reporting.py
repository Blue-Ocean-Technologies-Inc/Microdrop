from pathlib import Path

from pluggable_protocol_tree.services.logging.models import LoggingDeviceContext
from pluggable_protocol_tree.services.logging.reporting import LoggingReport


def _entries():
    return [
        {"step_idx": 0, "step_id": "s0", "Capacitance (pF)": 1.0,
         "Voltage (V)": 100.0, "Actuated Area (mm^2)": 2.0,
         "actuated_channels": [1, 2]},
        {"step_idx": 1, "step_id": "s1", "Capacitance (pF)": 3.0,
         "Voltage (V)": 100.0, "Actuated Area (mm^2)": 4.0,
         "actuated_channels": [3]},
    ]


def test_build_html_has_expected_sections():
    cols = ["step_idx", "step_id", "Capacitance (pF)", "Voltage (V)",
            "Actuated Area (mm^2)", "actuated_channels"]
    html = LoggingReport.build_html(
        entries=_entries(), columns=cols,
        metadata={"Experiment": "exp-1"},
        media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")),
        notes=None,
    )
    assert "<html" in html.lower()
    for section in ("Metadata", "Data Summary", "Data Trends"):
        assert section in html
    assert "exp-1" in html


def test_build_html_empty_data_does_not_crash():
    html = LoggingReport.build_html(
        entries=[], columns=[], metadata={}, media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")), notes=None)
    assert "<html" in html.lower()


def test_build_html_escapes_metadata():
    html = LoggingReport.build_html(
        entries=[], columns=[], metadata={"k": "<x> & y"},
        media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")), notes=None)
    assert "&lt;x&gt;" in html and "&amp;" in html


def test_write_report_creates_reports_dir(tmp_path):
    path = LoggingReport.write_report(tmp_path, "<html><body>ok</body></html>")
    assert path.exists() and path.parent.name == "reports" and path.suffix == ".html"


def test_build_html_uses_version_correct_plotly_cdn_not_stale_latest():
    """plotly-latest.min.js on the legacy CDN is pinned to plotly.js 1.x,
    which cannot decode the typed-array (bdata) output emitted by plotly
    >= 3.x and silently renders every chart blank. The report must instead
    let the first plotly figure emit its own version-correct CDN tag, so
    the bundle version matches the installed plotly."""
    import plotly                                  # installed version
    cols = ["step_idx", "step_id", "Capacitance (pF)", "Voltage (V)",
            "Actuated Area (mm^2)", "actuated_channels"]
    html = LoggingReport.build_html(
        entries=_entries(), columns=cols, metadata={},
        media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")),
        notes=None,
    )
    assert "plotly-latest.min.js" not in html      # stale v1.x bundle
    # The version-correct CDN script is what plotly.io emits when
    # include_plotlyjs='cdn'. Cross-check by asking plotly itself.
    import plotly.graph_objs as go
    import plotly.io as pio
    probe = pio.to_html(go.Figure([go.Bar(x=[1], y=[1])]),
                        include_plotlyjs="cdn", full_html=False)
    import re
    m = re.search(r'src="(https://cdn\.plot\.ly/plotly-[\d.]+\.min\.js)"', probe)
    assert m and m.group(1) in html, (
        f"expected version-correct plotly CDN URL in report (plotly "
        f"{plotly.__version__})")


def test_build_html_renders_path_metadata_as_clickable_anchors(tmp_path):
    """Path-valued metadata keys (Experiment Directory, Device SVG,
    Protocol Path) render as clickable file:// anchors showing just the
    basename — matches legacy protocol_grid's protocol_data_logger."""
    exp_dir = tmp_path / "exp with space"
    svg = tmp_path / "device.svg"
    proto = tmp_path / "protocols" / "protocol_x.json"
    proto.parent.mkdir(parents=True)

    html = LoggingReport.build_html(
        entries=[], columns=[],
        metadata={"Experiment Directory": str(exp_dir),
                  "Device SVG": str(svg),
                  "Protocol Path": str(proto),
                  "Steps": "0 / 1"},
        media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")),
        notes=None)

    # Anchor with file:// scheme; basename is the visible link text;
    # spaces inside the href become %20 (Path.as_uri percent-encodes the
    # URL), while the visible link text is just the basename.
    assert '<a href="file://' in html
    assert "exp%20with%20space" in html              # href is URL-encoded
    assert ">exp with space</a>" in html             # link text is plain basename
    assert ">device.svg</a>" in html
    assert ">protocol_x.json</a>" in html
    # Non-path keys still render as escaped plain text, not as anchors.
    assert "<td>0 / 1</td>" in html


def test_build_html_path_metadata_non_absolute_falls_back_to_escaped_text():
    """Relative paths can't form a file:// URI (Path.as_uri raises); the
    renderer must fall back to escaped text instead of crashing."""
    html = LoggingReport.build_html(
        entries=[], columns=[],
        metadata={"Protocol Path": "<not-a-path>"},
        media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")),
        notes=None)
    assert "&lt;not-a-path&gt;" in html
    assert "<a href" not in html.split("Metadata")[1].split("Data Summary")[0]


def test_build_html_without_step_idx_does_not_crash():
    from pathlib import Path
    html = LoggingReport.build_html(
        entries=[{"Capacitance (pF)": 1.0}],          # no step_idx
        columns=["Capacitance (pF)"],
        metadata={}, media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")),
        notes=None)
    assert "<html" in html.lower()
    assert "Data Trends" in html
