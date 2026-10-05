"""Command line entry point: reads a launch scenario and prints the range.

Usage::

    python range_calc_v4.py [scenario_path] [dt_max] [--adaptive]

``dt_max`` is a ceiling: with ``--adaptive`` each step is shortened to stay
inside the RK4 stability band, so a coarse value trades accuracy for stability
rather than diverging.

All physics lives in :mod:`ballistics`; this module only handles input parsing,
unit conversion, and presentation.
"""

from __future__ import annotations

import math
import sys
import warnings
from pathlib import Path

from ballistics import ProjectileSimulator, SimulationDiverged, derivatives, ideal_range
from physics_config import DEFAULT_PARAMETERS, ProjectileConstants

DATA_PATH = Path(__file__).resolve().parent / "data.csv"

DEFAULT_VELOCITY_KMPH = 170.0
DEFAULT_ANGLE_DEG = 35.0
DEFAULT_TIMESTEP = 0.01

KMPH_TO_MPS = 1000 / 3600

__all__ = [
    "ProjectileConstants",
    "ProjectileSimulator",
    "SimulationDiverged",
    "derivatives",
    "ideal_range",
    "load_scenario",
    "main",
    "parse_args",
]


def load_scenario(path: Path | str | None = None) -> tuple[float, float]:
    """Read ``velocity_kmph, angle_deg`` and fall back to the defaults.

    A missing file, an unparsable number, or a short line all resolve to the
    default scenario instead of raising.
    """
    data_path = Path(path) if path is not None else DATA_PATH
    try:
        line = data_path.read_text(encoding="utf-8").splitlines()[0]
        velocity_raw, angle_raw = line.split(",")[:2]
        return float(velocity_raw.strip()), float(angle_raw.strip())
    except (OSError, IndexError, ValueError) as exc:
        warnings.warn(
            f"could not read scenario from {data_path} ({exc}); "
            f"using defaults {DEFAULT_VELOCITY_KMPH} km/h, {DEFAULT_ANGLE_DEG} deg",
            stacklevel=2,
        )
        return DEFAULT_VELOCITY_KMPH, DEFAULT_ANGLE_DEG


def parse_args(argv: list[str] | None = None) -> tuple[Path | str | None, float, bool]:
    """Split ``argv`` into a scenario path, a timestep ceiling, and the mode flag.

    Positional arguments are ``[scenario_path] [dt_max]``; ``--adaptive`` switches
    the integrator to the adaptive-timestep mode. An empty or omitted ``argv``
    yields the shipped defaults, which is what ``main()`` relies on; the
    ``__main__`` block is what forwards the real command line.
    """
    args = list(argv or [])
    adaptive = False
    if "--adaptive" in args:
        args.remove("--adaptive")
        adaptive = True

    path = args[0] if args and args[0] else None
    dt_max = float(args[1]) if len(args) > 1 else DEFAULT_TIMESTEP
    return path, dt_max, adaptive


def main(argv: list[str] | None = None) -> int:
    path, dt_max, adaptive = parse_args(argv)

    velocity_kmph, angle_deg = load_scenario(path)

    velocity_mps = velocity_kmph * KMPH_TO_MPS
    angle_rad = math.radians(angle_deg)

    simulator = ProjectileSimulator(
        velocity_mps,
        angle_rad,
        DEFAULT_PARAMETERS,
        dt=dt_max,
        adaptive=adaptive,
    )
    ideal = simulator.calculate_ideal_range()
    ground_range, flight_time = simulator.run_simulation()
    result = simulator.result()

    mode = 'RK4, adaptive timestep' if adaptive else 'RK4, With Drag'
    print("--- Simulation Results (RK4 Refactored) ---")
    print(f"Input Velocity: {velocity_kmph} km/h")
    print(f"Launch Angle: {angle_deg} deg")
    print(f"Timestep Ceiling: {dt_max:g} s")
    print("\n--- Range Comparison ---")
    print(f"Ideal Range (No Drag): {ideal:.2f} m")
    print(f"Realistic Range ({mode}): {ground_range:.2f} m")
    print(f"Actual Flight Time: {flight_time:.2f} s")
    print(f"Integration Steps: {result.steps}")
    if result.timestep_min is not None and result.timestep_min < dt_max:
        print(f"Shortest Step Taken: {result.timestep_min:.6g} s")
    if result.timed_out:
        print(
            f"WARNING: simulation stopped at the {DEFAULT_PARAMETERS.max_time:g} s "
            "time limit without reaching the ground"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))