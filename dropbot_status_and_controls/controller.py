# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from traits.api import Instance, observe
from traitsui.api import UI

# Microdrop package imports.
from dropbot_controller.consts import SET_FREQUENCY, SET_VOLTAGE
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from template_status_and_controls.base_controller import BaseStatusController

# Microdrop utils imports.
from microdrop_utils.decorators import debounce

# Local imports.
from .consts import DIELECTRIC_MATERIAL_KEY
from .view import droplet_readouts_view

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()


class ControlsController(BaseStatusController):
    """DropBot controls controller.

    Extends BaseStatusController with voltage and frequency control:
      - Debounced setattr methods prevent hardware flooding during slider drags.
      - Observers publish hardware commands, queuing them when not in realtime mode.

    Inherited from BaseStatusController:
      - message_dict, _publish_or_queue(), publish_queued_messages()
      - realtime_mode_setattr(), _on_realtime_mode_changed()
    """

    #: The open droplet readouts dialog, if any.
    _droplet_readouts_ui = Instance(UI)

    # ------------------------------------------------------------------ #
    # Debounced setattr                                                    #
    # ------------------------------------------------------------------ #

    @debounce(wait_seconds=0.3)
    def voltage_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @debounce(wait_seconds=0.3)
    def frequency_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    # ------------------------------------------------------------------ #
    # Observers                                                            #
    # ------------------------------------------------------------------ #

    @observe("model:voltage")
    def _on_voltage_changed(self, event):
        if self._publish_or_queue(topic=SET_VOLTAGE, message=str(event.new)):
            logger.debug(f"Voltage --> {event.new} V")

    @observe("model:frequency")
    def _on_frequency_changed(self, event):
        if self._publish_or_queue(topic=SET_FREQUENCY, message=str(event.new)):
            logger.debug(f"Frequency --> {event.new} Hz")

    @observe("model:[preferences,dielectric_material]")
    def _publish_dielectric_material(self, event):
        """Share the picked dielectric with other plugins (the protocol run
        report). The dock pane assigning ``model.preferences`` is the startup
        write: the material's default is read from those preferences."""
        app_globals[DIELECTRIC_MATERIAL_KEY] = self.model.dielectric_material

    @observe("model:show_droplet_readouts")
    def _open_droplet_readouts(self, event):
        """Show every droplet readout in a non-modal window, raising the one
        already open instead of stacking another."""

        if self._droplet_readouts_ui is not None and self._droplet_readouts_ui.control:
            self._droplet_readouts_ui.control.raise_()
            self._droplet_readouts_ui.control.activateWindow()

            return

        parent = self.info.ui.control if self.info and self.info.ui else None
        self._droplet_readouts_ui = self.model.edit_traits(
            view=droplet_readouts_view, kind="live", parent=parent
        )
