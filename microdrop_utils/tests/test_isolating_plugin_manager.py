# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Launch-time failure isolation: one plugin raising in start() is recorded
and rolled back, and the rest still start; an essential one still fails the
launch. Runs real Envisage applications with fake plugins."""

# Third-party imports.
import pytest

# Enthought library imports.
from envisage.api import (
    SERVICE_OFFERS,
    Application,
    CorePlugin,
    ExtensionPoint,
    Plugin,
    ServiceOffer,
)
from traits.api import Interface, List

# Microdrop utils imports.
from microdrop_utils.isolating_plugin_manager import IsolatingPluginManager
from microdrop_utils.plugin_load_status import LOAD_FAILED, LOAD_LOADED

#: Extension point the fake consumer offers and the broken plugin contributes
#: to, standing in for task extensions, topic routes, status-bar icons, ...
WIDGETS = "test.widgets"


class IBrokenService(Interface):
    """Service offered by the broken plugin."""


class IGoodService(Interface):
    """Service offered by a plugin that starts."""


class ConsumerPlugin(Plugin):
    id = "test.consumer"

    widgets = ExtensionPoint(List, id=WIDGETS)


class GoodPlugin(Plugin):
    id = "test.good"

    service_offers = List(contributes_to=SERVICE_OFFERS)

    def _service_offers_default(self):
        return [ServiceOffer(protocol=IGoodService, factory=lambda **_: "good")]

    def start(self):
        self.started = True


class BrokenPlugin(Plugin):
    id = "test.broken"

    service_offers = List(contributes_to=SERVICE_OFFERS)
    widgets = List(contributes_to=WIDGETS)

    def _service_offers_default(self):
        return [ServiceOffer(protocol=IBrokenService, factory=lambda **_: "broken")]

    def _widgets_default(self):
        return ["broken widget"]

    def start(self):
        raise RuntimeError("cannot open the device")


class DependentPlugin(Plugin):
    """Needs the broken plugin's service, so it fails after it."""

    id = "test.dependent"

    def start(self):
        if self.application.get_service(IBrokenService) is None:
            raise LookupError("IBrokenService is not available")


class LaterPlugin(Plugin):
    id = "test.later"

    started = False

    def start(self):
        self.started = True


def _make_application(tmp_path, plugins, essential_plugin_ids=()):
    manager = IsolatingPluginManager(essential_plugin_ids=list(essential_plugin_ids))

    return Application(
        plugins=plugins,
        plugin_manager=manager,
        home=str(tmp_path / "home"),
        user_data=str(tmp_path / "data"),
    )


def test_a_failing_plugin_is_skipped_recorded_and_rolled_back(tmp_path):
    consumer, broken = ConsumerPlugin(), BrokenPlugin()
    dependent, later = DependentPlugin(), LaterPlugin()
    application = _make_application(
        tmp_path, [CorePlugin(), consumer, GoodPlugin(), broken, dependent, later]
    )
    started_events = []
    application.observe(started_events.append, "started")

    assert application.start()

    status = application.plugin_manager.load_status
    states = {record.plugin_id: record.state for record in status.records}

    assert states == {
        "envisage.core": LOAD_LOADED,
        "test.consumer": LOAD_LOADED,
        "test.good": LOAD_LOADED,
        "test.broken": LOAD_FAILED,
        "test.dependent": LOAD_FAILED,
        "test.later": LOAD_LOADED,
    }
    assert later.started
    assert len(started_events) == 1

    record = status.get_record("test.broken")

    assert record.error == "RuntimeError: cannot open the device"
    assert "Traceback" in record.traceback
    assert status.get_record("test.dependent").error.startswith("LookupError")

    # Rolled back: unregistered, its contributions and service offer gone,
    # while a started plugin's offer stays.
    assert application.get_plugin("test.broken") is None
    assert application.get_plugin("test.dependent") is None
    assert consumer.widgets == []
    assert application.get_service(IBrokenService) is None
    assert application.get_service(IGoodService) == "good"


def test_an_essential_plugin_failure_still_fails_the_launch(tmp_path):
    later = LaterPlugin()
    application = _make_application(
        tmp_path,
        [CorePlugin(), BrokenPlugin(), later],
        essential_plugin_ids=["test.broken"],
    )

    with pytest.raises(RuntimeError, match="cannot open the device"):
        application.start()

    record = application.plugin_manager.load_status.get_record("test.broken")

    assert record.state == LOAD_FAILED
    assert record.essential is True
    assert not later.started


def test_records_list_every_plugin_in_load_order(tmp_path):
    plugins = [CorePlugin(), GoodPlugin(), LaterPlugin()]
    application = _make_application(tmp_path, plugins)

    application.start()

    status = application.plugin_manager.load_status

    assert [record.plugin_id for record in status.records] == [
        plugin.id for plugin in plugins
    ]
    assert status.state == LOAD_LOADED
