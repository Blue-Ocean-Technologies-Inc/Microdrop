"""TableEditor + columns for the Installed Packages tab (issue #532).

Real-grid rendering (like the alpha view table): Name / Version as text, and
Documentation / Upgrade / Uninstall as Material-glyph action columns. The
reusable column types live in ``microdrop_utils.traitsui_qt_helpers``
(``GlyphActionColumn`` for the click-to-fire glyphs, ``EnumSelectColumn`` for
the version dropdown that blanks its static text while editing); only the
docs-specific greying is defined locally.
"""
from traitsui.api import TableEditor

from microdrop_style.colors import GREY
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
            return GREY
        return super().get_text_color(object)

    def get_tooltip(self, object):
        if not getattr(object, "doc_url", ""):
            return "Documentation link available after the plugin's next release."
        return "Open documentation"

    def on_click(self, object):
        if getattr(object, "doc_url", ""):
            object.open_docs = True


installed_table_editor = TableEditor(
    columns=[
        ObjectColumn(name="name", label="Name", editable=False),
        DocColumn(name="doc_url", label="Docs", glyph=ICON_DESCRIPTION),
        EnumSelectColumn(name="version", label="Version",
                         values_name="available_versions", width=90),
        GlyphActionColumn(name="dist_name", label="Upgrade", glyph=ICON_UPGRADE,
                          fire="upgrade"),
        GlyphActionColumn(name="manifest_name", label="Uninstall", glyph=ICON_DELETE,
                          fire="uninstall"),
    ],
    editable=True,
    sortable=False,
    auto_size=True,
    show_column_labels=False,   # glyphs + package name are self-explanatory
    selected="installed_selected",   # drives the details pane
    selection_mode="row",
)
