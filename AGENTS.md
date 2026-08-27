# AGENTS.md — Microdrop

Microdrop is a plugin-based GUI for digital microfluidics instruments
(DropBot, OpenDrop, Portable DropBot). It is built on the Enthought Tool
Suite — Envisage plugins, Traits/TraitsUI models, Pyface — with PySide6/Qt
widgets and a Dramatiq + Redis pub/sub message layer between frontend and
hardware backends.

Architecture, message topics, and plugin patterns are documented in
`docs/CLAUDE.md`, `MESSAGES.md`, and `DRAMATIQ_DOCS.md`. This file covers
the working environment and the code style.

## Repository Layout

Plugin packages live at the repo root, one directory per Envisage plugin
(`device_viewer/`, `dropbot_controller/`, `pluggable_protocol_tree/`,
`portable_dropbot_controller/`, …), plus the shared support packages
`microdrop_utils/`, `microdrop_style/`, and `logger/`. Run scripts and
cross-plugin tests are in `examples/`; docs and design specs in `docs/`.

This repo is normally checked out as the `microdrop-py/src` submodule of
the `pixi-microdrop` launcher repo, which owns the environment. The heater,
magnet, and fluorescence plugins for the classic DropBot rig live in their
own repos and are deliberately not part of this tree.

## Environment

The environment is managed by **pixi** from `microdrop-py/` in the outer
repo (`pyproject.toml` is the pixi manifest, `pixi.lock` the lockfile).
Run everything through it — the interpreter in `.pixi/envs/default` has
the right Qt/numpy DLL setup that a bare `python` does not:

```bash
cd microdrop-py
pixi run python -m examples.run_device_viewer_pluggable   # full app
```

Run modules with `-m` from `src/` rather than by file path, so package
imports resolve without `sys.path` surprises. Redis must be running before
the app starts (`redis-server`, or `python examples/start_redis_server.py`).

After changing dependencies in `pyproject.toml`, relock with `pixi install`
(or `pixi lock`) and commit `pixi.lock` alongside it.

## Dependencies

Runtime pins live in `[tool.pixi.dependencies]` in `microdrop-py/pyproject.toml`.
The core stack: `traits`, `traitsui`, `pyface`, `envisage`, `apptools`
(Enthought); `pyside6` (Qt); `dramatiq`, `redis-py` (messaging); `shapely`,
`pydantic`, `numpy`/`pandas` (data). Consult the manifest rather than this
list for versions.

## Testing

Tests use plain **pytest** functions and are partitioned by external needs:

- pure unit tests: `tests/` subpackages next to the code, and `examples/tests/`
- `tests_with_redis_server_need/` — require a running Redis
- `tests_with_dropbot_connection_need/` — require physical hardware

GUI imports construct a `QApplication`; run headless with
`QT_QPA_PLATFORM=offscreen pixi run pytest <path>`.

**Agent guidance — keep verification light.** The maintainer evaluates
changes quickly in the running GUI. The standard check for touched files is
compile + format:

```bash
pixi run python -m py_compile <files>
pixi run ruff format --check <files>
pixi run ruff check <files>
```

Do not run the pytest suite or write ad-hoc smoke scripts unless asked.
When a change genuinely needs a regression test (pure logic, message
routing), add a focused pytest in the right partition.

## Linting and Formatting

Style is enforced by **ruff** — both formatter and linter, one config:

```bash
pixi run ruff format .        # black-compatible formatting
pixi run ruff check --fix .   # lint + import sorting
```

Key settings (`ruff.toml` at the repo root):

- **Line length**: 88 (ruff's default); **target**: py312
- **Lint rules**: `CPY001` (copyright header), `E`, `F`, `W`, `I` (import
  sorting)
- **Import sections**: custom sections mirror the ordering below, so the
  import layout is machine-enforced, not just documented
- **ruff version**: pinned `>=0.16,<0.17` in the pixi manifest — ruff
  changes formatting in minor releases, so raising the bound means
  reformatting in the same change

**Adoption is incremental.** The legacy codebase is not yet ruff-clean, and
there was deliberately no big-bang reformat (it would conflict with every
open branch). The pre-commit hooks run only on staged files, so each file
is brought clean as it is touched. Run ruff on the files you changed, never
repo-wide.

## Code Style Guidelines

### Copyright Header

Every non-empty `.py` file starts with the standard header, enforced by
ruff's `CPY001` rule (the regex in `ruff.toml` accepts any year range —
state the years the file was created/last substantially revised):

```python
# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!
```

The vendored portable driver keeps its upstream provenance and is excluded.

### Import Ordering

Imports are grouped into sections, each introduced by a **labeled comment
header**, in this order:

1. `# Standard library imports.`
2. `# Third-party imports.` (`PySide6`, `shapely`, `dramatiq`, `numpy`, …)
3. `# Enthought library imports.` (`apptools`, `envisage`, `pyface`,
   `traits`, `traitsui`)
4. `# Microdrop package imports.` — other Microdrop packages
   (`device_viewer`, `dropbot_controller`, …)
5. `# Microdrop style imports.` — `microdrop_style`, always its own chunk
6. `# Microdrop utils imports.` — `microdrop_utils`, always its own chunk
7. `# Local imports.` — relative imports
8. `# Logger import.` — `logger`, always last

Ruff's isort sorts imports *into* these sections but cannot generate the
headers — write them yourself (only for the sections a module actually
has); ruff preserves them in place, the same way envisage maintains theirs.

The module-setup globals sit immediately after the imports, closing the
prologue: the logger first, then the Redis app-globals manager where the
module uses it, then module constants.

```python
# Standard library imports.
import json
from pathlib import Path

# Third-party imports.
from shapely.geometry import Polygon

# Enthought library imports.
from pyface.qt import QtWidgets
from traits.api import HasTraits, Instance, Str, observe
from traitsui.api import Item, View

# Microdrop package imports.
from device_viewer.models.electrodes import Electrodes
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Microdrop style imports.
from microdrop_style.colors import GREY, WHITE
from microdrop_style.icons.icons import ICON_DELETE

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from .consts import PKG

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()
```

Always import Enthought packages from their `.api` modules
(`from traits.api import ...`, never `from traits.has_traits import ...`).

### Type System

Typing is done through the **Traits type system**, not PEP 484 annotations —
do not add annotations to signatures or variables in traits-based code.

- Prefer `HasTraits` models over plain classes or dataclasses
- Use precise trait types; prefer `Union`/`Either` over `Any`
- Wire reactions with `@observe` decorators using extended trait names —
  never imperative `.observe()` calls
- Reuse an existing trait or Qt signal when the state already carries the
  information; don't add a parallel one
- Voltage (V) and frequency (Hz) are `Int` end-to-end, never `Float`

### Naming Conventions

- **Classes**: `PascalCase` — `DeviceViewerPlugin`, `ZoneLayerManager`
- **Interfaces**: `I`-prefix — `IDropbotControlMixinService`
- **Functions/methods**: `snake_case`, descriptive over terse —
  `capture_electrode_ids_touching`, not `capture_ids`
- **Private methods/traits**: single leading underscore
- **Constants**: `UPPER_SNAKE_CASE`, defined in the plugin's `consts.py`
- **Module logger**: always `logger = get_logger(__name__)` from
  `logger.logger_service` — never stdlib `logging.getLogger`
- Never mint a new name or constant when an existing one already expresses
  the value

### Docstrings

- Imperative mood, concise: `"""Run the application."""`
- PEP 257 plus NumPy-style `Parameters`/`Returns` sections where a signature
  genuinely needs them; skip boilerplate sections that restate the obvious
- Class attributes — traits especially — are documented with `#:` comments
  above the declaration, not in the class docstring
- Documentation should be clear and concise; a docstring that says what the
  name already says is noise

### Trait Documentation

```python
#: SOURCE OF TRUTH for the region — ids of the member electrodes.
electrode_ids = List(Str)
```

### Error Handling

- Report failures through the module logger: `logger.error(...)` for
  handled failures, `logger.exception(...)` when catching and re-raising
- User-facing errors go through `microdrop_application.dialogs.pyface_wrapper`
  dialogs — never a raw `QMessageBox`
- Never swallow an exception silently; a bare `except: pass` needs a comment
  explaining why ignoring is correct
- Mark known issues with a lowercase `# fixme:` comment carrying a GitHub
  issue reference

### String Formatting

**f-strings everywhere**, including logger calls:
`logger.info(f"Loaded device SVG {svg_path}")`. Do not use `%`-style or
`.format()` in new code.

### Readability

- Organize code into logical chunks separated by blank lines; whitespace is
  structure, not decoration
- Clean, elegant, human-readable code beats clever compression
- Comments state constraints the code cannot show — not what the next line
  does, and not the history of the change
- Match the surrounding file's idiom, comment density, and layout

### Architecture Conventions

- **Design first**: lean on established software design principles and
  patterns — separation of concerns above all, plus the patterns the app is
  already built from (MVC, observer via Traits, dependency injection via
  Envisage services, pub/sub via Dramatiq). Reach for the fitting pattern
  before inventing structure.
- **MVC split**: Qt-free `HasTraits` models; controllers translate signals
  into model changes or published topics; views observe the model. Views are
  the volatile layer — view preferences change often — so keep business
  logic out of them entirely, and make every view instantiable standalone
  against just its model (no plugin/app scaffolding) so it can be prototyped
  and tested alone.
- **TraitsUI first**: build views with TraitsUI/Pyface abstractions
  (`View`/`Item`/`Group`, editors, Handlers); drop to raw Qt widgets only
  when TraitsUI genuinely cannot express the widget or behavior. When raw Qt
  is needed, import it through the binding shim —
  `from pyface.qt import QtCore, QtGui, QtWidgets` — never `from PySide6...`
  directly in new code (existing PySide6 imports are converted as files are
  touched, not in sweeps).
- **Decoupling**: plugins never call each other directly — communicate via
  Dramatiq pub/sub topics or the Redis app-globals hash
- Every plugin has a `consts.py` with `PKG`, its topics, and
  `ACTOR_TOPIC_DICT`
- Styling goes through `microdrop_style/` helpers (colors, button styles,
  icon fonts)

## Commits, PRs, and Changelog

- **Conventional Commits**, CI-enforced: `type(scope): subject` with types
  `feat`/`fix`/`refactor`/`perf`/`docs`/`ci`/`chore`/`test`
- Small, single-purpose commits scoped with explicit pathspecs; never one
  bulk commit for iterative work
- Branch per issue; never commit directly to `main`
- A PR created with agent assistance must say so in its description
- `CHANGELOG.md` is generated by commitizen from the commit messages — do
  not edit it by hand
