# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A plugin manager that starts plugins one at a time and isolates failures.

Envisage's ``PluginManager.start`` starts every plugin in one loop, so one
plugin raising in ``start()`` aborts the launch. ``IsolatingPluginManager``
records each plugin's start in a ``PluginLoadStatus`` and, when a
non-essential plugin raises, rolls that plugin back with
``withdraw_plugin`` and carries on with the rest. An essential plugin's
failure still propagates. The application installs it through Envisage's own
seam, its ``plugin_manager`` trait default.
"""

# Enthought library imports.
from envisage.api import SERVICE_OFFERS, PluginManager
from traits.api import Instance, List, Str

# Local imports.
from .plugin_load_status import PluginLoadStatus

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def registered_service_ids(application):
    """Return the ids of every service registered with ``application``.

    The service registry has no public way to list its ids; the plugin-group
    manager snapshots the same private dict to find the services a plugin
    registered while it started.
    """
    return set(application.service_registry._services)


def _offered_service_ids(application, plugin):
    """Return the ids under which ``plugin``'s service offers are registered.

    The core plugin registers every offer, at its own start or as soon as a
    plugin is added at runtime, and never unregisters an offer whose plugin
    goes away. Each registration keeps the offer's own properties dict, which
    still identifies it after the factory has been replaced by the service it
    created.
    """
    offers = plugin.get_extensions(SERVICE_OFFERS)
    service_ids = set()

    for service_id, (_, service, properties) in list(
        application.service_registry._services.items()
    ):
        for offer in offers:
            if service is offer.factory or properties is offer.properties:
                service_ids.add(service_id)

    return service_ids


def unregister_services(application, service_ids):
    """Unregister ``service_ids``, skipping any already gone."""
    for service_id in sorted(service_ids):
        try:
            application.unregister_service(service_id)

        except ValueError:
            # Already unregistered, e.g. by the plugin's own stop().
            pass


def withdraw_plugin(application, plugin, service_ids=()):
    """Roll back a plugin whose start failed, or that must be unwound.

    Stops the plugin as far as it will stop, removes it from the application
    (which withdraws its extension contributions: task extensions, topic
    routes, status-bar icons, ...), and unregisters ``service_ids`` plus the
    services registered for its service offers. Each step is best effort:
    a plugin that failed half-way through ``start()`` may not stop cleanly.
    """
    plugin_id = plugin.id
    service_ids = set(service_ids) | _offered_service_ids(application, plugin)

    try:
        application.stop_plugin(plugin)

    except Exception:
        logger.warning(f"Rollback: {plugin_id} did not stop cleanly", exc_info=True)

    try:
        application.remove_plugin(plugin)

    except Exception:
        logger.error(f"Rollback: could not remove {plugin_id}", exc_info=True)

    unregister_services(application, service_ids)

    logger.info(
        f"Rollback: withdrew {plugin_id} and {len(service_ids)} service(s) it offered"
    )


class IsolatingPluginManager(PluginManager):
    """Start plugins one at a time, record each start, and skip failures."""

    #: The load record of every plugin this manager starts.
    load_status = Instance(PluginLoadStatus, ())

    #: Ids of the plugins the application cannot run without. A failure to
    #: start one of these is re-raised and fails the launch; any other plugin
    #: that fails is rolled back and skipped.
    essential_plugin_ids = List(Str)

    def start(self):
        """Start every plugin in order, isolating non-essential failures.

        Envisage's ``starting``/``started`` application events still wrap this
        whole loop, and the plugins that start see the same per-plugin
        sequence as with the stock manager.
        """
        plugins = list(self)

        for plugin in plugins:
            self.load_status.mark_pending(
                plugin.id, plugin.name, self._is_essential(plugin)
            )

        for plugin in plugins:
            self.start_isolated(plugin)

        logger.info(f"Plugin start finished: {self.load_status.summary}")

    def _is_essential(self, plugin):
        return plugin.id in self.essential_plugin_ids

    def start_isolated(self, plugin):
        """Start ``plugin``; roll it back if it fails and is not essential.

        Also starts a plugin added after the launch, e.g. one deferred until
        the main window painted.

        Returns
        -------
        bool
            True if the plugin started, False if it failed and was withdrawn.
        """
        essential = self._is_essential(plugin)
        services_before = registered_service_ids(self.application)

        try:
            with self.load_status.recording(plugin, essential):
                self.start_plugin(plugin)

        except Exception:
            if essential:
                logger.exception(
                    f"Essential plugin {plugin.id} failed to start; "
                    "MicroDrop cannot run without it"
                )

                raise

            logger.error(
                f"Plugin {plugin.id} failed to start; skipping it and "
                "starting the remaining plugins",
                exc_info=True,
            )

            started_services = registered_service_ids(self.application)
            withdraw_plugin(
                self.application, plugin, started_services - services_before
            )

            return False

        return True
