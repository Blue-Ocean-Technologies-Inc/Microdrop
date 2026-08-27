# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tree-level conftest. Pre-wires the dramatiq broker so the actors and
Redis-dependent tests added in Tasks 3-9 land on the same broker
configuration. Currently a no-op for the existing plugin-shell tests
(no actors registered yet); kept up-front to mirror PPT-4's conftest
and avoid a later cross-cutting test-infra change."""

from microdrop_utils.broker_server_helpers import configure_dramatiq_broker

configure_dramatiq_broker()
