# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The live volume estimate inverts the calibrated capacitance model."""

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import HasTraits, Instance, List, observe

# Microdrop package imports.
from device_viewer.models.volume_estimate import VolumeEstimateModel


def _calibrated(**traits):
    """An estimate over 4 mm² calibrated at 2.0 liquid / 0.5 filler pF/mm²."""
    defaults = dict(
        actuated_area_mm2=4.0,
        liquid_capacitance_over_area=2.0,
        filler_capacitance_over_area=0.5,
        gap_um=200.0,
    )
    defaults.update(traits)

    return VolumeEstimateModel(**defaults)


def test_fully_covered_reading_fills_the_actuated_area():
    estimate = _calibrated(capacitance_pf=8.0)

    assert estimate.has_estimate
    assert estimate.covered_area_mm2 == pytest.approx(4.0)
    assert estimate.fill_fraction == pytest.approx(1.0)
    assert estimate.volume_ul == pytest.approx(0.8)


def test_half_covered_reading_counts_the_filler_baseline():
    # Half liquid, half filler: 2 mm² * 2.0 + 2 mm² * 0.5 = 5 pF.
    estimate = _calibrated(capacitance_pf=5.0)

    assert estimate.covered_area_mm2 == pytest.approx(2.0)
    assert estimate.fill_fraction == pytest.approx(0.5)
    assert estimate.volume_ul == pytest.approx(0.4)


def test_unmeasured_filler_counts_as_zero():
    estimate = _calibrated(capacitance_pf=4.0, filler_capacitance_over_area=None)

    assert estimate.covered_area_mm2 == pytest.approx(2.0)


def test_reading_below_the_filler_baseline_clamps_to_zero():
    estimate = _calibrated(capacitance_pf=1.0)

    assert estimate.covered_area_mm2 == 0.0
    assert estimate.volume_ul == 0.0


def test_volume_follows_the_gap():
    estimate = _calibrated(capacitance_pf=8.0)

    estimate.gap_um = 100.0

    assert estimate.volume_ul == pytest.approx(0.4)


@pytest.mark.parametrize(
    "traits",
    [
        dict(capacitance_pf=0.0),
        dict(capacitance_pf=8.0, actuated_area_mm2=0.0),
        dict(capacitance_pf=8.0, liquid_capacitance_over_area=None),
        dict(capacitance_pf=8.0, liquid_capacitance_over_area=0.5),
    ],
)
def test_missing_inputs_give_no_estimate_and_say_why(traits):
    estimate = _calibrated(**traits)

    assert not estimate.has_estimate
    assert estimate.status_message
    assert estimate.covered_area_mm2 == 0.0
    assert estimate.fill_fraction == 0.0


class _VolumeRecorder(HasTraits):
    """Records every volume the estimate notifies, as the sidebar sees them."""

    estimate = Instance(VolumeEstimateModel)

    volumes = List()

    @observe("estimate:volume_ul")
    def _record_volume(self, event):
        self.volumes.append(event.new)


def test_derived_values_notify_on_input_change():
    recorder = _VolumeRecorder(estimate=_calibrated())

    recorder.estimate.capacitance_pf = 8.0

    assert recorder.volumes[-1] == pytest.approx(0.8)
