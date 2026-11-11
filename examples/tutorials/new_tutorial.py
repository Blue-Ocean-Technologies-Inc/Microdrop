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
import ast
import datetime
import html
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
TUTORIALS_DEFAULT = "    def _tutorials_default(self):\n        return [\n"
#: Any tutorials trait or default method, however it is written.
TUTORIALS_DECLARATION = re.compile(
    r"^\s+(?:tutorials\s*=|def _tutorials_default\b)", re.MULTILINE
)
#: The indentation of a line outside the ``_tutorials_default`` list.
OUTSIDE_TUTORIALS_LIST = re.compile(r"^ {0,11}\S", re.MULTILINE)
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
    text = text.replace("{{year}}", year).replace("{{title}}", html.escape(title))

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
        text = _add_imports(text, ["from pathlib import Path"], consts_path)

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


def _add_imports(text, statements, path):
    """Put ``statements`` after the last top-level import that comes before
    the file's first class or function."""
    last_import = None

    try:
        module = ast.parse(text)
    except SyntaxError as error:
        raise ValueError(f"{path} does not parse; fix it first: {error}") from error

    for node in module.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            break

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last_import = node

    if last_import is None:
        raise ValueError(
            f"{path} has no top-level import before its first class or "
            f"function to add these after; add them by hand: {statements}"
        )

    lines = text.split("\n")
    lines[last_import.end_lineno : last_import.end_lineno] = statements

    return "\n".join(lines)


def _has_entry(text, name):
    """Return True when a ``TutorialEntry(...)`` call already names ``name``."""
    pattern = rf"TutorialEntry\((?:(?!TutorialEntry\(|\n {{0,4}}\S).)*?\b{name}\b"

    return re.search(pattern, text, re.DOTALL) is not None


def _add_entry(text, entry, by_hand):
    """Add ``entry`` to the plugin's existing ``_tutorials_default`` list,
    after a comma the last entry may have been written without."""
    start = text.index(TUTORIALS_DEFAULT) + len(TUTORIALS_DEFAULT)
    end = text.find("        ]\n", start)

    if end < 0 or OUTSIDE_TUTORIALS_LIST.search(text, start, end):
        raise ValueError(f"Cannot find the end of the tutorials list in {by_hand}")

    head = text[:end].rstrip()

    if not head.endswith(("[", ",")):
        head += ","

    return f"{head}\n{entry}{text[end:]}"


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

    by_hand = (
        f"{plugin_path}; add TutorialEntry(title={quoted}, path={name}) to its "
        f"_tutorials_default by hand, importing {name} from .consts"
    )

    if _has_entry(text, name):
        return False

    if TUTORIALS_DEFAULT in text:
        text = _add_entry(text, entry, by_hand)
    elif TUTORIALS_DECLARATION.search(text):
        raise ValueError(f"Tutorials are declared in an unfamiliar shape in {by_hand}")
    else:
        text = _add_contribution(text, entry, plugin_path)

    text = _add_imports(text, [f"from .consts import {name}"], plugin_path)
    plugin_path.write_text(text, encoding="utf-8", newline="\n")
    logger.info(f"{plugin_path} now contributes '{title}'")

    return True


def _add_contribution(text, entry, plugin_path):
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

    return _add_imports(text, imports, plugin_path)


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
