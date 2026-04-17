from traits.has_traits import HasTraits
from traits.trait_types import Str, Bool, Float


class PeripheralModel(HasTraits):
    """Holds the raw state of the zstage device."""
    device_name = Str("ZStage")
    status = Bool(False)
    position = Float(0.0)  # Position in mm
    realtime_mode = Bool(False)
    # True once a connection search has been requested (by button or menu action) this session.
    search_requested = Bool(False)
