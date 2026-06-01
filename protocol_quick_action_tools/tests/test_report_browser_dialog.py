"""Smoke tests for the ported ReportBrowserDialog: constructor accepts
a list of path strings, populates a sortable tree of (Name, Size, Date),
filters by name in the search box, and opens the selected report via
QDesktopServices when the user activates a row."""

from protocol_quick_action_tools.views.report_browser_dialog import (
    ReportBrowserDialog,
)


def test_dialog_populates_one_row_per_path(qapp, tmp_path):
    a = tmp_path / "report_a.html"; a.write_text("a", encoding="utf-8")
    b = tmp_path / "report_b.html"; b.write_text("bb", encoding="utf-8")
    dlg = ReportBrowserDialog([str(a), str(b)])
    assert dlg._tree.topLevelItemCount() == 2


def test_dialog_handles_empty_list_without_crashing(qapp):
    """No reports yet -> open with an empty table; no rows shown."""
    dlg = ReportBrowserDialog([])
    assert dlg._tree.topLevelItemCount() == 0


def test_search_box_hides_non_matching_rows(qapp, tmp_path):
    a = tmp_path / "alpha.html"; a.write_text("a", encoding="utf-8")
    b = tmp_path / "beta.html"; b.write_text("b", encoding="utf-8")
    dlg = ReportBrowserDialog([str(a), str(b)])
    dlg._apply_filter("alph")
    visible = [
        dlg._tree.topLevelItem(i).text(0)
        for i in range(dlg._tree.topLevelItemCount())
        if not dlg._tree.topLevelItem(i).isHidden()
    ]
    assert visible == ["alpha.html"]


def test_format_size_threshold_branches():
    fs = ReportBrowserDialog._format_size
    assert fs(900) == "900 B"
    assert fs(2048) == "2.0 KB"
    assert fs(5 * 1024 * 1024) == "5.0 MB"


def test_open_item_calls_qdesktopservices(qapp, tmp_path, monkeypatch):
    """Double-click / Open routes through QDesktopServices.openUrl."""
    from protocol_quick_action_tools.views import report_browser_dialog as mod
    opened = []
    monkeypatch.setattr(mod.QDesktopServices, "openUrl",
                        lambda url: opened.append(url))
    p = tmp_path / "report.html"; p.write_text("", encoding="utf-8")
    dlg = ReportBrowserDialog([str(p)])
    item = dlg._tree.topLevelItem(0)
    dlg._open_item(item)
    assert len(opened) == 1
    from pathlib import Path
    assert Path(opened[0].toLocalFile()).resolve() == Path(str(p)).resolve()
