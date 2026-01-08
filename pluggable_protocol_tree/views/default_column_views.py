"""Columns that are permanently shown by default"""

from pluggable_protocol_tree.views.base_column_views import StringViewOnlyColumnView


class IDView(StringViewOnlyColumnView):

    def format_display(self, value, step):
        indices = []
        current_step = step

        while current_step.parent:
            try:
                # Add 1 because users expect 1-based indexing
                idx = current_step.parent.children.index(current_step) + 1
                indices.insert(0, str(idx))
            except ValueError:
                break
            current_step = current_step.parent

        return ".".join(indices) if indices else ""

    def create_editor(self, parent, context):
        return None
