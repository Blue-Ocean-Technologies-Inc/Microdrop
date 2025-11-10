from traits.api import HasTraits, Str, Range, Bool

class AlphaValue(HasTraits):
    """A class to represent an alpha value with a key."""
    key = Str()  # The key for the alpha value
    alpha = Range(0, 100, mode="spinner")  # The alpha value associated with the key
    visible = Bool(True)  # Whether the alpha value is visible in the UI