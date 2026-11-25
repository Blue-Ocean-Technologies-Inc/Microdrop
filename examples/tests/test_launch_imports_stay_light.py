# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The modules a launch imports must not pull in the heavy packages that are
only needed once a feature is used (#1063).

Each of these packages is imported where it is first used. A module-level
import added to any module below puts it back on the launch path, which only a
fresh interpreter can see: this test process has long imported all of them.
"""

# Standard library imports.
import json
import os
import subprocess
import sys
from pathlib import Path

#: The repository root, where the plugin packages are importable from.
REPO_ROOT = Path(__file__).resolve().parents[2]

#: Modules imported during a launch, by plugin import, task extensions or
#: ``start()``, that used to import one of the packages below at module level.
LAUNCH_MODULES = (
    "image_viewer.plugin",
    "image_viewer.dock_pane",
    "image_viewer.menus",
    "image_viewer.message_handler",
    "image_viewer.preferences",
    "image_viewer.analysis.roi_model",
    "device_viewer.utils.dmf_utils_helpers",
    "dropbot_controller.services.dropbot_self_tests_mixin_service",
    "dropbot_tools_menu.menus",
    "pluggable_protocol_tree.services.logging.controller",
    "ssh_controls.service",
    "user_help_plugin.plugin",
    # What NotificationsPlugin.start() imports; the toasts and settings
    # window are imported on first use, not here.
    "notifications.plugin",
    "notifications.controllers.load_failure_notifier",
    "notifications.controllers.message_handler",
    "notifications.controllers.section_alerts",
    "notifications.models.own_sections",
    "notifications.services.chime",
    "notifications.services.log_forwarder",
    "notifications.views.bell",
    # Right after the first paint: the saved settings, and the drawer, which
    # opens at start-up by default.
    "notifications.services.settings_store",
    "notifications.views.drawer_host",
    "notifications.views.column",
    # Read at launch to decide on the What's New dialog.
    "news.consts",
    # The news plugin, deferred but loaded first: what the loader's worker
    # imports (preload_modules) and runs (prepare) for it.
    "news.plugin",
    "news.services.news_feed",
    "news.controllers.news_alerts",
    "news.services.seen_state",
    "news.views.feed_column",
)

#: Packages none of them may import. Bare ``scipy`` is not listed: pint, which
#: the DropBot driver uses, imports it, and it is cheap on its own.
HEAVY_PACKAGES = (
    "matplotlib",
    "paramiko",
    "plotly",
    "scipy.optimize",
    "scipy.special",
    "scipy.stats",
    # The chime loads Qt Multimedia the first time it sounds.
    "PySide6.QtMultimedia",
)

_PROBE = """
import importlib, json, sys

for name in {modules!r}:
    importlib.import_module(name)

print(json.dumps([name for name in {packages!r} if name in sys.modules]))
"""


def test_launch_modules_do_not_import_heavy_packages():
    """Importing the launch modules in a fresh interpreter leaves the heavy
    packages unimported."""
    env = dict(
        os.environ,
        PYTHONPATH=str(REPO_ROOT),
        QT_QPA_PLATFORM="offscreen",
        MICRODROP_SKIP_GIT_UPDATE="1",
    )
    code = _PROBE.format(modules=LAUNCH_MODULES, packages=HEAVY_PACKAGES)

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr[-2000:]

    imported = json.loads(result.stdout.strip().splitlines()[-1])

    assert imported == [], f"imported at launch: {imported}"
