# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""
Touch-mode styling: finger-sized controls for the application stylesheet.

Spin boxes become horizontal steppers (a big minus at the left edge, a big
plus at the right), and check boxes, combo boxes, scroll bars, sliders, tabs,
menus, headers and item rows grow to finger size. Sizes come from padding
rather than minimum sizes wherever possible: Qt resets a widget's minimum
size to zero when a stylesheet minimum is removed, which would discard sizes
set in code once touch mode is turned off. Widgets held to a size in code
are matched through the TOUCH_COMPACT_PROPERTY / TOUCH_GROWS_PROPERTY marks
the touch event filter sets, so they keep that size.

Resizing a sub-control makes Qt stop drawing it natively, so every
sub-control touched here is styled completely. The glyph images are SVGs
written once per colour to a cache folder, so they follow the palette.
"""

# Standard library imports.
import tempfile
from pathlib import Path

# Enthought library imports.
from pyface.qt.QtGui import QColor, QPalette

# Local imports.
from .colors import ACCENT_COLOR, ERROR_COLOR, GREY, WHITE

#: The finger target: the smallest side of anything meant to be tapped.
TOUCH_TARGET_PX = 44

#: Rows of dense lists (tables, trees, menus): smaller than a full target,
#: as the row's whole width is the target.
TOUCH_DENSE_ROW_PX = 36

#: Corner radius shared by the touch frames.
TOUCH_RADIUS_PX = 6

#: Line width of the touch frames. The rig's interface scale (an xrandr
#: down-scale) drops or fades a 1 px line depending on which row it lands
#: on, so a frame can vanish at some pane sizes; 2 px always keeps a row.
TOUCH_FRAME_PX = 2

#: Side of the check-box and radio-button indicators.
TOUCH_INDICATOR_PX = 26

#: Thickness of the scroll bars, and of the thin ones marked compact (a
#: pane's or a strip's, which flick scrolling serves instead).
TOUCH_SCROLL_BAR_PX = 28
TOUCH_THIN_SCROLL_BAR_PX = 10

#: Diameter of the slider handles.
TOUCH_SLIDER_HANDLE_PX = 32

#: Opacity (0-255) of the error colour washed over an invalid field.
ERROR_TINT_ALPHA = 48

#: Where the generated glyph SVGs are cached, one file per glyph and colour.
TOUCH_GLYPH_DIR = Path(tempfile.gettempdir()) / "microdrop_touch_glyphs"

#: Glyph name -> SVG shape on a 24x24 grid, stroked in the glyph's colour.
TOUCH_GLYPH_SHAPES = {
    "plus": '<path d="M12 4.5v15M4.5 12h15"/>',
    "minus": '<path d="M4.5 12h15"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "dash": '<path d="M6 12h12"/>',
    "chevron_down": '<path d="M6 9l6 6 6-6"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
}

_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.6" '
    'stroke-linecap="round" stroke-linejoin="round">{shape}</svg>'
)

#: Dynamic property marking a widget held too small, in code, for its
#: finger size: a spin box keeps no stepper (the number pad edits it), a
#: combo box keeps its height, a scroll bar stays thin.
TOUCH_COMPACT_PROPERTY = "touchCompact"

#: Dynamic property marking a button or text field whose size code left
#: free, so it may grow to finger size; a fixed-size one would be clipped.
TOUCH_GROWS_PROPERTY = "touchGrows"

#: Style-sheet section that every spin-box rule below is scoped to.
_SPIN_BOX = "QAbstractSpinBox"

#: A spin box in an item view is a cell editor, matched by ancestry so it
#: never depends on the property being set in time.
_CELL_SPIN_BOX = f"QAbstractItemView {_SPIN_BOX}"

#: Spin boxes that keep no stepper: cell editors and those marked compact.
_COMPACT_SPIN_BOXES = (_CELL_SPIN_BOX, f'{_SPIN_BOX}[{TOUCH_COMPACT_PROPERTY}="true"]')


def touch_glyph_path(name, color):
    """Return the posix path of glyph ``name`` drawn in ``color``.

    The SVG is written on first use, so the stylesheet can reference it.
    """
    path = TOUCH_GLYPH_DIR / f"{name}_{color.lstrip('#').lower()}.svg"

    if not path.exists():
        TOUCH_GLYPH_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            _SVG_TEMPLATE.format(color=color, shape=TOUCH_GLYPH_SHAPES[name]),
            encoding="utf-8",
        )

    return path.as_posix()


def get_touch_colors(palette, dark):
    """Return the touch-style colours for ``palette``.

    Text and fields come from the palette, so the controls look native in
    either scheme; frames and button fills come from the Microdrop greys.
    """
    roles = QPalette.ColorRole
    disabled = QPalette.ColorGroup.Disabled
    error = QColor(ERROR_COLOR)

    if dark:
        frame, button, pressed, handle = (
            GREY["dark"],
            GREY["darker"],
            GREY["dark"],
            GREY["dark"],
        )
    else:
        frame, button, pressed, handle = (
            GREY["lighter"],
            GREY["lightest"],
            GREY["lighter"],
            GREY["lighter"],
        )

    return {
        "base": palette.color(roles.Base).name(),
        "text": palette.color(roles.Text).name(),
        "disabled_text": palette.color(disabled, roles.Text).name(),
        "window": palette.color(roles.Window).name(),
        "window_text": palette.color(roles.WindowText).name(),
        "highlight": palette.color(roles.Highlight).name(),
        "highlighted_text": palette.color(roles.HighlightedText).name(),
        "frame": frame,
        "button": button,
        "pressed": pressed,
        "handle": handle,
        "accent": ACCENT_COLOR,
        "error": ERROR_COLOR,
        "error_tint": (
            f"rgba({error.red()}, {error.green()}, {error.blue()}, {ERROR_TINT_ALPHA})"
        ),
    }


def get_touch_style(palette, dark):
    """Return the touch-mode QSS for ``palette``.

    Parameters
    ----------
    palette : QPalette
        The application palette the rules are coloured from.
    dark : bool
        Whether the palette is a dark one, which picks the frame greys.
    """
    colors = get_touch_colors(palette, dark)

    return "\n".join(
        (
            _spin_box_rules(colors),
            _check_rules(colors),
            _combo_box_rules(colors),
            _scroll_bar_rules(colors),
            _slider_rules(colors),
            _button_and_field_rules(),
            _tab_menu_and_header_rules(colors),
            _item_view_rules(),
        )
    )


def _spin_box_rules(colors):
    """Steppers: minus at the left edge, plus at the right, value centred."""
    target = TOUCH_TARGET_PX
    plus = touch_glyph_path("plus", colors["text"])
    minus = touch_glyph_path("minus", colors["text"])
    plus_disabled = touch_glyph_path("plus", colors["disabled_text"])
    minus_disabled = touch_glyph_path("minus", colors["disabled_text"])

    return f"""
{_SPIN_BOX} {{
    min-height: {target - 2 * TOUCH_FRAME_PX}px;
    padding: 0px 4px;
    border: {TOUCH_FRAME_PX}px solid {colors["frame"]};
    border-radius: {TOUCH_RADIUS_PX}px;
    background-color: {colors["base"]};
    color: {colors["text"]};
    selection-background-color: {colors["highlight"]};
    selection-color: {colors["highlighted_text"]};
}}
{_SPIN_BOX}:focus {{
    border-color: {colors["accent"]};
}}
{_SPIN_BOX}:disabled {{
    color: {colors["disabled_text"]};
}}
{_SPIN_BOX}::up-button, {_SPIN_BOX}::down-button {{
    subcontrol-origin: border;
    width: {target - 2 * TOUCH_FRAME_PX}px;
    height: {target - 2 * TOUCH_FRAME_PX}px;
    border: {TOUCH_FRAME_PX}px solid {colors["frame"]};
    background-color: {colors["button"]};
}}
{_SPIN_BOX}::up-button {{
    subcontrol-position: center right;
    border-top-right-radius: {TOUCH_RADIUS_PX}px;
    border-bottom-right-radius: {TOUCH_RADIUS_PX}px;
}}
{_SPIN_BOX}::down-button {{
    subcontrol-position: center left;
    border-top-left-radius: {TOUCH_RADIUS_PX}px;
    border-bottom-left-radius: {TOUCH_RADIUS_PX}px;
}}
{_SPIN_BOX}::up-button:pressed, {_SPIN_BOX}::down-button:pressed {{
    background-color: {colors["pressed"]};
    border-color: {colors["accent"]};
}}
{_SPIN_BOX}::up-arrow, {_SPIN_BOX}::down-arrow {{
    width: 20px;
    height: 20px;
}}
{_SPIN_BOX}::up-arrow {{
    image: url({plus});
}}
{_SPIN_BOX}::down-arrow {{
    image: url({minus});
}}
{_SPIN_BOX}::up-arrow:disabled, {_SPIN_BOX}::up-arrow:off {{
    image: url({plus_disabled});
}}
{_SPIN_BOX}::down-arrow:disabled, {_SPIN_BOX}::down-arrow:off {{
    image: url({minus_disabled});
}}
{_compact_selector("")} {{
    min-height: 0px;
    padding: 0px 2px;
    border-radius: 0px;
}}
{_CELL_SPIN_BOX} {{
    border: none;
}}
{_compact_selector("::up-button")}, {_compact_selector("::down-button")} {{
    width: 0px;
    height: 0px;
    border: none;
}}
{_compact_selector("::up-arrow")}, {_compact_selector("::down-arrow")} {{
    image: none;
    width: 0px;
    height: 0px;
}}
"""


def _compact_selector(sub_control):
    """Return the compact spin-box selector list, each with ``sub_control``."""
    return ", ".join(f"{selector}{sub_control}" for selector in _COMPACT_SPIN_BOXES)


def _check_rules(colors):
    """Check boxes, radio buttons and checkable group boxes."""
    size = TOUCH_INDICATOR_PX
    check = touch_glyph_path("check", WHITE)
    dash = touch_glyph_path("dash", WHITE)
    indicators = "QCheckBox::indicator, QGroupBox::indicator"
    radio_dot = (
        "qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5, "
        f"stop: 0 {WHITE}, stop: 0.4 {WHITE}, stop: 0.5 {colors['accent']}, "
        f"stop: 1 {colors['accent']})"
    )

    return f"""
QCheckBox, QRadioButton {{
    spacing: 10px;
    padding: 6px 0px;
}}
{indicators}, QRadioButton::indicator {{
    width: {size}px;
    height: {size}px;
    border: 2px solid {colors["frame"]};
    background-color: {colors["base"]};
}}
{indicators} {{
    border-radius: 5px;
}}
QRadioButton::indicator {{
    border-radius: {size // 2 + 2}px;
}}
QCheckBox::indicator:checked, QGroupBox::indicator:checked,
QCheckBox::indicator:indeterminate, QRadioButton::indicator:checked {{
    border-color: {colors["accent"]};
    background-color: {colors["accent"]};
}}
QCheckBox::indicator:checked, QGroupBox::indicator:checked {{
    image: url({check});
}}
QCheckBox::indicator:indeterminate {{
    image: url({dash});
}}
QRadioButton::indicator:checked {{
    background-color: {radio_dot};
}}
{indicators}:pressed, QRadioButton::indicator:pressed {{
    border-color: {colors["accent"]};
}}
{indicators}:disabled, QRadioButton::indicator:disabled {{
    border-color: {colors["disabled_text"]};
    background-color: {colors["window"]};
}}
"""


def _combo_box_rules(colors):
    """Tall combo boxes with a wide drop-down button and tall popup rows."""
    chevron = touch_glyph_path("chevron_down", colors["text"])
    chevron_disabled = touch_glyph_path("chevron_down", colors["disabled_text"])

    return f"""
QComboBox {{
    combobox-popup: 0;
    min-height: {TOUCH_TARGET_PX - 2 * TOUCH_FRAME_PX}px;
    padding: 0px 8px 0px 10px;
    border: {TOUCH_FRAME_PX}px solid {colors["frame"]};
    border-radius: {TOUCH_RADIUS_PX}px;
    background-color: {colors["base"]};
    color: {colors["text"]};
}}
QComboBox:focus, QComboBox:on {{
    border-color: {colors["accent"]};
}}
QComboBox:disabled {{
    color: {colors["disabled_text"]};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 40px;
    border: none;
    border-left: {TOUCH_FRAME_PX}px solid {colors["frame"]};
}}
QComboBox::down-arrow {{
    image: url({chevron});
    width: 20px;
    height: 20px;
}}
QComboBox::down-arrow:disabled {{
    image: url({chevron_disabled});
}}
QComboBox QAbstractItemView {{
    border: 1px solid {colors["frame"]};
    background-color: {colors["base"]};
    color: {colors["text"]};
    selection-background-color: {colors["highlight"]};
    selection-color: {colors["highlighted_text"]};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    min-height: {TOUCH_TARGET_PX}px;
    padding: 0px 10px;
}}
QComboBox[{TOUCH_COMPACT_PROPERTY}="true"] {{
    min-height: 0px;
}}
"""


def _scroll_bar_rules(colors):
    """Thick scroll bars with a rounded handle and no arrow buttons."""
    thickness = TOUCH_SCROLL_BAR_PX
    thin = f'QScrollBar[{TOUCH_COMPACT_PROPERTY}="true"]'
    inset = 5
    radius = (thickness - 2 * inset) // 2

    return f"""
QScrollBar:vertical {{
    width: {thickness}px;
    margin: 0px;
    border: none;
    background-color: transparent;
}}
QScrollBar:horizontal {{
    height: {thickness}px;
    margin: 0px;
    border: none;
    background-color: transparent;
}}
QScrollBar::handle {{
    margin: {inset}px;
    border-radius: {radius}px;
    background-color: {colors["handle"]};
}}
QScrollBar::handle:vertical {{
    min-height: {TOUCH_TARGET_PX}px;
}}
QScrollBar::handle:horizontal {{
    min-width: {TOUCH_TARGET_PX}px;
}}
QScrollBar::handle:pressed {{
    background-color: {colors["accent"]};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
    border: none;
    background: none;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
}}
{thin}:vertical {{
    width: {TOUCH_THIN_SCROLL_BAR_PX}px;
}}
{thin}:horizontal {{
    height: {TOUCH_THIN_SCROLL_BAR_PX}px;
}}
{thin}::handle {{
    margin: 2px;
    border-radius: {TOUCH_THIN_SCROLL_BAR_PX // 2 - 2}px;
}}
"""


def _slider_rules(colors):
    """Thick grooves and finger-sized round handles."""
    handle = TOUCH_SLIDER_HANDLE_PX
    groove = 8
    overhang = (handle - groove) // 2

    return f"""
QSlider:horizontal {{
    min-height: {handle + 4}px;
}}
QSlider:vertical {{
    min-width: {handle + 4}px;
}}
QSlider::groove {{
    border-radius: {groove // 2}px;
    background-color: {colors["frame"]};
}}
QSlider::groove:horizontal {{
    height: {groove}px;
}}
QSlider::groove:vertical {{
    width: {groove}px;
}}
QSlider::sub-page:horizontal, QSlider::add-page:vertical {{
    border-radius: {groove // 2}px;
    background-color: {colors["accent"]};
}}
QSlider::handle {{
    border: 2px solid {colors["accent"]};
    border-radius: {handle // 2}px;
    background-color: {colors["base"]};
}}
QSlider::handle:horizontal {{
    width: {handle - 4}px;
    margin: -{overhang}px 0px;
}}
QSlider::handle:vertical {{
    height: {handle - 4}px;
    margin: 0px -{overhang}px;
}}
QSlider::handle:pressed {{
    background-color: {colors["accent"]};
}}
QSlider::handle:disabled {{
    border-color: {colors["disabled_text"]};
}}
"""


def _button_and_field_rules():
    """Push and tool buttons, and text fields, grown by padding where their
    code left their size free."""
    grows = f'[{TOUCH_GROWS_PROPERTY}="true"]'

    return f"""
QPushButton{grows} {{
    padding: 11px 16px;
}}
QToolButton{grows} {{
    padding: 9px;
}}
QLineEdit{grows} {{
    padding: 9px 6px;
}}
"""


def _tab_menu_and_header_rules(colors):
    """Tabs, menu items and header sections, styled in full."""
    return f"""
QTabBar::tab {{
    padding: 10px 16px;
    margin: 2px;
    border: 1px solid {colors["frame"]};
    border-radius: {TOUCH_RADIUS_PX}px;
    background-color: {colors["window"]};
    color: {colors["window_text"]};
}}
QTabBar::tab:selected {{
    padding: 9px 15px;
    border: 2px solid {colors["accent"]};
    background-color: {colors["base"]};
}}
QMenuBar::item {{
    padding: 10px 14px;
    background: transparent;
}}
QMenuBar::item:selected, QMenuBar::item:pressed {{
    background-color: {colors["highlight"]};
    color: {colors["highlighted_text"]};
}}
QMenu {{
    border: 1px solid {colors["frame"]};
    background-color: {colors["base"]};
    color: {colors["text"]};
}}
QMenu::item {{
    padding: 10px 28px 10px 32px;
}}
QMenu::item:selected {{
    background-color: {colors["highlight"]};
    color: {colors["highlighted_text"]};
}}
QMenu::item:disabled {{
    color: {colors["disabled_text"]};
}}
QMenu::separator {{
    height: 1px;
    margin: 4px 8px;
    background-color: {colors["frame"]};
}}
QHeaderView::section {{
    padding: 8px 6px;
    border: none;
    border-right: 1px solid {colors["frame"]};
    border-bottom: 1px solid {colors["frame"]};
    background-color: {colors["window"]};
    color: {colors["window_text"]};
}}
"""


def _item_view_rules():
    """Taller rows in trees, tables and lists."""
    return f"""
QTreeView::item, QListView::item, QTableView::item {{
    min-height: {TOUCH_DENSE_ROW_PX}px;
}}
"""
