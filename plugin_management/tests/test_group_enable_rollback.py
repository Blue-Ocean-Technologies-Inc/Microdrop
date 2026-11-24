# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A plugin group is all or nothing: when one of its plugins fails to start,
the group is not marked loaded or persisted, every plugin it added is
withdrawn with its services, and the reason is recorded. Runs a real
Envisage application with fake plugins resolved from a synthetic manifest."""

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences
from envisage.api import SERVICE_OFFERS, Application, CorePlugin, Plugin, ServiceOffer
from traits.api import Interface, List

# Microdrop package imports.
from plugin_management import group_manager
from plugin_management.group_manager import PluginGroupManager
from plugin_management.manifest import manifest_from_dict

# Microdrop utils imports.
from microdrop_utils.isolating_plugin_manager import IsolatingPluginManager
from microdrop_utils.plugin_load_status import LOAD_FAILED, LOAD_LOADED


class IFirstService(Interface):
    """Service offered by the group's first plugin."""


class FirstPlugin(Plugin):
    id = "plugin_management.tests.first"

    service_offers = List(contributes_to=SERVICE_OFFERS)

    def _service_offers_default(self):
        return [ServiceOffer(protocol=IFirstService, factory=lambda **_: "first")]


class FailingPlugin(Plugin):
    id = "plugin_management.tests.failing"

    def start(self):
        raise RuntimeError("heater board not found")


_SPEC_PREFIX = "plugin_management.tests.test_group_enable_rollback"

MANIFEST = manifest_from_dict(
    {
        "schema_version": 1,
        "name": "rollback_device",
        "packages": ["plugin_management"],
        "groups": [
            {
                "name": "failing_group",
                "plugins": [
                    f"{_SPEC_PREFIX}:FirstPlugin",
                    f"{_SPEC_PREFIX}:FailingPlugin",
                ],
                "enabled_key": "plugin_group_enabled.failing_group",
            },
            {
                "name": "working_group",
                "plugins": [f"{_SPEC_PREFIX}:FirstPlugin"],
                "enabled_key": "plugin_group_enabled.working_group",
            },
            {
                "name": "unimportable_group",
                "plugins": [f"{_SPEC_PREFIX}:NoSuchPlugin"],
                "enabled_key": "plugin_group_enabled.unimportable_group",
            },
        ],
    }
)


@pytest.fixture(autouse=True)
def isolated_preferences(monkeypatch):
    """Keep enable from persisting flags into the REAL preferences file."""
    store = Preferences()
    monkeypatch.setattr(group_manager, "get_default_preferences", lambda: store)

    return store


@pytest.fixture
def application(tmp_path):
    application = Application(
        plugins=[CorePlugin()],
        plugin_manager=IsolatingPluginManager(),
        home=str(tmp_path / "home"),
        user_data=str(tmp_path / "data"),
    )
    application.start()

    return application


@pytest.fixture
def manager(monkeypatch, application):
    monkeypatch.setattr(
        group_manager.entry_point_discovery, "discover_entry_point_manifests", list
    )
    monkeypatch.setattr(group_manager, "BUILTIN_PLUGIN_GROUPS", ())

    manager = PluginGroupManager(load_status=application.plugin_manager.load_status)
    manager.register_manifest(MANIFEST, dist_name="rollback-device-plugin")

    return manager


def test_a_failing_plugin_unwinds_the_whole_group(
    application, manager, isolated_preferences
):
    group = manager.groups["failing_group"]

    manager.enable(application, "failing_group")

    assert not manager.is_loaded("failing_group")
    assert group.instances == []
    assert group.load_error == (
        "plugin_management.tests.failing: RuntimeError: heater board not found"
    )

    # Nothing of the group is left registered: neither plugin, nor the
    # service the plugin that did start offered.
    assert [plugin.id for plugin in application] == ["envisage.core"]
    assert application.get_service(IFirstService) is None

    # Not persisted as enabled.
    assert isolated_preferences.get(manager._flag_path(group)) is None

    # Only the failure keeps a record, with its traceback.
    status = manager.load_status
    record = status.get_record("plugin_management.tests.failing")

    assert record.state == LOAD_FAILED
    assert "Traceback" in record.traceback
    assert status.get_record("plugin_management.tests.first") is None


def test_a_working_group_records_its_plugins_and_disable_drops_them(
    application, manager
):
    manager.enable(application, "working_group")

    status = manager.load_status

    assert manager.is_loaded("working_group")
    assert manager.groups["working_group"].load_error == ""
    assert status.get_record("plugin_management.tests.first").state == LOAD_LOADED
    assert application.get_service(IFirstService) == "first"

    manager.disable(application, "working_group")

    assert status.get_record("plugin_management.tests.first") is None
    assert application.get_service(IFirstService) is None


def test_an_import_failure_is_recorded_and_cleared_on_the_next_attempt(
    monkeypatch, application, manager
):
    spec = f"{_SPEC_PREFIX}:NoSuchPlugin"

    manager.enable(application, "unimportable_group")

    record = manager.load_status.get_record(spec)

    assert not manager.is_loaded("unimportable_group")
    assert record.state == LOAD_FAILED
    assert record.error.startswith("AttributeError")
    assert manager.groups["unimportable_group"].load_error.startswith(spec)

    # The package gets fixed (e.g. reinstalled): the same spec now imports.
    monkeypatch.setitem(globals(), "NoSuchPlugin", FirstPlugin)
    manager.enable(application, "unimportable_group")

    assert manager.is_loaded("unimportable_group")
    assert manager.load_status.get_record(spec) is None
