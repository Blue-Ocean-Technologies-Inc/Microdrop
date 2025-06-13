# Imports:
from collections import defaultdict

# local
from ..utils.dmf_utils import SvgUtil
from microdrop_utils._logger import get_logger

# enthought
from traits.api import HasTraits, Int, Bool, Array, Float, Any, Dict, Str, Instance, Property, File, cached_property, List, observe

logger = get_logger(__name__)


class Electrode(HasTraits):
    """
    Electrode class for managing individual electrodes
    """

    #: Channel number
    channel = Int()

    #: NDArray path to electrode
    path = Array(dtype=Float, shape=(None, 2))

    #: State of the electrode (On or Off)
    _state = Bool(False)

    #: Property for state
    state = Property(Bool, observe='_state')

    # -------------- property trait handlers ----------------------

    def _get_state(self) -> Bool:
        return self._state

    def _set_state(self, state: Bool):
        if state != self._state and self.channel is not None:
            self._state = state
            logger.debug("State changed to %s for %s", self.state, self.channel)


class Electrodes(HasTraits):

    """
    Electrodes class for managing multiple electrodes
    """

    #: Dictionary of electrodes with keys being an electrode id and values being the electrode object
    _electrodes = Dict(Str, Electrode, desc="Dictionary of electrodes with keys being an electrode id and values "
                                            "being the electrode object")

    electrodes = Property(Dict(Str, Electrode), observe='_electrodes')

    svg_model = Instance(SvgUtil, allow_none=True, desc="Model for the SVG file if given")

    #: Properties of the contained electrode objects. Will update dynamically observing each electrode object traits.
    electrode_channels = Property(List(Int), observe='_electrodes:items:channel')
    electrode_states = Property(List(Bool), observe='_electrodes:items:state')

    #: Map of the unique channels found amongst the electrodes, and various electrode ids associated with them
    # Note that channel-electride_id is one-to-many! So there is meaningful difference in acting on one or the other
    channels_electrode_ids_map = Property(Dict(Int, List(Str)), observe='_electrodes')

    #: Map of the unique channels and their states, True means actuated.
    channels_states_map = Property(Dict(Int, Bool), observe='_electrodes:items:channel, _electrodes:items:state')

    # -------------------Magic methods ----------------------------------------------------------------------
    def __getitem__(self, item: Str) -> Electrode:
        return self._electrodes[item]

    def __setitem__(self, key, value):
        self._electrodes[key] = value

    def __iter__(self):
        return iter(self._electrodes.values())

    def __len__(self):
        return len(self._electrodes)

    # -------------------Trait Property getters and setters --------------------------------------------------
    def _get_electrodes(self) -> Dict(Str, Electrode):
        return self._electrodes

    def _set_electrodes(self, electrodes: Dict(Str, Electrode)):
        self._electrodes = electrodes

    @cached_property
    def _get_electrode_channels(self) -> List(Int):
        return [electrode.channel for electrode in self._electrodes.values()]

    def _get_electrode_states(self) -> List(Int):
        return [electrode.state for electrode in self._electrodes.values()]

    def _get_channels_states_map(self):
        return dict(zip(self.electrode_channels, self.electrode_states))

    @cached_property
    def _get_channels_electrode_ids_map(self):
        channel_to_electrode_ids_map = defaultdict(list)
        for electrode_id, electrode in self.electrodes.items():
            channel_to_electrode_ids_map[electrode.channel].append(electrode_id)

        logger.debug(f"Found new channel to electrode_ids mapping for each electrode")

        return channel_to_electrode_ids_map

    # -------------------Trait change handlers --------------------------------------------------
    def _svg_model_changed(self, new_model: SvgUtil):
        logger.debug(f"Setting new electrode models based on new svg model {new_model}")
        for k, v in new_model.electrodes.items():
            self.electrodes[k] = Electrode(channel=v['channel'], path=v['path'])

        logger.debug(f"Created electrodes from SVG file: {new_model.filename}")

    # -------------------Public methods --------------------------------------------------
    def set_electrodes_from_svg_file(self, svg_file: File):
        """
        Get electrodes from SVG file
        :param svg_file: Path to SVG file
        :return: Dictionary of electrodes
        """

        self.svg_model = SvgUtil(svg_file)
        logger.debug(f"Setting electrodes from SVG file: {svg_file}")