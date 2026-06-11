"""GUI presenter for protocol-load ``ValidationReport``s (issue #423, PPT-17).

View-layer counterpart to ``services.protocol_validator.log_report``: shows
one two-tier summary dialog over a report. Lives in views — not in the
validator service — because it pulls in Qt via the pyface dialog wrapper,
and the service layer must stay Qt-free.
"""

from microdrop_application.dialogs.pyface_wrapper import confirm


def _format_html(report) -> str:
    parts = []
    if report.errors:
        parts.append("<b>Errors</b><br>")
        parts.extend(f"&bull; {f.title}<br>" for f in report.errors)
    if report.warnings:
        parts.append("<b>Warnings</b><br>")
        parts.extend(f"&bull; {f.title}<br>" for f in report.warnings)
    return "".join(parts)


def _format_detail(report) -> str:
    lines = []
    for f in report.errors + report.warnings:
        lines.append(f"[{f.severity.upper()}] {f.title}")
        lines.extend(f"    - {item}" for item in f.items)
        lines.append("")
    return "\n".join(lines).rstrip()


def confirm_report(report, parent=None) -> int:
    """GUI presenter: one two-tier summary dialog. Returns the pyface
    confirm() code - YES means proceed with the load, anything else means
    cancel it.

    Uses exactly two buttons - a proceed button (yes_label) and Cancel - by
    passing no_label="" to suppress confirm()'s default No button. When errors
    are present the proceed button is the explicit drop-columns override."""
    if report.errors:
        title = "Protocol has errors"
        proceed_label = "Load anyway (drop columns)"
    else:
        title = "Protocol warnings"
        proceed_label = "Proceed anyway"
    return confirm(
        parent,
        message="",
        title=title,
        cancel=True,
        yes_label=proceed_label,
        no_label="",
        cancel_label="Cancel",
        informative=_format_html(report),
        detail=_format_detail(report),
    )
