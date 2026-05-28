"""Build the HTML report (legacy contract): metadata, data-files,
data summary, data trends (plotly), device heatmap, media, notes.
Imports only shared utils + plotly — no protocol_grid coupling."""

import html as _html
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from logger.logger_service import get_logger

logger = get_logger(__name__)

_NUMERIC_EXCLUDE = {"step_idx", "utc_time", "instrument_time_us",
                    "step_id", "actuated_channels"}

# Metadata keys whose values are filesystem paths and should render as
# clickable file:// anchors instead of raw strings. Legacy parity with
# protocol_grid.services.protocol_data_logger.
_PATH_METADATA_KEYS = {"Experiment Directory", "Device SVG", "Protocol Path"}


class LoggingReport:
    @staticmethod
    def build_html(*, entries: List[dict], columns: List[str],
                   metadata: Dict, media: Dict[str, List[str]],
                   device_context, notes: Optional[List[str]] = None) -> str:
        sections = [
            LoggingReport._metadata_section(metadata),
            LoggingReport._summary_section(entries, columns),
            LoggingReport._trends_section(entries, columns, device_context),
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
            "padding:4px 8px;}</style></head><body>"
            f"<h1>Protocol Report</h1>{body}</body></html>"
        )

    @staticmethod
    def _metadata_section(metadata: Dict) -> str:
        rows = "".join(
            f"<tr><th>{_html.escape(str(k))}</th>"
            f"<td>{LoggingReport._format_metadata_value(k, v)}</td></tr>"
            for k, v in (metadata or {}).items()
        )
        return f"<h2>Metadata</h2><table>{rows}</table>"

    @staticmethod
    def _format_metadata_value(key, value) -> str:
        """HTML for a metadata cell. Path-valued keys render as clickable
        file:// anchors showing just the basename; everything else is
        escaped plain text. Path.as_uri() handles percent-encoding (spaces,
        non-ASCII, Windows backslashes); a non-absolute path falls back to
        the escaped string so this can never raise on test fixtures like
        Path('.')."""
        text = str(value)
        if key not in _PATH_METADATA_KEYS or not text:
            return _html.escape(text)
        try:
            p = Path(text)
            uri = p.as_uri()
        except (ValueError, OSError):
            return _html.escape(text)
        return (f'<a href="{_html.escape(uri, quote=True)}">'
                f"{_html.escape(p.name)}</a>")

    @staticmethod
    def _numeric_columns(columns: List[str]) -> List[str]:
        return [c for c in columns if c not in _NUMERIC_EXCLUDE]

    @staticmethod
    def _summary_section(entries: List[dict], columns: List[str]) -> str:
        if not entries:
            return "<h2>Data Summary</h2><p>No data.</p>"
        df = pd.DataFrame(entries)
        rows = ""
        for col in LoggingReport._numeric_columns(columns):
            if col not in df:
                continue
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if s.empty:
                continue
            rows += (f"<tr><th>{_html.escape(col)}</th>"
                     f"<td>{s.mean():.4g}</td><td>{s.std():.4g}</td>"
                     f"<td>{s.min():.4g}</td><td>{s.max():.4g}</td></tr>")
        if not rows:
            return "<h2>Data Summary</h2><p>No numeric data.</p>"
        return ("<h2>Data Summary</h2><table>"
                "<tr><th>Column</th><th>mean</th><th>std</th>"
                f"<th>min</th><th>max</th></tr>{rows}</table>")

    @staticmethod
    def _trends_section(entries: List[dict], columns: List[str], device_context) -> str:
        try:
            import plotly.express as px
        except Exception:                      # pragma: no cover
            return "<h2>Data Trends</h2><p>plotly unavailable.</p>"
        if not entries:
            return "<h2>Data Trends</h2><p>No data.</p>"
        df = pd.DataFrame(entries)
        if "step_idx" not in df.columns:
            return "<h2>Data Trends</h2><p>No step index in data.</p>"
        charts = []
        plotly_js_emitted = False
        for col in LoggingReport._numeric_columns(columns):
            if col not in df:
                continue
            s = pd.to_numeric(df[col], errors="coerce")
            if s.dropna().empty:
                continue
            agg = df.assign(_v=s).groupby("step_idx")["_v"].agg(["mean", "std"]).reset_index()
            fig = px.bar(agg, x="step_idx", y="mean", error_y="std", title=col)
            # First chart pulls the version-correct plotly.js from the CDN;
            # subsequent charts reuse it. Never use plotly-latest.min.js.
            charts.append(fig.to_html(
                full_html=False,
                include_plotlyjs="cdn" if not plotly_js_emitted else False))
            plotly_js_emitted = True
        heatmap = LoggingReport._heatmap(
            df, device_context, include_plotlyjs=not plotly_js_emitted)
        return "<h2>Data Trends</h2>" + "".join(charts) + heatmap

    @staticmethod
    def _heatmap(df: pd.DataFrame, device_context, *,
                 include_plotlyjs: bool = False) -> str:
        svg = getattr(device_context, "device_svg_path", None)
        if not svg or "actuated_channels" not in df:
            return ""
        counts: Dict[int, int] = {}
        for chans in df["actuated_channels"]:
            for ch in (chans or []):
                counts[int(ch)] = counts.get(int(ch), 0) + 1
        try:
            from microdrop_utils.plotly_helpers import (
                create_plotly_svg_dropbot_device_heatmap,
            )
            fig = create_plotly_svg_dropbot_device_heatmap(
                str(svg), counts,
                quant_title="Actuation Count", quant_units="count")
            return ("<h3>Device actuation heatmap</h3>"
                    + fig.to_html(
                        full_html=False,
                        include_plotlyjs="cdn" if include_plotlyjs else False))
        except Exception as e:                 # pragma: no cover - defensive
            logger.warning(f"heatmap generation failed: {e}")
            return ""

    @staticmethod
    def _media_section(media: Dict[str, List[str]]) -> str:
        vids = "".join(
            f"<video controls width='320' src='{_html.escape(p)}'></video>"
            for p in media.get("video", []))
        imgs = "".join(
            f"<img width='320' src='{_html.escape(p)}'>"
            for p in media.get("image", []))
        others = "".join(
            f"<li>{_html.escape(p)}</li>" for p in media.get("other", []))
        if not (vids or imgs or others):
            return ""
        return (f"<h2>Media Captures</h2>{vids}{imgs}"
                f"{'<ul>' + others + '</ul>' if others else ''}")

    @staticmethod
    def _notes_section(notes: List[str]) -> str:
        items = "".join(f"<li>{_html.escape(str(n))}</li>" for n in notes)
        return f"<h2>Notes</h2><ul>{items}</ul>"

    @staticmethod
    def write_report(experiment_dir, html: str) -> Path:
        reports_dir = Path(experiment_dir) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = reports_dir / f"report_{stamp}.html"
        path.write_text(html, encoding="utf-8")
        return path
