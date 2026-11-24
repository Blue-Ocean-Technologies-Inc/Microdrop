# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A saved report carries the last board diagnostics read after the test
results, in both the Markdown and the HTML format; a read still in flight
leaves no placeholder in the file."""

# Third-party imports.
import pytest

# Local imports.
from ..consts import SelfTestDiagInfo
from ..models.run_outputs import SelfTestRunOutputs

pytest.importorskip("dropbot_portable.self_test")

SHORTS_TEST = "test_shorts"

#: DIAG_INFO text with characters HTML must escape.
DIAG_TEXT = "uptime 90.5 s <main> & kicker"


@pytest.fixture
def outputs():
    outputs = SelfTestRunOutputs()
    outputs.results = {
        SHORTS_TEST: {
            "shorts": [],
            "duration": 1.25,
            "utc_timestamp": "2026-11-20T12:00:00+00:00",
        }
    }

    return outputs


def _save(outputs, path):
    outputs.save_report(path)

    assert outputs.report_status.startswith("Saved to")

    return path.read_text(encoding="utf-8")


def test_markdown_report_ends_with_the_diagnostics(outputs, tmp_path):
    outputs.show_diagnostics(
        SelfTestDiagInfo(text=DIAG_TEXT, stalled_sources=["main loop"])
    )

    text = _save(outputs, tmp_path / "report.md")

    assert text.index("Shorts") < text.index("## Board diagnostics")
    assert "**STALLED** (IWDG reset pending): main loop" in text
    assert text.rstrip().endswith(f"{DIAG_TEXT}\n```")


def test_html_report_has_the_escaped_diagnostics_before_the_body_end(outputs, tmp_path):
    outputs.show_diagnostics(SelfTestDiagInfo(text=DIAG_TEXT))

    text = _save(outputs, tmp_path / "report.html")
    section = text.index('<section id="board-diagnostics">')

    assert text.index(f'<section id="{SHORTS_TEST}">') < section
    assert section < text.index("</body>")
    assert "<h2>Board diagnostics</h2>" in text
    assert "<pre>uptime 90.5 s &lt;main&gt; &amp; kicker</pre>" in text


@pytest.mark.parametrize("name", ["report.md", "report.html"])
def test_a_failed_read_is_saved_as_not_read(outputs, tmp_path, name):
    outputs.show_diagnostics(SelfTestDiagInfo(error="board busy"))

    text = _save(outputs, tmp_path / name)

    assert "Board diagnostics" in text and "board busy" in text


@pytest.mark.parametrize("name", ["report.md", "report.html"])
def test_a_read_in_flight_is_not_saved(outputs, tmp_path, name):
    outputs.show_diagnostics(None)

    text = _save(outputs, tmp_path / name)

    assert "Board diagnostics" not in text
    assert "Reading the signal board" not in text
