"""What a legacy protocol conversion mapped, dropped, and could not resolve.

Counts are per-step so the summary can say how much data a dropped field
actually represented, rather than just naming it.
"""

from traits.api import Dict, HasTraits, Int, List, Str


class ConversionReport(HasTraits):
    """Accumulated outcome of converting one legacy protocol."""

    step_count = Int(0)
    mapped_columns = List(Str())
    dropped_fields = Dict(Str(), Int())
    unresolved_electrode_ids = Dict(Str(), Int())
    failed_steps = List(Str())

    def record_mapped(self, column_id: str) -> None:
        if column_id not in self.mapped_columns:
            self.mapped_columns.append(column_id)

    def record_dropped(self, legacy_field: str) -> None:
        self.dropped_fields[legacy_field] = (
            self.dropped_fields.get(legacy_field, 0) + 1)

    def record_unresolved_electrode(self, electrode_id: str) -> None:
        self.unresolved_electrode_ids[electrode_id] = (
            self.unresolved_electrode_ids.get(electrode_id, 0) + 1)

    def record_step_failure(self, description: str) -> None:
        self.failed_steps.append(description)

    def render(self) -> str:
        """Human-readable summary for the post-import dialog."""
        lines = [f"Converted {self.step_count} steps."]
        if self.mapped_columns:
            lines.append("")
            lines.append("Mapped: " + ", ".join(sorted(self.mapped_columns)))
        if self.dropped_fields:
            lines.append("")
            lines.append("Dropped (no equivalent in this build):")
            for field, count in sorted(self.dropped_fields.items()):
                lines.append(f"    {field}  ({count} steps)")
        if self.unresolved_electrode_ids:
            lines.append("")
            lines.append("Electrodes not present in the selected device:")
            for electrode_id, count in sorted(
                    self.unresolved_electrode_ids.items()):
                lines.append(f"    {electrode_id}  ({count} steps)")
        if self.failed_steps:
            lines.append("")
            lines.append("Steps imported with defaults after an error:")
            for description in self.failed_steps:
                lines.append(f"    {description}")
        return "\n".join(lines)
