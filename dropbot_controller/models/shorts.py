"""Message schema for the SHORTS_DETECTED topic.

The dropbot controller owns the topic; the frontend task and the mock
controller import these as the pub/sub payload contract (sanctioned
cross-plugin message-schema import).
"""
from pydantic import BaseModel, StrictBool, StrictInt

from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

from logger.logger_service import get_logger
logger = get_logger(__name__)


class ShortsDetectedSignal(BaseModel):
    """Payload for a shorts-detected signal.

    Attributes
    ----------
    shorted_channels : list[int]
        Channel numbers reported as shorted. Empty means no shorts were
        found.
    show_window : bool
        Whether the frontend must surface a dialog even when
        ``shorted_channels`` is empty. Set by publishers that act on an
        explicit user request (a detect-shorts request, the shorts self
        test), so the user always gets an answer. Spontaneous hardware
        signals leave it False, letting a no-shorts result fall back to
        the user's suppress-no-shorts preference.
    """
    shorted_channels: list[StrictInt] = []
    show_window: StrictBool = False


class ShortsDetectedPublisher(ValidatedTopicPublisher):
    """Validated publisher for the ``SHORTS_DETECTED`` topic."""
    validator_class = ShortsDetectedSignal

    def publish(self, shorted_channels, show_window: bool = False, **kwargs):
        """Construct the payload from the shorted channels and the forced
        show-window flag.

        `shorted_channels` values are coerced to `int` because the DropBot
        proxy reports them as numpy integers, which StrictInt rejects.
        """
        logger.info(f"ShortsDetectedPublisher: {shorted_channels}")
        super().publish({
            "shorted_channels": [int(channel) for channel in shorted_channels],
            "show_window": show_window,
        }, **kwargs)
