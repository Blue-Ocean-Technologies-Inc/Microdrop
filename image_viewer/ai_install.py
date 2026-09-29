# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Help-menu installer for the optional SAM (osam) ROI-detection stack.

Runs ``pixi add --pypi osam`` (plus ``onnxruntime-directml`` on Windows, a
tolerated-failure optional GPU accelerator) from the pixi project root in a
worker thread, streaming output into a cancellable ``QProgressDialog``.
Mirrors ``image_viewer/sam_download.py``'s QThread + QProgressDialog
pattern for consistency.
"""

# Standard library imports.
import importlib
import os
import signal
import subprocess
import sys
from pathlib import Path

# Third-party imports.
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QProgressDialog

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Base label text the dialog stays pinned to; the latest output line (or
#: failure reason) is appended beneath it as the install progresses.
_INSTALL_LABEL = "Installing AI ROI support (osam)..."


def _pixi_project_root():
    """The pixi project root: walk up from the running interpreter's
    ``sys.prefix`` looking for a directory with a ``pixi.toml``, or a
    ``pyproject.toml`` whose text declares a ``[tool.pixi`` table. Falls
    back to the current working directory (logged) if neither is found."""
    start = Path(sys.prefix)
    for directory in (start, *start.parents):
        if (directory / "pixi.toml").exists():
            return directory
        pyproject = directory / "pyproject.toml"
        if pyproject.exists():
            try:
                text = pyproject.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning(f"Could not read {pyproject}: {e}")
                text = ""
            if "[tool.pixi" in text:
                return directory
    logger.warning(
        f"No pixi.toml or pyproject.toml with [tool.pixi] found above "
        f"{start}; falling back to cwd {Path.cwd()}"
    )
    return Path.cwd()


class _InstallThread(QThread):
    """Runs ``pixi add --pypi osam`` (plus ``onnxruntime-directml`` on
    Windows, tolerated failure) in the pixi project root, streaming output
    lines and reporting success/failure.

    ``succeeded``/``failed`` only drive the dialog's live label and
    auto-close -- they race a user cancel (Qt hides the dialog and
    ``exec()`` returns as soon as Cancel is clicked, independent of these
    signals). The authoritative result is ``osam_installed``, set the
    instant the required first step exits 0 and never revisited by the
    second, tolerated-failure step -- callers must read it only after
    ``wait()``ing for the thread to actually finish."""

    output = Signal(str)
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self._root = root
        self._process = None
        #: Set the moment `pixi add --pypi osam` exits 0. The definitive
        #: outcome: read only after the thread has finished.
        self.osam_installed = False

    def cancel(self):
        """Tree-kill the in-flight pixi process: pixi's resolver/download
        children run in their own group/session (see _run_step), so
        killing only the parent (as plain ``Popen.kill()`` would) can
        orphan them."""
        process = self._process
        if process is None:
            return
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                logger.debug(f"taskkill failed for pid {process.pid}: {e}")
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except Exception as e:
                logger.debug(f"killpg failed for pid {process.pid}: {e}")

    def _run_step(self, args):
        """Run one pixi command in its own process group/session (so
        cancel() can tree-kill it), streaming its output line by line.
        Returns the exit code."""
        if sys.platform == "win32":
            group_kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            group_kwargs = {"start_new_session": True}
        self._process = subprocess.Popen(
            args,
            cwd=self._root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            **group_kwargs,
        )
        for line in self._process.stdout:
            line = line.rstrip()
            if line:
                self.output.emit(line)
        return self._process.wait()

    def run(self):
        try:
            code = self._run_step(["pixi", "add", "--pypi", "osam"])
        except FileNotFoundError:
            self.failed.emit("pixi not found on PATH")
            return
        except Exception as e:
            self.failed.emit(f"Install failed: {e}")
            return

        if code != 0:
            self.failed.emit("Install failed")
            return

        self.osam_installed = True

        if sys.platform == "win32":
            try:
                gpu_code = self._run_step(
                    # --platform: the DirectML wheel exists only for
                    # win_amd64, and a multi-platform pixi manifest
                    # fails to resolve it without the restriction.
                    [
                        "pixi",
                        "add",
                        "--pypi",
                        "--platform",
                        "win-64",
                        "onnxruntime-directml",
                    ]
                )
            except Exception as e:
                gpu_code = None
                logger.warning(
                    f"onnxruntime-directml install could not run: {e} "
                    f"(optional GPU accelerator, continuing)"
                )
            if gpu_code:
                logger.warning(
                    f"pixi add --pypi onnxruntime-directml exited "
                    f"{gpu_code} (optional GPU accelerator, continuing)"
                )

        self.succeeded.emit()


def install_ai_support(parent=None):
    """Install the optional SAM (osam) segmentation stack with pixi,
    showing progress in a cancellable dialog. Returns True only if osam
    successfully imports afterwards. Never raises."""
    root = _pixi_project_root()

    dialog = QProgressDialog(_INSTALL_LABEL, "Cancel", 0, 0, parent)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(0)
    dialog.setMinimumWidth(400)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)

    thread = _InstallThread(root=root, parent=parent)

    def _on_output(line):
        dialog.setLabelText(f"{_INSTALL_LABEL}\n{line}")

    def _on_succeeded():
        dialog.close()

    def _on_failed(reason):
        logger.error(f"AI support install failed: {reason}")
        dialog.setRange(0, 1)
        dialog.setLabelText(f"{dialog.labelText()}\n{reason}")
        dialog.setCancelButtonText("Close")

    dialog.canceled.connect(thread.cancel)
    thread.output.connect(_on_output)
    thread.succeeded.connect(_on_succeeded)
    thread.failed.connect(_on_failed)

    dialog.show()
    thread.start()
    dialog.exec()

    # dialog.exec() can return the instant Cancel is clicked (Qt hides the
    # dialog natively), before the worker's succeeded/failed signal lands
    # -- e.g. a cancel during the optional, tolerated-failure DirectML step
    # would otherwise race a real osam success. Wait for the thread to
    # actually finish and read its recorded outcome instead of relying on
    # which signal happened to fire.
    if not thread.wait(5000):
        thread.terminate()
        thread.wait()
    succeeded = thread.osam_installed

    thread.output.disconnect(_on_output)
    thread.succeeded.disconnect(_on_succeeded)
    thread.failed.disconnect(_on_failed)

    if not succeeded:
        return False

    importlib.invalidate_caches()
    try:
        # optional dependency: same exception granted to sam_detect.py's
        # osam import — this just-installed package may still fail to
        # import (e.g. a partial/incompatible install).
        import osam  # noqa: F401
    except ImportError as e:
        logger.warning(f"osam import still failing after install: {e}")
        return False
    return True
