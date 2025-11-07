from PySide6.QtGui import QColor


def get_qcolor_lighter_percent_from_factor(color: 'QColor', lightness_scale: float):
    """
    Calculates the integer percentage for QColor.lighter()
    based on a 0.0-1.0 scale.

    color: QColor
    lightness_scale: float (0.0 to 1.0)
        0.0 means same lightness as color (returns 100).
        1.0 means fully white (returns 100 / lightnessF).
    """

    # 1. Define the start of our scale (100% = no change)
    min_lightness_percent = 100.0

    current_lightness = color.lightness()

    # 2. Define the end of our scale (the factor to get to white)
    if current_lightness == 0:
        # Handle pure black:
        h, s, l, a = color.getHsl()
        color.setHsl(h, s, 1, a)

    # The factor needed to reach 1.0 lightness (white)
    # e.g., if lightnessF is 0.5 (gray), we need a factor of
    # 1.0 / 0.5 = 2.0, which is 200%.
    max_lightness_percent = int(255 * 100 / current_lightness)
    for n in range(max_lightness_percent, max_lightness_percent + 10000):
        if color.lighter(n).lightness() == 255:
            max_lightness_percent = n
            break

    # 3. Linearly interpolate between min and max
    lightness_percentage = min_lightness_percent + (max_lightness_percent - min_lightness_percent) * lightness_scale

    # QColor.lighter() expects an integer
    return int(lightness_percentage)