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
