# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The order deferred plugins load in."""

# Microdrop utils imports.
from microdrop_utils.deferred_plugins import PRIORITY_FIRST, DeferredPlugin, load_order


def _specs(deferred_plugins):
    return [deferred.spec for deferred in deferred_plugins]


def test_load_order_keeps_the_declaration_order_without_priorities():
    declared = [DeferredPlugin(spec=f"package_{n}.plugin:Plugin") for n in range(3)]

    assert _specs(load_order(declared)) == _specs(declared)


def test_higher_priority_loads_first_and_ties_keep_their_order():
    service = DeferredPlugin(spec="service.plugin:ServicePlugin")
    viewer = DeferredPlugin(spec="viewer.plugin:ViewerPlugin")
    news = DeferredPlugin(spec="news.plugin:NewsPlugin", priority=PRIORITY_FIRST)
    service_ui = DeferredPlugin(spec="service_ui.plugin:ServiceUIPlugin")

    ordered = load_order([service, viewer, news, service_ui])

    assert _specs(ordered) == _specs([news, service, viewer, service_ui])
