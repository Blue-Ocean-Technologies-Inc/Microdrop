"""Demo: changelog markdown rendering with a mock changelog.

Exercises the two changelog UX paths without touching the real
CHANGELOG.md or the application-home cache:

1. ``changelog_sections_added_since`` — the What's New delta between a
   "previous run" changelog and the current one (printed to stdout and
   shown in the styled information dialog, like startup does).
2. ``markdown_text_to_html`` + ``WebViewDialog`` — the full changelog
   rendered as HTML (the Help -> Changelog... path).

The mock changelog deliberately includes the hostile cases:
- tag-like tokens (``PID_<HEATER>``, ``Dict<str, int>``) that used to be
  parsed as unclosed inline HTML and swallow the rest of the document,
- ``[text](url)`` links, ``<https://...>`` autolinks and ``<mailto:...>``,
- a LAST LINE MARKER so a cut-off render is obvious at a glance.

Run (no Redis needed):
    pixi run python examples/demos/mock_changelog_render_demo.py
"""

import sys

# QtWebEngine must be imported before the QApplication is created.
from microdrop_application.dialogs.web_view_dialog import WebViewDialog
from PySide6.QtWidgets import QApplication

from microdrop_utils.markdown_helpers import changelog_sections_added_since
from microdrop_utils.pyside_helpers import markdown_text_to_html

MOCK_PREVIOUS_CHANGELOG = """\
## v1.1.0 (2026-07-06)

### Feat

- **heater_ui**: per-heater status readouts driven by PID_<HEATER> frames
- **protocol-tree**: typed step params as Dict<str, int> maps

### Fix

- **logger**: write log files as utf-8

## v1.0.0 (2026-07-06)

### Feat

- initial release, see [Microdrop](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop)

LAST LINE MARKER — if you can't scroll down to this line, rendering is cut off.
"""

MOCK_CHANGELOG = """\
## v1.2.0 (2026-07-21)

### Feat

- **heater_ui**: retune PID_<HEATER> frames, see <https://sci-bots.com>
- **user_help**: Changelog viewer + What's New dialog
- **support**: reach us at <mailto:support@sci-bots.com>

### Fix

- **dialogs**: render markdown with tag-like tokens such as List<Path>

""" + MOCK_PREVIOUS_CHANGELOG


def main():
    app = QApplication(sys.argv)

    whats_new_delta = changelog_sections_added_since(
        MOCK_PREVIOUS_CHANGELOG, MOCK_CHANGELOG)
    print("=== What's New delta (should be only the v1.2.0 section) ===")
    print(whats_new_delta)

    from microdrop_application.dialogs.pyface_wrapper import information
    information(None, markdown_text_to_html(whats_new_delta),
                title="What's New?", cancel=False)

    dialog = WebViewDialog(html_content=markdown_text_to_html(MOCK_CHANGELOG),
                           title="Mock Changelog — scroll to the LAST LINE MARKER",
                           open_links_externally=True)
    dialog.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
