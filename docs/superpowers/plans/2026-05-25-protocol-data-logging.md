# Protocol Data Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project test convention:** the implementer does NOT auto-run the full pytest suite. Each "Run the test" step is a targeted run (the named selector). Run tests from `microdrop-py/` via:
> `pixi run bash -c "cd src && python -m pytest <path> -k <selector> -v"`
> A conftest skips the whole `pluggable_protocol_tree/tests/` session when Redis is unreachable, so always name the specific test FILE(s).

**Goal:** Give the pluggable protocol tree a data logger that produces the legacy artifact set (columnar `data_*.json` + `.csv`, `report_*.html`) on a real run, driven by the executor's lifecycle signals with no widget coupling, attributing each capacitance sample to the phase actuated when it arrived.

**Architecture:** Three single-responsibility units — `LoggingIngestion` (collect), `LoggingPersistence` (write data files), `LoggingReport` (HTML) — behind a GUI-thread `ProtocolLoggingController` connected to `executor.qsignals`. A dramatiq listener subscribes to `CAPACITANCE_UPDATED`, `ELECTRODES_STATE_CHANGE`, and `DEVICE_VIEWER_MEDIA_CAPTURED`, forwarding to the active controller. Device context (experiment dir, SVG path, channel→area map, capacitance-per-unit-area) is assembled by the dock pane.

**Tech Stack:** Python, Traits, pandas, plotly, dramatiq/Redis pub-sub, PySide6/Qt. Pixi env.

**Spec:** `docs/superpowers/specs/2026-05-25-protocol-data-logging-design.md`

**Working dir for all paths:** `microdrop-py/src/`.

---

## File Structure

- **Create** `pluggable_protocol_tree/services/logging/__init__.py` — package marker + public exports.
- **Create** `pluggable_protocol_tree/services/logging/models.py` — `LoggingDeviceContext` value object.
- **Create** `pluggable_protocol_tree/services/logging/ingestion.py` — `LoggingIngestion` (collect rows; force; media; thread-safe).
- **Create** `pluggable_protocol_tree/services/logging/persistence.py` — `LoggingPersistence` (columnar JSON + CSV, rollover).
- **Create** `pluggable_protocol_tree/services/logging/reporting.py` — `LoggingReport` (HTML + plotly via `microdrop_utils.plotly_helpers`).
- **Create** `pluggable_protocol_tree/services/logging/listener.py` — active-sink registry + dramatiq actor.
- **Create** `pluggable_protocol_tree/services/logging/controller.py` — `ProtocolLoggingController`.
- **Modify** `pluggable_protocol_tree/consts.py` — add `LOGGING_LISTENER_NAME` + an `ACTOR_TOPIC_DICT` entry (or a sibling dict) for the logging topics.
- **Modify** `pluggable_protocol_tree/views/protocol_tree_pane.py` — build + wire the controller; accept a `logging_device_context_provider`.
- **Modify** `pluggable_protocol_tree/views/dock_pane.py` — pass a provider that reads the device-viewer model.
- **Tests** alongside, under `pluggable_protocol_tree/tests/`.

Topic constants (import sites):
- `from dropbot_controller.consts import CAPACITANCE_UPDATED`
- `from pluggable_protocol_tree.consts import ELECTRODES_STATE_CHANGE`
- `from device_viewer.consts import DEVICE_VIEWER_MEDIA_CAPTURED`

Data-entry columns (legacy contract, in this order):
`["step_idx", "utc_time", "instrument_time_us", "step_id", "Capacitance (pF)", "Voltage (V)", "Force Over Unit Area (mN/mm^2)", "Actuated Area (mm^2)", "actuated_channels"]`

---

### Task 1: `LoggingDeviceContext` + `LoggingIngestion` collection core

**Files:**
- Create: `pluggable_protocol_tree/services/logging/__init__.py`
- Create: `pluggable_protocol_tree/services/logging/models.py`
- Create: `pluggable_protocol_tree/services/logging/ingestion.py`
- Test: `pluggable_protocol_tree/tests/test_logging_ingestion.py`

- [ ] **Step 1: Write the failing test**

Create `pluggable_protocol_tree/tests/test_logging_ingestion.py`:

```python
from pluggable_protocol_tree.services.logging.ingestion import LoggingIngestion


def test_log_data_tracks_columns_in_order():
    ing = LoggingIngestion()
    ing.log_data({"a": 1, "b": 2})
    ing.log_data({"a": 3, "c": 4})
    assert ing.columns == ["a", "b", "c"]
    assert ing.entries == [{"a": 1, "b": 2}, {"a": 3, "c": 4}]


def test_log_metadata_merges():
    ing = LoggingIngestion()
    ing.log_metadata({"x": 1})
    ing.log_metadata({"y": 2, "x": 9})
    assert ing.metadata == {"x": 9, "y": 2}


def test_calculate_force_formula():
    ing = LoggingIngestion()
    ing.update_capacitance_per_unit_area(2.0)
    # 0.5 * 2.0 * 10**2 = 100.0
    assert ing._calculate_force(10.0) == 100.0


def test_calculate_force_none_without_cpa_or_nonpositive_voltage():
    ing = LoggingIngestion()
    assert ing._calculate_force(10.0) is None       # no c-per-area
    ing.update_capacitance_per_unit_area(2.0)
    assert ing._calculate_force(0.0) is None         # voltage <= 0


def test_log_media_buckets_by_type():
    ing = LoggingIngestion()

    class _M:
        def __init__(self, path, type_):
            self.path = path
            self.type = type_

    class _T:
        value = "video"
    ing.log_media(_M("a.mp4", _T()))
    assert ing.media["video"] == ["a.mp4"]
```

- [ ] **Step 2: Run the test, verify it FAILS** (module missing).

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_ingestion.py -v"`
Expected: ImportError / collection error.

- [ ] **Step 3: Create the package + models**

`pluggable_protocol_tree/services/logging/__init__.py`:
```python
"""Protocol data logging for the pluggable protocol tree (issue #421)."""
```

`pluggable_protocol_tree/services/logging/models.py`:
```python
"""Per-run device context for the protocol logger, assembled by the dock
pane from the device viewer + application (keeps the logger units
decoupled from those subsystems)."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class LoggingDeviceContext:
    experiment_directory: Path
    device_svg_path: Optional[Path] = None
    # channel -> electrode area (mm^2); from the device viewer's
    # electrodes.channel_electrode_areas_scaled_map.
    channel_areas: Dict[int, float] = field(default_factory=dict)
    # dropbot calibration snapshot; live updates flow through the
    # controller. None -> force is None (legacy parity).
    capacitance_per_unit_area: Optional[float] = None
```

- [ ] **Step 4: Create `ingestion.py` (collection core)**

```python
"""Collects logged rows for one protocol run. No Qt, no broker — fed by
the ProtocolLoggingController. Append paths are lock-guarded because
capacitance/actuation arrive on a dramatiq worker thread while step
context updates arrive on the GUI thread."""

import threading
import time
from typing import Dict, List, Optional

from logger.logger_service import get_logger

logger = get_logger(__name__)


class LoggingIngestion:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries: List[dict] = []
        self._columns: List[str] = []
        self._metadata: Dict = {}
        self._media: Dict[str, List[str]] = {"video": [], "image": [], "other": []}
        # current step + phase context stamped onto each capacitance row
        self._step_id = ""
        self._step_idx = 0
        self._actuated_channels: List[int] = []
        self._actuated_area: float = 0.0
        self._cpa: Optional[float] = None

    # --- context setters ---
    def set_step(self, *, step_id: str, step_idx: int) -> None:
        self._step_id = step_id
        self._step_idx = step_idx

    def set_actuation(self, *, actuated_channels, actuated_area: float) -> None:
        self._actuated_channels = list(actuated_channels or [])
        self._actuated_area = float(actuated_area or 0.0)

    def update_capacitance_per_unit_area(self, value: Optional[float]) -> None:
        self._cpa = None if value is None else float(value)

    # --- collection ---
    def log_data(self, entry: dict) -> None:
        with self._lock:
            for k in entry:
                if k not in self._columns:
                    self._columns.append(k)
            self._entries.append(dict(entry))

    def log_metadata(self, entry: dict) -> None:
        with self._lock:
            self._metadata.update(entry)

    def log_media(self, model) -> None:
        bucket = getattr(getattr(model, "type", None), "value", "other")
        if bucket not in self._media:
            bucket = "other"
        with self._lock:
            self._media[bucket].append(str(model.path))

    # --- force ---
    def _calculate_force(self, voltage: float) -> Optional[float]:
        if self._cpa is None or voltage <= 0:
            return None
        try:
            return round(0.5 * self._cpa * (voltage ** 2), 6)
        except Exception as e:        # pragma: no cover - defensive
            logger.error(f"force calc failed: {e}")
            return None

    # --- accessors ---
    @property
    def entries(self) -> List[dict]:
        return self._entries

    @property
    def columns(self) -> List[str]:
        return self._columns

    @property
    def metadata(self) -> Dict:
        return self._metadata

    @property
    def media(self) -> Dict[str, List[str]]:
        return self._media
```

- [ ] **Step 5: Run the test, verify it PASSES.**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_ingestion.py -v"`
Expected: PASS.

- [ ] **Step 6: Commit**
```bash
git add pluggable_protocol_tree/services/logging/__init__.py pluggable_protocol_tree/services/logging/models.py pluggable_protocol_tree/services/logging/ingestion.py pluggable_protocol_tree/tests/test_logging_ingestion.py
git commit -m "[logging] LoggingDeviceContext + ingestion collection core (#421)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `LoggingIngestion.log_capacitance` — parse + per-phase stamping

**Files:**
- Modify: `pluggable_protocol_tree/services/logging/ingestion.py`
- Test: `pluggable_protocol_tree/tests/test_logging_ingestion.py` (append)

- [ ] **Step 1: Write the failing tests** — append:

```python
import json


def _msg(cap="12.5pF", volt="100V", instr=1000, recv=1700000000):
    return json.dumps({"capacitance": cap, "voltage": volt,
                       "instrument_time_us": instr, "reception_time": recv})


def test_log_capacitance_stamps_step_and_phase_and_force():
    ing = LoggingIngestion()
    ing.update_capacitance_per_unit_area(2.0)
    ing.set_step(step_id="uuid-1", step_idx=3)
    ing.set_actuation(actuated_channels=[5, 6], actuated_area=4.0)
    assert ing.log_capacitance(_msg()) is True
    e = ing.entries[-1]
    assert e["step_id"] == "uuid-1"
    assert e["step_idx"] == 3
    assert e["Capacitance (pF)"] == 12.5
    assert e["Voltage (V)"] == 100.0
    assert e["Force Over Unit Area (mN/mm^2)"] == round(0.5 * 2.0 * 100.0**2, 6)
    assert e["Actuated Area (mm^2)"] == 4.0
    assert e["actuated_channels"] == [5, 6]
    assert e["instrument_time_us"] == 1000


def test_log_capacitance_per_phase_attribution():
    ing = LoggingIngestion()
    ing.set_step(step_id="s", step_idx=1)
    ing.set_actuation(actuated_channels=[1], actuated_area=1.0)
    ing.log_capacitance(_msg())
    ing.set_actuation(actuated_channels=[2, 3], actuated_area=2.0)   # next phase
    ing.log_capacitance(_msg())
    assert ing.entries[0]["actuated_channels"] == [1]
    assert ing.entries[1]["actuated_channels"] == [2, 3]


def test_log_capacitance_bare_numbers_and_invalid():
    ing = LoggingIngestion()
    ing.set_step(step_id="s", step_idx=1)
    assert ing.log_capacitance(_msg(cap="9.0", volt="50")) is True
    assert ing.entries[-1]["Capacitance (pF)"] == 9.0
    assert ing.log_capacitance(_msg(cap="-", volt="-")) is False   # skipped
    assert ing.log_capacitance("not json") is False


def test_log_capacitance_requires_step_set():
    ing = LoggingIngestion()
    assert ing.log_capacitance(_msg()) is False    # no step set yet
```

- [ ] **Step 2: Run, verify FAIL** (`log_capacitance` undefined).

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_ingestion.py -k log_capacitance -v"`

- [ ] **Step 3: Implement `log_capacitance`** — add to `LoggingIngestion` (after `log_media`):

```python
    def log_capacitance(self, message) -> bool:
        """Parse a CAPACITANCE_UPDATED payload and append one row stamped
        with the current step + current phase actuation. Returns False
        (skips) when no step is set yet or the payload is unparseable —
        matches legacy lenient behavior."""
        if not self._step_id and self._step_idx == 0:
            return False
        try:
            data = json.loads(message)
        except (ValueError, TypeError):
            return False
        cap_str = data.get("capacitance", "-")
        volt_str = data.get("voltage", "-")
        if cap_str == "-" or volt_str == "-":
            return False
        cap = _parse_number(cap_str, "pF")
        volt = _parse_number(volt_str, "V")
        if cap is None or volt is None:
            return False
        force = self._calculate_force(volt)
        self.log_data({
            "step_idx": self._step_idx,
            "utc_time": int(data.get("reception_time", 0) or 0),
            "instrument_time_us": data.get("instrument_time_us", 0),
            "step_id": self._step_id,
            "Capacitance (pF)": cap,
            "Voltage (V)": volt,
            "Force Over Unit Area (mN/mm^2)": force,
            "Actuated Area (mm^2)": self._actuated_area,
            "actuated_channels": list(self._actuated_channels),
        })
        return True
```

Add `import json` at the top of `ingestion.py` (alongside the existing imports), and a module-level helper at the bottom:

```python
def _parse_number(raw: str, unit: str) -> Optional[float]:
    """Parse '12.5pF' / '12.5 pF' / '12.5' -> 12.5. Returns None on failure."""
    try:
        s = str(raw)
        if unit in s:
            s = s.replace(unit, "").strip()
        return float(s)
    except (ValueError, TypeError):
        return None
```

- [ ] **Step 4: Run, verify PASS** (all `test_logging_ingestion.py`).

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_ingestion.py -v"`

- [ ] **Step 5: Commit**
```bash
git add pluggable_protocol_tree/services/logging/ingestion.py pluggable_protocol_tree/tests/test_logging_ingestion.py
git commit -m "[logging] Capacitance ingestion with per-phase attribution + force (#421)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `LoggingPersistence` — columnar JSON + CSV + rollover

**Files:**
- Create: `pluggable_protocol_tree/services/logging/persistence.py`
- Test: `pluggable_protocol_tree/tests/test_logging_persistence.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

from pluggable_protocol_tree.services.logging.persistence import LoggingPersistence


def test_to_columnar_orders_and_fills():
    entries = [{"a": 1, "b": 2}, {"a": 3}]
    out = LoggingPersistence.to_columnar(entries, ["a", "b"])
    assert out == {"columns": ["a", "b"], "data": [[1, 3], [2, None]]}


def test_correct_rollover_adds_2_32_on_decrease():
    # uint32 wraps at 2**32; a decreasing instrument_time means a wrap.
    vals = [10, 20, 5, 15]           # wrap between index 1 and 2
    out = LoggingPersistence._correct_rollover(vals)
    assert out == [10, 20, 5 + 2**32, 15 + 2**32]


def test_write_data_files_writes_json_and_csv(tmp_path):
    entries = [
        {"step_idx": 0, "instrument_time_us": 100, "Capacitance (pF)": 1.0},
        {"step_idx": 0, "instrument_time_us": 200, "Capacitance (pF)": 2.0},
    ]
    cols = ["step_idx", "instrument_time_us", "Capacitance (pF)"]
    json_path, csv_path = LoggingPersistence.write_data_files(
        tmp_path, "20260525_120000", entries, cols)
    assert json_path.exists() and json_path.suffix == ".json"
    assert csv_path.exists() and csv_path.suffix == ".csv"
    payload = json.loads(json_path.read_text())
    assert payload["columns"] == cols
    assert json_path.parent.name == "data"
```

- [ ] **Step 2: Run, verify FAIL.**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_persistence.py -v"`

- [ ] **Step 3: Implement `persistence.py`**

```python
"""Write the collected rows to the legacy artifact set: a columnar
data_<t>.json and a data_<t>.csv under experiment_dir/data/."""

import json
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from logger.logger_service import get_logger

logger = get_logger(__name__)

_ROLLOVER = 2 ** 32   # instrument_time_us is a uint32 microsecond counter


class LoggingPersistence:
    @staticmethod
    def to_columnar(entries: List[dict], columns: List[str]) -> Dict:
        data = []
        for col in columns:
            data.append([e.get(col) for e in entries])
        return {"columns": columns, "data": data}

    @staticmethod
    def _correct_rollover(values: List[int]) -> List[int]:
        """Make a wrapping uint32 microsecond series monotonic by adding
        2**32 each time the raw value decreases."""
        out = []
        offset = 0
        prev = None
        for v in values:
            if v is None:
                out.append(None)
                continue
            if prev is not None and v < prev:
                offset += _ROLLOVER
            out.append(v + offset)
            prev = v
        return out

    @staticmethod
    def write_data_files(experiment_dir, start_time: str,
                         entries: List[dict], columns: List[str]) -> Tuple[Path, Path]:
        data_dir = Path(experiment_dir) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        columnar = LoggingPersistence.to_columnar(entries, columns)
        # Rollover-correct the instrument time column in place.
        if "instrument_time_us" in columns:
            i = columns.index("instrument_time_us")
            columnar["data"][i] = LoggingPersistence._correct_rollover(
                columnar["data"][i])

        json_path = data_dir / f"data_{start_time}.json"
        json_path.write_text(json.dumps(columnar))

        # CSV via a DataFrame built from the columnar form.
        frame = {col: columnar["data"][idx] for idx, col in enumerate(columns)}
        csv_path = data_dir / f"data_{start_time}.csv"
        pd.DataFrame(frame).to_csv(csv_path, index=False)

        return json_path, csv_path
```

- [ ] **Step 4: Run, verify PASS.**

- [ ] **Step 5: Commit**
```bash
git add pluggable_protocol_tree/services/logging/persistence.py pluggable_protocol_tree/tests/test_logging_persistence.py
git commit -m "[logging] Persistence: columnar JSON + CSV + uint32 rollover (#421)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `LoggingReport` — HTML report

**Files:**
- Create: `pluggable_protocol_tree/services/logging/reporting.py`
- Test: `pluggable_protocol_tree/tests/test_logging_reporting.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from pluggable_protocol_tree.services.logging.models import LoggingDeviceContext
from pluggable_protocol_tree.services.logging.reporting import LoggingReport


def _entries():
    return [
        {"step_idx": 0, "step_id": "s0", "Capacitance (pF)": 1.0,
         "Voltage (V)": 100.0, "Actuated Area (mm^2)": 2.0,
         "actuated_channels": [1, 2]},
        {"step_idx": 1, "step_id": "s1", "Capacitance (pF)": 3.0,
         "Voltage (V)": 100.0, "Actuated Area (mm^2)": 4.0,
         "actuated_channels": [3]},
    ]


def test_build_html_has_expected_sections():
    cols = ["step_idx", "step_id", "Capacitance (pF)", "Voltage (V)",
            "Actuated Area (mm^2)", "actuated_channels"]
    html = LoggingReport.build_html(
        entries=_entries(), columns=cols,
        metadata={"Experiment": "exp-1"},
        media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")),
        notes=None,
    )
    assert "<html" in html.lower()
    for section in ("Metadata", "Data Summary", "Data Trends"):
        assert section in html
    assert "exp-1" in html


def test_build_html_empty_data_does_not_crash():
    html = LoggingReport.build_html(
        entries=[], columns=[], metadata={}, media={"video": [], "image": [], "other": []},
        device_context=LoggingDeviceContext(experiment_directory=Path(".")), notes=None)
    assert "<html" in html.lower()


def test_write_report_creates_reports_dir(tmp_path):
    path = LoggingReport.write_report(tmp_path, "<html><body>ok</body></html>")
    assert path.exists() and path.parent.name == "reports" and path.suffix == ".html"
```

- [ ] **Step 2: Run, verify FAIL.**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_reporting.py -v"`

- [ ] **Step 3: Implement `reporting.py`**

```python
"""Build the HTML report (legacy contract): metadata, data-files,
data summary, data trends (plotly), device heatmap, media, notes.
Imports only shared utils + plotly — no protocol_grid coupling."""

import html as _html
import time
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
        # Per-step bar charts of each numeric column + a device heatmap of
        # per-channel actuation count. Plotly is optional at runtime; any
        # failure degrades to a note rather than crashing the report.
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
        # Per-channel actuation count across the run.
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
```

- [ ] **Step 4: Run, verify PASS.**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_reporting.py -v"`

- [ ] **Step 5: Commit**
```bash
git add pluggable_protocol_tree/services/logging/reporting.py pluggable_protocol_tree/tests/test_logging_reporting.py
git commit -m "[logging] HTML report (metadata/summary/trends/heatmap/media) (#421)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Active-sink registry + dramatiq listener + consts

**Files:**
- Create: `pluggable_protocol_tree/services/logging/listener.py`
- Modify: `pluggable_protocol_tree/consts.py`
- Test: `pluggable_protocol_tree/tests/test_logging_listener.py`

- [ ] **Step 1: Write the failing test**

```python
import pluggable_protocol_tree.services.logging.listener as L


class _Sink:
    def __init__(self):
        self.calls = []
    def on_capacitance(self, m): self.calls.append(("cap", m))
    def on_actuation(self, m): self.calls.append(("act", m))
    def on_media(self, m): self.calls.append(("media", m))


def test_route_to_active_sink_dispatches_by_topic():
    from dropbot_controller.consts import CAPACITANCE_UPDATED
    from pluggable_protocol_tree.consts import ELECTRODES_STATE_CHANGE
    from device_viewer.consts import DEVICE_VIEWER_MEDIA_CAPTURED
    sink = _Sink()
    L.set_active_logger(sink)
    try:
        L.route_to_active_logger(CAPACITANCE_UPDATED, "capmsg")
        L.route_to_active_logger(ELECTRODES_STATE_CHANGE, "actmsg")
        L.route_to_active_logger(DEVICE_VIEWER_MEDIA_CAPTURED, "mediamsg")
    finally:
        L.clear_active_logger()
    assert sink.calls == [("cap", "capmsg"), ("act", "actmsg"), ("media", "mediamsg")]


def test_route_with_no_active_logger_is_noop():
    L.clear_active_logger()
    L.route_to_active_logger("any/topic", "x")   # must not raise


def test_logging_topics_registered_in_consts():
    from pluggable_protocol_tree.consts import LOGGING_ACTOR_TOPIC_DICT, LOGGING_LISTENER_NAME
    from dropbot_controller.consts import CAPACITANCE_UPDATED
    topics = LOGGING_ACTOR_TOPIC_DICT[LOGGING_LISTENER_NAME]
    assert CAPACITANCE_UPDATED in topics
```

- [ ] **Step 2: Run, verify FAIL.**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_listener.py -v"`

- [ ] **Step 3: Add consts** — in `pluggable_protocol_tree/consts.py`, after the existing `ACTOR_TOPIC_DICT`/`SYNC_LISTENER_NAME` block, add:

```python
from dropbot_controller.consts import CAPACITANCE_UPDATED
from device_viewer.consts import DEVICE_VIEWER_MEDIA_CAPTURED

LOGGING_LISTENER_NAME = "protocol_tree_logging_listener"
LOGGING_ACTOR_TOPIC_DICT = {
    LOGGING_LISTENER_NAME: [
        CAPACITANCE_UPDATED,
        ELECTRODES_STATE_CHANGE,
        DEVICE_VIEWER_MEDIA_CAPTURED,
    ]
}
```
(`ELECTRODES_STATE_CHANGE` is already imported at the top of consts.py.)

- [ ] **Step 4: Implement `listener.py`** (mirrors `execution/listener.py`'s active-pointer + actor pattern):

```python
"""Active-logger registry + dramatiq actor. The actor receives every
message on the logging topics and routes it to the controller that is
active for the current run (set in start_logging, cleared in
stop_logging). Mirrors execution/listener.py's active-step pattern."""

import threading
from typing import Optional

import dramatiq

from dropbot_controller.consts import CAPACITANCE_UPDATED
from device_viewer.consts import DEVICE_VIEWER_MEDIA_CAPTURED
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_CHANGE, LOGGING_LISTENER_NAME,
)
from logger.logger_service import get_logger

logger = get_logger(__name__)

_active = None
_lock = threading.Lock()


def set_active_logger(controller) -> None:
    global _active
    with _lock:
        _active = controller


def clear_active_logger() -> None:
    global _active
    with _lock:
        _active = None


def get_active_logger():
    with _lock:
        return _active


def route_to_active_logger(topic: str, payload) -> None:
    sink = get_active_logger()
    if sink is None:
        return
    try:
        if topic == CAPACITANCE_UPDATED:
            sink.on_capacitance(payload)
        elif topic == ELECTRODES_STATE_CHANGE:
            sink.on_actuation(payload)
        elif topic == DEVICE_VIEWER_MEDIA_CAPTURED:
            sink.on_media(payload)
    except Exception as e:                     # pragma: no cover - defensive
        logger.error(f"logging route failed for {topic}: {e}")


@dramatiq.actor(actor_name=LOGGING_LISTENER_NAME, queue_name="default")
def logging_listener(message: str, topic: str, timestamp: float = None) -> None:
    route_to_active_logger(topic, message)
```

- [ ] **Step 5: Run, verify PASS.**

- [ ] **Step 6: Commit**
```bash
git add pluggable_protocol_tree/services/logging/listener.py pluggable_protocol_tree/consts.py pluggable_protocol_tree/tests/test_logging_listener.py
git commit -m "[logging] Active-logger registry + dramatiq listener + topics (#421)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `ProtocolLoggingController`

**Files:**
- Create: `pluggable_protocol_tree/services/logging/controller.py`
- Test: `pluggable_protocol_tree/tests/test_logging_controller.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from pluggable_protocol_tree.services.logging.controller import ProtocolLoggingController
from pluggable_protocol_tree.services.logging.models import LoggingDeviceContext
import pluggable_protocol_tree.services.logging.listener as L


def _ctx(tmp_path):
    return LoggingDeviceContext(
        experiment_directory=tmp_path,
        device_svg_path=None,
        channel_areas={5: 2.0, 6: 3.0},
        capacitance_per_unit_area=2.0,
    )


def _immediate_flush(controller):
    # Test flush scheduler: run synchronously instead of QTimer.
    controller._flush()


def test_start_logging_preview_is_noop(tmp_path):
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate_flush)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=True)
    assert c._ingestion is None
    assert L.get_active_logger() is None


def test_actuation_area_summed_from_channel_areas(tmp_path):
    import json
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate_flush)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    c._on_step_started(_FakeRow())
    c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [5, 6]}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    e = c._ingestion.entries[-1]
    assert e["Actuated Area (mm^2)"] == 5.0      # 2.0 + 3.0
    assert e["actuated_channels"] == [5, 6]
    c.stop_logging(completed_steps=1)


def test_flush_writes_artifacts(tmp_path):
    import json
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate_flush)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    c._on_step_started(_FakeRow())
    c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [5]}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    c.stop_logging(completed_steps=1)
    assert list((tmp_path / "data").glob("data_*.json"))
    assert list((tmp_path / "data").glob("data_*.csv"))
    assert list((tmp_path / "reports").glob("report_*.html"))
    assert L.get_active_logger() is None         # sink cleared on stop


class _FakeRow:
    uuid = "row-uuid"
    name = "Step A"
    path = (0,)
```

- [ ] **Step 2: Run, verify FAIL.**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_controller.py -v"`

- [ ] **Step 3: Implement `controller.py`**

```python
"""GUI-thread controller that turns executor lifecycle signals into a
run's worth of logged artifacts. Owns a LoggingIngestion per run; the
logging listener forwards capacitance/actuation/media to it. Settling
flush is deferred so in-flight capacitance after 'done' is captured."""

import json
from typing import Callable, Optional

from logger.logger_service import get_logger

from pluggable_protocol_tree.services.logging import listener as _listener
from pluggable_protocol_tree.services.logging.ingestion import LoggingIngestion
from pluggable_protocol_tree.services.logging.persistence import LoggingPersistence
from pluggable_protocol_tree.services.logging.reporting import LoggingReport

logger = get_logger(__name__)


def _default_settling_provider() -> float:
    try:
        from protocol_grid.preferences import ProtocolPreferences
        return float(ProtocolPreferences().logs_settling_time_s)
    except Exception as e:                     # pragma: no cover - defensive
        logger.debug(f"settling pref unavailable, default 3.0s: {e}")
        return 3.0


def _qtimer_flush_scheduler(controller) -> None:
    from pyface.qt.QtCore import QTimer
    QTimer.singleShot(int(controller._settling_provider() * 1000),
                      controller._flush)


class ProtocolLoggingController:
    def __init__(self, *, settling_provider: Callable[[], float] = None,
                 flush_scheduler: Callable[["ProtocolLoggingController"], None] = None):
        self._settling_provider = settling_provider or _default_settling_provider
        self._flush_scheduler = flush_scheduler or _qtimer_flush_scheduler
        self._ingestion: Optional[LoggingIngestion] = None
        self._device_context = None
        self._step_idx = 0
        self._start_time = ""

    # --- executor signal wiring ---
    def attach(self, qsignals) -> None:
        qsignals.protocol_started.connect(self._noop)   # start is driven by start_logging
        qsignals.step_started.connect(self._on_step_started)
        qsignals.protocol_finished.connect(lambda: self.stop_logging(self._step_idx))
        qsignals.protocol_aborted.connect(lambda: self.stop_logging(self._step_idx))
        qsignals.protocol_error.connect(lambda _msg: self.stop_logging(self._step_idx))

    def _noop(self, *a, **k):
        pass

    # --- lifecycle ---
    def start_logging(self, device_context, n_steps: int, preview_mode: bool) -> None:
        if preview_mode:
            self._ingestion = None
            return
        import time
        self._device_context = device_context
        self._ingestion = LoggingIngestion()
        self._ingestion.update_capacitance_per_unit_area(
            getattr(device_context, "capacitance_per_unit_area", None))
        self._step_idx = 0
        self._start_time = time.strftime("%Y%m%d_%H%M%S")
        self._ingestion.log_metadata({
            "Experiment Directory": str(device_context.experiment_directory),
            "Device SVG": str(getattr(device_context, "device_svg_path", "")),
            "Steps": f"0 / {n_steps}",
        })
        _listener.set_active_logger(self)

    def _on_step_started(self, row) -> None:
        if self._ingestion is None:
            return
        self._step_idx += 1
        self._ingestion.set_step(step_id=getattr(row, "uuid", ""),
                                 step_idx=self._step_idx)

    def stop_logging(self, completed_steps) -> None:
        if self._ingestion is None:
            return
        self._ingestion.log_metadata({"Completed Steps": completed_steps})
        _listener.clear_active_logger()
        self._flush_scheduler(self)

    def _flush(self) -> None:
        ing = self._ingestion
        if ing is None:
            return
        try:
            LoggingPersistence.write_data_files(
                self._device_context.experiment_directory, self._start_time,
                ing.entries, ing.columns)
            html = LoggingReport.build_html(
                entries=ing.entries, columns=ing.columns, metadata=ing.metadata,
                media=ing.media, device_context=self._device_context, notes=None)
            LoggingReport.write_report(
                self._device_context.experiment_directory, html)
        except Exception as e:
            logger.error(f"protocol logging flush failed: {e}")
        finally:
            self._ingestion = None

    # --- listener forwards (worker thread) ---
    def on_capacitance(self, message) -> None:
        if self._ingestion is not None:
            self._ingestion.log_capacitance(message)

    def on_actuation(self, message) -> None:
        if self._ingestion is None:
            return
        try:
            channels = json.loads(message).get("channels", []) or []
        except (ValueError, TypeError):
            return
        areas = getattr(self._device_context, "channel_areas", {}) or {}
        area = sum(float(areas.get(int(ch), 0.0)) for ch in channels)
        self._ingestion.set_actuation(actuated_channels=channels, actuated_area=area)

    def on_media(self, message) -> None:
        if self._ingestion is None:
            return
        try:
            from device_viewer.models.media_capture_model import (
                MediaCaptureMessageModel,
            )
            self._ingestion.log_media(MediaCaptureMessageModel.model_validate_json(message))
        except Exception as e:                 # pragma: no cover - defensive
            logger.warning(f"media log failed: {e}")

    def update_capacitance_per_unit_area(self, value) -> None:
        if self._ingestion is not None:
            self._ingestion.update_capacitance_per_unit_area(value)
```

- [ ] **Step 4: Run, verify PASS.**

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_controller.py -v"`

- [ ] **Step 5: Commit**
```bash
git add pluggable_protocol_tree/services/logging/controller.py pluggable_protocol_tree/tests/test_logging_controller.py
git commit -m "[logging] ProtocolLoggingController: lifecycle, signals, settling flush (#421)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Wire into the pane + dock-pane device-context provider + integration

**Files:**
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py`
- Modify: `pluggable_protocol_tree/views/dock_pane.py`
- Modify: `pluggable_protocol_tree/plugin.py` (register the logging listener subscriptions)
- Test: `pluggable_protocol_tree/tests/test_logging_integration.py`

- [ ] **Step 1: Write the failing integration test**

```python
import json
from pathlib import Path

from pluggable_protocol_tree.services.logging.controller import ProtocolLoggingController
from pluggable_protocol_tree.services.logging.models import LoggingDeviceContext


def test_two_phase_run_produces_artifacts_with_per_phase_channels(tmp_path):
    """Drive the controller as the executor + listener would: step start,
    phase A actuation + capacitance, phase B actuation + capacitance,
    finish. Assert artifacts + per-phase attribution."""
    flushed = {}
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=lambda ctrl: ctrl._flush())
    ctx = LoggingDeviceContext(experiment_directory=tmp_path, device_svg_path=None,
                               channel_areas={1: 1.0, 2: 2.0, 3: 3.0},
                               capacitance_per_unit_area=2.0)
    c.start_logging(ctx, n_steps=1, preview_mode=False)

    class _Row:
        uuid = "r1"; name = "S"; path = (0,)
    c._on_step_started(_Row())
    c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [1]}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 5, "reception_time": 1}))
    c.on_actuation(json.dumps({"electrodes": ["b", "c"], "channels": [2, 3]}))
    c.on_capacitance(json.dumps({"capacitance": "20pF", "voltage": "100V",
                                 "instrument_time_us": 6, "reception_time": 2}))
    c.stop_logging(completed_steps=1)

    data_json = list((tmp_path / "data").glob("data_*.json"))
    assert data_json and list((tmp_path / "data").glob("data_*.csv"))
    assert list((tmp_path / "reports").glob("report_*.html"))
    payload = json.loads(data_json[0].read_text())
    chan_col = payload["data"][payload["columns"].index("actuated_channels")]
    assert chan_col == [[1], [2, 3]]            # per-phase attribution
```

- [ ] **Step 2: Run, verify PASS already** (the controller test exercises the same path).

Run: `pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_integration.py -v"`
Expected: PASS (this test only depends on Tasks 1-6). If it passes, the integration contract holds; the remaining steps wire it into the live pane.

- [ ] **Step 3: Wire the controller into the pane**

In `pluggable_protocol_tree/views/protocol_tree_pane.py`:

(a) Add a constructor kwarg `logging_device_context_provider=None` (a callable returning a `LoggingDeviceContext` or None), store it: `self._logging_device_context_provider = logging_device_context_provider`.

(b) In `__init__`, after `self.executor = self._build_executor(...)`, create + attach the controller:
```python
        from pluggable_protocol_tree.services.logging.controller import (
            ProtocolLoggingController,
        )
        self.logging_controller = ProtocolLoggingController()
        self.logging_controller.attach(self.executor.qsignals)
```

(c) In `_start_protocol_run(preview_mode)`, just before `self.executor.start(...)`, start logging when a provider is present:
```python
        if self._logging_device_context_provider is not None:
            try:
                ctx = self._logging_device_context_provider()
                if ctx is not None:
                    n_steps = sum(1 for _ in self.manager.iter_execution_frames())
                    self.logging_controller.start_logging(ctx, n_steps, preview_mode)
            except Exception as e:
                logger.warning(f"could not start protocol logging: {e}")
```
(The controller's `stop_logging` is already driven by the finished/aborted/error signals via `attach`.)

- [ ] **Step 4: Provide the device context from the dock pane**

In `pluggable_protocol_tree/views/dock_pane.py` `create_contents`, build a provider that reads the device-viewer model + experiment manager, and pass it to the pane:
```python
        def _logging_device_context():
            from pluggable_protocol_tree.services.logging.models import (
                LoggingDeviceContext,
            )
            dv = getattr(sync, "device_view_model", None) or getattr(
                getattr(sync, "widget", None), "model", None)
            channel_areas, svg_path = {}, None
            if dv is not None:
                try:
                    channel_areas = dict(dv.electrodes.channel_electrode_areas_scaled_map)
                    svg_path = getattr(dv.electrodes.svg_model, "svg_path", None)
                except Exception:
                    pass
            return LoggingDeviceContext(
                experiment_directory=experiment_manager.get_experiment_directory(),
                device_svg_path=svg_path,
                channel_areas=channel_areas,
            )

        pane = ProtocolTreePane(
            manager,
            application=app,
            experiment_manager=experiment_manager,
            sticky_manager=sticky_manager,
            device_viewer_sync=sync,
            logging_device_context_provider=_logging_device_context,
            parent=parent,
        )
```
(Confirm the exact device-viewer model accessor on `DeviceViewerSyncController` during implementation; fall back to `{}`/`None` so logging degrades gracefully when the model isn't reachable. `capacitance_per_unit_area` is left at its default and updated live via the listener.)

- [ ] **Step 5: Register the logging listener subscriptions**

In `pluggable_protocol_tree/plugin.py`, where the executor listener's subscriptions are registered (search for `ACTOR_TOPIC_DICT` / `SYNC` registration in `start()`), also register `LOGGING_ACTOR_TOPIC_DICT` so the `logging_listener` actor receives the three topics. Import:
```python
from pluggable_protocol_tree.consts import LOGGING_ACTOR_TOPIC_DICT
from pluggable_protocol_tree.services.logging import listener as _logging_listener  # noqa: F401  (registers the actor)
```
and add its `(topic, actor_name)` pairs to the message-router subscription loop the plugin already runs for the other listeners.

- [ ] **Step 6: Run the integration test + the pane/dock tests**

Run:
```
pixi run bash -c "cd src && python -m pytest pluggable_protocol_tree/tests/test_logging_integration.py pluggable_protocol_tree/tests/test_protocol_tree_pane.py pluggable_protocol_tree/tests/test_dock_pane.py pluggable_protocol_tree/tests/test_plugin.py -v"
```
Expected: PASS. Update any pane/dock test that constructs `ProtocolTreePane` if a new required kwarg breaks it (the provider is optional/defaulted, so none should break).

- [ ] **Step 7: Commit**
```bash
git add pluggable_protocol_tree/views/protocol_tree_pane.py pluggable_protocol_tree/views/dock_pane.py pluggable_protocol_tree/plugin.py pluggable_protocol_tree/tests/test_logging_integration.py
git commit -m "[logging] Wire ProtocolLoggingController into the pane + dock provider (#421)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review notes (reconciled)

- **Spec coverage:** ingestion+force+per-phase → Tasks 1-2; persistence (JSON/CSV/rollover) → Task 3; reporting (HTML/plotly/heatmap) → Task 4; listener + topics → Task 5; controller lifecycle/settling/preview → Task 6; executor wiring + device-context sourcing + integration → Task 7. Acceptance criteria all map: no `protocol_grid` import except the settling pref (controller `_default_settling_provider`); preview no-ops (Task 6); capacitance via pub/sub (Task 5); `MediaCaptureMessageModel` (Task 6 `on_media`); force formula (Task 1); artifacts on a real run (Tasks 3/4/7).
- **Type consistency:** `LoggingIngestion` API (`set_step`, `set_actuation`, `update_capacitance_per_unit_area`, `log_capacitance`, `log_data`, `log_metadata`, `log_media`, `entries`/`columns`/`metadata`/`media`), `LoggingPersistence.{to_columnar,_correct_rollover,write_data_files}`, `LoggingReport.{build_html,write_report}`, controller `{start_logging,stop_logging,_on_step_started,on_capacitance,on_actuation,on_media,_flush}`, listener `{set_active_logger,clear_active_logger,get_active_logger,route_to_active_logger}` are used identically across tasks.
- **Known confirm-at-implementation point (flagged, not a placeholder):** the exact device-viewer model accessor in the dock-pane provider (Task 7 step 4) and the exact `capacitance_per_unit_area` calibration source — both degrade gracefully (`{}`/`None` → force `None`, empty areas) so they don't block the artifact set.
```
