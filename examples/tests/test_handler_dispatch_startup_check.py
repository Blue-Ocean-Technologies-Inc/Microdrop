# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""
Repo-wide audit for issue #617: reflective message-handler dispatch is
resolved by name at message time (frontend `_on_{topic}_triggered()`,
backend `on_{sub_topic}_request()` / `on_{sub_topic}_signal()`), so a typo
in a handler name or a renamed topic constant used to produce no error --
the message would arrive and silently match nothing.

`microdrop_utils.dramatiq_controller_base.assert_handlers_exist_for_topics`
is the startup check that catches this: given a listener's subscribed
topics and either the default `_on_{topic}_triggered` pattern or a
controller's own resolver, it verifies every non-wildcard topic maps to a
real, callable handler method.

This module IS the repo-wide audit the check is meant to run against: for
every plugin's ACTOR_TOPIC_DICT, it calls assert_handlers_exist_for_topics
against the real controller/handler class (no instantiation needed --
methods are attributes of the class itself), so a future typo anywhere in
this list fails this test the same way it would fail at app start.

Plugins using a hand-written, non-reflective listener_actor_routine (e.g.
dropbot_tools_menu's explicit if/elif chain, pluggable_protocol_tree's two
listeners, dropbot_protocol_controls' droplet-check-decision listener) are
out of scope: they don't use `_on_{topic}_triggered` / `on_..._request`
dispatch, so this check cannot and does not apply to them.
"""

import pytest

from microdrop_utils.dramatiq_controller_base import assert_handlers_exist_for_topics

# ---------------------------------------------------------------------------
# Unit tests for the shared check machinery itself
# ---------------------------------------------------------------------------


class _FakeHandlers:
    def _on_known_triggered(self, message):
        pass

    def _on_known_request(self, message):
        pass


def test_wildcard_topics_are_skipped():
    # A wildcard-only topic list has nothing to resolve; no methods needed.
    assert_handlers_exist_for_topics(_FakeHandlers(), ["dropbot/requests/#", "a/+/b"])


def test_missing_handler_raises_by_default():
    with pytest.raises(AttributeError, match="typo_topic.*_on_typo_topic_triggered"):
        assert_handlers_exist_for_topics(_FakeHandlers(), ["ui/typo_topic"])


def test_missing_handler_logs_instead_of_raising_when_asked(caplog):
    assert_handlers_exist_for_topics(
        _FakeHandlers(), ["ui/typo_topic"], raise_on_missing=False
    )
    assert "typo_topic" in caplog.text


def test_existing_handler_passes():
    assert_handlers_exist_for_topics(_FakeHandlers(), ["ui/known"])


def test_custom_pattern_is_used():
    assert_handlers_exist_for_topics(
        _FakeHandlers(), ["ui/known"], handler_name_pattern="_on_{topic}_request"
    )


def test_custom_resolver_none_skips_topic():
    # A resolver returning None (e.g. a pure side-effect topic) is not an error.
    assert_handlers_exist_for_topics(
        _FakeHandlers(), ["ui/anything"], handler_name_resolver=lambda topic: None
    )


def test_custom_resolver_missing_handler_raises():
    with pytest.raises(AttributeError, match="on_missing_signal"):
        assert_handlers_exist_for_topics(
            _FakeHandlers(),
            ["hardware/signals/missing"],
            handler_name_resolver=lambda topic: f"on_{topic.split('/')[-1]}_signal",
        )


# ---------------------------------------------------------------------------
# Backend: DropbotControllerBase's own resolver, unit-tested directly
# ---------------------------------------------------------------------------


def test_dropbot_controller_base_resolver_matches_dispatch_rules():
    from dropbot_controller.consts import (
        CHANGE_SETTINGS,
        CHIP_INSERTED,
        DROPBOT_CONNECTED,
        DROPBOT_DISCONNECTED,
        RETRY_CONNECTION,
        SELF_TEST_CANCEL,
        START_DEVICE_MONITORING,
    )
    from dropbot_controller.dropbot_controller_base import DropbotControllerBase

    resolve = DropbotControllerBase._resolve_handler_name
    dummy = DropbotControllerBase.__new__(DropbotControllerBase)

    assert resolve(dummy, DROPBOT_CONNECTED) == "on_connected_signal"
    assert resolve(dummy, DROPBOT_DISCONNECTED) == "on_disconnected_signal"
    assert resolve(dummy, CHIP_INSERTED) is None
    assert (
        resolve(dummy, START_DEVICE_MONITORING) == "on_start_device_monitoring_request"
    )
    assert resolve(dummy, RETRY_CONNECTION) == "on_retry_connection_request"
    assert resolve(dummy, CHANGE_SETTINGS) == "on_change_settings_request"
    assert resolve(dummy, SELF_TEST_CANCEL) == "on_self_test_cancel_request"
    assert resolve(dummy, "dropbot/error") is None


def test_dropbot_controller_composed_class_has_a_handler_for_every_topic():
    """Mirrors dropbot_controller/plugin.py's dynamic composition
    (`class DropbotController(*services, DropbotControllerBase)`) so the
    audit sees the same method-resolution-order the real app builds --
    request handlers for many topics live in the mixin services, not on
    DropbotControllerBase itself."""
    from dropbot_controller.consts import ACTOR_TOPIC_DICT, PKG
    from dropbot_controller.dropbot_controller_base import DropbotControllerBase
    from dropbot_controller.services.dropbot_monitor_mixin_service import (
        DropbotMonitorMixinService,
    )
    from dropbot_controller.services.dropbot_self_tests_mixin_service import (
        DropbotSelfTestsMixinService,
    )
    from dropbot_controller.services.dropbot_settings_change import (
        DropbotChangeSettingsService,
    )
    from dropbot_controller.services.dropbot_states_setting_mixin_service import (
        DropbotStatesSettingMixinService,
    )
    from dropbot_controller.services.droplet_detection_mixin_service import (
        DropletDetectionMixinService,
    )

    ComposedController = type(
        "ComposedDropbotController",
        (
            DropbotMonitorMixinService,
            DropbotStatesSettingMixinService,
            DropbotSelfTestsMixinService,
            DropletDetectionMixinService,
            DropbotChangeSettingsService,
            DropbotControllerBase,
        ),
        {},
    )

    listener_name = f"{PKG}_listener"
    # _resolve_handler_name is a pure function of topic (it never touches
    # self), so it can be called unbound against the composed class.
    assert_handlers_exist_for_topics(
        ComposedController,
        ACTOR_TOPIC_DICT[listener_name],
        handler_name_resolver=lambda topic: DropbotControllerBase._resolve_handler_name(
            None, topic
        ),
    )


# ---------------------------------------------------------------------------
# Backend-style duplicates (opendrop / mock dropbot / portable dropbot):
# each implements the same signal/request routing rule independently rather
# than sharing DropbotControllerBase, so the audit replicates that rule
# locally (test-only -- these classes are out of scope for issue #617,
# which limits the production change to the two shared base classes).
# ---------------------------------------------------------------------------


def _make_signal_request_resolver(
    connected_topic, disconnected_topic, exception_topics
):
    """Mirror the common 'signal for connect/disconnect, request otherwise'
    rule these backend-style controllers duplicate from DropbotControllerBase.
    """

    def resolver(topic):
        parts = topic.split("/")
        if len(parts) < 2:
            return None
        primary_sub_topic = parts[1]
        specific_sub_topic = parts[-1]

        if topic in (connected_topic, disconnected_topic):
            return f"on_{specific_sub_topic}_signal"
        if topic in exception_topics:
            return f"on_{specific_sub_topic}_request"
        if primary_sub_topic == "requests":
            return f"on_{specific_sub_topic}_request"
        return None

    return resolver


def test_opendrop_controller_base_has_a_handler_for_every_topic():
    from dropbot_controller.consts import START_DEVICE_MONITORING
    from opendrop_controller.consts import (
        ACTOR_TOPIC_DICT,
        CHANGE_SETTINGS,
        OPENDROP_CONNECTED,
        OPENDROP_DISCONNECTED,
        PKG,
        RETRY_CONNECTION,
    )
    from opendrop_controller.opendrop_controller_base import OpenDropControllerBase

    assert_handlers_exist_for_topics(
        OpenDropControllerBase,
        ACTOR_TOPIC_DICT[f"{PKG}_listener"],
        handler_name_resolver=_make_signal_request_resolver(
            OPENDROP_CONNECTED,
            OPENDROP_DISCONNECTED,
            (START_DEVICE_MONITORING, RETRY_CONNECTION, CHANGE_SETTINGS),
        ),
    )


def test_mock_dropbot_controller_has_a_handler_for_every_topic():
    from dropbot_controller.consts import (
        CHANGE_SETTINGS,
        DROPBOT_CONNECTED,
        DROPBOT_DISCONNECTED,
        RETRY_CONNECTION,
        START_DEVICE_MONITORING,
    )
    from mock_dropbot_controller.consts import ACTOR_TOPIC_DICT, PKG
    from mock_dropbot_controller.mock_controller import MockDropbotController

    assert_handlers_exist_for_topics(
        MockDropbotController,
        ACTOR_TOPIC_DICT[f"{PKG}_listener"],
        handler_name_resolver=_make_signal_request_resolver(
            DROPBOT_CONNECTED,
            DROPBOT_DISCONNECTED,
            (START_DEVICE_MONITORING, RETRY_CONNECTION, CHANGE_SETTINGS),
        ),
    )


def test_portable_dropbot_controller_composed_class_has_a_handler_for_every_topic():
    # Imported via importlib rather than "from <long module path> import
    # (...)" -- these fully-qualified service module paths run well past
    # the 88-column limit on their own.
    import importlib

    from portable_dropbot_controller.consts import (
        ACTOR_TOPIC_DICT,
        CONNECT_TO_PORT,
        PKG,
        PORTABLE_DROPBOT_CONNECTED,
        PORTABLE_DROPBOT_DISCONNECTED,
        REFRESH_PORTS,
        RETRY_CONNECTION,
    )
    from portable_dropbot_controller.portable_dropbot_controller_base import (
        PortableDropbotControllerBase,
    )

    services = "portable_dropbot_controller.services"
    PortableDropbotCalibrationMixinService = importlib.import_module(
        f"{services}.portable_dropbot_calibration_mixin_service"
    ).PortableDropbotCalibrationMixinService
    PortableDropbotElectrodesMixinService = importlib.import_module(
        f"{services}.portable_dropbot_electrodes_mixin_service"
    ).PortableDropbotElectrodesMixinService
    PortableDropbotMonitorMixinService = importlib.import_module(
        f"{services}.portable_dropbot_monitor_mixin_service"
    ).PortableDropbotMonitorMixinService
    PortableDropbotMotorsMixinService = importlib.import_module(
        f"{services}.portable_dropbot_motors_mixin_service"
    ).PortableDropbotMotorsMixinService
    PortableDropbotPmtMixinService = importlib.import_module(
        f"{services}.portable_dropbot_pmt_mixin_service"
    ).PortableDropbotPmtMixinService
    PortableDropbotStatesSettingMixinService = importlib.import_module(
        f"{services}.portable_dropbot_states_setting_mixin_service"
    ).PortableDropbotStatesSettingMixinService
    PortableDropbotSystemMixinService = importlib.import_module(
        f"{services}.portable_dropbot_system_mixin_service"
    ).PortableDropbotSystemMixinService
    PortableDropbotTempMixinService = importlib.import_module(
        f"{services}.portable_dropbot_temp_mixin_service"
    ).PortableDropbotTempMixinService

    ComposedController = type(
        "ComposedPortableDropbotController",
        (
            PortableDropbotMonitorMixinService,
            PortableDropbotStatesSettingMixinService,
            PortableDropbotElectrodesMixinService,
            PortableDropbotMotorsMixinService,
            PortableDropbotCalibrationMixinService,
            PortableDropbotTempMixinService,
            PortableDropbotPmtMixinService,
            PortableDropbotSystemMixinService,
            PortableDropbotControllerBase,
        ),
        {},
    )

    assert_handlers_exist_for_topics(
        ComposedController,
        ACTOR_TOPIC_DICT[f"{PKG}_listener"],
        handler_name_resolver=_make_signal_request_resolver(
            PORTABLE_DROPBOT_CONNECTED,
            PORTABLE_DROPBOT_DISCONNECTED,
            (RETRY_CONNECTION, CONNECT_TO_PORT, REFRESH_PORTS),
        ),
    )


# ---------------------------------------------------------------------------
# Frontend: default `_on_{topic}_triggered` pattern, checked class-side
# (no instantiation needed -- getattr on the class finds the methods).
# ---------------------------------------------------------------------------


def test_device_viewer_dock_pane_has_a_handler_for_every_topic():
    from device_viewer.consts import ACTOR_TOPIC_DICT, listener_name
    from device_viewer.views.device_view_dock_pane import DeviceViewerDockPane

    assert_handlers_exist_for_topics(
        DeviceViewerDockPane, ACTOR_TOPIC_DICT[listener_name]
    )


def test_manual_controls_has_a_handler_for_every_topic():
    from manual_controls.consts import ACTOR_TOPIC_DICT, listener_name
    from manual_controls.MVC import ManualControlControl

    assert_handlers_exist_for_topics(
        ManualControlControl, ACTOR_TOPIC_DICT[listener_name]
    )


def test_ssh_controls_service_has_a_handler_for_every_topic():
    """ssh_controls/service.py overrides the default pattern to
    '_on_{topic}_request'."""
    from ssh_controls.consts import ACTOR_TOPIC_DICT, listener_name
    from ssh_controls.service import SSHService

    assert_handlers_exist_for_topics(
        SSHService,
        ACTOR_TOPIC_DICT[listener_name],
        handler_name_pattern="_on_{topic}_request",
    )


def test_ssh_controls_ui_listeners_have_a_handler_for_every_topic():
    """Both ssh_controls_ui listeners dispatch to a `ui` view-model instance
    (basic_listener_actor_routine(self.ui, ...)), not to the listener class
    itself -- the check must target the class that actually owns the
    handler methods."""
    from ssh_controls_ui.consts import (
        ACTOR_TOPIC_DICT,
        listener_name,
        sync_listener_name,
    )
    from ssh_controls_ui.sync_dialog.view_model import SyncDialogViewModel
    from ssh_controls_ui.view_model import SSHControlViewModel

    assert_handlers_exist_for_topics(
        SSHControlViewModel, ACTOR_TOPIC_DICT[listener_name]
    )
    assert_handlers_exist_for_topics(
        SyncDialogViewModel, ACTOR_TOPIC_DICT[sync_listener_name]
    )


def test_microdrop_application_task_has_a_handler_for_every_topic():
    """Covers microdrop_application's own ACTOR_TOPIC_DICT entry plus the
    SELF_TESTS_PROGRESS topic dropbot_tools_menu contributes to this same
    listener (dropbot_tools_menu/consts.py)."""
    from dropbot_tools_menu.consts import (
        ACTOR_TOPIC_DICT as TOOLS_MENU_ACTOR_TOPIC_DICT,
    )
    from microdrop_application.consts import ACTOR_TOPIC_DICT as APP_ACTOR_TOPIC_DICT
    from microdrop_application.consts import PKG
    from microdrop_application.task import MicrodropTask

    listener_name = f"{PKG}_listener"
    topics = [
        *APP_ACTOR_TOPIC_DICT[listener_name],
        *TOOLS_MENU_ACTOR_TOPIC_DICT[listener_name],
    ]
    assert_handlers_exist_for_topics(MicrodropTask, topics)


def test_dropbot_protocol_controls_force_column_has_a_handler_for_every_topic():
    from dropbot_protocol_controls.consts import (
        ACTOR_TOPIC_DICT,
        CALIBRATION_LISTENER_ACTOR_NAME,
    )
    from dropbot_protocol_controls.protocol_columns.force_column import (
        ForceColumnHandler,
    )

    assert_handlers_exist_for_topics(
        ForceColumnHandler, ACTOR_TOPIC_DICT[CALIBRATION_LISTENER_ACTOR_NAME]
    )


# ---------------------------------------------------------------------------
# Frontend: BaseMessageHandler subclasses (template_status_and_controls)
# ---------------------------------------------------------------------------


def test_dropbot_status_and_controls_has_a_handler_for_every_topic():
    from dropbot_status_and_controls.consts import ACTOR_TOPIC_DICT, listener_name
    from dropbot_status_and_controls.message_handler import (
        DropbotStatusAndControlsMessageHandler,
    )

    assert_handlers_exist_for_topics(
        DropbotStatusAndControlsMessageHandler, ACTOR_TOPIC_DICT[listener_name]
    )


def test_opendrop_status_and_controls_has_a_handler_for_every_topic():
    from opendrop_status_and_controls.consts import ACTOR_TOPIC_DICT, PKG
    from opendrop_status_and_controls.message_handler import (
        OpendropStatusAndControlsMessageHandler,
    )

    assert_handlers_exist_for_topics(
        OpendropStatusAndControlsMessageHandler, ACTOR_TOPIC_DICT[f"{PKG}_listener"]
    )


def test_mock_dropbot_status_has_a_handler_for_every_topic():
    from mock_dropbot_status.consts import ACTOR_TOPIC_DICT, listener_name
    from mock_dropbot_status.message_handler import MockDropbotMessageHandler

    assert_handlers_exist_for_topics(
        MockDropbotMessageHandler, ACTOR_TOPIC_DICT[listener_name]
    )


def test_portable_dropbot_status_listeners_have_handlers():
    """Five independent BaseMessageHandler subclasses, each with its own
    listener name and topic list (portable_dropbot_status_and_controls's
    consts.py). Imported via importlib -- these module paths run past the
    88-column limit as plain "from ... import (...)" statements."""
    import importlib

    from portable_dropbot_status_and_controls.consts import (
        ACTOR_TOPIC_DICT,
        ADVANCED_CONTROLS_LISTENER,
        CALIBRATION_LISTENER,
        MORE_CONTROLS_LISTENER,
        MOTORS_LISTENER,
        PKG,
    )

    handlers = "portable_dropbot_status_and_controls.message_handlers"
    PortableDropbotAdvancedControlsMessageHandler = importlib.import_module(
        f"{handlers}.advanced_controls_message_handler"
    ).PortableDropbotAdvancedControlsMessageHandler
    PortableDropbotCalibrationMessageHandler = importlib.import_module(
        f"{handlers}.calibration_message_handler"
    ).PortableDropbotCalibrationMessageHandler
    PortableDropbotStatusAndControlsMessageHandler = importlib.import_module(
        f"{handlers}.message_handler"
    ).PortableDropbotStatusAndControlsMessageHandler
    PortableDropbotMoreControlsMessageHandler = importlib.import_module(
        f"{handlers}.more_controls_message_handler"
    ).PortableDropbotMoreControlsMessageHandler
    PortableDropbotMotorsMessageHandler = importlib.import_module(
        f"{handlers}.motors_message_handler"
    ).PortableDropbotMotorsMessageHandler

    listener_name = f"{PKG}_listener"
    for handler_class, key in (
        (PortableDropbotStatusAndControlsMessageHandler, listener_name),
        (PortableDropbotMotorsMessageHandler, MOTORS_LISTENER),
        (PortableDropbotCalibrationMessageHandler, CALIBRATION_LISTENER),
        (PortableDropbotMoreControlsMessageHandler, MORE_CONTROLS_LISTENER),
        (PortableDropbotAdvancedControlsMessageHandler, ADVANCED_CONTROLS_LISTENER),
    ):
        assert_handlers_exist_for_topics(handler_class, ACTOR_TOPIC_DICT[key])
