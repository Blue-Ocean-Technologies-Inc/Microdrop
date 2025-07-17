from traits.api import HasTraits, Str, Float

class AlphaValue(HasTraits):
    """A class to represent an alpha value with a key."""
    key = Str()  # The key for the alpha value
    alpha = Float()  # The alpha value associated with the key

    def __init__(self, value: str, alpha: float):
        self.value = value
        self.alpha = alpha