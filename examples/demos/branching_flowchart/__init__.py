"""Standalone branching-protocol flowchart UX demo.

Run from the repo root:

    python -m examples.demos.branching_flowchart

Pure PySide6 + stdlib — no envisage/traits/dramatiq/redis. The executor in
``executor.py`` mirrors the hook/bucket/pause/stop logic of
``pluggable_protocol_tree/execution/executor.py`` and adds the one new
concept under test: decision-based routing between steps, drawn by the
user on a node-graph canvas.
"""
