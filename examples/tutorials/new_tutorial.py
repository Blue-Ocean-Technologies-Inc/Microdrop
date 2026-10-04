# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Scaffold a new in-app tutorial and wire it into Help > Tutorials.

Creates ``<plugin>/resources/<slug>.src.html`` from ``template.src.html``,
builds it, adds ``<SLUG>_TUTORIAL_HTML_PATH`` to ``<plugin>/consts.py`` and
registers the page in ``user_help_plugin/menus.py``'s ``TUTORIALS``. Every
step is idempotent: re-running leaves existing files alone. From ``src``::

    pixi run python -m examples.tutorials.new_tutorial <plugin> <slug> "<Title>"

Set ``QT_QPA_PLATFORM=offscreen`` to trace the template's glyph headless.
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
MENUS_RELATIVE_PATH = Path("user_help_plugin") / "menus.py"
LINE_LENGTH = 88
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
PACKAGE_IMPORTS_HEADER = "# Microdrop package imports.\n"

#: Inserted into a menus.py that has no Tutorials submenu yet.
TUTORIALS_BLOCK = """
#: Help > Tutorials entries: (menu title, built page). New entries are added by
#: examples/tutorials/new_tutorial.py.
TUTORIALS = (
)
"""
TUTORIALS_FACTORY = '''def tutorials_menu_factory():
    """Help > Tutorials: one entry per bundled tutorial page."""
    return SMenu(
        *[
            OpenWebViewDialogAction(
                name=f"{title.replace('&', '&&')}...",
                tooltip=f"Open the {title}",
                source=path,
                window_title=title,
            )
            for title, path in TUTORIALS
        ],
        id="tutorials_submenu",
        name="&Tutorials",
    )


'''


def tutorial_constant_name(slug):
    """Return the consts.py name of a tutorial's built page."""
    return f"{slug.upper()}_TUTORIAL_HTML_PATH"


def _fit(one_line, wrapped):
    """Return ``one_line`` when it fits ruff's line length, else ``wrapped``."""
    return one_line if len(one_line) <= LINE_LENGTH else wrapped


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
        text = _insert_path_import(text)

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


def _insert_path_import(text):
    """Put ``from pathlib import Path`` after the file's first import block."""
    lines = text.split("\n")
    indices = [i for i, line in enumerate(lines) if re.match(r"(import|from) ", line)]

    if not indices:
        return "from pathlib import Path\n" + text

    end = indices[0]

    while end + 1 < len(lines) and re.match(r"(import|from) ", lines[end + 1]):
        end += 1

    lines.insert(end + 1, "from pathlib import Path")

    return "\n".join(lines)


def _import_statements(block):
    """Split an import block into whole statements (parenthesised ones kept)."""
    statements = []
    current = []

    for line in block.splitlines(keepends=True):
        current.append(line)
        parenthesised = current[0].rstrip().endswith("(")

        if not parenthesised or line.strip() == ")":
            statements.append("".join(current))
            current = []

    return statements


def register_menu_entry(menus_path, plugin, slug, title):
    """Add the tutorial to ``TUTORIALS`` in menus.py, creating the Tutorials
    submenu when the file has none; return True when the file changed."""
    name = tutorial_constant_name(slug)
    text = menus_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    original = text

    if "TUTORIALS = (" not in text:
        text = _add_tutorials_submenu(text)

    if f"import {name}" not in text:
        text = _add_package_import(text, f"from {plugin}.consts import {name}\n")

    entry_start = text.index("TUTORIALS = (\n") + len("TUTORIALS = (\n")
    entry_end = text.index("\n)\n", entry_start - 1) + 1

    if not re.search(rf"\b{name}\b", text[entry_start:entry_end]):
        quoted = json.dumps(title, ensure_ascii=False)
        entry = _fit(
            f"    ({quoted}, {name}),\n",
            f"    (\n        {quoted},\n        {name},\n    ),\n",
        )
        text = text[:entry_end] + entry + text[entry_end:]

    if text == original:
        return False

    menus_path.write_text(text, encoding="utf-8", newline="\n")
    logger.info(f"Registered '{title}' in {menus_path}")

    return True


def _add_tutorials_submenu(text):
    anchors = (
        "logger = get_logger(__name__)\n",
        "def menu_factory():",
        'id="user_help_actions"',
    )

    for anchor in anchors:
        if anchor not in text:
            raise ValueError(
                f"menus.py has no '{anchor}' to anchor the Tutorials submenu"
            )

    text = text.replace(anchors[0], anchors[0] + TUTORIALS_BLOCK, 1)
    text = text.replace(anchors[1], TUTORIALS_FACTORY + anchors[1], 1)
    group_end = text.index(anchors[2])
    line_start = text.rindex("\n", 0, group_end) + 1
    indent = text[line_start:group_end]

    return (
        text[:line_start] + f"{indent}tutorials_menu_factory(),\n" + text[line_start:]
    )


def _add_package_import(text, statement):
    """Insert ``statement`` into the sorted Microdrop package imports block."""
    if PACKAGE_IMPORTS_HEADER not in text:
        raise ValueError("menus.py has no '# Microdrop package imports.' section")

    start = text.index(PACKAGE_IMPORTS_HEADER) + len(PACKAGE_IMPORTS_HEADER)
    end = text.index("\n\n", start) + 1
    statements = _import_statements(text[start:end]) + [statement]
    statements.sort(key=lambda line: line.split()[1])

    return text[:start] + "".join(statements) + text[end:]


def scaffold_tutorial(plugin, slug, title, root=SRC_ROOT, build=True):
    """Create, build and wire one tutorial; return the source path."""
    if not SLUG_PATTERN.match(slug):
        raise ValueError(f"Slugs are lower_snake_case identifiers: {slug!r}")

    plugin_dir = Path(root) / plugin
    consts_path = plugin_dir / "consts.py"

    if not consts_path.is_file():
        raise ValueError(f"{consts_path} does not exist")

    source = write_source(plugin_dir, slug, title)

    if build:
        build_tutorial(source)

    add_constant(consts_path, slug)
    register_menu_entry(Path(root) / MENUS_RELATIVE_PATH, plugin, slug, title)

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
