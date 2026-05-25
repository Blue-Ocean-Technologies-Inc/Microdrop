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
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<script src='https://cdn.plot.ly/plotly-latest.min.js'></script>"
            "<style>body{font-family:sans-serif;margin:24px;} "
            "table{border-collapse:collapse;} td,th{border:1px solid #ccc;"
            "padding:4px 8px;}</style></head><body>"
            f"<h1>Protocol Report</h1>{body}</body></html>"
        )

    @staticmethod
    def _metadata_section(metadata: Dict) -> str:
        rows = "".join(
            f"<tr><th>{_html.escape(str(k))}</th>"
            f"<td>{_html.escape(str(v))}</td></tr>"
            for k, v in (metadata or {}).items()
        )
        return f"<h2>Metadata</h2><table>{rows}</table>"

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
        charts = []
        for col in LoggingReport._numeric_columns(columns):
            if col not in df:
                continue
            s = pd.to_numeric(df[col], errors="coerce")
            if s.dropna().empty:
                continue
            agg = df.assign(_v=s).groupby("step_idx")["_v"].agg(["mean", "std"]).reset_index()
            fig = px.bar(agg, x="step_idx", y="mean", error_y="std", title=col)
            charts.append(fig.to_html(full_html=False, include_plotlyjs=False))
        heatmap = LoggingReport._heatmap(df, device_context)
        return "<h2>Data Trends</h2>" + "".join(charts) + heatmap

    @staticmethod
    def _heatmap(df: pd.DataFrame, device_context) -> str:
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
            fig = create_plotly_svg_dropbot_device_heatmap(str(svg), counts)
            return ("<h3>Device actuation heatmap</h3>"
                    + fig.to_html(full_html=False, include_plotlyjs=False))
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
