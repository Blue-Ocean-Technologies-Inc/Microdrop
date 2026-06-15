"""Execution-only lifecycle handlers.

These are IColumnHandler implementations with no column/view, attached to
the executor's ``lifecycle_handlers`` list. They run once-per-run policy
(via on_pre_protocol_start / on_post_protocol_end) at high priority so they
trail every real column's hooks.
"""
