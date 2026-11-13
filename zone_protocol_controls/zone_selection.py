# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure region selection for the Zone Target column (#965) — no Qt, no
Redis, no hardware.

Inputs are the device viewer's zones snapshot (``ZONES_KEY`` in app_globals,
see ``ZoneLayerManager.snapshot_for_app_globals``): ``{zone_id: {"name",
"color", "regions": [{"id", "electrode_ids", "channels"}, ...]}}``. Region
order is the manager's stored order (creation order), which is the order
the regions are checked in.

Channels come from the protocol's electrode-to-channel map — the same map
RoutesHandler actuates through — so the electrodes a region is sensed on are
exactly the ones it is actuated on. A region none of whose electrodes map to
a channel cannot be sensed, so it never matches either criterion.
"""

# Local imports.
from .consts import ZONE_CRITERIA, ZoneCriterion


def zone_regions(zones_snapshot, zone_id):
    """The regions of ``zone_id`` in check order, or None when the snapshot
    has no such zone type (deleted, renamed, or another device loaded)."""
    zone = (zones_snapshot or {}).get(zone_id)

    if zone is None:
        return None

    return list(zone.get("regions", []))


def region_channels(region, electrode_to_channel):
    """Sorted channels of the region's electrodes that the map knows."""
    channels = {
        electrode_to_channel[electrode_id]
        for electrode_id in region.get("electrode_ids", [])
        if electrode_to_channel.get(electrode_id) is not None
    }

    return sorted(int(channel) for channel in channels)


def zone_detection_channels(regions, electrode_to_channel):
    """Sorted union of the regions' channels — the droplet-detection request."""
    channels = set()

    for region in regions:
        channels.update(region_channels(region, electrode_to_channel))

    return sorted(channels)


def select_zone_region(regions, detected_channels, criterion, electrode_to_channel):
    """Return the first region, in check order, that meets ``criterion``.

    A region has a droplet when detection reported a droplet on any of its
    channels. Regions without a mapped channel are skipped. Returns None when
    no region meets the criterion.

    Raises
    ------
    ValueError
        ``criterion`` is not one of ``ZONE_CRITERIA``.
    """

    if criterion not in ZONE_CRITERIA:
        raise ValueError(f"Unknown zone criterion {criterion!r}")

    wants_droplet = criterion == ZoneCriterion.HAS_DROPLET
    detected = set(detected_channels)

    for region in regions:
        channels = region_channels(region, electrode_to_channel)

        if not channels:
            continue

        if (not detected.isdisjoint(channels)) == wants_droplet:
            return region

    return None
