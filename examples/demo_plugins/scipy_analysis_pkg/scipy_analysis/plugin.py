"""A minimal installable demo plugin that contributes one dock pane.

The plugin module itself imports no third-party analysis libraries, so it can be
imported during plugin resolution even before its declared dependency (scipy) is
installed. The dock pane (which does import scipy) is imported lazily only when
the task extension is materialized at plugin start — so without scipy the group
simply fails to enable cleanly (the dependency-resolution backstop), and after a
relaunch into the microdrop-plugins env it mounts normally.
"""
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension
from traits.api import List, Str

from microdrop_application.consts import PKG as APP_PKG


class ScipyAnalysisPlugin(Plugin):
    id = "scipy_analysis.plugin"
    name = "Scipy Analysis Plugin"

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)
    task_id = Str(f"{APP_PKG}.task")

    def _contributed_task_extensions_default(self):
        from .dock_pane import ScipyAnalysisDockPane
        return [
            TaskExtension(
                task_id=self.task_id,
                dock_pane_factories=[ScipyAnalysisDockPane],
            )
        ]
