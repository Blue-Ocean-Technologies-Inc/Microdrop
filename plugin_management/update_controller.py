"""Handler for the launch update-check dialog: Update All hot-unloads every
plugin being updated, runs the bulk update on a worker thread, then applies
each new version live (``hot_load_installed``) — the relaunch popup is offered
only for the plugins whose hot-load refused, naming the reasons; Later just
closes.

Worker callables (do_update_all) must not touch model traits — they return
data and the GUI-thread callbacks act on it (project threading rule)."""
from traits.api import Any
from traitsui.api import Handler

from microdrop_application.dialogs.pyface_wrapper import (
    error as error_dialog, escape_html_multiline)
from microdrop_utils.threaded_progress import run_with_wait

from .hot_load import hot_load_installed, unload_for_change
from .i_plugin_group_manager import IPluginGroupManager
from .package_installer import EnvDiff
from .relaunch import finish_change


def show_update_dialog(report, application):
    """Open the update dialog for a non-empty report. GUI thread only —
    schedule via ``GUI.invoke_later`` from workers."""
    from .update_model import UpdateDialogModel
    from .update_view import update_view

    window = getattr(application, "active_window", None)
    task = getattr(window, "active_task", None)
    manager = (application.get_service(IPluginGroupManager)
               if application is not None else None)
    model = UpdateDialogModel(report=report)
    model.edit_traits(view=update_view,
                      handler=UpdateDialogHandler(task=task,
                                                  application=application,
                                                  manager=manager))


class UpdateDialogHandler(Handler):
    """Runs the bulk update, reports failures, applies the updates live, and
    offers a relaunch only for those that could not be hot-loaded."""

    #: The active task, for confirm_and_relaunch (None-safe: the helper
    #: degrades gracefully without a running application).
    task = Any(None)

    #: The Envisage application + PluginGroupManager service, for the live
    #: unload/hot-load. Both None-safe: without them every successful update
    #: skips the hot-load and falls back to the relaunch offer.
    application = Any(None)
    manager = Any(None)

    def update_all(self, info):
        model = info.object
        # Hot-unload + purge each plugin BEFORE its package is replaced (GUI
        # thread — mutates manager traits), so the new version's code is
        # genuinely importable and the update hot-loads like an install.
        if self.manager is not None:
            for manifest_name, dist_name in self._manifests_for_updates(model):
                unload_for_change(self.manager, self.application,
                                  manifest_name, dist_name)
        run_with_wait(
            model.do_update_all,
            title="Updating plugins", message="Updating plugins…",
            on_success=lambda result: self._after_update(info, result),
            on_error=lambda e: error_dialog(
                parent=None, title="Update failed", message=str(e)),
        )

    def _manifests_for_updates(self, model):
        """(manifest_name, dist_name) for every registered manifest owned by
        a distribution the update report lists."""
        norm = self.manager._norm_dist
        updating = {norm(name) for name, _installed, _latest
                    in model.report.updates}
        return [(manifest_name, dist_name)
                for manifest_name, _label, dist_name, _group_names
                in self.manager.installed_plugins()
                if norm(dist_name) in updating]

    def _hot_load(self, dist_name, diff):
        """Apply an updated distribution live if possible; None when it is
        live, else the refusal reason (``hot_load_installed``'s contract)."""
        if self.manager is None or self.application is None:
            return "no running application to hot-load into"
        return hot_load_installed(self.application, self.manager,
                                  dist_name, diff)

    def _after_update(self, info, result):
        succeeded, failed = result
        if failed:
            # A failed pixi step rolled the package back with its groups
            # unloaded + purged while its files are still on disk; re-enable
            # from disk so the failure costs only the error dialog (an empty
            # diff passes the gate, and the purge means fresh imports).
            for name, _err in failed:
                self._hot_load(name, EnvDiff({}, {}, {}))
            failures = "<br>".join(
                f"<b>{escape_html_multiline(name)}</b>: "
                f"{escape_html_multiline(err)}"
                for name, err in failed
            )
            error_dialog(parent=None, title="Some updates failed",
                         message=failures)
        info.ui.dispose()
        if not succeeded:
            return
        refusals = [(name, self._hot_load(name, change.diff))
                    for name, change in succeeded]
        refusals = [(name, reason) for name, reason in refusals
                    if reason is not None]
        names = ", ".join(
            f"<b>{escape_html_multiline(name)}</b>" for name, _ in succeeded
        )
        finish_change(self.task, f"Updated {names}.", not refusals,
                      "; ".join(f"{name}: {reason}"
                                for name, reason in refusals))

    def do_close(self, info):
        info.ui.dispose()
