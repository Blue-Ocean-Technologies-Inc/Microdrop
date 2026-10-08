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
from examples.tutorials.new_tutorial import _add_imports, scaffold_tutorial
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

#: The consts.py and plugin.py of a plugin already contributing a tutorial,
#: shaped like the bundled ones: no comma after the list's last entry.
CONSTS_WITH_TUTORIAL_FIXTURE = f"""from pathlib import Path

PKG = '{FIXTURE_PLUGIN}'
EXISTING_TUTORIAL_HTML_PATH = Path(__file__).parent / "existing.html"
"""
PLUGIN_WITH_TUTORIAL_FIXTURE = """# Enthought library imports.
from envisage.api import Plugin
from traits.api import List

# Microdrop package imports.
from user_help_plugin.consts import TUTORIALS, TutorialEntry

# Local imports.
from .consts import EXISTING_TUTORIAL_HTML_PATH, PKG


class FixturePlugin(Plugin):
    id = PKG + ".plugin"

    #: Help > Tutorials entries for this plugin's panes.
    tutorials = List(contributes_to=TUTORIALS)

    def _tutorials_default(self):
        return [
            TutorialEntry(
                title="Existing Tutorial",
                path=EXISTING_TUTORIAL_HTML_PATH,
            )
        ]
"""

#: Import layouts a line-based scan misreads: an import-like docstring line
#: and a parenthesised import closed with a trailing comment.
IMPORTS_FIXTURE = '''"""A module.

from the docstring, not an import
"""

from envisage.api import (
    Plugin,
)  # the base class


def helper():
    import os
'''


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


def test_scaffold_adds_to_a_list_without_a_trailing_comma(scaffold_root):
    package = scaffold_root / FIXTURE_PLUGIN
    (package / "consts.py").write_text(CONSTS_WITH_TUTORIAL_FIXTURE)
    (package / "plugin.py").write_text(PLUGIN_WITH_TUTORIAL_FIXTURE)

    scaffold_tutorial(FIXTURE_PLUGIN, "more", "More Tutorial", scaffold_root, False)
    plugin_text = (package / "plugin.py").read_text()

    compile(plugin_text, "plugin.py", "exec")
    assert [title for title, _path in _fixture_plugin_tutorials()] == [
        "Existing Tutorial",
        "More Tutorial",
    ]


def test_scaffold_recognises_a_positional_entry(scaffold_root):
    package = scaffold_root / FIXTURE_PLUGIN
    positional = PLUGIN_WITH_TUTORIAL_FIXTURE.replace(
        'title="Existing Tutorial",\n                path=', '"Existing Tutorial", '
    )
    (package / "consts.py").write_text(CONSTS_WITH_TUTORIAL_FIXTURE)
    (package / "plugin.py").write_text(positional)

    scaffold_tutorial(FIXTURE_PLUGIN, "existing", "Existing", scaffold_root, False)

    assert (package / "plugin.py").read_text() == positional


def test_scaffold_refuses_an_unfamiliar_tutorials_declaration(scaffold_root):
    package = scaffold_root / FIXTURE_PLUGIN
    unfamiliar = PLUGIN_WITH_TUTORIAL_FIXTURE.replace(
        "List(contributes_to=TUTORIALS)", "List([], contributes_to=TUTORIALS)"
    ).replace("_tutorials_default", "_other_tutorials")
    (package / "consts.py").write_text(CONSTS_WITH_TUTORIAL_FIXTURE)
    (package / "plugin.py").write_text(unfamiliar)

    with pytest.raises(ValueError, match="by hand"):
        scaffold_tutorial(FIXTURE_PLUGIN, "more", "More", scaffold_root, False)

    assert (package / "plugin.py").read_text() == unfamiliar


def test_imports_go_after_the_last_top_level_import():
    lines = _add_imports(IMPORTS_FIXTURE, ["import json"], "m.py").split("\n")

    assert lines[lines.index(")  # the base class") + 1] == "import json"
    assert lines.count("import json") == 1


def test_imports_need_an_existing_import_to_follow():
    with pytest.raises(ValueError, match="by hand"):
        _add_imports('"""No imports."""\n\nX = 1\n', ["import json"], "m.py")


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


@pytest.mark.parametrize(
    "markup",
    [
        '<IMG SRC="HTTPS://example.com/a.png">',
        '<img srcset="a.png 1x, //example.com/a.png 2x">',
        '<img src="&#104;ttps://example.com/a.png">',
        '<img src="ht&#9;tps://example.com/a.png">',
        '<video poster="https://example.com/p.png"></video>',
        '<object data="https://example.com/a.svg"></object>',
        '<form action="https://example.com/submit"></form>',
        '<link rel="stylesheet" href="//example.com/a.css">',
        '<div style="background: URL(https://example.com/a.png)"></div>',
        '<style>@import "theme.css";</style>',
    ],
)
def test_network_references_are_found(markup):
    assert find_network_references(markup) != []


@pytest.mark.parametrize(
    "markup",
    [
        '<a href="https://example.com/docs">docs</a>',
        "<p>Write url(https://example.com) or @import in a stylesheet.</p>",
        '<img src="data:image/png;base64,AAAA" alt="">',
        '<svg><use href="#ic-info"/></svg>',
    ],
)
def test_links_and_prose_are_not_network_references(markup):
    assert find_network_references(markup) == []


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
