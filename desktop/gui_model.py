"""GUI-independent logic for the desktop apps.

Everything here is free of Tkinter so it can be unit-tested headlessly. The GUIs
(:mod:`app_common`, :mod:`ballistic_app`, :mod:`orbital_app`) only wire widgets
to these functions.

The drag-coefficient presets, default launch conditions, and the dt validation
messages mirror ``webapp/src/lib/sim.ts``. That duplication is intentional (each
entry point stays self-contained) and is guarded by
``desktop/tests/test_agreement.py``, which parses ``sim.ts`` and fails if the
values or labels ever drift apart. Update both when a preset or message changes.

The N-body section (scenario presets, condition parsing, :func:`run_nbody`) has
no webapp counterpart: the API exposes only single-body launches, so those
presets and validation messages are desktop-only and live at the end of this
module.
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

from ballistics import (  # noqa: E402
    EARTH_ATMOSPHERE_LAYERS,
    ProjectileSimulator,
    SimulationDiverged,
    atmospheric_drag,
    exponential_density,
    flat_altitude,
    j2_gravity,
    magnus_lift,
    newtonian_gravity,
    orbital_altitude,
    tabulated_density,
)
from nbody import (  # noqa: E402
    Body as NBodyBody,
    NBodySimulator,
    SystemState,
    total_energy,
)
from orbital import OrbitalElements, orbital_elements  # noqa: E402
from physics_config import DEFAULT_PARAMETERS, coerce_parameters  # noqa: E402

KMPH_TO_MPS = 1000 / 3600

GRAVITY_MODELS = ("constant", "newtonian", "j2")
DRAG_MODELS = ("constant", "exponential", "tabulated")

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
DEFAULT_SPIN_RPM = 0.0
DEFAULT_SPIN_AXIS_DEG = 0.0

SPIN_RATE_MIN = 0.0
SPIN_RATE_MAX = 6000.0
SPIN_AXIS_MIN = -180.0
SPIN_AXIS_MAX = 180.0

# The only supported drag coefficient is the default sphere; the value and label
# mirror DRAG_PRESETS in webapp/src/lib/sim.ts. Kept as a list so the agreement
# test still guards the default against drift.
DRAG_PRESETS: tuple[tuple[float, str], ...] = (
    (DRAG_COEFFICIENT_DEFAULT, "球体（既定値）"),
)

MAX_TRAJECTORY_POINTS = 2000

# Order and labels for the gravity / drag-density selectors. The values are the
# exact strings :func:`simulate` accepts (see GRAVITY_MODELS / DRAG_MODELS).
GRAVITY_PRESETS: tuple[tuple[str, str], ...] = (
    ("constant", "一定（地表弾道）"),
    ("newtonian", "ニュートン（軌道）"),
    ("j2", "ニュートン+J2（軌道）"),
)

# "none" disables drag entirely; the remaining values map onto DRAG_MODELS and
# ``None`` is realised by forcing ``drag_coefficient`` to 0.
DENSITY_PRESETS: tuple[tuple[str, str], ...] = (
    ("none", "なし"),
    ("constant", "一様（既定）"),
    ("exponential", "指数（高度依存）"),
    ("tabulated", "区分指数（0–1000 km）"),
)

DEFAULT_ORBITAL_RADIUS = 7.0e6

RADIUS_MIN = 6.5e6
RADIUS_MAX = 4.2e7
ORBITAL_SPEED_MIN = 100.0
ORBITAL_SPEED_MAX = 12000.0

# Closed orbits are integrated for one full period times this margin, so the
# trajectory visibly closes instead of stopping after the projectile max_time.
ORBITAL_PERIOD_MARGIN = 1.05

# Upper bound on the number of integration steps for one orbit. A full period at
# the projectile dt (0.01 s) would need ~600k steps (~30 s of wall time), so the
# orbital timestep is raised to ``period / this`` when the caller asks for finer.
MAX_ORBITAL_STEPS = 4000

# Placeholder rows shown before the first run (ballistic shape, values blank).
# Kept in sync with :func:`result_metrics` by ``test_gui_model``.
DEFAULT_METRIC_ROWS: tuple[tuple[str, str, str], ...] = (
    ("ideal_range", "理想射程（抗力なし）", "-"),
    ("ground_range", "実射程（抗力あり）", "-"),
    ("reduction", "到達距離の低減率", "-"),
    ("lateral_range", "横方向のずれ z", "-"),
    ("flight_time", "飛行時間", "-"),
    ("impact_speed", "着弾速度", "-"),
    ("steps", "積分ステップ数", "-"),
    ("timestep", "刻み幅", "-"),
    ("landed", "着弾", "-"),
)

# Placeholder rows for the orbital window before the first run. Kept in sync
# with :func:`result_metrics` for an orbital outcome by ``test_gui_model``.
DEFAULT_ORBITAL_METRIC_ROWS: tuple[tuple[str, str, str], ...] = (
    ("semi_major_axis", "長半径 a", "-"),
    ("eccentricity", "離心率 e", "-"),
    ("periapsis", "近点半径 r_p", "-"),
    ("apoapsis", "遠点半径 r_a", "-"),
    ("period", "公転周期 T", "-"),
    ("inclination", "軌道傾斜角 i", "-"),
    ("flight_time", "積分時間", "-"),
    ("steps", "積分ステップ数", "-"),
    ("timestep", "刻み幅", "-"),
)

# Placeholder rows for the N-body window before the first run. Kept in sync
# with :func:`nbody_result_metrics` by ``test_nbody_gui_model``.
DEFAULT_NBODY_METRIC_ROWS: tuple[tuple[str, str, str], ...] = (
    ("bodies", "天体数", "-"),
    ("elapsed", "経過時間", "-"),
    ("steps", "積分ステップ数", "-"),
    ("timed_out", "時間上限", "-"),
    ("energy_drift", "エネルギー相対変化", "-"),
    ("frames", "記録フレーム数", "-"),
)


@dataclass(frozen=True)
class LaunchConditions:
    """The launch inputs collected from the UI, before running a simulation.

    ``gravity_model`` selects the acceleration field: ``"constant"`` (the flat
    surface field used for projectiles), ``"newtonian"`` (central gravity, in
    which case ``initial_state`` supplies the full 6-component state and
    ``velocity_kmph``/``angle_deg`` are ignored), or ``"j2"`` (Newtonian plus
    the oblateness perturbation). ``drag_model`` selects the drag law:
    ``"constant"`` (density from the profile's ``air_density``), or a
    position-dependent atmosphere (``"exponential"`` or ``"tabulated"``).
    """

    velocity_kmph: float = DEFAULT_VELOCITY_KMPH
    angle_deg: float = DEFAULT_ANGLE_DEG
    dt: float = DEFAULT_TIMESTEP
    adaptive: bool = DEFAULT_ADAPTIVE
    drag_coefficient: float = DRAG_COEFFICIENT_DEFAULT
    gravity_model: str = "constant"
    drag_model: str = "constant"
    j2: float | None = None
    initial_state: tuple[float, float, float, float, float, float] | None = None
    spin_rate: float = DEFAULT_SPIN_RPM
    spin_axis_deg: float = DEFAULT_SPIN_AXIS_DEG


@dataclass(frozen=True)
class TrajectoryPoint:
    """One recorded integration step, in the same shape the web API returns."""

    t: float
    x: float
    y: float
    vx: float
    vy: float
    speed: float
    z: float = 0.0


@dataclass(frozen=True)
class SimulationResult:
    """Outcome metrics, named to match the web API's ``result`` object.

    ``ideal_range`` is ``None`` for central-gravity runs, where the flat-surface
    closed form does not apply.
    """

    ideal_range: float | None
    ground_range: float | None
    flight_time: float
    impact_speed: float
    landed: bool
    timed_out: bool
    steps: int
    timestep_min: float | None
    timestep_max: float | None
    lateral_range: float = 0.0


@dataclass(frozen=True)
class SimulationOutcome:
    """A full run: the conditions, the metrics, and the recorded trajectory.

    ``orbital`` carries the osculating elements for central-gravity runs and is
    ``None`` for surface projectiles.
    """

    conditions: LaunchConditions
    result: SimulationResult
    trajectory: list[TrajectoryPoint] = field(default_factory=list)
    orbital: OrbitalElements | None = None

    @property
    def reduction_percent(self) -> float:
        """Distance lost to drag as a percentage of the ideal range."""
        ideal = self.result.ideal_range
        if ideal is None or ideal <= 0.0:
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


def gravity_label(value: str) -> str:
    """Human label for a gravity-model value (falls back to the raw value)."""
    for candidate, label in GRAVITY_PRESETS:
        if candidate == value:
            return label
    return value


def density_label(value: str) -> str:
    """Human label for a drag-density value (falls back to the raw value)."""
    for candidate, label in DENSITY_PRESETS:
        if candidate == value:
            return label
    return value


def orbital_speed(radius: float, mu: float = DEFAULT_PARAMETERS.mu) -> float:
    """Circular-orbit speed ``sqrt(mu / r)`` at ``radius`` (SI units)."""
    if radius <= 0.0:
        raise ValueError("radius must be greater than 0")
    return math.sqrt(mu / radius)


def orbital_time_span(
    state: tuple[float, float, float, float, float, float],
    mu: float = DEFAULT_PARAMETERS.mu,
    margin: float = ORBITAL_PERIOD_MARGIN,
) -> float | None:
    """Integration span for a central-gravity run: one orbital period × ``margin``.

    A closed orbit is integrated for a full revolution so the trajectory closes,
    rather than stopping at the projectile ``max_time`` (300 s) after a short arc.
    Open orbits (``period is None``) return ``None`` so the caller keeps the
    configured ``max_time``.
    """
    elements = orbital_elements(state, mu)
    if elements.period is None:
        return None
    return elements.period * margin


def orbital_timestep(
    state: tuple[float, float, float, float, float, float],
    requested_dt: float,
    mu: float = DEFAULT_PARAMETERS.mu,
    max_steps: int = MAX_ORBITAL_STEPS,
    margin: float = ORBITAL_PERIOD_MARGIN,
) -> float:
    """Orbital timestep bounded by ``max_steps`` over one orbit.

    Returns ``max(requested_dt, period * margin / max_steps)`` for a closed orbit
    so a full revolution stays affordable; open orbits return ``requested_dt``.
    A coarser ``requested_dt`` is always honoured (fewer steps than the bound).
    """
    span = orbital_time_span(state, mu, margin)
    if span is None:
        return requested_dt
    return max(requested_dt, span / max_steps)


def make_conditions(
    *,
    gravity_model: str = "constant",
    velocity_kmph: float = DEFAULT_VELOCITY_KMPH,
    angle_deg: float = DEFAULT_ANGLE_DEG,
    dt: float = DEFAULT_TIMESTEP,
    adaptive: bool = DEFAULT_ADAPTIVE,
    drag_coefficient: float = DRAG_COEFFICIENT_DEFAULT,
    density_model: str = "constant",
    radius: float = DEFAULT_ORBITAL_RADIUS,
    speed_mps: float | None = None,
    spin_rate: float = DEFAULT_SPIN_RPM,
    spin_axis_deg: float = DEFAULT_SPIN_AXIS_DEG,
) -> LaunchConditions:
    """Assemble :class:`LaunchConditions` from the UI's raw control values.

    ``density_model`` is a :data:`DENSITY_PRESETS` value; ``"none"`` disables drag
    (``drag_coefficient = 0``). For a central-gravity model the state is a
    circular orbit at ``radius`` (speed defaults to the circular speed), which
    makes ``velocity_kmph`` / ``angle_deg`` irrelevant. ``spin_rate`` /
    ``spin_axis_deg`` drive the Magnus force and apply to the flat-surface
    ballistic model only.
    """
    if gravity_model not in GRAVITY_MODELS:
        raise ValueError(f"unknown gravity_model: {gravity_model!r}")
    if density_model not in tuple(value for value, _ in DENSITY_PRESETS):
        raise ValueError(f"unknown density_model: {density_model!r}")

    drag_model = "constant" if density_model == "none" else density_model
    coefficient = 0.0 if density_model == "none" else drag_coefficient

    initial_state = None
    if gravity_model != "constant":
        speed = orbital_speed(radius) if speed_mps is None else speed_mps
        initial_state = (radius, 0.0, 0.0, 0.0, speed, 0.0)

    return LaunchConditions(
        velocity_kmph=velocity_kmph,
        angle_deg=angle_deg,
        dt=dt,
        adaptive=adaptive,
        drag_coefficient=coefficient,
        gravity_model=gravity_model,
        drag_model=drag_model,
        initial_state=initial_state,
        spin_rate=spin_rate,
        spin_axis_deg=spin_axis_deg,
    )


def format_optional(value: float | None, digits: int = 2) -> str:
    """Fixed-decimal formatting that renders ``None`` as a dash."""
    if value is None:
        return "-"
    return format_number(value, digits)


def result_metrics(outcome: SimulationOutcome) -> list[tuple[str, str, str]]:
    """``(key, label, value)`` rows for the results panel.

    Ballistic runs report range metrics; central-gravity runs report the
    osculating elements instead. Both share step/timestep rows.
    """
    result = outcome.result
    timestep_label = "最短刻み" if outcome.conditions.adaptive else "刻み幅"
    timestep = (
        f"{format_decimal(result.timestep_min)} s"
        if result.timestep_min is not None
        else "-"
    )

    if outcome.orbital is None:
        return [
            ("ideal_range", "理想射程（抗力なし）", f"{format_number(result.ideal_range)} m"),
            ("ground_range", "実射程（抗力あり）", f"{format_number(result.ground_range)} m"),
            ("reduction", "到達距離の低減率", f"{format_number(outcome.reduction_percent, 1)} %"),
            ("lateral_range", "横方向のずれ z", f"{format_number(result.lateral_range)} m"),
            ("flight_time", "飛行時間", f"{format_number(result.flight_time)} s"),
            ("impact_speed", "着弾速度", f"{format_number(result.impact_speed)} m/s"),
            ("steps", "積分ステップ数", str(result.steps)),
            ("timestep", timestep_label, timestep),
            ("landed", "着弾", "yes" if result.landed else "no"),
        ]

    elements = outcome.orbital
    return [
        ("semi_major_axis", "長半径 a", f"{format_optional(elements.semi_major_axis)} m"),
        ("eccentricity", "離心率 e", f"{format_number(elements.eccentricity, 6)}"),
        ("periapsis", "近点半径 r_p", f"{format_number(elements.periapsis)} m"),
        ("apoapsis", "遠点半径 r_a", f"{format_optional(elements.apoapsis)} m"),
        ("period", "公転周期 T", f"{format_optional(elements.period)} s"),
        (
            "inclination",
            "軌道傾斜角 i",
            f"{format_number(math.degrees(elements.inclination_rad), 4)} deg",
        ),
        ("flight_time", "積分時間", f"{format_number(result.flight_time)} s"),
        ("steps", "積分ステップ数", str(result.steps)),
        ("timestep", timestep_label, timestep),
    ]


def validate_dt(text: str) -> str | None:
    """Validate the dt entry text, returning a Japanese message or ``None``.

    Mirrors ``dtValidityMessage`` in ``webapp/src/lib/sim.ts`` for the checks that
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

    A ``"constant"`` gravity model reproduces the flat-surface projectile
    behaviour; ``"newtonian"`` and ``"j2"`` integrate central gravity from
    ``initial_state`` and additionally report the osculating elements. Raises
    whatever the core raises (:class:`SimulationDiverged` or ``ValueError`` for
    a too-coarse timestep); the caller localises the message for display.
    """
    constants = {"drag_coefficient": conditions.drag_coefficient}
    if conditions.j2 is not None:
        constants["j2"] = conditions.j2
    profile = coerce_parameters(constants)
    orbital = conditions.gravity_model in ("newtonian", "j2")

    if conditions.gravity_model == "constant":
        mu = None
        gravity_model = None
        span = None
    elif conditions.gravity_model in ("newtonian", "j2"):
        if conditions.initial_state is None:
            raise ValueError(
                f"initial_state is required for {conditions.gravity_model} gravity"
            )
        mu = profile.mu
        if conditions.gravity_model == "j2":
            gravity_model = j2_gravity(
                mu, profile.j2, profile.equatorial_radius
            )
        else:
            gravity_model = newtonian_gravity(mu)
        span = orbital_time_span(conditions.initial_state, mu)
        if span is not None:
            constants["max_time"] = span
            profile = coerce_parameters(constants)
    else:
        raise ValueError(f"unknown gravity_model: {conditions.gravity_model!r}")

    timestep = conditions.dt
    if span is not None:
        timestep = max(timestep, span / MAX_ORBITAL_STEPS)

    if conditions.drag_model not in DRAG_MODELS:
        raise ValueError(f"unknown drag_model: {conditions.drag_model!r}")
    drag_model = None
    if conditions.drag_model != "constant":
        altitude = (
            orbital_altitude(profile.equatorial_radius)
            if orbital
            else flat_altitude()
        )
        if conditions.drag_model == "exponential":
            density = exponential_density(
                profile.sea_level_density, profile.scale_height
            )
        else:
            density = tabulated_density(EARTH_ATMOSPHERE_LAYERS)
        drag_model = atmospheric_drag(profile, density, altitude)

    if conditions.gravity_model == "constant":
        lift_model = None
        if conditions.spin_rate != 0.0:
            lift_model = magnus_lift(
                profile, conditions.spin_rate, conditions.spin_axis_deg
            )
        simulator = ProjectileSimulator(
            conditions.velocity_kmph * KMPH_TO_MPS,
            math.radians(conditions.angle_deg),
            constants,
            dt=timestep,
            adaptive=conditions.adaptive,
            drag_model=drag_model,
            lift_model=lift_model,
        )
    else:
        simulator = ProjectileSimulator.from_state(
            conditions.initial_state,
            constants,
            timestep,
            adaptive=conditions.adaptive,
            gravity_model=gravity_model,
            drag_model=drag_model,
            ground_collision=False,
        )

    trajectory: list[TrajectoryPoint] = []

    def record(t: float, state: tuple[float, float, float, float, float, float]) -> None:
        x, y, z, vx, vy, vz = state
        trajectory.append(
            TrajectoryPoint(
                t=t, x=x, y=y, vx=vx, vy=vy, speed=math.hypot(vx, vy, vz), z=z
            )
        )

    ideal = None if mu is not None else simulator.calculate_ideal_range()
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
        lateral_range=raw.lateral_range,
    )
    orbital = None if mu is None else orbital_elements(simulator.state, mu)
    return SimulationOutcome(
        conditions=conditions,
        result=result,
        trajectory=_downsample(trajectory, MAX_TRAJECTORY_POINTS),
        orbital=orbital,
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

    Mirrors ``formatDecimal`` in ``webapp/src/lib/sim.ts``.
    """
    if not math.isfinite(value):
        return str(value)
    return f"{float(f'{value:.{significant_digits}g}'):g}"


def format_grouped(value: float, digits: int = 2) -> str:
    """Fixed-decimal formatting with thousands separators (as ``format_number``)."""
    return f"{value:,.{digits}f}"


def format_duration(seconds: float) -> str:
    """Decompose a duration in seconds into ``D日H時間M分S秒`` for display.

    Days are omitted when the duration is under one day.
    """
    days, remainder = divmod(int(round(seconds)), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days:,}日{hours}時間{minutes}分{secs}秒"
    return f"{hours:,}時間{minutes}分{secs}秒"


# --------------------------------------------------------------- N-body (多体)

# Gravitational constant used to derive mu from bulk density and radius:
# mu = G * rho * (4/3) pi r^3. Derived mu differs slightly from measured GM
# values (volume-mean density is an approximation); the GUI trades that
# precision for physically intuitive, editable inputs.
NBODY_G = 6.674_30e-11

# Preset centres: the first body is the central body, placed at the origin at
# rest; the remaining bodies are added from the catalogue on a circular orbit
# about it. The presets themselves only fix the centre, so a scenario starts
# with one body instead of a full configuration the user did not ask for.
NBODY_PRESET_CENTERS: dict[str, str] = {
    "sun_centered": "太陽",
    "earth_centered": "地球",
}

# Default timestep and time span per preset. The Sun-centred preset integrates
# one Earth year at dt = 3600 s (inner planets resolve well); the Earth-centred
# preset integrates one lunar period at dt = 60 s (a low orbit wants a finer dt).
SUN_CENTERED_DT = 3600.0
SUN_CENTERED_MAX_TIME = 365.25 * 86400.0
EARTH_CENTERED_DT = 60.0
EARTH_CENTERED_MAX_TIME = 27.321_661 * 86400.0

# Body catalogue for the per-body selector and the preset centre:
# (display name, bulk density kg/m^3, mean radius m, default orbital radius m)
# for the Sun, the eight planets, and the Moon. mu is derived from the density
# and radius, never stored. The default orbital radius is the body's mean
# distance from its natural primary (heliocentric for the planets, geocentric
# for the Moon; the Sun's value is its distance from Earth, used when the Sun
# is added around another centre). Selecting a body loads these into the
# inputs, which stay freely editable afterwards.
NBODY_CATALOG: tuple[tuple[str, float, float, float], ...] = (
    ("太陽", 1408.0, 695_700_000.0, 1.496e11),
    ("水星", 5427.0, 2_439_700.0, 5.791e10),
    ("金星", 5243.0, 6_051_800.0, 1.082e11),
    ("地球", 5514.0, 6_371_000.0, 1.496e11),
    ("月", 3344.0, 1_737_400.0, 3.844e8),
    ("火星", 3933.0, 3_389_500.0, 2.279e11),
    ("木星", 1326.0, 69_911_000.0, 7.785e11),
    ("土星", 687.0, 58_232_000.0, 1.434e12),
    ("天王星", 1271.0, 25_362_000.0, 2.871e12),
    ("海王星", 1638.0, 24_622_000.0, 4.495e12),
)


def nbody_mu(density: float, radius: float) -> float:
    """Gravitational parameter mu = G*M (m^3/s^2) from density and radius."""
    return NBODY_G * density * (4.0 / 3.0) * math.pi * radius**3


def _catalog_entry(name: str) -> tuple[float, float, float]:
    """(density, radius, orbit_radius) of a body; raises ``KeyError``."""
    for catalog_name, density, radius, orbit_radius in NBODY_CATALOG:
        if catalog_name == name:
            return density, radius, orbit_radius
    raise KeyError(name)


# Dropdown values and labels for the scenario presets.
NBODY_PRESETS: tuple[tuple[str, str], ...] = (
    ("sun_centered", "太陽を中心とした多体問題"),
    ("earth_centered", "地球を中心とした多体問題"),
)

# Upper bound on the integration steps of one run. One lunar period at dt = 60 s
# needs ~39k steps (< 1 s of wall time); anything beyond this is rejected with a
# Japanese message instead of freezing the UI for minutes.
MAX_NBODY_STEPS = 50_000

# Frames are recorded every accepted step and then thinned to this many, so the
# playback slider stays responsive and each redraw draws a bounded polyline.
MAX_NBODY_FRAMES = 2000


@dataclass(frozen=True)
class NBodySpec:
    """One body as entered in the UI: name, bulk density, radius, and state.

    ``mu`` is derived from density and radius (:func:`nbody_mu`) instead of
    being entered directly, so editing the physical size updates the mass.
    """

    name: str
    density: float
    radius: float
    state: tuple[float, float, float, float, float, float]

    @property
    def mu(self) -> float:
        """Gravitational parameter mu = G*M (m^3/s^2)."""
        return nbody_mu(self.density, self.radius)


@dataclass(frozen=True)
class NBodyConditions:
    """The N-body inputs collected from the UI, before running a simulation."""

    bodies: tuple[NBodySpec, ...]
    dt: float
    max_time: float

    @property
    def estimated_steps(self) -> int:
        """Steps the run will take, ``ceil(max_time / dt)`` (dt is positive)."""
        return math.ceil(self.max_time / self.dt)


@dataclass(frozen=True)
class NBodyFrame:
    """One recorded system snapshot: elapsed time and each body's (x, y, z)."""

    t: float
    positions: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class NBodyOutcome:
    """A full N-body run: conditions, metrics, and the recorded frames.

    The energy diagnostics use :func:`nbody.total_energy`'s ``G = 1`` units;
    only the relative drift between the first and last snapshot is displayed.
    """

    conditions: NBodyConditions
    elapsed_time: float
    steps: int
    timed_out: bool
    frames: list[NBodyFrame]
    energy_initial: float
    energy_final: float

    @property
    def energy_drift_percent(self) -> float:
        """Relative change of the total energy over the run, in percent."""
        baseline = abs(self.energy_initial)
        if baseline == 0.0:
            return 0.0
        return (self.energy_final - self.energy_initial) / baseline * 100.0


def nbody_circular_state(
    orbit_radius: float, central_mu: float
) -> tuple[float, float, float, float, float, float]:
    """State of a circular orbit of radius ``orbit_radius`` about a body.

    The body sits on the +x axis moving in +y at the circular speed
    ``sqrt(central_mu / orbit_radius)``. Raises ``ValueError`` when the radius
    is not positive (the speed would be undefined or imaginary).
    """
    if orbit_radius <= 0.0:
        raise ValueError("orbit_radius must be greater than 0")
    return (
        orbit_radius, 0.0, 0.0,
        0.0, math.sqrt(central_mu / orbit_radius), 0.0,
    )


def nbody_catalog_spec(
    name: str, central_mu: float, min_separation: float = 0.0
) -> NBodySpec:
    """Catalogue body ``name`` on a circular orbit about a central body.

    The catalogue's default orbital radius seeds the state; ``min_separation``
    (typically the sum of the central and body radii) keeps the body clear of
    the centre. Raises ``KeyError`` for an unknown name.
    """
    density, radius, orbit_radius = _catalog_entry(name)
    separation = max(orbit_radius, min_separation)
    return NBodySpec(
        name=name,
        density=density,
        radius=radius,
        state=nbody_circular_state(separation, central_mu),
    )


def nbody_preset_bodies(preset: str) -> tuple[NBodySpec, ...]:
    """Central body of a :data:`NBODY_PRESETS` scenario, at the origin at rest.

    The preset only fixes the centre (the Sun or the Earth); the remaining
    bodies are added from the catalogue in the UI. Starting from the centre
    alone keeps the scenario at the centre of mass (nothing drifts) until the
    user adds a body of their choosing.
    """
    try:
        name = NBODY_PRESET_CENTERS[preset]
    except KeyError:
        raise ValueError(f"unknown nbody preset: {preset!r}") from None
    density, radius, _orbit_radius = _catalog_entry(name)
    return (
        NBodySpec(
            name=name,
            density=density,
            radius=radius,
            state=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        ),
    )


def nbody_preset_conditions(preset: str) -> NBodyConditions:
    """Preset centre with a scenario-appropriate timestep and time span.

    The Sun-centred preset integrates one Earth year at ``dt = 3600 s``; the
    Earth-centred preset integrates one lunar period at ``dt = 60 s`` (~39k
    steps, under :data:`MAX_NBODY_STEPS`).
    """
    bodies = nbody_preset_bodies(preset)
    if preset == "sun_centered":
        return NBodyConditions(
            bodies=bodies, dt=SUN_CENTERED_DT, max_time=SUN_CENTERED_MAX_TIME
        )
    if preset == "earth_centered":
        return NBodyConditions(
            bodies=bodies, dt=EARTH_CENTERED_DT, max_time=EARTH_CENTERED_MAX_TIME
        )
    raise ValueError(f"unknown nbody preset: {preset!r}")


def nbody_number(text: str, label: str) -> float:
    """Parse one numeric entry, raising a Japanese :class:`ValueError`.

    ``label`` names the field (``"刻み幅 dt"``, ``"天体1 の μ"``, ...) so the
    message can point at the offending input.
    """
    try:
        value = float(text)
    except (TypeError, ValueError):
        raise ValueError(f"{label} には数値を指定してください。") from None
    if not math.isfinite(value):
        raise ValueError(f"{label} には数値を指定してください。")
    return value


# UI row order: display name, density, radius, then the six state components.
NBodyRow = tuple[str, str, str, str, str, str, str, str, str]
NBODY_STATE_FIELDS: tuple[str, ...] = ("x", "y", "z", "vx", "vy", "vz")


def nbody_conditions_from_rows(
    rows: list[NBodyRow],
    dt_text: str,
    time_text: str,
) -> NBodyConditions:
    """Assemble :class:`NBodyConditions` from the raw entry-field strings.

    Raises a Japanese :class:`ValueError` for any unparsable field or an empty
    body list; an empty body name falls back to ``天体<n>``. Range checks
    (step budget, duplicate positions) live in :func:`validate_nbody_conditions`.
    """
    if not rows:
        raise ValueError("天体を 1 つ以上指定してください。")
    bodies: list[NBodySpec] = []
    for index, row in enumerate(rows):
        if len(row) != 9:
            raise ValueError(f"天体{index + 1} の入力欄が不足しています。")
        label = f"天体{index + 1}"
        name = row[0].strip() or label
        density = nbody_number(row[1], f"{label} の体積密度")
        radius = nbody_number(row[2], f"{label} の半径")
        values = tuple(
            nbody_number(row[3 + offset], f"{label} の {field}")
            for offset, field in enumerate(NBODY_STATE_FIELDS)
        )
        bodies.append(
            NBodySpec(name=name, density=density, radius=radius, state=values)
        )
    dt = nbody_number(dt_text, "刻み幅 dt")
    max_time = nbody_number(time_text, "最大時間")
    return NBodyConditions(bodies=tuple(bodies), dt=dt, max_time=max_time)


def validate_nbody_conditions(conditions: NBodyConditions) -> str | None:
    """Range checks for parsed conditions, returning a Japanese message or ``None``.

    Mirrors the style of :func:`validate_dt`: the GUI calls this before
    spawning the worker thread so an impossible run fails fast with a message
    instead of a long freeze or a core exception.
    """
    if conditions.dt <= 0.0:
        return "刻み幅 dt は正の数で指定してください。"
    if conditions.max_time <= 0.0:
        return "最大時間は正の数で指定してください。"
    for index, body in enumerate(conditions.bodies):
        if body.density <= 0.0:
            return f"天体{index + 1} の体積密度は正の数で指定してください。"
        if body.radius <= 0.0:
            return f"天体{index + 1} の半径は正の数で指定してください。"
    steps = conditions.estimated_steps
    if steps > MAX_NBODY_STEPS:
        return (
            f"推定ステップ数 {steps:,} が上限 {MAX_NBODY_STEPS:,} を超えます。"
            f"刻み幅 dt を大きくするか、最大時間を短くしてください。"
        )
    for i in range(len(conditions.bodies)):
        for j in range(i + 1, len(conditions.bodies)):
            if conditions.bodies[i].state == conditions.bodies[j].state:
                return (
                    f"天体{i + 1} と天体{j + 1} が同じ位置で開始します。"
                    f"重力が特異になるため開始できません。"
                )
    return None


def run_nbody(conditions: NBodyConditions) -> NBodyOutcome:
    """Run one N-body simulation and record every accepted frame.

    Frames are captured through the core's ``on_step`` observation hook (the
    system tuple is immutable, so a reference can be kept without copying) and
    thinned to :data:`MAX_NBODY_FRAMES`. Raises whatever the core raises
    (:class:`SimulationDiverged` or ``ValueError``); the caller localises the
    message for display.
    """
    message = validate_nbody_conditions(conditions)
    if message is not None:
        raise ValueError(message)
    bodies = tuple(NBodyBody(spec.mu, spec.state) for spec in conditions.bodies)
    simulator = NBodySimulator(
        bodies, dt=conditions.dt, max_time=conditions.max_time
    )
    frames: list[NBodyFrame] = []

    def record(t: float, system: SystemState) -> None:
        frames.append(
            NBodyFrame(
                t=t,
                positions=tuple(
                    (state[0], state[1], state[2]) for state in system
                ),
            )
        )

    energy_initial = total_energy(simulator.bodies)
    simulator.run_simulation(on_step=record)
    energy_final = total_energy(simulator.bodies)
    raw = simulator.result()
    return NBodyOutcome(
        conditions=conditions,
        elapsed_time=raw.elapsed_time,
        steps=raw.steps,
        timed_out=raw.timed_out,
        frames=_downsample_frames(frames, MAX_NBODY_FRAMES),
        energy_initial=energy_initial,
        energy_final=energy_final,
    )


def nbody_result_metrics(outcome: NBodyOutcome) -> list[tuple[str, str, str]]:
    """``(key, label, value)`` rows for the N-body results panel."""
    return [
        ("bodies", "天体数", str(len(outcome.conditions.bodies))),
        (
            "elapsed",
            "経過時間",
            f"{format_grouped(outcome.elapsed_time)} s"
            f"（{format_duration(outcome.elapsed_time)}）",
        ),
        ("steps", "積分ステップ数", f"{outcome.steps:,}"),
        ("timed_out", "時間上限", "yes" if outcome.timed_out else "no"),
        (
            "energy_drift",
            "エネルギー相対変化",
            f"{format_decimal(outcome.energy_drift_percent)} %",
        ),
        ("frames", "記録フレーム数", f"{len(outcome.frames):,}"),
    ]


def _downsample_frames(
    frames: list[NBodyFrame], limit: int
) -> list[NBodyFrame]:
    """Thin recorded frames to at most ``limit``, always keeping the last."""
    if len(frames) <= limit:
        return frames
    step = math.ceil(len(frames) / limit)
    sampled = frames[::step]
    if sampled[-1] is not frames[-1]:
        sampled.append(frames[-1])
    return sampled


__all__ = [
    "ANGLE_MAX",
    "ANGLE_MIN",
    "DEFAULT_ADAPTIVE",
    "DEFAULT_ANGLE_DEG",
    "DEFAULT_METRIC_ROWS",
    "DEFAULT_NBODY_METRIC_ROWS",
    "DEFAULT_ORBITAL_METRIC_ROWS",
    "DEFAULT_ORBITAL_RADIUS",
    "DEFAULT_SPIN_AXIS_DEG",
    "DEFAULT_SPIN_RPM",
    "DEFAULT_TIMESTEP",
    "DEFAULT_VELOCITY_KMPH",
    "DENSITY_PRESETS",
    "DRAG_COEFFICIENT_DEFAULT",
    "DRAG_MODELS",
    "DRAG_PRESETS",
    "DT_MAX",
    "DT_MIN",
    "GRAVITY_MODELS",
    "GRAVITY_PRESETS",
    "LaunchConditions",
    "MAX_NBODY_FRAMES",
    "MAX_NBODY_STEPS",
    "MAX_ORBITAL_STEPS",
    "NBODY_CATALOG",
    "NBODY_G",
    "NBODY_PRESETS",
    "NBodyConditions",
    "NBodyFrame",
    "NBodyOutcome",
    "NBodySpec",
    "ORBITAL_PERIOD_MARGIN",
    "ORBITAL_SPEED_MAX",
    "ORBITAL_SPEED_MIN",
    "OrbitalElements",
    "RADIUS_MAX",
    "RADIUS_MIN",
    "SimulationDiverged",
    "SimulationOutcome",
    "SimulationResult",
    "SPIN_AXIS_MAX",
    "SPIN_AXIS_MIN",
    "SPIN_RATE_MAX",
    "SPIN_RATE_MIN",
    "TrajectoryPoint",
    "VELOCITY_MAX",
    "VELOCITY_MIN",
    "density_label",
    "format_decimal",
    "format_duration",
    "format_grouped",
    "format_number",
    "format_optional",
    "gravity_label",
    "make_conditions",
    "nbody_catalog_spec",
    "nbody_circular_state",
    "nbody_conditions_from_rows",
    "nbody_mu",
    "nbody_number",
    "nbody_preset_bodies",
    "nbody_preset_conditions",
    "nbody_result_metrics",
    "orbital_speed",
    "orbital_time_span",
    "orbital_timestep",
    "preset_label",
    "result_metrics",
    "run_nbody",
    "simulate",
    "validate_dt",
    "validate_nbody_conditions",
]
