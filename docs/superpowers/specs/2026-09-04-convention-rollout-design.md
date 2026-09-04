# Convention enforcement rollout across the MicroDrop repos

Date: 2026-09-04. Status: draft for review.

Microdrop milestone 9 ("Convention enforcement") is implemented in PRs #654 to
#659: ruff gate, import-section stamper, import-linter contract, handler
dispatch startup check, and a unit-test CI job. This spec extends the same
enforcement to the other repos in the organisation and decides how the shared
pieces are distributed so they do not drift.

## Scope

In scope, in delivery order:

1. `microdrop-dev-hooks`: a new repo that owns the shared pre-commit hooks.
2. `microdrop-plugin-template`: a new copier template that owns the shared
   config files of a plugin repo.
3. `heater-microdrop-plugin-py`, `magnet-microdrop-plugin-py`,
   `fluorescence-microdrop-plugin-py`: retrofitted from the template, one PR
   each.
4. `pixi-microdrop` and `microdrop-launcher`: direct sweep, one PR each.
5. Microdrop follow-ups: switch its own config to the hook repo, add the
   handler check to `PeripheralDeviceControllerBase`.

Out of scope: `dropbot.py` (upstream conventions), a new-plugin scaffold in
the template (the template starts tooling-only; scaffolding is additive
later), fixing the 139 unit tests that fail on Microdrop `main`, and any
change to the plugins' own pixi environments.

## Findings the design rests on

Surveyed 2026-09-04 from fresh clones of `main`.

- The three plugin repos are one skeleton already: byte-identical
  `conventional-commits.yml`, `publish.yml`, and `.pre-commit-config.yaml`
  (commitizen, check-ast, merge-conflict, large-files, scratch block); the same
  pyproject shape; the same three-package layout (`<device>_controller`,
  `<device>_controls_ui` or `_ui`, `<device>_protocol_controls`).
- None has ruff, pytest config, AGENTS.md, or copyright headers. Ruff dry run:
  fluorescence 172 findings / 117 files to reformat, heater 363 / 51, magnet
  147 / 31. Zero of 235 files carry the header.
- Plugins do not register Dramatiq listeners themselves. Backends subclass
  `PeripheralDeviceControllerBase` (Microdrop), UI panes use
  `template_status_and_controls.BaseMessageHandler`, which gained a `topics`
  trait in #659. Dispatch is reflective (`on_<topic>_request`).
- Plugins are tested from the `pixi-microdrop` workspace, cloned recursively
  so the `src` submodule is present, with the plugin repos cloned under
  `microdrop-py/<plugin>`. The workspace's editable `microdrop_py` install
  exposes every `src/` package through a `.pth`, and `python -m pytest` run
  from a plugin directory puts the plugin's own packages on the path via the
  working directory. Microdrop is not a package, so a plugin repo has no
  standalone environment and does not need one.
- Cross-repo imports are mostly legitimate: shared packages
  (`microdrop_utils`, `microdrop_style`, `logger`,
  `template_status_and_controls`, `peripheral_device_controller_base`) and the
  protocol-tree framework. Only magnet imports other Microdrop plugins, and
  only their `consts`. Fluorescence has an import cycle between its own UI and
  protocol-controls packages.
- `pixi-microdrop` has two Python files, `microdrop-launcher` has one
  stdlib-only script and no pixi manifest. Both are two or three ruff findings
  from clean and lack the header.

## Component 1: `microdrop-dev-hooks`

A small public repo in the organisation. pre-commit's native sharing model:
consumer repos reference it by `rev`, a fix ships once.

Contents:

- `.pre-commit-hooks.yaml` exposing
  - `stamp-import-sections`: the script from Microdrop `tools/` (moved here,
    Microdrop then consumes it like everyone else). `language: python`,
    `types: [python]`. Reads section order from the consumer's `ruff.toml`.
  - `forbid-scratch-files`: the `language: fail` hook with the current
    pattern.
- `ruff-base.toml`: the Microdrop `ruff.toml` (line length, target, `CPY001`
  regex, the isort custom sections). Ruff cannot extend a remote file, so the
  template and the sweeps copy it; the hook repo is the single place it is
  edited, and `copier update` propagates it to plugins.
- `copyright-header.txt`: the header text used by the `insert-license` hook.
- Tagged releases (`v0.1.0`, ...) driven by commitizen like the other repos.

Not owned here: ruff itself (consumers use `astral-sh/ruff-pre-commit` pinned
to the same `>=0.16,<0.17` line as the Microdrop manifest) and copyright
insertion (consumers use `Lucas-C/pre-commit-hooks` `insert-license` with
`--license-filepath` pointing at a repo-local copy of the header; nothing to
own).

## Component 2: `microdrop-plugin-template`

A copier template with the same mechanics as `scibots-package-template`:
`[[ ]]` / `[% %]` delimiters so GitHub `${{ }}` survives, `.copier-answers.yml`,
`_templates_suffix: .jinja`, a `scripts/extract_answers.py` that derives the
answers for an existing plugin from its `pyproject.toml` and
`microdrop_plugin.toml`, and a `scripts/bootstrap.py` that applies the
template to a list of repos.

Questions (defaults derived where possible):

| Question | Type | Notes |
|---|---|---|
| `package_name` | str | conda name, e.g. `heater-microdrop-plugin` |
| `device_label` | str | human label for `microdrop_plugin.toml` |
| `backend_package`, `ui_package`, `protocol_package` | str | the three top-level packages |
| `backend_entry_point` | str | e.g. `heater = "heater_controller"` |
| `run_dependencies` | yaml | device-specific conda run deps |
| `optional_extras` | yaml | fluorescence's `ai = ["osam"]`; default empty |
| `extra_listeners` | yaml | heater's `*_plot_listener`; default empty |
| `has_redis_gated_tests` | bool | magnet's `tests_with_redis_server_need/` |
| `large_file_exclude` | str | fluorescence's `^ASI_SDK/`; default empty |
| `version` | str | current version, for `pyproject.toml` |

Files owned by the template:

- `pyproject.toml.jinja`: current skeleton, unchanged in substance. The pixi
  workspace section is left as it is today; the plugin repo is not an
  environment.
- `microdrop_plugin.toml.jinja`: current two-group shape.
- `ruff.toml`: copied from the hook repo's `ruff-base.toml`.
- `.pre-commit-config.yaml.jinja`: commitizen, pre-commit-hooks, ruff check
  and format, `insert-license`, then the hook repo's two hooks, then
  `import-linter` (`repo: local`, `pass_filenames: false`).
- `.importlinter.jinja`: see contract below.
- `.github/workflows/conventional-commits.yml`, `publish.yml`: current
  files, made templates only where the package name appears.
- `.github/workflows/unit-tests.yml.jinja`: see CI below.
- `AGENTS.md.jinja`: short. Says the code style is Microdrop's `AGENTS.md`
  (linked), then the plugin-specific facts: the three packages and what each
  owns, the test partitions, how to run tests from `pixi-microdrop`, the
  release rule that only conventional commits publish.
- `.gitignore`, `CHANGELOG.md.j2`, `LICENSE` header file.

Import-linter contract for a plugin (root packages: its own three packages,
`include_external_packages = true`):

- `forbidden`: the plugin's packages must not import Microdrop plugin
  internals. Forbidden modules are the Microdrop plugin packages
  (`device_viewer`, `dropbot_controller`, `dropbot_tools_menu`,
  `microdrop_application`, `dropbot_protocol_controls`, ...), with
  `ignore_imports` allowing `** -> <pkg>.consts` and
  `** -> microdrop_application.helpers`, `** -> microdrop_application.dialogs.**`.
  Shared packages and `pluggable_protocol_tree` are not forbidden.
- `layers`: `protocol_package` and `ui_package` above `backend_package`,
  and `ui_package` and `protocol_package` independent of each other.
  Fluorescence's cycle is seeded as explicit debt so its list can shrink.

Unit-test CI for a plugin (`unit-tests.yml`): on `pull_request` and pushes to
`main`. Steps, mirroring the local workflow exactly:

1. `actions/checkout` of `pixi-microdrop` at `master` with
   `submodules: recursive`, so `microdrop-py/src` is populated.
2. `actions/checkout` of the plugin's commit at `microdrop-py/<repo-name>`,
   the path the local clones use.
3. `prefix-dev/setup-pixi` with `manifest-path: microdrop-py/pyproject.toml`
   and `environments: test` (`ubuntu-24.04-arm`, same lock constraint as
   Microdrop's job). The editable `microdrop_py` install makes the `src/`
   packages importable.
4. `pixi run --manifest-path microdrop-py/pyproject.toml -e test python -m
   pytest -q` with `working-directory: microdrop-py/<repo-name>` and
   `QT_QPA_PLATFORM=offscreen`, ignoring `**/tests_with_redis_server_need`
   and `**/tests_with_dropbot_connection_need` by glob. The working directory
   puts the plugin's packages on `sys.path`; no install step is needed.

The `test` environment is defined in the `pixi-microdrop` manifest (see
Component 4): the base stack plus `src`, without the plugin packages that the
default environment pulls from the `microdrop-plugins` channel. That way the
plugin checkout under test is the only copy of itself in the environment,
which matters for magnet, whose released package is a default dependency.
Local runs use the same `-e test` flag, so CI and the desk workflow stay one
command.

## Component 3: plugin retrofit (three PRs)

Per plugin, after the Microdrop PRs merge and the hook repo and template
exist:

1. `copier copy --trust` with answers from `extract_answers.py`; reconcile the
   diff against the existing files (they are near-identical, so the diff is
   the new files plus the pre-commit additions).
2. One-shot `ruff format` and `ruff check --fix` over the whole repo, then
   hand-fix the residue (mostly E501 in comments, E402, a few W605/E721/E712).
   The repos are small with one maintainer, so incremental adoption would
   only prolong it. The pre-commit stamper then adds headers file by file as
   they are touched; a one-shot stamp is also acceptable here for the same
   reason.
3. `insert-license` run once over all files to add the copyright header.
4. Pass `topics=ACTOR_TOPIC_DICT[<listener>]` in each UI message-handler
   factory, mirroring #659.
5. Seed `.importlinter` until `lint-imports` is green; the debt list is part
   of the PR so review sees the real coupling.
6. Commits by concern: template application, format sweep, headers, lint
   residue, topics wiring, import-linter.

## Component 4: launcher repos (two PRs)

`pixi-microdrop`: add `ruff.toml` (copy of `ruff-base.toml`), extend the root
`.pre-commit-config.yaml` with ruff check and format, `insert-license`, the
hook repo's two hooks; add headers to the two Python files; a `unit-tests`
job is not needed since the two tests import the Microdrop plugin stack and
Microdrop's own job covers that environment. `import-linter` (`==2.14`) is
added to `[tool.pixi.dependencies]` here, which is the manifest change #655
asks for.

The same PR adds the `test` environment: the plugin channel packages
(currently `magnet-microdrop-plugin`) move from `[tool.pixi.dependencies]`
into a `plugins` feature, and `[tool.pixi.environments]` declares
`default = ["plugins"]` and `test = []` in one solve group, so the lock stays
consistent and the default environment is unchanged for users. `pixi.lock`
is relocked and committed in the same PR. Because the plugin CI jobs depend
on this environment, the `pixi-microdrop` PR moves ahead of the plugin PRs
in the sequence.

`microdrop-launcher`: add `.pre-commit-config.yaml` (commitizen, ruff check
and format, `insert-license`, scratch block) and `ruff.toml`; add the header
and trailing newline. No pixi manifest, no pytest config: pre-commit installs
ruff in its own environment, so the stdlib-only constraint holds.

## Component 5: Microdrop follow-ups

- Switch `.pre-commit-config.yaml` to the hook repo for the stamper and the
  scratch block; delete `tools/stamp_import_sections.py` and move its tests
  to the hook repo.
- `PeripheralDeviceControllerBase.traits_init` runs
  `assert_handlers_exist_for_topics` against the subclass's
  `ACTOR_TOPIC_DICT`, the same way `DropbotControllerBase` does after #659, so
  plugin backends get the check without any change in their repos.
- Issue for `dropbot_tools_menu`'s hand-written listener (drops
  `SELF_TESTS_PROGRESS`, dead `DROPBOT_CONNECTED` branch) and for
  `manual_controls` never clearing its message queue.

## Sequencing

1. Merge #654 to #659 (order: 654, 655, 656, 659, 658, 657).
2. Create `microdrop-dev-hooks`, move the stamper, tag `v0.1.0`.
3. Microdrop follow-up PR: consume the hook repo, peripheral base check.
4. `pixi-microdrop` PR: ruff and hooks sweep, `import-linter` dependency,
   the `test` environment and relock. The plugin CI jobs need it merged.
5. Create `microdrop-plugin-template`, verify with a dry run against a
   scratch clone of heater (the messiest).
6. Three plugin PRs, one at a time, heater first so the template's rough
   edges surface on the hardest case.
7. `microdrop-launcher` PR.

Each PR is reviewed and merged by the maintainer; nothing is force-pushed to
`main` anywhere.

## Risks and decisions taken

- **Plugin test failures on `main`** are unknown until the job first runs;
  the plugin repos cannot run pytest standalone today. The job starts with
  `continue-on-error: true` like Microdrop's and is flipped to a gate once
  each repo is green.
- **arm64 runner**: inherited from #656 because the lock has no `linux-64`.
  If #656's review adds `linux-64` to the manifest, the template's job follows
  without change since it uses the same setup.
- **One-shot format in plugins** conflicts with open branches there. Check
  `gh pr list` per repo before the sweep and rebase or merge those first.
- **copier-astral** was rejected earlier for colliding with pixi and
  commitizen; this template is house-built and reuses the sci-bots template's
  proven mechanics, so that decision stands.
- **Hook repo versioning**: consumers pin a `rev`; `pre-commit autoupdate`
  or `copier update` bumps it. The template's `.pre-commit-config.yaml` is
  therefore the one place the pin is edited for all plugins.
