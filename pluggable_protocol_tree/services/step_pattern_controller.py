# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Opens the Fill Pattern dialog on the tree's selection and applies it.

Two or more selected steps: the pattern is fitted onto them. One selected
step: new steps are inserted after it. Nothing selected: new steps are
appended to the protocol, copied from its last step.
"""

# Enthought library imports.
from traits.api import Callable, HasTraits, Instance

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import error, information
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.models.step_pattern_model import StepPatternModel
from pluggable_protocol_tree.services.step_pattern import (
    apply_pattern_to_steps,
    discover_pattern_fields,
    insert_pattern_steps,
    last_step_path,
    selected_steps_in_order,
)
from pluggable_protocol_tree.views.step_pattern_view import step_pattern_view

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class StepPatternController(HasTraits):
    """Builds the dialog model from the selection, shows it, applies OK."""

    #: The protocol tree the pattern edits.
    manager = Instance(RowManager)

    #: ``is_editable(column, row) -> bool`` — supplied by the Qt tree view,
    #: which owns the item-flag vocabulary.
    is_editable = Callable()

    def open(self, parent=None):
        """Run the dialog; return the paths of any newly created steps."""
        step_paths = selected_steps_in_order(self.manager)
        model = self._build_model(step_paths)

        if model is None:
            information(
                parent=parent,
                title="Fill Pattern",
                message="No numeric step columns are available to fill.",
                cancel=False,
            )

            return []

        ui = model.edit_traits(view=step_pattern_view, parent=parent)

        if not ui.result:
            return []

        try:
            return self._apply(model, step_paths)
        except Exception as exc:
            logger.exception(f"Fill Pattern failed: {exc}")
            error(parent=parent, title="Fill Pattern", message=f"{exc}")

            return []

    def _build_model(self, step_paths):
        """Dialog model for ``step_paths``, or None when no field qualifies."""
        fields = discover_pattern_fields(
            self.manager.columns, self.manager.step_type, self.is_editable
        )

        if not fields:
            return None

        # With nothing selected, new steps copy the last step: prefill from it.
        seed_path = last_step_path(self.manager)
        seed_paths = step_paths or ([seed_path] if seed_path is not None else [])
        rows = [self.manager.get_row(path) for path in seed_paths]

        current_values = {
            field.col_id: [getattr(row, field.col_id) for row in rows]
            for field in fields
        }

        return StepPatternModel(
            current_values=current_values,
            fit_count=len(step_paths),
            fields=fields,
        )

    def _apply(self, model, step_paths):
        if model.is_fit:
            apply_pattern_to_steps(self.manager, step_paths, model.field, model.values)
            logger.info(
                f"Fill Pattern set {model.field.col_id} on {len(step_paths)} steps: "
                f"{model.values}"
            )

            return []

        anchor_path = step_paths[0] if step_paths else None
        new_paths = insert_pattern_steps(
            self.manager,
            anchor_path,
            model.field,
            model.values,
            group_name=model.new_group_name,
        )
        logger.info(
            f"Fill Pattern created {len(new_paths)} steps for "
            f"{model.field.col_id}: {model.values}"
        )

        return new_paths
