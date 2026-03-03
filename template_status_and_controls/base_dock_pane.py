"""
BaseStatusDockPane — orchestrates model + view + controller + message handler.

TraitsDockPane wires a HasTraits model to a TraitsUI View through a Controller
(Handler). The concrete dock pane subclass sets the class-level model, view,
and controller attributes that TraitsDockPane expects, then calls super().

This base class provides:
  1. traits_init(): calls the two factory hooks and assembles the pane.
  2. _create_message_handler(): factory hook — subclass must implement.
  3. _setup_extras(): optional hook for device-specific additions such as
     status-bar icons, dialog views, or help pages.

Design notes:
  - We use factory *methods* (not class-level attributes) for the message
    handler and extras so that each pane *instance* gets its own objects —
    the existing code had a subtle bug where class-level model/controller
    were shared across instances.
  - Subclasses that need a status-bar icon or dialog popups override
    _setup_extras(); this keeps the base class free of device-specific code.
"""

from pyface.tasks.api import TraitsDockPane

from logger.logger_service import get_logger

from .interfaces import IMessageHandler

logger = get_logger(__name__)


class BaseStatusDockPane(TraitsDockPane):
    """
    Base dock pane for device status-and-controls panels.

    Minimal subclass example
    ------------------------
    ::

        class MyDeviceDockPane(BaseStatusDockPane):
            id   = f"{PKG}.dock_pane"
            name = PKG_name

            # TraitsDockPane class-level attributes
            model      = MyDeviceModel()
            view       = MyDeviceView
            controller = MyDeviceController(model)
            view.handler = controller

            def _create_message_handler(self) -> IMessageHandler:
                return MyDeviceMessageHandler(
                    model=self.model,
                    name=f"{PKG}_listener",
                )
    """

    # ------------------------------------------------------------------ #
    # Lifecycle                                                             #
    # ------------------------------------------------------------------ #

    def traits_init(self):
        """
        Assemble the pane after traits initialisation.

        Order matters: the message handler must be started before _setup_extras
        because extras (e.g. dialog views) may connect to handler signals.
        """
        self.message_handler = self._create_message_handler()
        self._setup_extras()

    # ------------------------------------------------------------------ #
    # Factory hooks — implement / override in subclass                     #
    # ------------------------------------------------------------------ #

    def _create_message_handler(self) -> IMessageHandler:
        """
        Create and return the device-specific message handler.

        The returned object must satisfy IMessageHandler (i.e. it must be a
        BaseMessageHandler subclass or equivalent HasTraits object whose
        traits_init() registers a Dramatiq actor).

        Raises NotImplementedError if not overridden.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _create_message_handler()"
        )

    def _setup_extras(self):
        """
        Hook for device-specific one-time setup after the handler is running.

        Examples of what subclasses put here:
          - Dialog views (shorts detected, no-power, halted)
          - Status-bar icon widget and colour observer
          - Help page action

        Default: no-op.
        """
