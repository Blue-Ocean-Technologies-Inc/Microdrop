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
