# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# template_status_and_controls
#
# A reusable base layer for device "status and controls" panels.
# Each device plugin (dropbot, opendrop, …) composes the base classes here
# with its own device-specific model traits, message handlers, and views.
#
# Typical usage:
#
#   from template_status_and_controls.base_model import BaseStatusModel
#   from template_status_and_controls.base_controller import BaseStatusController
#   from template_status_and_controls.base_message_handler import BaseMessageHandler
#   from template_status_and_controls.base_dock_pane import BaseStatusDockPane
#   from template_status_and_controls.base_plugin import BaseStatusPlugin
