# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Stamp AGENTS.md's labeled import-section headers onto staged files.

Ruff's isort already sorts every module's imports into the sections
configured in ``ruff.toml`` (``[lint.isort.sections]`` /
``section-order``); ruff has no way to emit the labeled comment header
AGENTS.md requires above each group, so this script does that mechanical
step as a ``repo: local`` pre-commit hook run *after* the ruff hooks.

The script reads ``ruff.toml`` with :mod:`tomllib` so the section
classification (which top-level module belongs to which named section) has
exactly one source of truth; nothing here duplicates ``ruff.toml``'s package
lists. Only the module-level import block at the top of a file is touched --
function-local imports and anything after the first non-import statement are
left alone.

Usage::

    python tools/stamp_import_sections.py [--check] FILE [FILE ...]

Without ``--check`` files are rewritten in place and the script exits ``1``
if anything changed (the pre-commit convention: modify, then fail so the
author re-stages). With ``--check`` nothing is written; the script lists
files that would change and exits ``1`` if there are any -- this doubles as
the validator, since re-running on an already-stamped file is a no-op.
"""

# Standard library imports.
import argparse
import ast
import sys
import tomllib
from pathlib import Path

#: Canonical header text for each isort section key, per AGENTS.md's
#: "Import Ordering" list. There is no equivalent in ruff.toml -- the label
#: wording is a documentation choice, not something ruff configures -- so
#: this mapping is the one place it is hardcoded.
SECTION_HEADERS = {
    "standard-library": "# Standard library imports.",
    "third-party": "# Third-party imports.",
    "enthought": "# Enthought library imports.",
    "first-party": "# Microdrop package imports.",
    "microdrop-style": "# Microdrop style imports.",
    "microdrop-utils": "# Microdrop utils imports.",
    "local-folder": "# Local imports.",
    "logger": "# Logger import.",
}

#: Reverse lookup, used to recognize a line as *some* section header when
#: scanning for stale/leftover ones -- regardless of which section it names.
_HEADER_TEXTS = set(SECTION_HEADERS.values())


class IsortConfig:
    """The parts of ``ruff.toml``'s isort configuration we need.

    Parameters
    ----------
    section_order : list of str
        ``[lint.isort] section-order``, e.g. ``["future", "standard-library",
        ...]``. The ``"future"`` entry is ignored -- ``from __future__``
        imports sit in the preamble, before the block this script manages.
    sections : dict
        ``[lint.isort.sections]`` -- maps a custom section name to the list
        of top-level module names that belong to it (e.g.
        ``{"enthought": ["traits", "pyface", ...]}``).
    """

    def __init__(self, section_order, sections):
        self.section_order = [s for s in section_order if s != "future"]
        self.sections = sections

        #: top-level module name -> custom section key, built once so
        #: classification is a dict lookup rather than a repeated scan.
        self._module_to_section = {}
        for section_name, modules in sections.items():
            for module in modules:
                self._module_to_section[module] = section_name

    def custom_section_for(self, top_level_module):
        """Return the custom section key for a top-level module, or None."""
        return self._module_to_section.get(top_level_module)


def load_isort_config(ruff_toml_path):
    """Build an :class:`IsortConfig` from a ``ruff.toml`` file."""
    with open(ruff_toml_path, "rb") as fh:
        data = tomllib.load(fh)

    isort_cfg = data.get("lint", {}).get("isort", {})
    section_order = isort_cfg.get(
        "section-order",
        ["future", "standard-library", "third-party", "local-folder"],
    )
    sections = isort_cfg.get("sections", {})
    return IsortConfig(section_order, sections)


def find_repo_root(start_path):
    """Walk upward from `start_path` to find the directory holding ruff.toml."""
    current = Path(start_path).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "ruff.toml").is_file():
            return candidate
    # Fall back to the starting directory -- callers may pass an explicit
    # config anyway (e.g. tests using a scratch tree).
    return current


def is_first_party(top_level_module, repo_root):
    """Does `top_level_module` resolve to a source root under `repo_root`?

    Mirrors ruff's own first-party detection for ``src = ["."]``: a module
    is first-party if a package directory or a ``.py`` module of that name
    exists at the repository root.
    """
    return (repo_root / top_level_module).is_dir() or (
        repo_root / f"{top_level_module}.py"
    ).is_file()


def classify_import(node, config, repo_root):
    """Return the isort section key for an `ast.Import`/`ast.ImportFrom` node."""
    if isinstance(node, ast.ImportFrom) and node.level > 0:
        return "local-folder"

    if isinstance(node, ast.ImportFrom):
        top_level = (node.module or "").split(".")[0]
    else:
        top_level = node.names[0].name.split(".")[0]

    custom = config.custom_section_for(top_level)
    if custom is not None:
        return custom

    if top_level in sys.stdlib_module_names:
        return "standard-library"

    if is_first_party(top_level, repo_root):
        return "first-party"

    return "third-party"


def _is_gap_line(line):
    """Blank, or an exact section-header comment -- safe to discard/regenerate."""
    stripped = line.strip()
    return stripped == "" or stripped in _HEADER_TEXTS


def _find_module_body_bounds(tree):
    """Return (import_start, import_end) indices into `tree.body`.

    Skips a leading module docstring and any leading ``from __future__``
    imports, then finds the contiguous run of top-level ``Import``/
    ``ImportFrom`` statements that follows -- that run is the block this
    script owns.
    """
    body = tree.body
    idx = 0

    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        idx = 1

    while idx < len(body) and (
        isinstance(body[idx], ast.ImportFrom) and body[idx].module == "__future__"
    ):
        idx += 1

    import_start = idx
    while idx < len(body) and isinstance(body[idx], (ast.Import, ast.ImportFrom)):
        idx += 1

    return import_start, idx


def stamp_source(source, config, repo_root):
    """Return `source` with the import-section block stamped, and whether it changed."""
    tree = ast.parse(source)
    import_start, import_end = _find_module_body_bounds(tree)

    if import_start == import_end:
        # No module-level imports to organize -- nothing to stamp.
        return source, False

    lines = source.splitlines(keepends=True)
    import_nodes = tree.body[import_start:import_end]

    # Walk backward from the first import statement over blank lines and
    # stale/misplaced section headers to find where the managed block
    # actually begins; anything before that (copyright header, docstring,
    # a genuine comment) is left untouched.
    first_lineno = import_nodes[0].lineno  # 1-indexed
    block_start = first_lineno - 1  # 0-indexed line to start replacing from
    while block_start > 0 and _is_gap_line(lines[block_start - 1]):
        block_start -= 1

    block_end = import_nodes[-1].end_lineno  # 0-indexed exclusive == end_lineno

    # Group statements by section, preserving each statement's own relative
    # order but placing groups in ruff.toml's canonical section-order --
    # this is what makes the stamper self-correcting against stale/misplaced
    # headers, not just header text.
    groups = {section: [] for section in config.section_order}
    for node in import_nodes:
        section = classify_import(node, config, repo_root)
        statement_text = "".join(lines[node.lineno - 1 : node.end_lineno]).rstrip("\n")
        groups.setdefault(section, []).append(statement_text)

    rebuilt_groups = []
    for section in config.section_order:
        statements = groups.get(section) or []
        if not statements:
            continue
        header = SECTION_HEADERS.get(section)
        group_lines = ([header] if header else []) + statements
        rebuilt_groups.append("\n".join(group_lines))

    new_block = "\n\n".join(rebuilt_groups)
    if block_start > 0:
        # Separate the block from whatever precedes it (copyright header,
        # docstring, future imports) with exactly one blank line.
        new_block = "\n" + new_block

    new_lines = lines[:block_start] + [new_block + "\n"] + lines[block_end:]
    new_source = "".join(new_lines)
    return new_source, new_source != source


def process_file(path, config, repo_root, check_only):
    """Stamp one file. Returns True if it changed (or would change)."""
    source = path.read_text(encoding="utf-8")
    try:
        new_source, changed = stamp_source(source, config, repo_root)
    except SyntaxError as exc:
        print(f"{path}: skipped (SyntaxError: {exc})", file=sys.stderr)
        return False

    if changed and not check_only:
        path.write_text(new_source, encoding="utf-8")

    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="list files that would change and exit non-zero; do not rewrite",
    )
    args = parser.parse_args(argv)

    changed_files = []
    for file_path in args.files:
        if file_path.suffix != ".py":
            continue
        repo_root = find_repo_root(file_path)
        config = load_isort_config(repo_root / "ruff.toml")
        if process_file(file_path, config, repo_root, args.check):
            changed_files.append(file_path)

    if changed_files:
        verb = "would be reformatted" if args.check else "reformatted"
        for file_path in changed_files:
            print(f"{file_path}: {verb}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
