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
        """Transpose a list of row dicts into a {columns, data} columnar dict (missing keys -> None)."""
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
                continue          # keep `prev` as the last real value
            if prev is not None and v < prev:
                offset += _ROLLOVER
            out.append(v + offset)
            prev = v
        return out

    @staticmethod
    def write_data_files(experiment_dir, start_time: str,
                         entries: List[dict], columns: List[str]) -> Tuple[Path, Path]:
        """Write data_<start_time>.json + .csv under experiment_dir/data/. Returns (json_path, csv_path)."""
        data_dir = Path(experiment_dir) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        safe_time = "".join(c if c not in ':*?"<>|/\\' else "-" for c in str(start_time))

        columnar = LoggingPersistence.to_columnar(entries, columns)
        # Rollover-correct the instrument time column in place.
        if "instrument_time_us" in columns:
            i = columns.index("instrument_time_us")
            columnar["data"][i] = LoggingPersistence._correct_rollover(
                columnar["data"][i])

        json_path = data_dir / f"data_{safe_time}.json"
        json_path.write_text(json.dumps(columnar))

        # CSV via a DataFrame built from the columnar form.
        frame = {col: columnar["data"][idx] for idx, col in enumerate(columns)}
        csv_path = data_dir / f"data_{safe_time}.csv"
        pd.DataFrame(frame).to_csv(csv_path, index=False)

        logger.debug(f"wrote protocol data files: {json_path}, {csv_path}")
        return json_path, csv_path
