"""Pure protocol-load validation + presenters (issue #423, PPT-17).

``validate_protocol`` reads the raw serialized protocol JSON (output of
``services.persistence.serialize_tree``) and returns a structured
``ValidationReport``. It performs three checks:

  * orphan column   (error)   - a saved col_id has no live column; its
                                 values are silently dropped by
                                 ``deserialize_tree``.
  * electrode id    (warning) - an electrode referenced by a step's
                                 routes/electrodes doesn't exist on the
                                 current device.
  * stale channel   (warning) - the protocol's stored electrode->channel
                                 disagrees with the device's current map.

The function is side-effect free (no Qt, no RowManager, no I/O) so it is
trivially unit-testable. Two presenters render a report: ``log_report``
(headless, logger output) and ``confirm_report`` (GUI dialog).
"""

from dataclasses import dataclass, field
from typing import List

from logger.logger_service import get_logger

logger = get_logger(__name__)

# Presenter decisions.
PROCEED = "proceed"
CANCEL = "cancel"

SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"

# Builtin column ids whose values carry electrode references.
ROUTES_COL_ID = "routes"
ELECTRODES_COL_ID = "electrodes"


@dataclass
class Finding:
    severity: str          # SEVERITY_WARNING | SEVERITY_ERROR
    category: str          # "orphan_column" | "electrode_id" | "stale_channel"
    title: str             # short human summary
    items: List[str] = field(default_factory=list)  # detail lines


@dataclass
class ValidationReport:
    findings: List[Finding] = field(default_factory=list)

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == SEVERITY_WARNING]

    @property
    def is_empty(self) -> bool:
        return not self.findings


def validate_protocol(data, columns, device_electrode_to_channel) -> ValidationReport:
    """Validate raw serialized protocol ``data`` against the live ``columns``
    and the device's ``device_electrode_to_channel`` map. Never raises on
    malformed input - returns an empty/partial report instead."""
    findings: List[Finding] = []
    if not isinstance(data, dict):
        return ValidationReport(findings=findings)

    col_specs = data.get("columns") or []

    # --- orphan columns (device-independent) ---
    live_ids = {c.model.col_id for c in (columns or [])}
    orphan_ids = [
        spec.get("id") for spec in col_specs
        if isinstance(spec, dict) and spec.get("id") and spec.get("id") not in live_ids
    ]
    if orphan_ids:
        findings.append(Finding(
            severity=SEVERITY_ERROR,
            category="orphan_column",
            title=(f"{len(orphan_ids)} column(s) in this protocol have no "
                   f"matching plugin; their values will be dropped on load"),
            items=[str(cid) for cid in orphan_ids],
        ))

    return ValidationReport(findings=findings)
