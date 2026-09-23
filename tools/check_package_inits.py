# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""
Fail if a tracked directory under an import-linter root package holds
tracked ``*.py`` files but has no ``__init__.py``.

grimp (the dependency graph behind import-linter) does not descend into a
directory without ``__init__.py``, so the ``.importlinter`` independence
contract silently skips every import inside it (#679). This script re-derives
the same directory set the contract's ``root_packages`` cover and checks each
one has an ``__init__.py``, so the gap cannot reopen unnoticed.
"""

# Standard library imports.
import configparser
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Directories deliberately left package-less, with the reason why.
EXCLUDED_DIRS = {
    # pgva_controller_plugin is going away with #644; not worth packaging.
    "pgva_controller_plugin/services",
}


def _tracked_py_files():
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.splitlines()


def _root_packages():
    config = configparser.ConfigParser()
    config.read(REPO_ROOT / ".importlinter")

    return set(config["importlinter"]["root_packages"].split())


def find_missing_inits():
    tracked = _tracked_py_files()
    tracked_set = set(tracked)
    roots = _root_packages()

    package_dirs = set()

    for path in tracked:
        top, sep, _ = path.partition("/")

        if not sep or top not in roots:
            continue

        package_dirs.add(path.rsplit("/", 1)[0])

    missing = []

    for directory in sorted(package_dirs):
        if directory in EXCLUDED_DIRS:
            continue

        if f"{directory}/__init__.py" not in tracked_set:
            missing.append(directory)

    return missing


def main():
    missing = find_missing_inits()

    if not missing:
        return 0

    print("Directories with tracked .py files but no __init__.py:")

    for directory in missing:
        print(f"  {directory}")

    print(
        "\ngrimp (import-linter) silently skips these, so the plugin-"
        "decoupling contract can't see imports inside them. Add an "
        "__init__.py (copyright header only, see .copyright-header.txt), or "
        "add the directory to EXCLUDED_DIRS in tools/check_package_inits.py "
        "with a reason if it's genuinely not meant to be a package."
    )

    return 1


if __name__ == "__main__":
    sys.exit(main())
