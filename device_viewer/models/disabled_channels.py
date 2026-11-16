# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The user-disabled channels, mirrored to app_globals so every hardware
backend can refuse them.

The device viewer writes the set; each backend reads it while handling an
electrode state change or a droplet detection request. Backends import the
mirror through ``device_viewer.consts`` (``user_disabled_channels_mirror``),
never from this module."""

# Third-party imports.
from redis.exceptions import RedisError

# Enthought library imports.
from traits.api import HasTraits, Str

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()


def split_disabled_channels(channels, disabled_channels):
    """Split ``channels`` into the ones to keep and the disabled ones.

    Returns
    -------
    tuple of list of int
        The kept channels and the dropped channels, each sorted.
    """

    requested = set(channels)
    dropped = requested & set(disabled_channels)

    return sorted(requested - dropped), sorted(dropped)


class UserDisabledChannelsMirror(HasTraits):
    """Reads and writes the user-disabled channel list in app_globals."""

    #: The app_globals key holding the sorted channel list. Set at
    #: construction to device_viewer.consts.USER_DISABLED_CHANNELS_KEY —
    #: consts imports this module, so it can't import the constant back.
    globals_key = Str()

    def write(self, channels):
        """Mirror ``channels`` as the user-disabled set."""
        try:
            app_globals[self.globals_key] = sorted(channels)

        except RedisError as error:
            # A headless model (tests, demos) has no Redis; the app does.
            logger.error(f"Could not mirror the user-disabled channels: {error}")

            return

        logger.debug(f"App Globals Update: {self.globals_key}: {sorted(channels)}")

    def read(self):
        """Return the user-disabled channels as a set."""
        return set(app_globals.get(self.globals_key) or [])

    def drop_from(self, channels, purpose, also_disabled=()):
        """Return ``channels`` without the user-disabled ones (and
        ``also_disabled``), sorted, logging what was dropped for ``purpose``.

        An empty result means every requested channel is disabled — callers
        must not mistake it for an "all channels" request.
        """

        disabled_channels = self.read() | set(also_disabled)
        kept, dropped = split_disabled_channels(channels, disabled_channels)

        if dropped:
            logger.info(f"{purpose}: dropped disabled channels {dropped}")

        return kept
