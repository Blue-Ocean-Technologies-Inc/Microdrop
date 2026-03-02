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
