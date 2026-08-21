"""Small color-representation converters shared across the app —
notably between the '#rrggbb' hex strings we persist in preferences
and the (r, g, b) float tuples TraitsUI's RGBColor trait uses."""


def hex_to_rgb(hex_color: str) -> tuple:
    """'#rrggbb' -> (r, g, b) floats in 0..1."""
    value = hex_color.lstrip("#")

    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_to_hex(rgb) -> str:
    """(r, g, b) floats in 0..1 -> '#rrggbb'."""
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)
