# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Scaffold a new in-app tutorial and contribute it to Help > Tutorials.

Creates ``<plugin>/resources/<slug>.src.html`` from ``template.src.html``,
builds it, adds ``<SLUG>_TUTORIAL_HTML_PATH`` to ``<plugin>/consts.py`` and
makes ``<plugin>/plugin.py`` contribute a ``TutorialEntry`` for it to the
``TUTORIALS`` extension point. Every step is idempotent: re-running leaves
existing work alone. From ``src``::

    pixi run python -m examples.tutorials.new_tutorial <plugin> <slug> "<Title>"

Then run ``ruff check --fix`` and ``ruff format`` on the touched ``consts.py``
and ``plugin.py`` to settle import order. Set ``QT_QPA_PLATFORM=offscreen``
to trace the template's glyph headless.
"""

# Standard library imports.
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

# Local imports.
from .build_tutorial import build_tutorial

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

SRC_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = Path(__file__).parent / "template.src.html"
LINE_LENGTH = 88
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
IMPORT_LINE = re.compile(r"^(import|from) \S+")
TUTORIALS_DEFAULT = "    def _tutorials_default(self):\n        return [\n"
CONTRIBUTION_IMPORT = "from user_help_plugin.consts import TUTORIALS, TutorialEntry"


def tutorial_constant_name(slug):
    """Return the consts.py name of a tutorial's built page."""
    return f"{slug.upper()}_TUTORIAL_HTML_PATH"


def _fit(one_line, wrapped):
    """Return ``one_line`` when it fits ruff's line length, else ``wrapped``."""
    return one_line if len(one_line.rstrip("\n")) <= LINE_LENGTH else wrapped


def write_source(plugin_dir, slug, title):
    """Create the tutorial source from the template; return its path."""
    source = plugin_dir / "resources" / f"{slug}.src.html"

    if source.exists():
        logger.info(f"{source} exists; leaving it as it is")

        return source

    year = str(datetime.date.today().year)
    text = TEMPLATE_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = text.replace("{{year}}", year).replace("{{title}}", title)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(text, encoding="utf-8", newline="\n")
    logger.info(f"Created {source}")

    return source


def add_constant(consts_path, slug):
    """Add the built page's path constant to ``consts.py`` unless present."""
    name = tutorial_constant_name(slug)
    text = consts_path.read_text(encoding="utf-8")

    if re.search(rf"^{name}\s*=", text, re.MULTILINE):
        return False

    if "from pathlib import Path" not in text:
        text = _add_imports(text, ["from pathlib import Path"])

    value = f'Path(__file__).parent / "resources" / "{slug}.html"'
    assignment = _fit(f"{name} = {value}", f"{name} = (\n    {value}\n)")
    text = (
        text.rstrip("\n")
        + f"\n\n#: Help > Tutorials page, built from resources/{slug}.src.html.\n"
        + f"{assignment}\n"
    )
    consts_path.write_text(text, encoding="utf-8", newline="\n")
    logger.info(f"Added {name} to {consts_path}")

    return True


def _add_imports(text, statements):
    """Put ``statements`` after the file's last top-level import line."""
    lines = text.split("\n")
    indices = [i for i, line in enumerate(lines) if IMPORT_LINE.match(line)]
    end = indices[-1] if indices else -1

    # A parenthesised import continues to its closing bracket.
    if end >= 0 and lines[end].rstrip().endswith("("):
        while lines[end].strip() != ")":
            end += 1

    lines[end + 1 : end + 1] = statements

    return "\n".join(lines)


def contribute_to_plugin(plugin_path, slug, title):
    """Make ``plugin.py`` contribute the tutorial to ``TUTORIALS``; return
    True when the file changed."""
    name = tutorial_constant_name(slug)
    text = plugin_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    quoted = json.dumps(title, ensure_ascii=False)
    entry = _fit(
        f"            TutorialEntry(title={quoted}, path={name}),\n",
        f"            TutorialEntry(\n                title={quoted},\n"
        f"                path={name},\n            ),\n",
    )

    if re.search(rf"\bpath={name}\b", text):
        return False

    if TUTORIALS_DEFAULT in text:
        # Add to the plugin's existing list of tutorials.
        start = text.index(TUTORIALS_DEFAULT) + len(TUTORIALS_DEFAULT)
        end = text.index("        ]\n", start)
        text = text[:end] + entry + text[end:]
    else:
        text = _add_contribution(text, entry)

    text = _add_imports(text, [f"from .consts import {name}"])
    plugin_path.write_text(text, encoding="utf-8", newline="\n")
    logger.info(f"{plugin_path} now contributes '{title}'")

    return True


def _add_contribution(text, entry):
    """Give the file's plugin class a ``tutorials`` contribution."""
    match = re.search(r"^class \w+\(.*Plugin\w*\):\n", text, re.MULTILINE)

    if match is None:
        raise ValueError("plugin.py has no Plugin class to contribute from")

    next_top_level = re.search(r"^\S", text[match.end() :], re.MULTILINE)
    end = match.end() + next_top_level.start() if next_top_level else len(text)
    block = (
        "\n    #: Help > Tutorials entries for this plugin's panes.\n"
        "    tutorials = List(contributes_to=TUTORIALS)\n\n"
        f"{TUTORIALS_DEFAULT}{entry}        ]\n"
    )
    body = text[:end].rstrip("\n") + "\n" + block
    rest = text[end:]
    text = body + ("\n\n" + rest if rest else "")
    imports = [CONTRIBUTION_IMPORT]

    if not re.search(r"from traits\.api import [^\n]*\bList\b", text):
        imports.append("from traits.api import List")

    return _add_imports(text, imports)


def scaffold_tutorial(plugin, slug, title, root=SRC_ROOT, build=True):
    """Create, build and contribute one tutorial; return the source path."""
    if not SLUG_PATTERN.match(slug):
        raise ValueError(f"Slugs are lower_snake_case identifiers: {slug!r}")

    plugin_dir = Path(root) / plugin

    for required in ("consts.py", "plugin.py"):
        if not (plugin_dir / required).is_file():
            raise ValueError(f"{plugin_dir / required} does not exist")

    source = write_source(plugin_dir, slug, title)

    if build:
        build_tutorial(source)

    add_constant(plugin_dir / "consts.py", slug)
    contribute_to_plugin(plugin_dir / "plugin.py", slug, title)

    return source


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "plugin", help="plugin package, e.g. dropbot_status_and_controls"
    )
    parser.add_argument("slug", help="lower_snake_case page name")
    parser.add_argument("title", help='menu and page title, e.g. "Heater Tutorial"')
    parser.add_argument("--root", type=Path, default=SRC_ROOT, help="source root")
    args = parser.parse_args(argv)
    scaffold_tutorial(args.plugin, args.slug, args.title, root=args.root)

    return 0


if __name__ == "__main__":
    sys.exit(main())
