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
Ratchet on production-file line counts, so god files (#615) stop growing
before they get split.

``tools/file_length_baseline.json`` records the line count of every
production ``*.py`` file already over ``THRESHOLD`` lines. This script,
wired as the ``file-length-ratchet`` pre-commit hook, fails staged files
that grew past their baseline, warns on new files that start out over the
threshold, and lets a file shrink freely (with a hint to lower its
baseline). The baseline can only move down on its own; moving it up is a
manual edit to the JSON file, visible in review (#643).

Run with ``--update`` to rescan the whole tree and rewrite the baseline:
existing entries only ever go down (or are dropped once a file falls back
under the threshold), new over-threshold files are added.
"""

# Standard library imports.
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "tools" / "file_length_baseline.json"

#: Lines a production file may reach before it needs a baseline entry.
THRESHOLD = 500

#: Directory name components excluded from the ratchet entirely: test
#: suites and demo scripts are expected to run long and aren't the god
#: files #615 is about. (The vendored portable driver this mirrors from
#: AGENTS.md's style-exclusion policy is gone from this tree — #dropbot-
#: portable-package-imports — so there is nothing to list here yet; add its
#: directory back if it returns.)
EXCLUDED_DIR_NAMES = {"tests", "demos"}


def is_excluded(path):
    """Return whether `path` (repo-relative, forward slashes) is exempt."""
    parts = path.split("/")[:-1]

    return any(
        part in EXCLUDED_DIR_NAMES or part.startswith("tests_with_") for part in parts
    )


def _tracked_py_files():
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.splitlines()


def _normalize(arg):
    """Turn a hook/CLI argument into a repo-relative, forward-slash path."""
    path = Path(arg)

    if path.is_absolute():
        try:
            path = path.relative_to(REPO_ROOT)
        except ValueError:
            pass

    return path.as_posix()


def count_lines(path):
    """Return the line count of `path` (repo-relative), or None if unreadable."""
    try:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    return len(text.splitlines())


def load_baseline():
    if not BASELINE_PATH.exists():
        return {}

    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def save_baseline(baseline):
    lines = json.dumps(baseline, indent=2, sort_keys=True) + "\n"
    BASELINE_PATH.write_text(lines, encoding="utf-8")


def classify(path, current, baseline_lines):
    """Compare one file's current length against its baseline entry.

    Returns a ``(kind, path, current, baseline_lines)`` tuple where `kind`
    is one of ``"growth"``, ``"new_over_threshold"``, ``"shrink"``, or
    `None` when the file needs no comment.
    """

    if baseline_lines is not None:
        if current > baseline_lines:
            return ("growth", path, current, baseline_lines)

        if current < baseline_lines:
            return ("shrink", path, current, baseline_lines)

        return None

    if current > THRESHOLD:
        return ("new_over_threshold", path, current, None)

    return None


def format_finding(finding, blocking):
    kind, path, current, baseline_lines = finding

    if kind == "growth":
        tag = "FAIL" if blocking else "WARN"
        delta = current - baseline_lines
        header = (
            f"[{tag}] {path}: {current} lines, baseline is {baseline_lines} (+{delta})"
        )
        body = (
            "  Already over the file-length guardrail (#615) and grew instead of "
            "shrinking. Extract before adding more, or if the growth is genuinely "
            "deliberate, raise its entry in tools/file_length_baseline.json in this "
            "commit with a reason in the commit message."
        )

        if not blocking:
            body += (
                "\n  (Guardrail is warning-only for one release per #643; it will "
                "start failing commits after that.)"
            )

        return f"{header}\n{body}"

    if kind == "new_over_threshold":
        header = (
            f"[WARN] {path}: {current} lines, no baseline yet "
            f"(threshold is {THRESHOLD})"
        )
        body = (
            "  New file already above the file-length guardrail (#615). Consider "
            "splitting it now, or accept the size by running "
            "`python tools/check_file_length_ratchet.py --update` to add it to "
            "tools/file_length_baseline.json."
        )

        return f"{header}\n{body}"

    # kind == "shrink"
    delta = baseline_lines - current
    header = f"[INFO] {path}: {current} lines, baseline is {baseline_lines} (-{delta})"
    body = (
        "  Nice shrink! Lower its baseline by running "
        "`python tools/check_file_length_ratchet.py --update`."
    )

    return f"{header}\n{body}"


def check_files(paths, baseline, blocking):
    """Classify each staged path; return (findings, exit_code)."""
    findings = []

    for path in paths:
        if is_excluded(path):
            continue

        current = count_lines(path)

        if current is None:
            continue

        finding = classify(path, current, baseline.get(path))

        if finding is not None:
            findings.append(finding)

    blocking_growth = blocking and any(finding[0] == "growth" for finding in findings)

    return findings, (1 if blocking_growth else 0)


def update_baseline():
    """Rescan the whole tree; lower or add entries, never raise one."""
    baseline = load_baseline()
    updated = {}

    for path in _tracked_py_files():
        if is_excluded(path):
            continue

        current = count_lines(path)

        if current is None or current <= THRESHOLD:
            continue

        previous = baseline.get(path)
        updated[path] = min(previous, current) if previous is not None else current

    added = sorted(set(updated) - set(baseline))
    lowered = sorted(p for p in updated if p in baseline and updated[p] < baseline[p])
    dropped = sorted(set(baseline) - set(updated))

    save_baseline(updated)

    for path in added:
        print(f"added {path}: {updated[path]} lines")

    for path in lowered:
        print(f"lowered {path}: {baseline[path]} -> {updated[path]} lines")

    for path in dropped:
        print(f"dropped {path}: fell to or under {THRESHOLD} lines, or was deleted")

    if not (added or lowered or dropped):
        print("baseline already up to date")

    return 0


def main(argv):
    if argv[:1] == ["--update"]:
        return update_baseline()

    paths = [_normalize(arg) for arg in argv if arg.endswith(".py")]
    baseline = load_baseline()

    # Warning-only for one release after #643 lands; flip to True once the
    # team has seen a cycle of its messages. See format_finding() above.
    blocking = False

    findings, exit_code = check_files(paths, baseline, blocking)

    for finding in findings:
        print(format_finding(finding, blocking))

    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
