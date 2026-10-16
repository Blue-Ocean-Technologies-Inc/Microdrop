# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Build the HTML report (legacy contract): metadata, data-files,
data summary, data trends (plotly), device heatmap, media, notes.
Imports only shared utils + plotly — no protocol_grid coupling."""

# Standard library imports.
import html as _html
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Third-party imports.
import pandas as pd

# Microdrop package imports.
from pluggable_protocol_tree.services.logging.consts import RUN_TIMESTAMP_FMT
from pluggable_protocol_tree.services.logging.persistence import LoggingPersistence

# Logger import.
from logger.logger_service import get_logger

# Optional visualisation deps, hoisted to module top: a missing lib degrades
# the corresponding report section to a placeholder instead of failing import.
try:
    import plotly.express as px
    import plotly.graph_objects as go
except Exception:  # pragma: no cover
    px = None
    go = None
try:
    from microdrop_utils.plotly_helpers import (
        create_plotly_svg_dropbot_device_heatmap,
    )
except Exception:  # pragma: no cover
    create_plotly_svg_dropbot_device_heatmap = None

logger = get_logger(__name__)

_NUMERIC_EXCLUDE = {
    "step_idx",
    "utc_time",
    "instrument_time_us",
    "step_id",
    "actuated_channels",
}

#: Tukey fence multiplier: a sample is a per-step outlier when it lies more
#: than this many interquartile ranges outside its step's Q1..Q3.
_OUTLIER_IQR_FENCE = 1.5
#: Steps with fewer samples than this have no meaningful quartiles and are
#: kept whole by the outlier filter.
_OUTLIER_MIN_STEP_SAMPLES = 4
#: The fence half-width is never narrower than this fraction of the step's
#: median magnitude, so quantisation noise on a steady signal is not an
#: outlier.
_OUTLIER_MIN_FENCE_FRACTION = 0.01

# The report is static HTML with both the raw and the outlier-filtered views
# baked in (summary rows and chart traces), so the toggle swaps them
# client-side.
_OUTLIER_TOGGLE_HTML = (
    '<label class="outlier-toggle">'
    '<input type="checkbox" id="outlier-filter" autocomplete="off">'
    f" Exclude per-step outliers ({_OUTLIER_IQR_FENCE:g} × IQR)</label>"
    "<script>"
    "document.getElementById('outlier-filter')"
    ".addEventListener('change', function (e) {"
    "var on = e.target.checked;"
    "document.querySelectorAll('.outlier-raw')"
    ".forEach(function (el) { el.hidden = on; });"
    "document.querySelectorAll('.outlier-filtered')"
    ".forEach(function (el) { el.hidden = !on; });"
    "document.querySelectorAll('.trend-chart .js-plotly-plot')"
    ".forEach(function (div) {"
    "Plotly.restyle(div, {visible: [!on, on]}, [0, 1]);"
    "});"
    "});"
    "</script>"
)

# Metadata keys whose values are filesystem paths and should render as
# clickable file:// anchors instead of raw strings. Legacy parity with
# protocol_grid.services.protocol_data_logger.
_PATH_METADATA_KEYS = {"Experiment Directory", "Device SVG", "Protocol Path"}
#: Contributed metadata (PROTOCOL_LOGGING_METADATA_CONTRIBUTION) names a
#: path by its key's suffix, e.g. "PMT Captures Folder".
_PATH_METADATA_KEY_SUFFIXES = (" Directory", " Folder", " Path")


def _is_path_metadata_key(key) -> bool:
    return key in _PATH_METADATA_KEYS or str(key).endswith(_PATH_METADATA_KEY_SUFFIXES)


class LoggingReport:
    @staticmethod
    def build_html(
        *,
        entries: List[dict],
        columns: List[str],
        metadata: Dict,
        media: Dict[str, List[str]],
        device_context,
        notes: Optional[List[str]] = None,
        data_files: Optional[List] = None,
        column_notes: Optional[Dict[str, str]] = None,
    ) -> str:
        """Render the run report. ``column_notes`` maps a data column to a
        footnote shown under that column's trend chart."""
        # One outlier-filtered frame feeds both the summary and the trends,
        # so the single toggle (under the metadata) swaps them to the same set
        # of samples.
        df = pd.DataFrame(entries)
        filtered = LoggingReport._outlier_filtered(df, columns)
        has_steps = bool(entries) and "step_idx" in df

        sections = [
            LoggingReport._metadata_section(metadata, has_steps),
            LoggingReport._data_files_section(data_files or []),
            LoggingReport._summary_section(entries, columns, filtered),
            LoggingReport._trends_section(
                entries, columns, device_context, column_notes, filtered
            ),
            LoggingReport._media_section(media),
        ]
        if notes:
            sections.append(LoggingReport._notes_section(notes))
        body = "\n".join(s for s in sections if s)
        # NOTE: plotly.js is loaded from the CDN by the first plotly figure
        # itself (include_plotlyjs='cdn' in _trends_section / _heatmap), so
        # the bundle version always matches the installed Python plotly. Do
        # NOT add a hardcoded <script src=".../plotly-latest.min.js"> here:
        # that URL is pinned to plotly.js 1.x and cannot decode the typed-
        # array (bdata) output emitted by plotly >= 3.x, which silently
        # renders every chart as blank.
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<style>body{font-family:sans-serif;margin:24px;} "
            "table{border-collapse:collapse;} td,th{border:1px solid #ccc;"
            "padding:4px 8px;} "
            "summary{cursor:pointer;font-weight:bold;margin:12px 0 4px} "
            "details.section>summary{margin:20px 0 8px} "
            "summary>h2{display:inline;margin:0} "
            ".footnote{color:#666;font-size:small;margin:4px 0 8px} "
            ".outlier-toggle{display:block;font-size:small;margin:8px 0 0}"
            "</style></head><body>"
            f"<h1>Protocol Report</h1>{body}</body></html>"
        )

    @staticmethod
    def _metadata_section(metadata: Dict, has_steps: bool = False) -> str:
        """Render the metadata table; with step-indexed data, the page's
        single outlier toggle follows it as the section's last item."""
        rows = "".join(
            f"<tr><th>{_html.escape(str(k))}</th>"
            f"<td>{LoggingReport._format_metadata_value(k, v)}</td></tr>"
            for k, v in (metadata or {}).items()
        )
        toggle = _OUTLIER_TOGGLE_HTML if has_steps else ""

        return LoggingReport._section("Metadata", f"<table>{rows}</table>{toggle}")

    @staticmethod
    def _data_files_section(data_files: List) -> str:
        """Legacy-parity 'Data Files' section: clickable file:// link per
        artifact written this run (data_<t>.json / data_<t>.csv)."""
        if not data_files:
            return ""
        items = []
        for f in data_files:
            try:
                p = Path(f)
                uri = p.as_uri()
                items.append(
                    f'<li><a href="{_html.escape(uri, quote=True)}">'
                    f"{_html.escape(p.name)}</a></li>"
                )
            except (ValueError, OSError):
                items.append(f"<li>{_html.escape(str(f))}</li>")
        return LoggingReport._section("Data Files", f"<ul>{''.join(items)}</ul>")

    @staticmethod
    def _format_metadata_value(key, value) -> str:
        """HTML for a metadata cell. Path-valued keys render as clickable
        file:// anchors showing just the basename; everything else is
        escaped plain text. Path.as_uri() handles percent-encoding (spaces,
        non-ASCII, Windows backslashes); a non-absolute path falls back to
        the escaped string so this can never raise on test fixtures like
        Path('.')."""
        text = str(value)
        if not _is_path_metadata_key(key) or not text:
            return _html.escape(text)
        try:
            p = Path(text)
            uri = p.as_uri()
        except (ValueError, OSError):
            return _html.escape(text)
        return f'<a href="{_html.escape(uri, quote=True)}">{_html.escape(p.name)}</a>'

    @staticmethod
    def _numeric_columns(columns: List[str]) -> List[str]:
        return [c for c in columns if c not in _NUMERIC_EXCLUDE]

    @staticmethod
    def _summary_section(
        entries: List[dict],
        columns: List[str],
        filtered: Optional[pd.DataFrame] = None,
    ) -> str:
        """Render mean/std/min/max per numeric column, raw and outlier-filtered.

        Both bodies list the same columns so they line up; a column with no
        surviving samples in ``filtered`` gets a row of dashes.
        """
        if not entries:
            return LoggingReport._section("Data Summary", "<p>No data.</p>")

        df = pd.DataFrame(entries)

        if filtered is None:
            filtered = LoggingReport._outlier_filtered(df, columns)

        summary_cols = [
            c
            for c in LoggingReport._numeric_columns(columns)
            if c in df and pd.to_numeric(df[c], errors="coerce").notna().any()
        ]

        if not summary_cols:
            return LoggingReport._section("Data Summary", "<p>No numeric data.</p>")

        def rows(frame):
            html = ""

            for col in summary_cols:
                s = pd.to_numeric(frame[col], errors="coerce").dropna()
                stats = (s.mean(), s.std(), s.min(), s.max())
                cells = ["–"] * 4 if s.empty else [f"{v:.4g}" for v in stats]
                html += f"<tr><th>{_html.escape(col)}</th>"
                html += "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

            return html

        return LoggingReport._section(
            "Data Summary",
            "<table><thead><tr><th>Column</th><th>mean</th><th>std</th>"
            "<th>min</th><th>max</th></tr></thead>"
            f'<tbody class="outlier-raw">{rows(df)}</tbody>'
            f'<tbody class="outlier-filtered" hidden>{rows(filtered)}</tbody>'
            "</table>",
        )

    @staticmethod
    def _trends_section(
        entries: List[dict],
        columns: List[str],
        device_context,
        column_notes: Optional[Dict[str, str]] = None,
        filtered: Optional[pd.DataFrame] = None,
    ) -> str:
        if px is None:  # pragma: no cover
            return LoggingReport._section("Data Trends", "<p>plotly unavailable.</p>")
        if not entries:
            return LoggingReport._section("Data Trends", "<p>No data.</p>")
        df = pd.DataFrame(entries)
        if "step_idx" not in df.columns:
            return LoggingReport._section(
                "Data Trends", "<p>No step index in data.</p>"
            )

        if filtered is None:
            filtered = LoggingReport._outlier_filtered(df, columns)

        # Legacy parity: heatmap first (it represents the whole run), then a
        # per-quantity horizontal bar chart per step_id. First plotly figure
        # pulls in the version-correct plotly.js from the CDN; subsequent
        # figures reuse it. Never use plotly-latest.min.js (1.x) which can't
        # decode the typed-array output from plotly >= 3.x.
        heatmap = LoggingReport._heatmap(df, device_context, include_plotlyjs=True)
        plotly_js_emitted = bool(heatmap)

        # Steps are categorical along the y-axis: just the 1-indexed step
        # number ("Step 1", "Step 2", ...) — not the row uuid (step_id),
        # which is unreadable. Sort by step_idx descending so step 1
        # appears at the top of each chart, like the legacy report. Each bar
        # chart also carries a hidden outlier-filtered trace that the
        # page-level toggle swaps in; the heatmap sits outside .trend-chart,
        # so the toggle leaves it alone.
        trend_cols = [c for c in LoggingReport._numeric_columns(columns) if c in df]
        values = LoggingReport._numeric_frame(df, trend_cols)
        kept = LoggingReport._numeric_frame(filtered, trend_cols)

        # Outliers are whole rows, so every chart's filtered view drops the
        # same samples and the excluded count per step is shared.
        excluded_per_step = (
            values.groupby("step_idx")
            .size()
            .sub(kept.groupby("step_idx").size(), fill_value=0)
            .astype(int)
        )

        charts = []
        for col in trend_cols:
            if values[col].dropna().empty:
                continue

            agg = (
                values.groupby("step_idx")[col]
                .agg(["mean", "std"])
                .reset_index()
                .sort_values("step_idx", ascending=False)
            )
            agg["step_label"] = agg["step_idx"].apply(lambda i: f"Step {int(i)}")

            # Reindex onto the raw steps so both traces share categories; a
            # step that lost every sample stays in place as NaN.
            filtered_agg = (
                kept.groupby("step_idx")[col]
                .agg(["mean", "std"])
                .reindex(agg["step_idx"])
            )
            excluded = excluded_per_step.reindex(agg["step_idx"], fill_value=0)

            # No figure title: the collapsible section's summary names it.
            fig = px.bar(
                agg,
                x="mean",
                y="step_label",
                error_x="std",
                orientation="h",
                labels={"mean": f"Mean {col}", "step_label": "Protocol Steps"},
                template="plotly_white",
                color_discrete_sequence=["#17a2b8"],
            )
            fig.add_trace(
                go.Bar(
                    x=filtered_agg["mean"].to_numpy(),
                    y=agg["step_label"].to_numpy(),
                    error_x=dict(type="data", array=filtered_agg["std"].to_numpy()),
                    orientation="h",
                    marker_color="#17a2b8",
                    customdata=list(zip(filtered_agg["std"], excluded)),
                    hovertemplate=(
                        "Mean %{x:.4g} ± %{customdata[0]:.4g}<br>"
                        "%{customdata[1]} sample(s) excluded<extra></extra>"
                    ),
                    visible=False,
                    showlegend=False,
                )
            )
            fig.update_layout(
                # Overlay so the hidden filtered trace reserves no bar width.
                barmode="overlay",
                yaxis=dict(type="category", title="Protocol Steps"),
                xaxis=dict(title=f"Mean {col}"),
                margin=dict(l=20, r=20, t=20, b=20),
                # Grow height with step count so labels don't overlap.
                height=250 + (len(agg) * 35),
            )
            chart = fig.to_html(
                full_html=False,
                include_plotlyjs="cdn" if not plotly_js_emitted else False,
            )
            chart = f'<div class="trend-chart">{chart}</div>'

            note = (column_notes or {}).get(col)

            if note:
                chart += f'<p class="footnote">{_html.escape(note)}</p>'

            charts.append(LoggingReport._collapsible(col, chart))
            plotly_js_emitted = True

        return LoggingReport._section("Data Trends", heatmap + "".join(charts))

    @staticmethod
    def _numeric_frame(frame: pd.DataFrame, value_cols: List[str]) -> pd.DataFrame:
        """``step_idx`` plus ``value_cols`` coerced to numbers (junk -> NaN)."""
        return frame[["step_idx"]].assign(
            **{c: pd.to_numeric(frame[c], errors="coerce") for c in value_cols}
        )

    @staticmethod
    def _outlier_filtered(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
        """The rows of ``df`` that survive the per-step outlier filter over
        every numeric column present; ``df`` unchanged without a step index."""
        if "step_idx" not in df:
            return df

        value_cols = [c for c in LoggingReport._numeric_columns(columns) if c in df]
        kept = LoggingReport._without_step_outliers(
            LoggingReport._numeric_frame(df, value_cols), value_cols
        )

        return df.loc[kept.index]

    @staticmethod
    def _without_step_outliers(df: pd.DataFrame, value_cols: List[str]) -> pd.DataFrame:
        """Drop every row that is a per-step outlier in any of ``value_cols``.

        An outlier sample is excluded from every trend, not only the column
        where it was spotted, so derived columns stay consistent with their
        inputs. Each column's fence comes from that step's own quartiles,
        ``Q1 - reach <= v <= Q3 + reach`` with ``reach = k*IQR`` but never
        below ``_OUTLIER_MIN_FENCE_FRACTION`` of the step's median magnitude.
        A NaN never marks a row, and a column with fewer than
        ``_OUTLIER_MIN_STEP_SAMPLES`` values in a step marks nothing there;
        identical values (IQR 0) sit on the fence and are all kept.
        """
        outlier = pd.Series(False, index=df.index)

        for col in value_cols:
            values = df[col]
            by_step = values.groupby(df["step_idx"])

            q1 = by_step.transform("quantile", 0.25)
            q3 = by_step.transform("quantile", 0.75)
            floor = _OUTLIER_MIN_FENCE_FRACTION * by_step.transform("median").abs()
            reach = (_OUTLIER_IQR_FENCE * (q3 - q1)).clip(lower=floor)

            outside = ~values.between(q1 - reach, q3 + reach)
            judged = values.notna() & (
                by_step.transform("count") >= _OUTLIER_MIN_STEP_SAMPLES
            )
            outlier |= outside & judged

        return df[~outlier]

    @staticmethod
    def _section(title: str, content: str) -> str:
        """Wrap a top-level report section in an open fold headed by an h2."""
        return (
            '<details open class="section">'
            f"<summary><h2>{_html.escape(title)}</h2></summary>{content}</details>"
        )

    @staticmethod
    def _collapsible(title: str, content: str) -> str:
        """Wrap a chart in a section the reader can fold away. Rendered open:
        plotly sizes a chart from its container, and one first drawn inside a
        closed <details> gets zero width."""
        return (
            f"<details open><summary>{_html.escape(title)}</summary>{content}</details>"
        )

    @staticmethod
    def _heatmap(
        df: pd.DataFrame, device_context, *, include_plotlyjs: bool = False
    ) -> str:
        svg = getattr(device_context, "device_svg_path", None)
        if not svg or "actuated_channels" not in df:
            return ""
        durations = LoggingReport._channel_durations_seconds(df)
        if not durations or create_plotly_svg_dropbot_device_heatmap is None:
            return ""
        try:
            # Defaults ("Actuation Times" / "seconds") trigger the helper's
            # format_time_tooltip auto-scaling (sec --> min --> hours). Passing
            # "s" instead of "seconds" disables it and shows raw floats.
            fig = create_plotly_svg_dropbot_device_heatmap(str(svg), durations)
            chart = fig.to_html(
                full_html=False, include_plotlyjs="cdn" if include_plotlyjs else False
            )

            return LoggingReport._collapsible("Device actuation heatmap", chart)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"heatmap generation failed: {e}")
            return ""

    @staticmethod
    def _channel_durations_seconds(df: pd.DataFrame) -> Dict[int, float]:
        """Estimate total actuation time per channel, in seconds.

        Direct port of legacy ``protocol_data_logger._get_channel_duration``:
        explode the per-row ``actuated_channels`` list, count samples per
        channel, multiply by the mean sample interval over the rollover-
        corrected ``instrument_time_us`` series (mean uses ``fillna(0)`` so
        the leading NaN from ``.diff()`` is treated as a zero-step gap —
        same biased average the legacy report ships).
        """
        if (
            "actuated_channels" not in df.columns
            or "instrument_time_us" not in df.columns
            or df.empty
        ):
            return {}
        # Reuse the persistence rollover correction so the heatmap agrees
        # with the on-disk corr_instrument_time_us in the data file.
        corr = LoggingPersistence._correct_rollover(df["instrument_time_us"].tolist())
        if not corr or len([v for v in corr if v is not None]) < 2:
            return {}
        df = df.assign(_corr_us=corr)
        avg_interval_s = (
            float(df.sort_values("_corr_us")["_corr_us"].diff().fillna(0).mean()) * 1e-6
        )
        if avg_interval_s <= 0:
            return {}
        counts = (
            df.explode("actuated_channels")["actuated_channels"]
            .dropna()
            .astype(int)
            .value_counts()
        )
        return {
            int(ch): float(round(n * avg_interval_s, 6))
            for ch, n in counts.to_dict().items()
        }

    @staticmethod
    def _media_section(media: Dict[str, List[str]]) -> str:
        """Render legacy-parity Media Captures with thumbnails and
        click-to-play video placeholders. Mirrors
        protocol_data_logger._get_files_summary."""
        videos = media.get("video", []) or []
        images = media.get("image", []) or []
        others = media.get("other", []) or []
        if not (videos or images or others):
            return ""
        out = []
        if videos:
            out.append("<h3>Video Captures</h3>")
            out.append(LoggingReport._media_items(videos, kind="video"))
        if images:
            out.append("<h3>Image Captures</h3>")
            out.append(LoggingReport._media_items(images, kind="image"))
        if others:
            out.append("<h3>Other Captures</h3>")
            out.append(LoggingReport._media_items(others, kind="other"))
        return LoggingReport._section("Media Captures", "".join(out))

    @staticmethod
    def _media_items(paths: List[str], *, kind: str) -> str:
        """Numbered list of <a>basename</a> + (image thumbnail | video
        play-button placeholder | nothing) per item. ``kind`` is one of
        "image" / "video" / "other"."""
        parts = []
        for idx, p in enumerate(paths, start=1):
            try:
                file_url = Path(p).as_uri()
            except (ValueError, OSError):
                file_url = ""
            display_name = Path(p).name if p else ""
            link_html = (
                f'<a href="{_html.escape(file_url, quote=True)}">'
                f"{_html.escape(display_name)}</a>"
                if file_url
                else _html.escape(str(p))
            )
            extra = ""
            if file_url and kind == "image":
                extra = (
                    f'<br><br><img src="{_html.escape(file_url, quote=True)}"'
                    f' width="360" height="240">'
                )
            elif file_url and kind == "video":
                # Click swaps the placeholder div for a <video> tag,
                # matching the legacy report. Single-quoted inner HTML
                # so the outer double-quotes stay valid.
                safe_url = _html.escape(file_url, quote=True)
                extra = (
                    "<br><br>"
                    "<div onclick=\"this.outerHTML='"
                    "<video width=&quot;360&quot; height=&quot;240&quot;"
                    " controls autoplay>"
                    f"<source src=&quot;{safe_url}&quot;"
                    " type=&quot;video/x-matroska&quot;>"
                    "Your browser does not support the video tag."
                    "</video>'\" "
                    'style="cursor:pointer;width:360px;height:240px;'
                    "background:#000;display:flex;align-items:center;"
                    'justify-content:center;">'
                    '<div style="font-size:50px;color:white;">&#9658;</div>'
                    "</div>"
                )
            parts.append(f"<b>{idx}.</b> {link_html}{extra}<br><br>")
        return "".join(parts)

    @staticmethod
    def _notes_section(notes: List[str]) -> str:
        items = "".join(f"<li>{_html.escape(str(n))}</li>" for n in notes)
        return LoggingReport._section("Notes", f"<ul>{items}</ul>")

    @staticmethod
    def write_report(experiment_dir, html: str) -> Path:
        reports_dir = Path(experiment_dir) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime(RUN_TIMESTAMP_FMT)
        path = reports_dir / f"report_{stamp}.html"
        path.write_text(html, encoding="utf-8")
        return path
