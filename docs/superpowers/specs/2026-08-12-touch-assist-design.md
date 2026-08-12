# Touch Assist: virtual mouse, numpad, keyboard (design)

Date: 2026-08-12
Branch: `feat/touchscreen-input-assist`

## Problem

On a touchscreen bench setup there is no mouse or keyboard: nothing
to scroll with, right-click with, or type numbers and names into.
Microdrop's panes assume all three.

## Decision

Three independent floating tools, each summoned from a **Tools →
Touch Assist** submenu of checkbox actions — Virtual Numpad, Virtual
Keyboard, Virtual Mouse. No mode switch, no focus detection, no
per-widget wiring: the user decides what is on screen. Checked
states persist in `MicrodropPreferences`, so the tools come back as
they were left.

All three live in a new `microdrop_application/touch_assist/`
subpackage (application chrome, like the canvas background — not a
hardware plugin): `virtual_mouse.py`, `input_pads.py`,
`manager.py`. Widgets are styled with `microdrop_style` helpers.

## Components

### Menu and manager

- Three pyface toggle `Action`s (the `AdvancedModeAction` pattern)
  in a "Touch Assist" menu group under Tools, each flipping one Bool
  on `MicrodropPreferences`: `touch_virtual_numpad`,
  `touch_virtual_keyboard`, `touch_virtual_mouse` (all False by
  default).
- `TouchAssistManager` (singleton owned by the application task):
  observes the three preferences, creates each widget lazily on
  first show, shows/hides on toggle, and tears all three down on
  application exit. No dramatiq/Redis involvement — purely
  frontend-local.

### Key delivery (numpad + keyboard)

Both pads deliver input as synthesized `QKeyEvent`s
(press + release) posted to `QApplication.focusWidget()` — the
widget the user last tapped. This works unmodified with TraitsUI
editors, plugin panes, and dialogs. Guards: no focus widget → the
tap does nothing; the pads themselves are
`Qt.WindowDoesNotAcceptFocus` tool windows, so tapping keys never
steals the caret from the target field.

Both are frameless, always-on-top, movable by a drag-handle strip,
and closable from their corner (which unchecks the menu item).

### Virtual Numpad (`input_pads.py`)

Digits 0-9, minus sign, decimal point, Backspace, Up/Down arrows
(spinbox stepping), Enter, and a close button. Large touch-target
buttons.

### Virtual Keyboard (`input_pads.py`)

Compact QWERTY: letter rows, digit row, Space, Backspace, Enter,
close button, and three one-shot latching modifiers — Shift, Ctrl,
Alt. Each arms the NEXT key and then releases: Shift uppercases
letters and turns the digit row into its symbols; Ctrl/Alt send a
shortcut chord (Ctrl+A, Ctrl+C…) with no typed text. No further
symbols layer in v1.

### Virtual Mouse (`virtual_mouse.py`)

A frameless, always-on-top widget painted as a mouse — left and
right button zones with a wheel strip between them — plus a visible
**pointer tip (crosshair) fixed above the body**. Dragging the body
moves the whole widget, so the pointer aims precisely while the
finger stays below the target (the classic assistive offset).

- Left/right button tap → synthesized `QMouseEvent` press+release
  at the pointer tip: target found with `QApplication.widgetAt()`,
  coordinates mapped to it, events sent with the matching button.
  Two quick left taps read as a double-click through Qt's normal
  timing. Right-click opens context menus.
- Wheel strip vertical drag → `QWheelEvent`s at the pointer tip,
  angle delta proportional to finger travel, so whatever is under
  the pointer scrolls as with a real wheel.
- Scope is the Microdrop application only (Qt event synthesis, not
  an OS-level mouse).
- A **Hold pill** on the body latches a left press at the tip:
  while lit, dragging the body streams MouseMove events (left
  button down) to the held widget — sliders, ROI drags and text
  selection in slow motion. Tapping Hold again, or the L zone,
  releases at the current tip position; closing the widget releases
  first.
- Guards: no widget under the tip → the tap does nothing; targets
  re-resolved per event so a widget destroyed mid-gesture cannot be
  dereferenced.

## Error handling

Every synthesized event re-checks its target for `None` first. The
manager tolerates a missing main window (headless tests) by simply
not showing widgets.

## Testing

User verifies through the GUI (per their call — this is UI work).
The widgets are self-contained and take injected targets, so unit
tests can come later if wanted.
