"""Constants for the Touch Assist tools (virtual numpad, keyboard,
mouse — floating helpers for touchscreen benches with no physical
mouse or keyboard)."""

PKG = '.'.join(__name__.split('.')[:-1])

#: The three tools, as the manager and the menu actions name them.
TOOL_NUMPAD = "numpad"
TOOL_KEYBOARD = "keyboard"
TOOL_MOUSE = "mouse"

#: Pad buttons are finger targets, not mouse targets.
PAD_KEY_SIZE_PX = 44
PAD_KEY_SPACING_PX = 4

#: Held-key auto-repeat (the numpad's ▲/▼): how long a hold waits
#: before repeating, then the repeat cadence — a spinbox climbs
#: steadily without racing away.
PAD_KEY_REPEAT_DELAY_MS = 400
PAD_KEY_REPEAT_INTERVAL_MS = 80

#: The virtual mouse's proportions: the body, the wheel strip inside
#: it, and the gap between the body and the crosshair pointer tip
#: floating above (the offset that keeps the finger off the target).
MOUSE_BODY_WIDTH_PX = 110
MOUSE_BODY_HEIGHT_PX = 150
MOUSE_WHEEL_WIDTH_PX = 26
MOUSE_TIP_GAP_PX = 14
MOUSE_TIP_SIZE_PX = 25

#: A press that travels less than this (px) is a tap (a click); more
#: is a drag that moves the mouse widget.
MOUSE_TAP_SLOP_PX = 8

#: Wheel-strip travel to wheel-notch conversion: one notch (120
#: angle-delta units) per this many pixels of finger travel.
MOUSE_WHEEL_PX_PER_NOTCH = 12
