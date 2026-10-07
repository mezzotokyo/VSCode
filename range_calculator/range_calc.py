"""Command line entry point: reads a launch scenario and prints the range.

Usage::

    python range_calc.py [scenario_path] [dt_max] [--adaptive] [--v0=<km/h>] [--angle=<deg>]

``dt_max`` is a ceiling: with ``--adaptive`` each step is shortened to stay
inside the RK4 stability band, so a coarse value trades accuracy for stability
rather than diverging. ``--v0`` and ``--angle`` override the launch conditions
per field, falling back to the scenario file and then to the built-in
defaults.

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


def load_scenario(
    path: Path | str | None = None,
    *,
    v0_kmph: float | None = None,
    angle_deg: float | None = None,
) -> tuple[float, float]:
    """Resolve ``velocity_kmph, angle_deg`` per field with fallback.

    Each field uses ``v0_kmph`` / ``angle_deg`` when provided, otherwise the
    scenario file, otherwise the built-in defaults. The file is read only when
    a field still needs it; a missing file, an unparsable number, or a short
    line resolves to the default instead of raising.
    """
    velocity = v0_kmph
    angle = angle_deg
    if velocity is None or angle is None:
        file_velocity, file_angle = _read_scenario(path)
        if velocity is None:
            velocity = file_velocity
        if angle is None:
            angle = file_angle
    return velocity, angle


def _read_scenario(path: Path | str | None) -> tuple[float, float]:
    """Read ``velocity_kmph, angle_deg`` and fall back to the defaults."""
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


def parse_args(
    argv: list[str] | None = None,
) -> tuple[Path | str | None, float, bool, float | None, float | None]:
    """Split ``argv`` into path, ceiling, mode flag, and launch overrides.

    Positional arguments are ``[scenario_path] [dt_max]``; ``--adaptive``
    switches the integrator to the adaptive-timestep mode. Launch conditions
    may be overridden with ``--v0=<km/h>`` and ``--angle=<deg>`` (equals form
    only); each field independently falls back to the scenario file and then
    to the built-in defaults. An empty or omitted ``argv`` yields the shipped
    defaults, which is what ``main()`` relies on; the ``__main__`` block is
    what forwards the real command line.
    """
    args = list(argv or [])
    adaptive = False
    if "--adaptive" in args:
        args.remove("--adaptive")
        adaptive = True

    v0: float | None = None
    angle: float | None = None
    positional: list[str] = []
    for token in args:
        if token in ("--v0", "--angle"):
            raise SystemExit(
                f"error: {token} requires the equals form, e.g. {token}=170"
            )
        if token.startswith("--v0=") or token.startswith("--angle="):
            name, _, raw = token.partition("=")
            value = _parse_override(name, raw)
            if name == "--v0":
                if v0 is not None:
                    raise SystemExit("error: --v0 given more than once")
                v0 = value
            else:
                if angle is not None:
                    raise SystemExit("error: --angle given more than once")
                angle = value
            continue
        positional.append(token)

    path: Path | str | None = None
    dt_max = DEFAULT_TIMESTEP
    for token in positional:
        if token == "":
            continue
        try:
            dt_max = float(token)
        except ValueError:
            if path is None:
                path = token
    return path, dt_max, adaptive, v0, angle


def _parse_override(name: str, raw: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        raise SystemExit(f"error: {name} expects a number, got {raw!r}") from None
    if not math.isfinite(value):
        raise SystemExit(f"error: {name} expects a finite number, got {raw!r}")
    return value


def main(argv: list[str] | None = None) -> int:
    path, dt_max, adaptive, v0_kmph, angle_override = parse_args(argv)

    velocity_kmph, angle_deg = load_scenario(
        path, v0_kmph=v0_kmph, angle_deg=angle_override
    )

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