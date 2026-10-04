# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the tutorial kit: build, scaffold and glyph tracing."""

# Standard library imports.
import os

# Third-party imports.
import pytest

# Microdrop package imports.
from dropbot_status_and_controls.consts import DROPBOT_STATUS_TUTORIAL_HTML_PATH
from examples.tutorials.build_tutorial import (
    SIZE_BUDGET_BYTES,
    TutorialBuildError,
    find_network_references,
    is_up_to_date,
    render_tutorial,
)
from examples.tutorials.new_tutorial import scaffold_tutorial

# Microdrop style imports.
from microdrop_style.tutorial.glyphs import read_symbols, symbol_markup, trace_glyphs

# Tracing glyphs needs a QGuiApplication; never open a window for it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DROPBOT_SOURCE = DROPBOT_STATUS_TUTORIAL_HTML_PATH.with_name("dropbot_status.src.html")

#: The anchors new_tutorial.py needs in user_help_plugin/menus.py.
MENUS_FIXTURE = """# Microdrop package imports.
from image_viewer.consts import ANALYSIS_HELP_HTML_PATH

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def menu_factory():
    return SGroup(
        OpenWebViewDialogAction(source=ANALYSIS_HELP_HTML_PATH),
        id="user_help_actions",
    )
"""


@pytest.fixture
def scaffold_root(tmp_path):
    """A source root with one plugin and a Help menu without Tutorials."""
    (tmp_path / "demo_plugin").mkdir()
    (tmp_path / "demo_plugin" / "consts.py").write_text("import os\n\nPKG = 'x'\n")
    (tmp_path / "user_help_plugin").mkdir()
    (tmp_path / "user_help_plugin" / "menus.py").write_text(MENUS_FIXTURE)

    return tmp_path


def test_scaffold_builds_an_offline_page_and_wires_the_menu(scaffold_root):
    source = scaffold_tutorial("demo_plugin", "demo", "Demo Tutorial", scaffold_root)
    page = source.with_name("demo.html").read_text(encoding="utf-8")
    consts = (scaffold_root / "demo_plugin" / "consts.py").read_text()
    menus = (scaffold_root / "user_help_plugin" / "menus.py").read_text()

    assert find_network_references(page) == []
    assert "<title>Demo Tutorial</title>" in page
    assert 'id="ic-info"' in page
    assert "from pathlib import Path" in consts
    assert "DEMO_TUTORIAL_HTML_PATH = " in consts
    assert "from demo_plugin.consts import DEMO_TUTORIAL_HTML_PATH" in menus
    assert '("Demo Tutorial", DEMO_TUTORIAL_HTML_PATH),' in menus
    assert "tutorials_menu_factory()," in menus

    compile(consts, "consts.py", "exec")
    compile(menus, "menus.py", "exec")


def test_scaffold_is_idempotent(scaffold_root):
    scaffold_tutorial("demo_plugin", "demo", "Demo Tutorial", scaffold_root)
    files = sorted(scaffold_root.rglob("*.*"))
    before = {path: path.read_bytes() for path in files}

    scaffold_tutorial("demo_plugin", "demo", "Demo Tutorial", scaffold_root)

    assert {path: path.read_bytes() for path in files} == before


def test_dropbot_tutorial_rebuilds_identically():
    assert is_up_to_date(DROPBOT_SOURCE)


def test_dropbot_tutorial_is_offline_and_small():
    page = DROPBOT_STATUS_TUTORIAL_HTML_PATH.read_text(encoding="utf-8")

    assert find_network_references(page) == []
    assert len(page.encode("utf-8")) < SIZE_BUDGET_BYTES


def test_network_reference_fails_the_build(tmp_path):
    source = '<title>T</title><img src="https://example.com/a.png">'

    with pytest.raises(TutorialBuildError):
        render_tutorial(source, tmp_path, {}, "t.src.html")


def test_term_facts_become_a_definition_list(tmp_path):
    source = (
        "<title>T</title><section data-term id='a' data-where='here'>"
        "<h3>A</h3><div data-what>x</div><div data-typical>y</div></section>"
    )
    page, _cache = render_tutorial(source, tmp_path, {}, "t.src.html")

    assert '<article class="term" id="a">' in page
    assert '<h3>A <span class="where">here</span></h3>' in page
    assert '<dl class="facts"><dt>What it is</dt><dd>x</dd>' in page
    assert "<dt>Typical value</dt><dd>y</dd></dl></article>" in page


def test_glyph_tracer_outlines_an_icon_constant():
    glyph = trace_glyphs(["ICON_DROP_EC"])["drop_ec"]

    assert glyph["d"].startswith("M")
    assert read_symbols(symbol_markup("drop_ec", glyph)) == {"drop_ec": glyph}
