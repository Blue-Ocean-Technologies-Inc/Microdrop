# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pydantic contracts for the report-contribution logging topics.

``PROTOCOL_LOGGING_METADATA_CONTRIBUTION`` — flat mapping merged into the
run report's Metadata table.

``PROTOCOL_LOGGING_DATA_CONTRIBUTION`` — flat mapping appended as one data
row; numeric columns automatically flow into the report's Data Summary /
Data Trends sections and the persisted data files. ``step_idx`` /
``step_id`` keys override the logger's own step stamping when present.

Both messages are RootModels so they serialize to the flat JSON object
itself (no wrapper key) — the wire format the logging listener's lenient
handlers expect. Values are restricted to scalars: the Metadata table
renders them with str(), and data-row scalars are what the summary/trends
charting can aggregate. Publisher singletons live in
``pluggable_protocol_tree/consts.py`` next to the topic constants.
"""

from typing import Annotated

from pydantic import Field, RootModel

from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

ContributionScalar = str | int | float | bool | None
# Non-empty, flat (scalar-valued) mapping — an empty contribution is a
# caller bug, and nested values would defeat the report's aggregation.
FlatContributionMapping = Annotated[
    dict[str, ContributionScalar], Field(min_length=1)]


class ProtocolLoggingMetadataContributionMessage(
        RootModel[FlatContributionMapping]):
    """Key/value rows merged into the report's Metadata table."""


class ProtocolLoggingDataContributionMessage(
        RootModel[FlatContributionMapping]):
    """One contributed data row (column name -> value)."""


class ProtocolLoggingMetadataContributionPublisher(ValidatedTopicPublisher):
    """Validated publisher for ``PROTOCOL_LOGGING_METADATA_CONTRIBUTION``.

    ``publish({"Heater Firmware": "v2.1.0"})`` — the payload is the flat
    mapping itself.
    """
    validator_class = ProtocolLoggingMetadataContributionMessage


class ProtocolLoggingDataContributionPublisher(ValidatedTopicPublisher):
    """Validated publisher for ``PROTOCOL_LOGGING_DATA_CONTRIBUTION``.

    ``publish({"Temperature (C)": 64.5})`` — the payload is the flat
    mapping itself; include ``step_idx``/``step_id`` keys to override the
    logger's step stamping.
    """
    validator_class = ProtocolLoggingDataContributionMessage
