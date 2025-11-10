from traits.has_traits import HasTraits
from traits.trait_types import Bool, Float


class ZStageModel(HasTraits):
    """Holds the raw state of the zstage device."""
    status = Bool(False)
    position = Float(0.0)  # Position in mm
