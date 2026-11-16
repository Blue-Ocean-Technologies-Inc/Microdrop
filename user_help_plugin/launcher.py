# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Start the standalone MicroDrop setup and launcher as its own process."""

# Standard library imports.
import subprocess
import sys
from pathlib import Path


def is_launcher_executable(path):
    """Return whether ``path`` names a launcher MicroDrop can start."""

    if not path:
        return False

    path = Path(path)

    # The macOS build is an .app bundle, which is a directory.
    if sys.platform == "darwin" and path.suffix == ".app":
        return path.is_dir()

    return path.is_file()


def start_launcher(path):
    """Start the launcher at ``path`` detached, so it outlives MicroDrop."""
    path = Path(path)

    if sys.platform == "darwin" and path.suffix == ".app":
        argv, options = ["open", "-n", str(path)], {}

    elif sys.platform == "win32":
        # The Windows build is a console exe; give it its own console window
        # rather than sharing the one MicroDrop may be running in.
        argv = [str(path)]
        options = {
            "creationflags": subprocess.CREATE_NEW_CONSOLE
            | subprocess.CREATE_NEW_PROCESS_GROUP
        }

    else:
        argv, options = [str(path)], {"start_new_session": True}

    subprocess.Popen(
        argv,
        cwd=path.parent,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        **options,
    )
