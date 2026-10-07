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
import importlib
import os
import sys

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences import package_globals
from envisage.api import Application

# Microdrop package imports.
from dropbot_status_and_controls.consts import DROPBOT_STATUS_TUTORIAL_HTML_PATH
from dropbot_status_and_controls.plugin import DropbotStatusAndControlsPlugin
from examples.tutorials.build_tutorial import (
    SIZE_BUDGET_BYTES,
    TutorialBuildError,
    find_network_references,
    is_up_to_date,
    render_tutorial,
)
from examples.tutorials.new_tutorial import scaffold_tutorial
from image_viewer.plugin import ImageViewerPlugin
from user_help_plugin.plugin import UserHelpPlugin

# Microdrop style imports.
from microdrop_style.tutorial.glyphs import read_symbols, symbol_markup, trace_glyphs

# Tracing glyphs needs a QGuiApplication; never open a window for it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DROPBOT_SOURCE = DROPBOT_STATUS_TUTORIAL_HTML_PATH.with_name("dropbot_status.src.html")
FIXTURE_PLUGIN = "tutorial_kit_fixture_plugin"

#: A plugin.py with no tutorials yet, as new_tutorial.py first meets it.
PLUGIN_FIXTURE = """# Enthought library imports.
from envisage.api import Plugin

# Local imports.
from .consts import PKG


class FixturePlugin(Plugin):
    id = PKG + ".plugin"
"""


@pytest.fixture
def scaffold_root(tmp_path, monkeypatch):
    """An importable source root holding one plugin without tutorials."""
    package = tmp_path / FIXTURE_PLUGIN
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "consts.py").write_text(f"import os\n\nPKG = '{FIXTURE_PLUGIN}'\n")
    (package / "plugin.py").write_text(PLUGIN_FIXTURE)
    monkeypatch.syspath_prepend(str(tmp_path))

    yield tmp_path

    for module in [name for name in sys.modules if name.startswith(FIXTURE_PLUGIN)]:
        del sys.modules[module]


def _fixture_plugin_tutorials():
    plugin_module = importlib.import_module(f"{FIXTURE_PLUGIN}.plugin")

    return [
        (entry.title, entry.path) for entry in plugin_module.FixturePlugin().tutorials
    ]


def test_scaffold_builds_an_offline_page_and_contributes_it(scaffold_root):
    source = scaffold_tutorial(FIXTURE_PLUGIN, "demo", "Demo Tutorial", scaffold_root)
    page_path = source.with_name("demo.html")
    page = page_path.read_text(encoding="utf-8")

    assert find_network_references(page) == []
    assert "<title>Demo Tutorial</title>" in page
    assert 'id="ic-info"' in page
    assert _fixture_plugin_tutorials() == [("Demo Tutorial", page_path)]


def test_scaffold_adds_a_second_tutorial_to_the_same_plugin(scaffold_root):
    scaffold_tutorial(FIXTURE_PLUGIN, "demo", "Demo Tutorial", scaffold_root)
    scaffold_tutorial(FIXTURE_PLUGIN, "more", "More & Less Tutorial", scaffold_root)

    assert [title for title, _path in _fixture_plugin_tutorials()] == [
        "Demo Tutorial",
        "More & Less Tutorial",
    ]


def test_scaffold_is_idempotent(scaffold_root):
    scaffold_tutorial(FIXTURE_PLUGIN, "demo", "Demo Tutorial", scaffold_root)
    files = sorted(scaffold_root.rglob("*.*"))
    before = {path: path.read_bytes() for path in files}

    scaffold_tutorial(FIXTURE_PLUGIN, "demo", "Demo Tutorial", scaffold_root)

    assert {path: path.read_bytes() for path in files} == before


def test_bundled_tutorials_reach_the_help_menu(monkeypatch):
    # An envisage Application installs its preferences as the process-wide
    # default node; restore it so later PreferencesHelper tests don't share it.
    monkeypatch.setattr(package_globals, "_default_preferences", None)

    help_plugin = UserHelpPlugin()
    application = Application(plugins=[help_plugin])
    application.start()
    contributors = [ImageViewerPlugin(), DropbotStatusAndControlsPlugin()]

    # Added, not started: contributions resolve without the plugins running.
    for plugin in contributors:
        application.add_plugin(plugin)

    entries = help_plugin.tutorial_catalog.entries

    for plugin in contributors:
        application.remove_plugin(plugin)

    application.stop()

    assert [entry.title for entry in entries] == [
        "Dropbot Status & Controls Tutorial",
        "Image Analysis Tutorial",
    ]

    for entry in entries:
        page = entry.path.read_text(encoding="utf-8")

        assert find_network_references(page) == []


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
