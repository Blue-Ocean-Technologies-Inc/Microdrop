# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Constants for Touch mode: the number pad that edits spin boxes, and the
event filter that adapts widgets for fingers while the mode is on."""

# Microdrop style imports.
from microdrop_style.touch_style import TOUCH_TARGET_PX

PKG = ".".join(__name__.split(".")[:-1])

#: Side of a number-pad key, comfortably larger than the finger target.
NUMBER_PAD_KEY_PX = 64

#: Gap between number-pad keys, and the pad's inner margin.
NUMBER_PAD_SPACING_PX = 6
NUMBER_PAD_MARGIN_PX = 10

#: Height of the number pad's value display.
NUMBER_PAD_DISPLAY_PX = 64

#: Point size of the key digits and of the value display.
NUMBER_PAD_KEY_POINT_SIZE = 20
NUMBER_PAD_DISPLAY_POINT_SIZE = 26

#: Side of the number pad's close glyph.
NUMBER_PAD_CLOSE_ICON_PX = 20

#: Gap between the number pad and the field it edits.
NUMBER_PAD_FIELD_GAP_PX = 6

#: The most digits a typed value may hold; more is never a real setting.
NUMBER_ENTRY_MAX_DIGITS = 12

#: Text shown for a bound at or beyond the spin-box "unbounded" value.
UNBOUNDED_TEXT = "∞"

#: Narrowest a stepper can be: both buttons and a few digits between them.
#: A spin box held narrower in code keeps no stepper.
STEPPER_MIN_WIDTH_PX = 3 * TOUCH_TARGET_PX

#: Qt's QWIDGETSIZE_MAX: a maximum size at or above it was left free.
UNCONSTRAINED_SIZE_PX = (1 << 24) - 1

#: Dynamic property marking a spin box touch mode adapted, holding the
#: alignment to restore when touch mode is turned off.
ADAPTED_ALIGNMENT_PROPERTY = "_touch_mode_alignment"

#: Dynamic property holding the minimum width touch mode widened a spin box
#: from, to restore when touch mode is turned off.
ADAPTED_MIN_WIDTH_PROPERTY = "_touch_mode_minimum_width"

#: Dynamic property holding the maximum height touch mode held a spin box
#: to, to restore when touch mode is turned off.
ADAPTED_MAX_HEIGHT_PROPERTY = "_touch_mode_maximum_height"

#: Dynamic property marking a spin box touch mode made accelerated.
ADAPTED_ACCELERATION_PROPERTY = "_touch_mode_accelerated"

#: Dynamic property marking a cell editor whose number pad already opened,
#: so re-showing it (the view scrolling it back into sight) does not reopen.
PAD_OPENED_PROPERTY = "_touch_mode_pad_opened"

#### Help mode ##############################################################

#: Longest button or label text used as a help bubble's bold title.
HELP_TITLE_MAX_CHARS = 40

#: Font families whose button "text" is an icon ligature, never a title.
ICON_FONT_FAMILY_PREFIXES = ("Material",)

#: Help bubble: widest text column, arrow depth, gap to the control, and
#: how far above the touch point it stays so the finger never covers it.
HELP_BUBBLE_MAX_WIDTH_PX = 320
HELP_BUBBLE_ARROW_PX = 10
HELP_BUBBLE_GAP_PX = 4
HELP_BUBBLE_FINGER_CLEARANCE_PX = 40

#: Width of the accent outline around the control a bubble describes.
HELP_OUTLINE_PX = 3

#: How long a long-press help bubble stays up outside Help mode.
HELP_TRANSIENT_HIDE_MS = 6000

#: Bubble text for a control without any description.
HELP_NO_DESCRIPTION_TEXT = "No description yet."

#: Banner shown while Help mode is on.
HELP_BANNER_TEXT = "Help mode — touch anything to see what it does"

#: Tooltip of the Help-mode toggle.
HELP_TOGGLE_TOOLTIP = "Help mode: touch any control to read what it does"

#: Dynamic property marking the Help-mode controls (toggle, Done), whose
#: input Help mode lets through.
HELP_MODE_CONTROL_PROPERTY = "_help_mode_control"

#: Dynamic property marking a viewport whose flick scrolling Help mode
#: suspended, to grab again when it ends.
SUSPENDED_SCROLLER_PROPERTY = "_help_mode_suspended_scroller"

#: Dynamic property marking a viewport touch mode gave flick scrolling.
FLICK_SCROLLING_PROPERTY = "_touch_mode_flick_scrolling"
