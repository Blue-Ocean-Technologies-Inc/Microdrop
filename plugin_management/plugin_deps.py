"""Parse a plugin archive's pyproject.toml dependency tables and check which
declared deps are missing from the current environment.

Qt-free, pure data. Mirrors the main env's pyproject shape: conda specs from
[tool.pixi.dependencies], PyPI specs from [project.dependencies] +
[tool.pixi.pypi-dependencies]. Only string version values are converted to
specs; dict values (channel/path/editable) contribute just the bare name
(lossy — noted as a limitation)."""

import importlib.metadata as importlib_metadata
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Union


@dataclass
class PluginDependencies:
    conda: List[str] = field(default_factory=list)
    pypi: List[str] = field(default_factory=list)


def _table_spec(name, value):
    """A pixi/conda or PyPI MatchSpec from a manifest table entry."""
    if isinstance(value, str) and value not in ("", "*"):
        return f"{name}{value}"
    return name


def _load(source: Union[str, bytes, Path]) -> dict:
    if isinstance(source, (str, Path)) and Path(str(source)).exists():
        return tomllib.loads(Path(source).read_text(encoding="utf-8"))
    if isinstance(source, bytes):
        return tomllib.loads(source.decode("utf-8"))
    return tomllib.loads(str(source))


def read_plugin_dependencies(source: Union[str, bytes, Path]) -> PluginDependencies:
    """Parse conda + PyPI deps from a plugin pyproject.toml. Missing file or
    tables → empty lists. Never raises for an absent file."""
    if isinstance(source, Path) and not source.exists():
        return PluginDependencies()
    try:
        data = _load(source)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return PluginDependencies()

    pixi = (data.get("tool") or {}).get("pixi") or {}
    conda_table = pixi.get("dependencies") or {}
    conda = [_table_spec(n, v) for n, v in conda_table.items()]

    pypi = list((data.get("project") or {}).get("dependencies") or [])
    pypi_table = pixi.get("pypi-dependencies") or {}
    pypi += [_table_spec(n, v) for n, v in pypi_table.items()]
    return PluginDependencies(conda=conda, pypi=pypi)


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _dep_name(spec: str) -> str:
    """The bare package name from a MatchSpec / PEP 508 string."""
    return re.split(r"[<>=!~;\s\[]", spec.strip(), 1)[0]


def _installed_dist_names() -> set:
    names = set()
    for dist in importlib_metadata.distributions():
        name = dist.metadata["Name"] if dist.metadata else None
        if name:
            names.add(_normalize(name))
    return names


def unsatisfied(deps: PluginDependencies) -> List[str]:
    """Declared deps NOT present as an installed distribution in the current
    process. Errs toward 'unsatisfied' (conda pkgs without dist-info, name
    mismatches) so at worst we offer an unnecessary relaunch — never the
    reverse."""
    installed = _installed_dist_names()
    missing = []
    for spec in list(deps.conda) + list(deps.pypi):
        name = _normalize(_dep_name(spec))
        if name and name not in installed:
            missing.append(spec)
    return missing
