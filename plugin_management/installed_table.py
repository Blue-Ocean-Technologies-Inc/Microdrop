"""TableEditor + columns for the Installed Packages tab (issue #532).

Real-grid rendering (like the alpha view table): Name / Version as text, and
Documentation / Upgrade / Uninstall as Material-glyph action columns. The
reusable column types live in ``microdrop_utils.traitsui_qt_helpers``
(``GlyphActionColumn`` for the click-to-fire glyphs, ``EnumSelectColumn`` for
the version dropdown that blanks its static text while editing); only the
docs- and upgrade-specific enabled/disabled treatments are defined locally.
"""
from traitsui.api import TableEditor

from microdrop_style.colors import GREY, INFO_COLOR, SUCCESS_COLOR
from microdrop_style.icons.icons import ICON_DESCRIPTION, ICON_DELETE
from microdrop_utils.traitsui_qt_helpers import (
    ObjectColumn, GlyphActionColumn, EnumSelectColumn)

#: Material Symbols Outlined resolves the "upgrade" ligature (no ICON_UPGRADE
#: constant exists yet — same as ICON_DELETE = "delete").
ICON_UPGRADE = "upgrade"


class DocColumn(GlyphActionColumn):
    """Documentation glyph: greyed + explanatory tooltip when the package has no
    published URL yet (the case until each plugin's next release); opens the
    repo/docs page otherwise (fires ``open_docs``)."""

    def get_text_color(self, object):
        if not getattr(object, "doc_url", ""):
            return GREY["dark"]
        return INFO_COLOR

    def get_tooltip(self, object):
        if not getattr(object, "doc_url", ""):
            return "Documentation link available after the plugin's next release."
        return "Open documentation"

    def on_click(self, object):
        if getattr(object, "doc_url", ""):
            object.open_docs = True


class UpgradeColumn(GlyphActionColumn):
    """Upgrade glyph: success-green + click-to-fire when the channel offers a
    newer version; darker grey and inert when already up to date (the same
    disabled treatment as DocColumn)."""

    def get_text_color(self, object):
        if object.upgrade_available():
            return SUCCESS_COLOR
        return GREY["dark"]

    def get_tooltip(self, object):
        if object.upgrade_available():
            return f"Upgrade to {object.available_versions[0]}"
        return "Already up to date"

    def on_click(self, object):
        if object.upgrade_available():
            object.upgrade = True


installed_table_editor = TableEditor(
    columns=[
        ObjectColumn(name="name", label="", editable=False),
        DocColumn(name="doc_url", label="", glyph=ICON_DESCRIPTION),
        EnumSelectColumn(name="version", label="",
                         values_name="available_versions", width=90),
        UpgradeColumn(name="dist_name", label="", glyph=ICON_UPGRADE),
        GlyphActionColumn(name="manifest_name", label="", glyph=ICON_DELETE,
                          fire="uninstall"),
    ],
    editable=True,
    sortable=False,
    auto_size=True,
    show_column_labels=False,   # glyphs + package name are self-explanatory
    selected="installed_selected",   # drives the details pane
    selection_mode="row",
)
