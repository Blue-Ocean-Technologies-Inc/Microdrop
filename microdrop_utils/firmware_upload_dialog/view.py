"""View layer for the firmware-upload dialog: the append-only log console
editor, the TraitsUI config-panel view, and the panel stylesheet that makes
the embedded TraitsUI widgets match BaseMessageDialog's theme."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit

from traits.api import Int
from traitsui.api import (
    BasicEditorFactory, HGroup, HSplit, Item, Label, RangeEditor, UItem,
    VGroup, View, spring,
)
from traitsui.qt.editor import Editor as QtEditor

from microdrop_style.colors import PRIMARY_COLOR, WHITE
from microdrop_style.icons.icons import (
    ICON_ARCHIVE, ICON_AUTOMATION, ICON_DELETE, ICON_REFRESH, ICON_USB,
)
from microdrop_utils.traitsui_qt_helpers import (
    HoverScrollEnumEditor, IconButtonEditor, IconToggleEditor,
)

from .consts import LOG_CONSOLE_FONT_FAMILY


# --------------------------------------------------------------------------
# Log console editor (append-only, auto-scrolling)
# --------------------------------------------------------------------------

class _LogViewEditor(QtEditor):
    """Read-only console over a Str trait: appends only the new tail on each
    change (the upload log grows by appending), auto-scrolls to the bottom,
    and resets wholesale when the trait shrinks (e.g. Clear log)."""

    def init(self, parent):
        self.control = QPlainTextEdit()
        self.control.setReadOnly(True)
        self.control.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont(LOG_CONSOLE_FONT_FAMILY)
        font.setPointSize(self.factory.point_size)
        self.control.setFont(font)
        self.control.setMinimumHeight(self.factory.min_height)
        self.control.setMinimumWidth(self.factory.min_width)
        self.control.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 6px;
                padding: 6px;
                selection-background-color: {PRIMARY_COLOR};
            }}
            /* This widget-level QSS forces non-native scrollbars, so restyle
               them to match the console (dark twin of the panel's light
               scrollbar rules). */
            QScrollBar:vertical {{
                background: transparent;
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: #4A4A4A;
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: #5C5C5C;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: #4A4A4A;
                border-radius: 6px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: #5C5C5C;
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{
                width: 0px;
                height: 0px;
            }}
            QScrollBar::add-page, QScrollBar::sub-page {{
                background: none;
            }}
        """)
        self._shown_text = ""
        self.update_editor()

    def update_editor(self):
        text = self.value or ""
        if text == self._shown_text:
            return
        if text.startswith(self._shown_text):
            cursor = self.control.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.insertText(text[len(self._shown_text):])
        else:
            self.control.setPlainText(text)
        self._shown_text = text
        scrollbar = self.control.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class LogViewEditor(BasicEditorFactory):
    """Factory for the dark console log view over a Str trait."""

    klass = _LogViewEditor

    min_height = Int(220)
    min_width = Int(300)
    point_size = Int(9)


# --------------------------------------------------------------------------
# View
# --------------------------------------------------------------------------

def _collapse_header(trait, label):
    """A section header row: a Material arrow glyph that expands / collapses
    the section by toggling ``trait``, followed by the section's label (same
    structure as the fluorescence controls pane)."""
    return HGroup(
        UItem(trait, editor=IconToggleEditor()),
        Label(label),
    )


# Left: collapsible config sections. Right: the log console, permanently
# visible on the other side of a draggable splitter.
firmware_upload_view = View(
    HSplit(
        VGroup(
            _collapse_header("show_source", "Firmware source"),
            VGroup(
                HGroup(
                    Item("firmware_source", label="Firmware", springy=True,
                         tooltip="Folder tree, or a .zip bundle, pushed to "
                                 "the board (a zip is unzipped, uploaded, "
                                 "then deleted)"),
                    UItem("browse_firmware_zip", editor=IconButtonEditor(
                        glyph=ICON_ARCHIVE,
                        tooltip="Select a firmware .zip bundle")),
                ),
                Item("single_file", label="Single file",
                     tooltip="Optional: upload only this file instead of "
                             "the whole firmware source"),
                visible_when="show_source",
                show_border=True,
                enabled_when="not uploading",
            ),
            _collapse_header("show_port", "Device & port"),
            VGroup(
                HGroup(
                    Item("auto_port", label="Auto-detect port",
                         editor=IconToggleEditor(
                             on_glyph=ICON_AUTOMATION, off_glyph=ICON_USB,
                             tooltip="On: the backend finds the board itself "
                                     "(a connected proxy's port, else "
                                     "whoami / Pico VID probing). "
                                     "Off: use the port selected here.")),
                    Item("selected_port_entry", label="Port",
                         editor=HoverScrollEnumEditor(
                             values_name="available_ports"),
                         enabled_when="not auto_port", springy=True),
                    UItem("refresh_ports", editor=IconButtonEditor(
                        glyph=ICON_REFRESH, tooltip="Re-scan serial ports")),
                ),
                Item("device_id", label="Device ID", style="readonly",
                     tooltip="The connected board's whoami id — the upload "
                             "flashes exactly this board (read from the "
                             "board, not editable)."),
                visible_when="show_port",
                show_border=True,
                enabled_when="not uploading",
            ),
            _collapse_header("show_options", "Options"),
            VGroup(
                Item("update_config", label="Upload config.json",
                     tooltip="Overwrite the board's config.json with the repo "
                             "copy. Off: the board keeps its own, backed up "
                             "and restored around the reflash."),
                Item("skip_filesystem_format", label="Skip format",
                     tooltip="Don't wipe the board's filesystem first"),
                Item("reset_after_upload", label="Reset after upload",
                     tooltip="Reset the board when the upload finishes"),
                Item("dry_run", label="Dry run",
                     tooltip="Only log what would happen"),
                Item("upload_timeout_s", label="Timeout (s)",
                     editor=RangeEditor(low=0, high=10000, mode="spinner"),
                     tooltip="Kill the upload if it runs longer than this many "
                             "seconds (0 = no timeout)"),
                visible_when="show_options",
                show_border=True,
                enabled_when="not uploading",
            ),
            # Only this column scrolls (vertically) when the dialog is short —
            # the log console on the right has its own scrollbars.
            scrollable=True,
        ),
        VGroup(
            HGroup(
                Label("Upload log"),
                spring,
                UItem("clear_log", editor=IconButtonEditor(
                    glyph=ICON_DELETE, tooltip="Clear the log")),
            ),
            UItem("upload_log", editor=LogViewEditor()),
            show_border=True,
            springy=True,
        ),
    ),
    # Resizable so sections take their natural height instead of being
    # crushed to their minimums; scrolling is per-side — the left column has
    # scrollable=True, the log console scrolls by itself.
    resizable=True,
)


# --------------------------------------------------------------------------
# Panel stylesheet
# --------------------------------------------------------------------------

def build_panel_stylesheet(dialog):
    """Scoped stylesheet for the embedded TraitsUI panel.

    BaseMessageDialog styles only its own widgets: its bare ``QPushButton``
    rule cascades primary-color/white onto the panel's Browse buttons, while
    the panel's labels/checkboxes/line edits get no rule at all and fall back
    to the system palette (white text in Windows dark mode on the dialog's
    always-light background). Pin every widget class here, in the dialog's own
    theme colors, so the panel matches the dialog in both system modes.
    QToolButton glyph buttons keep their Material Symbols font (no font-family
    rule on them); the log console carries its own stylesheet and wins anyway.
    """
    dialog_color = dialog.TYPE_COLORS.get(dialog.dialog_type, PRIMARY_COLOR)
    accent_bg = dialog._lighten_color(dialog_color, dialog.LIGHT_ACCENT_FACTOR)
    text_font = dialog.text_font_family
    return f"""
        #firmwareUploadPanel {{
            background: transparent;
        }}
        #firmwareUploadPanel QScrollArea {{
            background: transparent;
            border: none;
        }}
        #firmwareUploadPanel QScrollArea > QWidget > QWidget {{
            background: transparent;
        }}
        /* Any QSS on a scroll area drops its scrollbars to the ancient
           non-native look — restyle them like the dialog's own scroll areas
           (slim, rounded, no arrow buttons). */
        #firmwareUploadPanel QScrollBar:vertical {{
            background: transparent;
            width: 12px;
            border-radius: 6px;
            margin: 0px;
        }}
        #firmwareUploadPanel QScrollBar::handle:vertical {{
            background-color: #C0C0C0;
            border-radius: 6px;
            min-height: 20px;
        }}
        #firmwareUploadPanel QScrollBar::handle:vertical:hover {{
            background-color: #A0A0A0;
        }}
        #firmwareUploadPanel QScrollBar:horizontal {{
            background: transparent;
            height: 12px;
            border-radius: 6px;
            margin: 0px;
        }}
        #firmwareUploadPanel QScrollBar::handle:horizontal {{
            background-color: #C0C0C0;
            border-radius: 6px;
            min-width: 20px;
        }}
        #firmwareUploadPanel QScrollBar::handle:horizontal:hover {{
            background-color: #A0A0A0;
        }}
        #firmwareUploadPanel QScrollBar::add-line, #firmwareUploadPanel QScrollBar::sub-line {{
            width: 0px;
            height: 0px;
        }}
        #firmwareUploadPanel QScrollBar::add-page, #firmwareUploadPanel QScrollBar::sub-page {{
            background: none;
        }}
        #firmwareUploadPanel::handle:horizontal {{
            width: 5px;
            background-color: {dialog.BORDER_COLOR};
            border-radius: 2px;
            margin: 8px 0px;
        }}
        #firmwareUploadPanel QLabel {{
            color: {dialog.TEXT_COLOR};
            background: transparent;
            font-family: "{text_font}";
            font-size: 12px;
        }}
        #firmwareUploadPanel QGroupBox {{
            color: {dialog.TEXT_COLOR};
            background: transparent;
            border: 1px solid {dialog.BORDER_COLOR};
            border-radius: 8px;
            margin-top: 12px;
            font-family: "{text_font}";
            font-size: 12px;
            font-weight: 600;
        }}
        #firmwareUploadPanel QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0px 4px;
            color: {dialog_color};
            background-color: {accent_bg};
        }}
        #firmwareUploadPanel QCheckBox {{
            color: {dialog.TEXT_COLOR};
            background: transparent;
            font-family: "{text_font}";
            font-size: 12px;
        }}
        #firmwareUploadPanel QCheckBox::indicator {{
            width: 15px;
            height: 15px;
            border: 1px solid {dialog.BORDER_COLOR};
            border-radius: 4px;
            background-color: {dialog.DIALOG_BG_COLOR};
        }}
        #firmwareUploadPanel QCheckBox::indicator:checked {{
            background-color: {dialog_color};
            border-color: {dialog_color};
        }}
        #firmwareUploadPanel QLineEdit {{
            color: {dialog.TEXT_COLOR};
            background-color: {dialog.DIALOG_BG_COLOR};
            border: 1px solid {dialog.BORDER_COLOR};
            border-radius: 4px;
            padding: 3px 6px;
            font-family: "{text_font}";
            font-size: 12px;
            selection-background-color: {dialog_color};
            selection-color: {WHITE};
        }}
        #firmwareUploadPanel QComboBox {{
            color: {dialog.TEXT_COLOR};
            background-color: {dialog.DIALOG_BG_COLOR};
            border: 1px solid {dialog.BORDER_COLOR};
            border-radius: 4px;
            padding: 3px 6px;
            font-family: "{text_font}";
            font-size: 12px;
        }}
        #firmwareUploadPanel QComboBox QAbstractItemView {{
            color: {dialog.TEXT_COLOR};
            background-color: {dialog.DIALOG_BG_COLOR};
            selection-background-color: {dialog_color};
            selection-color: {WHITE};
        }}
        #firmwareUploadPanel QSpinBox {{
            color: {dialog.TEXT_COLOR};
            background-color: {dialog.DIALOG_BG_COLOR};
            border: 1px solid {dialog.BORDER_COLOR};
            border-radius: 4px;
            padding: 2px 4px;
            font-family: "{text_font}";
            font-size: 12px;
            selection-background-color: {dialog_color};
            selection-color: {WHITE};
        }}
        /* Slim up/down buttons in the dialog's border color; the arrows keep
           the native glyphs (no image needed). */
        #firmwareUploadPanel QSpinBox::up-button,
        #firmwareUploadPanel QSpinBox::down-button {{
            width: 16px;
            background-color: {accent_bg};
            border-left: 1px solid {dialog.BORDER_COLOR};
        }}
        #firmwareUploadPanel QSpinBox::up-button {{
            subcontrol-position: top right;
            border-top-right-radius: 4px;
        }}
        #firmwareUploadPanel QSpinBox::down-button {{
            subcontrol-position: bottom right;
            border-bottom-right-radius: 4px;
        }}
        #firmwareUploadPanel QSpinBox::up-button:hover,
        #firmwareUploadPanel QSpinBox::down-button:hover {{
            background-color: {dialog._lighten_color(dialog_color, 0.7)};
        }}
        #firmwareUploadPanel QPushButton {{
            color: {dialog.EXIT_BUTTON_TEXT_COLOR};
            background-color: {dialog.EXIT_BUTTON_COLOR};
            border: 1px solid {dialog.BORDER_COLOR};
            border-radius: 6px;
            padding: 4px 12px;
            font-family: "{text_font}";
            font-size: 12px;
        }}
        #firmwareUploadPanel QPushButton:hover {{
            background-color: {dialog._darken_color(dialog.EXIT_BUTTON_COLOR, 0.05)};
        }}
        #firmwareUploadPanel QToolButton {{
            color: {dialog.TEXT_COLOR};
            background: transparent;
            border: none;
            border-radius: 4px;
            padding: 2px;
        }}
        #firmwareUploadPanel QToolButton:hover {{
            background-color: rgba(0, 0, 0, 0.08);
        }}
        #firmwareUploadPanel QToolButton:checked {{
            color: {WHITE};
            background-color: {dialog_color};
        }}
    """
