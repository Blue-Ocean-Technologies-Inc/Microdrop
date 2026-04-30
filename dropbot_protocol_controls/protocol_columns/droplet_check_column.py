"""PPT-8: per-step droplet check column. After a step's phases complete,
the handler publishes DETECT_DROPLETS for the channels we expect droplets
on, awaits the backend's DROPLETS_DETECTED reply, and on missing channels
drives a UI confirm dialog via topic round-trip.

This file holds the pure helper, the model/view/factory, and the handler.
Splitting them across files would just spread cohesive logic; see PPT-7's
force_column.py for the same single-file convention.
"""

from logger.logger_service import get_logger

logger = get_logger(__name__)


def expected_channels_for_step(row, electrode_to_channel: dict) -> list:
    """Channels we expect droplets on after this step's phases finish.

    Mirrors legacy _get_expected_droplet_channels
    (protocol_runner_controller.py:1763): the union of
    (statically activated electrodes) and (the LAST electrode of each
    route — that's where the droplet ends up). Returns a sorted unique
    list of int channels. Unknown electrode IDs are silently dropped
    rather than raising — same behavior as legacy.
    """
    expected = set()
    for eid in (row.activated_electrodes or []):
        ch = electrode_to_channel.get(eid)
        if ch is not None:
            expected.add(int(ch))
    for route in (row.routes or []):
        if route:
            ch = electrode_to_channel.get(route[-1])
            if ch is not None:
                expected.add(int(ch))
    return sorted(expected)


from traits.api import Bool, Str

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView

from ..consts import (
    DROPLET_CHECK_DECISION_REQUEST,
    DROPLET_CHECK_DECISION_RESPONSE,
)
from dropbot_controller.consts import DETECT_DROPLETS, DROPLETS_DETECTED


class DropletCheckColumnModel(BaseColumnModel):
    """Per-step Bool: 'verify expected droplets after this step's phases'.
    Default True; user can disable per-step via header right-click on the
    hidden column."""

    col_id        = Str("check_droplets")
    col_name      = Str("Check Droplets")
    default_value = Bool(True)

    def trait_for_row(self):
        return Bool(True)
    # serialize / deserialize / get_value / set_value: BaseColumnModel
    # defaults are correct (Bool is JSON-native).


class DropletCheckColumnView(CheckboxColumnView):
    """Hidden by default — surfaces via header right-click. Same posture
    as PPT-3's trail/loop knob columns."""

    renders_on_group  = False
    hidden_by_default = True


class DropletCheckHandler(BaseColumnHandler):
    """Skeleton — Tasks 4–7 fill in on_post_step body."""

    priority        = 80
    wait_for_topics = [DROPLETS_DETECTED, DROPLET_CHECK_DECISION_RESPONSE]

    def on_post_step(self, row, ctx):
        # Body added in Tasks 4–7. Empty here so column-shape tests
        # (Task 3) can run without pulling in handler integration tests.
        return None


def make_droplet_check_column() -> Column:
    return Column(
        model   = DropletCheckColumnModel(),
        view    = DropletCheckColumnView(),
        handler = DropletCheckHandler(),
    )
