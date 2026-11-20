# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The plugin load-status views: the status-bar indicator and its panel.

The indicator is a glyph that pulses while any plugin loads, then shows a
check when all loaded or a red X when any failed; it stays raw Qt because
TraitsUI cannot animate a label. The panel is a read-only table of every
plugin's load record over a copyable details area that shows the selected
failure's traceback.

Both run standalone against just their model:
``PluginLoadStatusIndicator(status=PluginLoadStatus()).widget.show()`` and
``PluginLoadStatusPanelModel().edit_traits(view=PluginLoadStatusView)``.
"""

# Enthought library imports.
from pyface.qt import QtGui
from traits.api import Bool, HasTraits, Instance, observe
from traitsui.api import (
    NoButtons,
    TableEditor,
    TextEditor,
    UItem,
    VGroup,
    View,
    VSplit,
)

# Microdrop style imports.
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import LOAD_LOADING, PluginLoadStatus
from microdrop_utils.pyside_helpers import ClickableLabel, PulsingLabel
from microdrop_utils.traitsui_qt_helpers import ObjectColumn

# Local imports.
from .consts import (
    PLUGIN_LOAD_STATE_COLORS,
    PLUGIN_LOAD_STATE_GLYPHS,
    TRACEBACK_STYLE_SHEET,
)

#: Point size of the state glyphs in the panel's table.
_TABLE_GLYPH_POINT_SIZE = 14


class PluginLoadStatusIcon(ClickableLabel, PulsingLabel):
    """Status-bar glyph that can pulse and emits ``clicked`` on a left press.

    Unlike PulsingLabel's start()/stop(), pulsing here never changes the
    icon's visibility: it may pulse before the status bar adopts it, when
    showing it would pop it up as a window of its own.
    """

    def set_pulsing(self, pulsing):
        """Start or stop the pulse, resetting the opacity when stopped."""
        if pulsing:
            self._animation.start()

            return

        self._animation.stop()
        self._opacity_effect.setOpacity(1.0)


class PluginLoadStatusIndicator(HasTraits):
    """Keep the status-bar icon in step with the aggregate load state."""

    #: The load records the icon summarises.
    status = Instance(PluginLoadStatus)

    #: The icon the status bar shows.
    widget = Instance(PluginLoadStatusIcon)

    #: Whether the icon is pulsing (any plugin pending or loading).
    _pulsing = Bool(False)

    def _widget_default(self):
        widget = PluginLoadStatusIcon("")

        font = QtGui.QFont(ICON_FONT_FAMILY)
        font.setPointSize(STATUSBAR_ICON_POINT_SIZE)
        widget.setFont(font)

        return widget

    @observe("status.[state, summary]")
    def _show_state(self, event):
        """Glyph and colour for the aggregate state, pulsing while loading."""
        state = self.status.state

        self.widget.setText(PLUGIN_LOAD_STATE_GLYPHS[state])
        self.widget.setStyleSheet(f"color: {PLUGIN_LOAD_STATE_COLORS[state]};")
        self.widget.setToolTip(f"Plugins: {self.status.summary}. Click for details.")

        loading = state == LOAD_LOADING

        if loading != self._pulsing:
            self.widget.set_pulsing(loading)
            self._pulsing = loading


class _StateColumn(ObjectColumn):
    """The state as its glyph, coloured like the status-bar indicator."""

    def traits_init(self):
        self.text_font = QtGui.QFont(ICON_FONT_FAMILY, _TABLE_GLYPH_POINT_SIZE)
        self.horizontal_alignment = "center"
        self.format_func = PLUGIN_LOAD_STATE_GLYPHS.get

    def get_text_color(self, object):
        return PLUGIN_LOAD_STATE_COLORS[object.state]

    def get_tooltip(self, object):
        return object.state.capitalize()


def _format_duration(seconds):
    """Seconds as a plain number; blank until the start finished."""
    return f"{seconds:.3f}" if seconds else ""


records_table = TableEditor(
    columns=[
        _StateColumn(name="state", label="", editable=False),
        ObjectColumn(name="name", label="Plugin", editable=False),
        ObjectColumn(
            name="duration",
            label="Start-up (s)",
            editable=False,
            format_func=_format_duration,
            horizontal_alignment="right",
        ),
        ObjectColumn(name="error", label="Error", editable=False),
    ],
    editable=False,
    sortable=False,
    auto_size=True,
    selected="selected",
    selection_mode="row",
)

PluginLoadStatusView = View(
    VGroup(
        UItem("object.status.summary", style="readonly"),
        VSplit(
            UItem("object.status.records", editor=records_table),
            UItem(
                "details_text",
                style="custom",
                editor=TextEditor(multi_line=True, read_only=True),
                style_sheet=TRACEBACK_STYLE_SHEET,
            ),
        ),
    ),
    title="Plugin Load Status",
    kind="live",
    resizable=True,
    width=760,
    height=560,
    buttons=NoButtons,
)
