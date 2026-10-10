"""GUI-independent logic for the desktop app.

Everything here is free of Tkinter so it can be unit-tested headlessly. The GUI
in :mod:`app` only wires widgets to these functions.

The drag-coefficient presets, default launch conditions, and the dt validation
messages mirror ``webapp/src/App.tsx``. That duplication is intentional (each
entry point stays self-contained) and is guarded by
``desktop/tests/test_agreement.py``, which parses ``App.tsx`` and fails if the
values or labels ever drift apart. Update both when a preset or message changes.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RANGE_CALCULATOR = REPO_ROOT / "range_calculator"
if str(RANGE_CALCULATOR) not in sys.path:
    sys.path.insert(0, str(RANGE_CALCULATOR))

from ballistics import ProjectileSimulator, SimulationDiverged  # noqa: E402

KMPH_TO_MPS = 1000 / 3600

DT_MIN = 0.0001
DT_MAX = 10.0

VELOCITY_MIN = 10.0
VELOCITY_MAX = 500.0
ANGLE_MIN = 1.0
ANGLE_MAX = 89.0

DEFAULT_VELOCITY_KMPH = 170.0
DEFAULT_ANGLE_DEG = 35.0
DEFAULT_TIMESTEP = 0.01
DEFAULT_ADAPTIVE = False
DRAG_COEFFICIENT_DEFAULT = 0.47

# Order and labels mirror DRAG_PRESETS in webapp/src/App.tsx.
DRAG_PRESETS: tuple[tuple[float, str], ...] = (
    (0.47, "球体（既定値）"),
    (0.348, "MLB（無回転）"),
    (0.358, "MLB（2500rpm, 自由飛行）"),
    (0.3, "NPB"),
)

MAX_TRAJECTORY_POINTS = 2000


@dataclass(frozen=True)
class LaunchConditions:
    """The launch inputs collected from the UI, before running a simulation."""

    velocity_kmph: float = DEFAULT_VELOCITY_KMPH
    angle_deg: float = DEFAULT_ANGLE_DEG
    dt: float = DEFAULT_TIMESTEP
    adaptive: bool = DEFAULT_ADAPTIVE
    drag_coefficient: float = DRAG_COEFFICIENT_DEFAULT


@dataclass(frozen=True)
class TrajectoryPoint:
    """One recorded integration step, in the same shape the web API returns."""

    t: float
    x: float
    y: float
    vx: float
    vy: float
    speed: float


@dataclass(frozen=True)
class SimulationResult:
    """Outcome metrics, named to match the web API's ``result`` object."""

    ideal_range: float
    ground_range: float
    flight_time: float
    impact_speed: float
    landed: bool
    timed_out: bool
    steps: int
    timestep_min: float | None
    timestep_max: float | None


@dataclass(frozen=True)
class SimulationOutcome:
    """A full run: the conditions, the metrics, and the recorded trajectory."""

    conditions: LaunchConditions
    result: SimulationResult
    trajectory: list[TrajectoryPoint] = field(default_factory=list)

    @property
    def reduction_percent(self) -> float:
        """Distance lost to drag as a percentage of the ideal range."""
        ideal = self.result.ideal_range
        if ideal <= 0.0:
            return 0.0
        return (ideal - self.result.ground_range) / ideal * 100.0


def preset_label(value: float) -> str:
    """Dropdown label for a drag coefficient, matching the web UI.

    Known presets render as ``<label>（Cd=<value>）``; unknown values fall back
    to ``Cd=<value>``.
    """
    for preset_value, preset in DRAG_PRESETS:
        if math.isclose(preset_value, value, rel_tol=0.0, abs_tol=1e-12):
            return f"{preset}（Cd={preset_value:g}）"
    return f"Cd={value:g}"


def validate_dt(text: str) -> str | None:
    """Validate the dt entry text, returning a Japanese message or ``None``.

    Mirrors ``dtValidityMessage`` in ``webapp/src/App.tsx`` for the checks that
    make sense outside a browser (bad input, range, and step mismatch).
    """
    try:
        value = float(text)
    except (TypeError, ValueError):
        return "刻み幅 dt には数値を指定してください。"
    if not math.isfinite(value):
        return "刻み幅 dt には数値を指定してください。"
    if value < DT_MIN:
        return f"刻み幅 dt は {DT_MIN} 以上で指定してください。"
    if value > DT_MAX:
        return f"刻み幅 dt は {DT_MAX} 以下で指定してください。"
    steps = value / DT_MIN
    if not math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-6):
        return f"刻み幅 dt は {DT_MIN} 単位で指定してください。"
    return None


def simulate(conditions: LaunchConditions) -> SimulationOutcome:
    """Run one launch through the tested physics core and collect its trajectory.

    Raises whatever the core raises (:class:`SimulationDiverged` or ``ValueError``
    for a too-coarse timestep); the caller localises the message for display.
    """
    simulator = ProjectileSimulator(
        conditions.velocity_kmph * KMPH_TO_MPS,
        math.radians(conditions.angle_deg),
        {"drag_coefficient": conditions.drag_coefficient},
        dt=conditions.dt,
        adaptive=conditions.adaptive,
    )

    trajectory: list[TrajectoryPoint] = []

    def record(t: float, state: tuple[float, float, float, float]) -> None:
        x, y, vx, vy = state
        trajectory.append(
            TrajectoryPoint(t=t, x=x, y=y, vx=vx, vy=vy, speed=math.hypot(vx, vy))
        )

    ideal = simulator.calculate_ideal_range()
    simulator.run_simulation(on_step=record)
    raw = simulator.result()

    result = SimulationResult(
        ideal_range=ideal,
        ground_range=raw.ground_range,
        flight_time=raw.flight_time,
        impact_speed=raw.impact_speed,
        landed=raw.landed,
        timed_out=raw.timed_out,
        steps=raw.steps,
        timestep_min=raw.timestep_min,
        timestep_max=raw.timestep_max,
    )
    return SimulationOutcome(
        conditions=conditions,
        result=result,
        trajectory=_downsample(trajectory, MAX_TRAJECTORY_POINTS),
    )


def _downsample(
    points: list[TrajectoryPoint], limit: int
) -> list[TrajectoryPoint]:
    """Thin a trajectory to at most ``limit`` points, always keeping the last."""
    if len(points) <= limit:
        return points
    step = math.ceil(len(points) / limit)
    sampled = points[::step]
    if sampled[-1] is not points[-1]:
        sampled.append(points[-1])
    return sampled


def format_number(value: float, digits: int = 2) -> str:
    """Fixed-decimal formatting, mirroring the web UI's ``format`` helper."""
    return f"{value:.{digits}f}"


def format_decimal(value: float, significant_digits: int = 6) -> str:
    """Compact significant-digit formatting for timestep values.

    Mirrors ``formatDecimal`` in ``webapp/src/App.tsx``.
    """
    if not math.isfinite(value):
        return str(value)
    return f"{float(f'{value:.{significant_digits}g}'):g}"


__all__ = [
    "ANGLE_MAX",
    "ANGLE_MIN",
    "DEFAULT_ADAPTIVE",
    "DEFAULT_ANGLE_DEG",
    "DEFAULT_TIMESTEP",
    "DEFAULT_VELOCITY_KMPH",
    "DRAG_COEFFICIENT_DEFAULT",
    "DRAG_PRESETS",
    "DT_MAX",
    "DT_MIN",
    "LaunchConditions",
    "SimulationDiverged",
    "SimulationOutcome",
    "SimulationResult",
    "TrajectoryPoint",
    "VELOCITY_MAX",
    "VELOCITY_MIN",
    "format_decimal",
    "format_number",
    "preset_label",
    "simulate",
    "validate_dt",
]
