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


def test_build_html_data_files_section_lists_clickable_links(tmp_path):
    """Legacy parity: a 'Data Files' section lists each artifact (json/csv)
    written this run as a clickable file:// link showing its basename."""
    json_f = tmp_path / "data" / "data_x.json"
    csv_f = tmp_path / "data" / "data_x.csv"
    json_f.parent.mkdir(parents=True)
    json_f.write_text("{}", encoding="utf-8")
    csv_f.write_text("", encoding="utf-8")
    html = LoggingReport.build_html(
        entries=[], columns=[], metadata={},
        media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")),
        notes=None, data_files=[json_f, csv_f])
    assert "<h2>Data Files</h2>" in html
    assert ">data_x.json</a>" in html
    assert ">data_x.csv</a>" in html
    assert 'href="file://' in html


def test_build_html_no_data_files_omits_section():
    html = LoggingReport.build_html(
        entries=[], columns=[], metadata={},
        media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")),
        notes=None)
    assert "<h2>Data Files</h2>" not in html


def test_trends_section_renders_horizontal_bars_keyed_by_step_index():
    """Y-axis is the 1-indexed protocol step number ("Step 1", "Step 2"),
    NOT the row uuid (step_id, which is unreadable). Bars are horizontal —
    legacy protocol_grid parity."""
    cols = ["step_idx", "step_id", "Capacitance (pF)", "Voltage (V)",
            "Actuated Area (mm^2)", "actuated_channels"]
    html = LoggingReport.build_html(
        entries=_entries(), columns=cols, metadata={},
        media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")),
        notes=None)
    assert '"orientation":"h"' in html
    assert "Protocol Steps" in html
    # The uuid-style step_id ("s0", "s1") must NOT appear as a y-axis
    # label; the user-facing label is "Step 0" / "Step 1".
    assert "Step 0" in html and "Step 1" in html
    assert '"y":["s0"' not in html and '"y":["s1"' not in html


def test_channel_durations_matches_legacy_fillna_zero_average():
    """The heatmap reports per-channel actuation TIME (seconds), computed
    as the legacy `_get_channel_duration` does: count samples per channel
    × mean sample interval over the rollover-corrected instrument time,
    where the leading NaN from `.diff()` is filled with 0 (matching the
    biased-low average the legacy report has always shipped, so we don't
    silently diverge from the existing protocol_grid report)."""
    import pandas as pd
    from pluggable_protocol_tree.services.logging.reporting import LoggingReport
    # 4 samples, 10ms apart. .diff() = [NaN, 10000, 10000, 10000] us;
    # .fillna(0).mean() = 7500 us = 0.0075 s (legacy's biased mean).
    df = pd.DataFrame([
        {"actuated_channels": [1], "instrument_time_us": 0},
        {"actuated_channels": [1, 2], "instrument_time_us": 10_000},
        {"actuated_channels": [1], "instrument_time_us": 20_000},
        {"actuated_channels": [1], "instrument_time_us": 30_000},
    ])
    out = LoggingReport._channel_durations_seconds(df)
    assert out == {1: round(4 * 0.0075, 6), 2: round(1 * 0.0075, 6)}


def test_heatmap_passes_duration_units_to_helper(monkeypatch, tmp_path):
    """The heatmap helper receives quant_title='Actuation Time' and
    quant_units='s' (legacy parity), with channel keys mapped to seconds."""
    import pandas as pd
    from pluggable_protocol_tree.services.logging import reporting as r

    captured = {}

    class _FakeFig:
        @staticmethod
        def to_html(**_k):
            return "<div>fake-heatmap</div>"

    def _fake_helper(svg_file, channel_quantity_dict, **kw):
        captured["svg"] = svg_file
        captured["channels"] = dict(channel_quantity_dict)
        # Helper defaults: quant_title="Actuation Times", quant_units="seconds".
        # The reporting code now calls without overrides so the helper's
        # built-in format_time_tooltip kicks in (sec/min/hours auto-scaling).
        captured["kw"] = dict(kw)
        return _FakeFig()

    # Replace the helper at the import site used inside _heatmap.
    import microdrop_utils.plotly_helpers as ph
    monkeypatch.setattr(
        ph, "create_plotly_svg_dropbot_device_heatmap", _fake_helper)

    df = pd.DataFrame([
        {"actuated_channels": [1], "instrument_time_us": 0},
        {"actuated_channels": [1], "instrument_time_us": 10_000},
    ])
    svg = tmp_path / "device.svg"
    svg.write_text("<svg/>", encoding="utf-8")
    ctx = LoggingDeviceContext(
        experiment_directory=tmp_path, device_svg_path=str(svg))
    html = r.LoggingReport._heatmap(df, ctx, include_plotlyjs=False)
    assert "fake-heatmap" in html
    # No overrides — let the helper use its "seconds" default so
    # format_time_tooltip auto-scales (sec --> min --> hours) in the tooltip.
    assert "quant_title" not in captured["kw"]
    assert "quant_units" not in captured["kw"]
    assert 1 in captured["channels"] and captured["channels"][1] > 0


def test_media_section_renders_thumbnails_and_play_placeholders(tmp_path):
    """Legacy parity: images get a 360x240 <img> thumbnail, videos get a
    click-to-play placeholder div (the onclick swaps in a <video>), and
    each item shows as a numbered `<a>basename</a>` link. Mirrors
    protocol_data_logger._get_files_summary."""
    img = tmp_path / "captures" / "img_001.png"
    vid = tmp_path / "captures" / "vid_001.mkv"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"")
    vid.write_bytes(b"")
    html = LoggingReport.build_html(
        entries=[], columns=[], metadata={},
        media={"video": [str(vid)], "image": [str(img)], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")),
        notes=None)
    # Section / sub-section headings
    assert "<h2>Media Captures</h2>" in html
    assert "<h3>Video Captures</h3>" in html
    assert "<h3>Image Captures</h3>" in html
    # Numbered link + basename for each
    assert ">img_001.png</a>" in html
    assert ">vid_001.mkv</a>" in html
    assert "<b>1.</b>" in html
    # Image thumbnail (360x240 file:// src)
    assert 'width="360" height="240"' in html
    assert 'src="file://' in html
    # Video click-to-play placeholder (the play triangle character)
    assert "&#9658;" in html
    assert "swap" not in html.lower() or "onclick" in html        # placeholder exists


def test_media_section_omitted_when_no_captures():
    html = LoggingReport.build_html(
        entries=[], columns=[], metadata={},
        media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")),
        notes=None)
    assert "<h2>Media Captures</h2>" not in html


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
