"""Device-agnostic constants for the shared firmware-upload dialog."""

#: Separates "COM7" from its human-readable description in the port dropdown.
PORT_ENTRY_SEPARATOR = " — "

LOG_CONSOLE_FONT_FAMILY = "Consolas"

#: Shown in the read-only Device ID field until the board's whoami arrives
#: (matches the status panes' board_id_text "-" placeholder). Treated as
#: "no id known" when building the upload payload.
DEVICE_ID_PLACEHOLDER = "-"

#: Raspberry Pi Foundation's USB vendor id (the whole Pico family) — the port
#: dropdown lists Pico-vendor ports first.
PICO_USB_VENDOR_ID = 0x2E8A
