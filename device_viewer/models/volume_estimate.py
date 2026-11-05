# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Live droplet volume estimate from the DropBot's capacitance reading.

The actuated electrodes read as a parallel sum of their liquid-covered and
filler-covered parts, so with the calibrated capacitances per unit area
``c_l`` (liquid) and ``c_f`` (filler) a reading ``C`` over actuated area
``A`` resolves to::

    covered_area = (C - c_f * A) / (c_l - c_f)
    volume       = covered_area * gap_height

The same model the Volume Threshold column inverts for its targets. Without
a filler calibration ``c_f`` counts as 0, i.e. ``covered_area = C / c_l``.
"""

# Enthought library imports.
from traits.api import Bool, Event, Float, HasTraits, Property, Str, Union, observe

# Local imports.
from ..consts import DEFAULT_GAP_HEIGHT_UM, UM_MM2_PER_UL, VOLUME_READOUT_NOISE_UL

#: Inputs every derived value depends on.
_INPUTS = (
    "capacitance_pf, actuated_area_mm2, liquid_capacitance_over_area, "
    "filler_capacitance_over_area"
)


class VolumeEstimateModel(HasTraits):
    """Covered area, volume and fill fraction of the actuated electrodes."""

    #: Latest total capacitance of the actuated electrodes, in pF.
    capacitance_pf = Float(0.0)

    #: Summed area of the actuated electrodes, in mm².
    actuated_area_mm2 = Float(0.0)

    #: Calibrated liquid-covered capacitance per area, in pF/mm²; None
    #: until measured (Calibration section, liquid button).
    liquid_capacitance_over_area = Union(None, Float)

    #: Calibrated filler-covered capacitance per area, in pF/mm²; None
    #: until measured, and then taken as 0.
    filler_capacitance_over_area = Union(None, Float)

    #: Gap between the plates the droplet fills, in µm.
    gap_um = Float(DEFAULT_GAP_HEIGHT_UM)

    #: Whether the inputs support an estimate at all.
    has_estimate = Property(Bool, observe=_INPUTS)

    #: Liquid-covered part of the actuated area, in mm².
    covered_area_mm2 = Property(Float, observe=_INPUTS)

    #: Droplet volume over the covered area, in µL.
    volume_ul = Property(Float, observe=f"{_INPUTS}, gap_um")

    #: Covered over actuated area; above 1 flags liquid outside the
    #: actuated set or a stale calibration.
    fill_fraction = Property(Float, observe=_INPUTS)

    #: Why there is no estimate, or "" when there is one.
    status_message = Property(Str, observe=_INPUTS)

    #: The readout's volume, µL: ``volume_ul`` as of the last change worth
    #: reporting, so capacitance noise does not flicker the display.
    shown_volume_ul = Float(0.0)

    #: The readout's fill fraction, snapshot with ``shown_volume_ul``.
    shown_fill_fraction = Float(0.0)

    #: The readout's covered area, mm², snapshot with ``shown_volume_ul``.
    shown_covered_area_mm2 = Float(0.0)

    #: The readout's status message, snapshot with ``shown_volume_ul``.
    shown_status_message = Str("Measure the liquid capacitance to calibrate.")

    #: Fires once per new readout snapshot, after all shown values are set.
    shown_values_updated = Event()

    # ------------------------- Observers ------------------------------

    @observe(f"{_INPUTS}, gap_um")
    def _update_shown_values(self, event):
        """Snapshot the derived values for the readout, skipping reading
        noise: a new capacitance counts only once it moves the volume by
        more than VOLUME_READOUT_NOISE_UL or changes the status. Area,
        calibration and gap changes are exact, so they always count."""
        is_reading_noise = (
            event.name == "capacitance_pf"
            and self.status_message == self.shown_status_message
            and abs(self.volume_ul - self.shown_volume_ul) <= VOLUME_READOUT_NOISE_UL
        )

        if is_reading_noise:
            return

        self.trait_set(
            shown_volume_ul=self.volume_ul,
            shown_fill_fraction=self.fill_fraction,
            shown_covered_area_mm2=self.covered_area_mm2,
            shown_status_message=self.status_message,
        )
        self.shown_values_updated = True

    # ------------------------- Properties ------------------------

    def _get_status_message(self):
        if self.liquid_capacitance_over_area is None:
            return "Measure the liquid capacitance to calibrate."

        if self.liquid_capacitance_over_area <= self._filler_per_area():
            return "Liquid calibration must exceed the filler calibration."

        if self.actuated_area_mm2 <= 0:
            return "No actuated electrodes."

        if self.capacitance_pf <= 0:
            return "No capacitance reading."

        return ""

    def _get_has_estimate(self):
        return not self.status_message

    def _get_covered_area_mm2(self):
        if not self.has_estimate:
            return 0.0

        filler_per_area = self._filler_per_area()
        excess_pf = self.capacitance_pf - filler_per_area * self.actuated_area_mm2
        covered_area = excess_pf / (self.liquid_capacitance_over_area - filler_per_area)

        # A reading under the filler baseline is noise, not negative liquid.
        return max(covered_area, 0.0)

    def _get_volume_ul(self):
        return self.covered_area_mm2 * self.gap_um / UM_MM2_PER_UL

    def _get_fill_fraction(self):
        if not self.has_estimate:
            return 0.0

        return self.covered_area_mm2 / self.actuated_area_mm2

    # ------------------------ Methods ---------------------------------

    def _filler_per_area(self):
        """The filler calibration, or 0 while it is unmeasured."""
        return self.filler_capacitance_over_area or 0.0
