# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The pre-flight card's fixed parts: the header, the quiet line, the Run
footer and the run-info rows, each built from the report or the run."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_CLOSE
from microdrop_style.palette_helpers import css, icon_font, with_alpha
from microdrop_style.panel_metrics import DRAWER_PADDING_PX
from microdrop_style.panel_theme import (
    icon_button_style,
    link_button_style,
    muted_text,
    primary_button_style,
    quiet_button_style,
)
from microdrop_style.typography import BUTTON, CARD_TITLE, META, role_font

# Local imports.
from .view_consts import (
    ENTRANCE_MS,
    ICON_COLLAPSE,
    ICON_EXPAND,
    ICON_SETTINGS,
    ROW_HEIGHT,
)

_ALIGN = QtCore.Qt.AlignmentFlag
_HAND = QtCore.Qt.CursorShape.PointingHandCursor


def header(summary, scope, palette, on_close, on_settings=None):
    """The one-line header: the summary, the run scope, a settings gear
    (when ``on_settings`` is given) and a close button."""
    widget = QtWidgets.QWidget()
    widget.setFixedHeight(ROW_HEIGHT)
    row = QtWidgets.QHBoxLayout(widget)
    row.setContentsMargins(6, 0, 6, 0)
    row.setSpacing(6)

    title = QtWidgets.QLabel(summary)
    title.setFont(role_font(CARD_TITLE))

    scope_label = muted_label(scope, palette)
    scope_label.setAlignment(_ALIGN.AlignRight | _ALIGN.AlignVCenter)

    row.addWidget(title)
    row.addWidget(scope_label, 1)

    if on_settings is not None:
        row.addWidget(icon_button(ICON_SETTINGS, "Settings", palette, on_settings))

    row.addWidget(icon_button(ICON_CLOSE, "Close", palette, on_close))

    return widget


def icon_button(glyph, tooltip, palette, on_click):
    """A borderless row-high glyph button calling ``on_click()``."""
    button = QtWidgets.QToolButton()
    button.setText(glyph)
    button.setToolTip(tooltip)
    button.setFixedSize(ROW_HEIGHT, ROW_HEIGHT)
    button.setCursor(_HAND)
    button.setStyleSheet(icon_button_style(palette, 20))
    button.clicked.connect(on_click)

    return button


def quiet_line(report, expanded, palette, on_toggle):
    """ "✓ 9 passed · 2 not checked · 1 muted", folding the full list."""
    line = QtWidgets.QPushButton()
    line.setFixedHeight(ROW_HEIGHT)
    line.setFont(role_font(META))
    line.setStyleSheet(link_button_style(palette, muted_text(palette)))

    passed, not_checked, muted = report.quiet_counts()
    parts = [f"✓ {passed} passed"]

    if not_checked:
        parts.append(f"{not_checked} not checked")

    if muted:
        parts.append(f"{muted} muted")

    line.setText("  " + " · ".join(parts))
    line.setIcon(glyph_icon(ICON_COLLAPSE if expanded else ICON_EXPAND, palette))
    line.setCursor(_HAND)
    line.clicked.connect(on_toggle)

    return line


def footer(report, palette, on_run):
    """The Run row: "Run anyway" over warnings, a disabled Run (its reason
    on hover) over blocking checks, else Run. ``on_run(anyway)``."""
    widget = QtWidgets.QWidget()
    buttons = QtWidgets.QHBoxLayout(widget)
    buttons.setContentsMargins(0, 0, 0, 0)
    buttons.setSpacing(DRAWER_PADDING_PX)
    buttons.addStretch(1)

    if report.overall == "warn":
        run_anyway = _button("Run anyway", quiet_button_style(palette))
        run_anyway.clicked.connect(lambda: on_run(True))
        buttons.addWidget(run_anyway)

    elif report.overall == "fail":
        run = _button("Run", _disabled_primary_style(palette))
        run.setEnabled(False)

        # A disabled button shows no tooltip; its holder does.
        holder = QtWidgets.QWidget()
        holder.setToolTip(report.first_blocking_reason)
        holder_layout = QtWidgets.QHBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.addWidget(run)

        buttons.addWidget(holder)

    else:
        run = _button("Run", primary_button_style(palette))
        run.clicked.connect(lambda: on_run(False))
        buttons.addWidget(run)

    return widget


def run_info_values(run_info):
    """The run in progress as ``(name, value)`` pairs: its step, elapsed
    time and the acknowledgement it waits on (empty while none shows)."""
    minutes, seconds = divmod(run_info.elapsed_s, 60)

    return (
        ("Step", f"{run_info.step}/{run_info.step_total}"),
        ("Elapsed", f"{minutes:02d}:{seconds:02d}"),
        ("Waiting on", run_info.wait_line),
    )


def run_info_rows(run_info, palette):
    """The run in progress, a row per value; each row's ``value_label``
    takes the value's later updates in place."""
    return [
        _pair_row(name, value, palette) for name, value in run_info_values(run_info)
    ]


def scrolling(body):
    """``body`` in a frameless, see-through vertical scroll area."""
    scroll = QtWidgets.QScrollArea()
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(body)

    # setWidget fills the body; the panel's own surface shows through.
    scroll.viewport().setAutoFillBackground(False)
    body.setAutoFillBackground(False)

    return scroll


def fade_in(widget):
    """Fade ``widget`` in over ENTRANCE_MS, then drop the effect."""
    effect = QtWidgets.QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)

    animation = QtCore.QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(ENTRANCE_MS)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.finished.connect(lambda: widget.setGraphicsEffect(None))
    animation.start()


def muted_label(text, palette):
    """``text`` in the small muted meta style."""
    label = QtWidgets.QLabel(text)
    label.setFont(role_font(META))
    label.setStyleSheet(f"color: {css(muted_text(palette))};")

    return label


def glyph_icon(glyph, palette):
    """``glyph`` from the icon font as a small muted icon."""
    pixmap = QtGui.QPixmap(14, 14)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)

    painter = QtGui.QPainter(pixmap)
    painter.setFont(icon_font(14))
    painter.setPen(muted_text(palette))
    painter.drawText(pixmap.rect(), _ALIGN.AlignCenter, glyph)
    painter.end()

    return QtGui.QIcon(pixmap)


def _pair_row(name, value, palette):
    row = QtWidgets.QWidget()
    row.setFixedHeight(ROW_HEIGHT)
    layout = QtWidgets.QHBoxLayout(row)
    layout.setContentsMargins(6, 0, 6, 0)
    layout.setSpacing(6)

    value_label = QtWidgets.QLabel(value)
    value_label.setAlignment(_ALIGN.AlignRight | _ALIGN.AlignVCenter)

    layout.addWidget(muted_label(name, palette))
    layout.addWidget(value_label, 1)
    row.value_label = value_label

    return row


def _button(text, style):
    button = QtWidgets.QPushButton(text)
    button.setFont(role_font(BUTTON))
    button.setCursor(_HAND)
    button.setStyleSheet(style)

    return button


def _disabled_primary_style(palette):
    text = palette.color(QtGui.QPalette.ColorRole.Text)

    return (
        "QPushButton:disabled {"
        f" background: {css(with_alpha(text, 0.10))};"
        f" color: {css(with_alpha(text, 0.40))}; border: none;"
        " border-radius: 5px; padding: 4px 12px; font-weight: 600; }"
    )
