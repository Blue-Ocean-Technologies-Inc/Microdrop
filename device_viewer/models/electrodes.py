# Imports:
from collections import defaultdict

# local
from ..utils.dmf_utils import SvgUtil
from microdrop_utils._logger import get_logger

# enthought
from traits.api import HasTraits, Int, Bool, Array, Float, String, Dict, Str, Instance, Property, File, cached_property, List, observe

logger = get_logger(__name__)


class Electrode(HasTraits):
    """
    Electrode class for managing individual electrodes
    """

    #: Channel number
    channel = Instance(int, allow_none=True) # Int() doesn't seem to follow allow_none for some reason

    #: Electrode id
    id = String()

    #: NDArray path to electrode
    path = Array(dtype=Float, shape=(None, 2))

    #: Electrode area in mm^2
    area_scaled = Float(allow_none=True)


class Electrodes(HasTraits):

    """
    Electrodes class for managing multiple electrodes
    """

    #: Dictionary of electrodes with keys being an electrode id and values being the electrode object
    electrodes = Dict(Str, Electrode, desc="Dictionary of electrodes with keys being an electrode id and values "
                                            "being the electrode object")
    electrode_editing = Instance(Electrode)

    svg_model = Instance(SvgUtil, allow_none=True, desc="Model for the SVG file if given")

    #: Map of the unique channels found amongst the electrodes, and various electrode ids associated with them
    # Note that channel-electrode_id is one-to-many! So there is meaningful difference in acting on one or the other
    electrode_ids_channels_map = Property(Dict(Str, Int), observe='electrodes.items.channel')
    channels_electrode_ids_map = Property(Dict(Int, List(Str)), observe='electrode_ids_channels_map')

    #: Map of the unique channels and their states, True means actuated, anything else means not actuated
    channels_states_map = Dict(Int, Bool, {})

    #: Map of electrode_areas
    electrode_ids_areas_scaled_map = Property(Dict(Str, Float), observe=['electrodes.items.channel', 'svg_model.area_scale'])
    #: Map of channel areas
    channel_electrode_areas_scaled_map = Property(Dict(Int, Float), observe='electrode_ids_areas_scaled_map')

    #: Flag indicating electrode areas are being updated in bulk (true on init).
    # If False: change made on single electrode only.
    _is_bulk_updating_electrode_areas = Bool(True)


    # ------------------- Magic methods ----------------------------------------------------------------------
    def __getitem__(self, item: Str) -> Electrode:
        return self.electrodes[item]

    def __setitem__(self, key, value):
        self.electrodes[key] = value

    def __iter__(self):
        return iter(self.electrodes.values())

    def __len__(self):
        return len(self.electrodes)

    # -------------------Trait Property getters and setters --------------------------------------------------

    @cached_property
    def _get_electrode_ids_channels_map(self):
        """
        Creates a map from each electrode ID to its corresponding channel.
        This is the base property that iterates through the raw data.
        """
        logger.debug("Building electrode_id -> channel map...")
        electrode_ids_channels_map = {}
        for electrode_id, electrode in self.electrodes.items():
            electrode_ids_channels_map[electrode_id] = electrode.channel

        return electrode_ids_channels_map

    @cached_property
    def _get_channels_electrode_ids_map(self):
        """
        Creates an inverted map from each channel to a list of its electrode IDs.
        This property depends on and reuses the result from the first property.
        """
        logger.debug("Building channel -> electrode_ids map by inverting the first map...")
        channel_to_electrode_ids_map = defaultdict(list)

        # Call the other cached_property to get the data
        for electrode_id, channel in self.electrode_ids_channels_map.items():
            channel_to_electrode_ids_map[channel].append(electrode_id)

        return channel_to_electrode_ids_map


    @cached_property
    def _get_electrode_ids_areas_scaled_map(self) -> dict[str, float]:
        """
        Get the areas of all electrodes in mm^2
        :return: Dictionary of electrode id to area in mm^2
        """
        if self.svg_model is not None:
            areas = {}
            for electrode_id, area in self.svg_model.electrode_areas.items():
                areas[electrode_id] = area * self.svg_model.area_scale
            return areas
        return {}

    @cached_property
    def _get_channel_electrode_areas_scaled_map(self):
        """
        Get the areas of all electrode area in mm^2 affected by each channel:
        I.e. If a channel maps to multiple electrode_ids, sum areas and map to channel.

        :return: Dictionary of channel to area in mm^2
        """
        if self.svg_model is not None:
            channel_electrode_areas_map = {}

            # We can iterate over the electrode ids for each channel
            for channel, electrode_ids in self.channels_electrode_ids_map.items():
                # Aggregate the electrode_ids using their area values
                total_area_scaled = sum([self.electrode_ids_areas_scaled_map[electrode_id] for electrode_id in electrode_ids])

                # Set channel id scaled area
                channel_electrode_areas_map[channel] = total_area_scaled

            return channel_electrode_areas_map

    # -------------------Trait change handlers --------------------------------------------------
    def _svg_model_changed(self, new_model: SvgUtil):
        logger.debug(f"Setting new electrode models based on new svg model {new_model}")
        self.electrodes.clear()
        new_electrodes = {}
        for k, v in new_model.electrodes.items():
            new_electrodes[k] = Electrode(channel=v['channel'], path=v['path'], id=k)
        
        # self.electrode_scale = new_model.pixel_scale
        self.electrodes.update(new_electrodes) # Single update to model = single draw

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
    
    def reset_electrode_states(self):
        self.channels_states_map.clear()
        self.electrode_editing = None

    def any_electrode_on(self) -> bool:
        """
        Check if any electrode is on
        :return: True if any electrode is on, False otherwise
        """
        return any(self.channels_states_map.values())

    def get_activated_electrode_area_mm2(self) -> float | None:
        """
        Get the areas of all activated electrodes in mm^2
        :return: Dictionary of electrode id to area in mm^2
        """
        if self.svg_model is not None:
            total_area = 0.0
            for electrode_id, channel in self.electrode_ids_channels_map.items():
                if self.channels_states_map.get(channel, False):
                    area = self.svg_model.electrode_areas.get(electrode_id, 0)
                    total_area += area * (self.svg_model.area_scale ** 2)
            return total_area
        return None

    #### Observer methods ######
    @observe('electrode_ids_areas_scaled_map')
    def update_electrode_areas(self, event):
        if event.new:

            self._is_bulk_updating_electrode_areas = True
            try:
                for electrode_id, electrode in self.electrodes.items():
                    electrode.area_scaled = event.new[electrode_id]

            finally:
                self._is_bulk_updating_electrode_areas = False

    @observe('electrodes.items.area_scaled')
    def electrode_area_scaled_changed(self, event):
        """
        Handle cases when the area information is changed at the electrode level post initialization using the
        svg model data.
        """

        # if the previous value is 0.0, then this is just the initialization of this value by the
        # get_electrode_ids_areas_scaled_map method using the svg model data.
        # If not, then it is a post init modification of the electrode model area information.
        if not self._is_bulk_updating_electrode_areas:
            electrode_id = event.object.id
            self.electrode_ids_areas_scaled_map[electrode_id] = event.new

            # find channel affected by this electrode.
            channel_affected = self.electrode_ids_channels_map[electrode_id]
            # apply change in area to this channel's area
            area_change = event.new - event.old
            self.channel_electrode_areas_scaled_map[channel_affected] += area_change