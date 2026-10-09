"""Pure projectile-flight physics: RK4 integration with quadratic air drag.

No file I/O happens in this module. Callers supply a :class:`PhysicalParameters`
profile (or the legacy constants mapping) and receive the flight result, which
makes the integrator directly unit-testable.

:class:`ProjectileSimulator` integrates either at a fixed timestep or, with
``adaptive=True``, at a timestep shortened to stay inside the RK4 stability
band. The adaptive mode is a divergence safeguard: it shortens a step that would
breach the stability bound, but never lengthens one past the caller's ``dt``, so
it cannot make a result more accurate than the fixed mode at the same ``dt``.
"""

from __future__ import annotations

import math
import warnings
from typing import Any, Callable, NamedTuple

from physics_config import DEFAULT_PARAMETERS, coerce_parameters

State = tuple[float, float, float, float]

LAUNCH_X = 0.0
LAUNCH_Y = 0.0

STABILITY_LIMIT = 0.5
UPWARD_TOLERANCE = 1e-9


class SimulationDiverged(RuntimeError):
    """Raised when the integration stops producing physically meaningful states."""


def derivatives(
    state: State,
    k: float,
    gravity: float = DEFAULT_PARAMETERS.gravity,
) -> State:
    """Time derivatives of ``state = (x, y, vx, vy)``.

    ``k`` is the drag scaling factor (1/2 * rho * A * Cd) / m, so that the drag
    acceleration is -k * v * |v|. Returns (dx/dt, dy/dt, dvx/dt, dvy/dt).
    """
    vx, vy = state[2], state[3]
    speed = math.hypot(vx, vy)
    return vx, vy, -k * vx * speed, -k * vy * speed - gravity


def ideal_range(
    initial_velocity: float,
    launch_angle_rad: float,
    gravity: float = DEFAULT_PARAMETERS.gravity,
) -> float:
    """Closed-form ground range assuming no air resistance."""
    return (
        initial_velocity**2 * math.sin(2 * launch_angle_rad) / gravity
    )


class FlightResult(NamedTuple):
    """Detailed outcome of a flight, available via :meth:`ProjectileSimulator.result`."""

    ground_range: float
    flight_time: float
    impact_speed: float
    landed: bool
    timed_out: bool
    steps: int
    timestep_min: float | None
    timestep_max: float | None


class ProjectileSimulator:
    """Integrates a projectile launch with the classical RK4 method.

    With ``adaptive=False`` (the default) every step uses the configured ``dt``.
    With ``adaptive=True`` the configured ``dt`` becomes an upper bound and each
    step is shortened by :meth:`_next_timestep` to stay inside the RK4
    stability band.
    """

    def __init__(
        self,
        initial_velocity: float,
        launch_angle_rad: float,
        constants: Any = None,
        dt: float = 0.01,
        *,
        divergence_speed_factor: float = 1000.0,
        adaptive: bool = False,
    ) -> None:
        self.parameters = coerce_parameters(constants)
        self.initial_velocity = _finite("initial_velocity", initial_velocity)
        self.launch_angle_rad = _finite("launch_angle_rad", launch_angle_rad)
        self.dt = _positive("dt", dt)
        self.default_dt = self.dt
        self.adaptive = bool(adaptive)
        self.divergence_speed_factor = _positive(
            "divergence_speed_factor", divergence_speed_factor
        )
        self.k = self.parameters.drag_scaling_factor()
        self.gravity = self.parameters.gravity
        self.max_time = self.parameters.max_time
        self.initial_state: State = (
            LAUNCH_X,
            LAUNCH_Y,
            self.initial_velocity * math.cos(self.launch_angle_rad),
            self.initial_velocity * math.sin(self.launch_angle_rad),
        )
        self.reset()

    def reset(self) -> None:
        """Restore the configured launch conditions so a fresh run can start.

        This also drops any timestep override passed to
        :meth:`run_simulation`, so a failed run never leaves the simulator
        configured with the timestep that broke it.
        """
        self.state: State = self.initial_state
        self.t = 0.0
        self.landed = False
        self.timed_out = False
        self.dt = self.default_dt
        self.steps = 0
        self.timestep_min: float | None = None
        self.timestep_max: float | None = None

    def calculate_ideal_range(self) -> float:
        """Ground range that would be reached without air resistance."""
        return ideal_range(self.initial_velocity, self.launch_angle_rad, self.gravity)

    def run_simulation(
        self,
        dt: float | None = None,
        resume: bool = False,
        *,
        on_step: Callable[[float, State], None] | None = None,
    ) -> tuple[float, float]:
        """Integrate until ground impact or the configured time limit.

        Returns ``(ground_range, flight_time)``; use :meth:`result` for the
        impact speed and landing flags.

        The optional ``on_step`` callback is invoked as ``on_step(t, state)``
        with the launch state, each accepted intermediate state, and the final
        landing state. It is a pure observation hook: it does not influence the
        integration, so it is safe to use for recording a trajectory. Passing
        ``None`` (the default) keeps the behaviour identical to before.

        The call is idempotent: unless ``resume`` is true the state is reset to
        the launch conditions first, so repeated calls reproduce the same result.

        In adaptive mode ``dt`` is a ceiling, not the step actually taken: every
        step is shortened by :meth:`_next_timestep`. The step therefore never
        exceeds the value the caller asked for, so this shortens coarse
        timesteps without silently claiming more accuracy than ``dt`` allows.

        Raises:
            SimulationDiverged: the integration produced non-finite states or
                velocities beyond ``divergence_speed_factor`` times the launch
                speed, which means the timestep is too coarse for the physics.
            ValueError: an upward launch reached the ground inside the first
                timestep, which means the timestep is too coarse to be trusted.
                This stays active in adaptive mode because without drag there is
                no stability band to shrink into.
        """
        timestep = self.dt if dt is None else _positive("dt", dt)
        if resume:
            if self.landed:
                return self.state[0], self.t
        else:
            self.reset()
        self.dt = timestep
        if on_step is not None:
            on_step(self.t, self.state)

        k, gravity, dt = self.k, self.gravity, self.dt
        launch_speed = math.hypot(self.state[2], self.state[3])
        if not self.adaptive:
            self._warn_if_unstable(dt, k, launch_speed)
        speed_limit = max(
            launch_speed * self.divergence_speed_factor,
            self.gravity * self.max_time,
        )
        launched_upwards = (
            self.initial_state[3] > UPWARD_TOLERANCE * launch_speed
        )

        while True:
            if self.adaptive:
                h = self._next_timestep(self.state, dt, k)
                # max_time - t is strictly positive here: the loop below breaks
                # as soon as t reaches the limit, so this only trims the
                # overshoot instead of stalling the integration.
                h = min(h, self.max_time - self.t)
            else:
                h = dt
            next_state = self._rk4_step(self.state, h, k, gravity)
            next_t = self.t + h
            self._record_timestep(h)

            self._guard_against_divergence(next_state, speed_limit)

            if next_state[1] < 0.0:
                if self.steps == 1 and launched_upwards:
                    raise ValueError(
                        f"timestep dt={h:g} is too coarse: an upward launch reached "
                        f"the ground within the first step. Reduce dt below "
                        f"{self._stable_timestep(k, launch_speed):g}."
                    )
                self.state, self.t = self._interpolate_ground_crossing(
                    self.state, next_state, self.t, h
                )
                self.landed = True
                if on_step is not None:
                    on_step(self.t, self.state)
                break

            self.state = next_state
            self.t = next_t
            if on_step is not None:
                on_step(self.t, self.state)
            if self.t >= self.max_time:
                self.timed_out = True
                break

        return self.state[0], self.t

    def _next_timestep(self, state: State, dt_max: float, k: float) -> float:
        """Step to take from ``state``, never longer than ``dt_max``.

        The only limit is the RK4 stability bound ``STABILITY_LIMIT / (k * speed)``,
        the same divergence guard as :meth:`_stable_timestep` but evaluated at the
        speed reached here rather than at the launch speed.

        The result is never larger than ``dt_max``, so the step only shrinks. That
        makes this a divergence safeguard rather than an accuracy upgrade: the
        overall error still scales with the caller's ``dt_max``.

        A cap on the time remaining until impact was tried here and removed. Any
        bound of the form ``h <= c * y / -vy`` with ``c < 1`` lets the step cover
        only a fixed fraction of the height still to fall, so ``y`` decays
        geometrically towards zero and never passes it; since landing is detected
        by the strict test ``y < 0``, the integration would never terminate. The
        cap is also redundant, because the ground crossing is already resolved by
        the interpolation in :meth:`_interpolate_ground_crossing`.
        """
        speed = math.hypot(state[2], state[3])
        return min(dt_max, self._stable_timestep(k, speed))

    def _record_timestep(self, timestep: float) -> None:
        self.steps += 1
        if self.timestep_min is None or timestep < self.timestep_min:
            self.timestep_min = timestep
        if self.timestep_max is None or timestep > self.timestep_max:
            self.timestep_max = timestep

    @staticmethod
    def _stable_timestep(k: float, speed: float) -> float:
        """Largest timestep that keeps the explicit RK4 within its stability band."""
        if k <= 0.0 or speed <= 0.0:
            return float("inf")
        return STABILITY_LIMIT / (k * speed)

    def _warn_if_unstable(self, dt: float, k: float, launch_speed: float) -> None:
        """Warn when dt breaches the explicit-RK4 stability band.

        Only the fixed-timestep mode reaches this; adaptive mode shortens the
        step instead of warning. This is a divergence guard, not an accuracy
        guarantee: the measured range error still grows roughly as
        (dt * k * v)**2, so keeping dt below the advertised value only bounds
        divergence, not the error magnitude. Tight accuracy needs a much smaller
        dt, or an adaptive timestep.
        """
        stable_dt = self._stable_timestep(k, launch_speed)
        if dt <= stable_dt:
            return
        warnings.warn(
            f"timestep dt={dt:g} is too coarse for a {launch_speed:.3f} m/s launch: "
            f"dt*k*v = {dt * k * launch_speed:.3f} exceeds {STABILITY_LIMIT}, so the "
            f"RK4 result may be inaccurate. Use dt <= {stable_dt:g} to stay stable.",
            RuntimeWarning,
            stacklevel=3,
        )

    def _guard_against_divergence(self, state: State, speed_limit: float) -> None:
        if not all(map(math.isfinite, state)):
            raise SimulationDiverged(
                f"integration produced a non-finite state {state}; "
                f"the timestep is too coarse for this scenario"
            )
        speed = math.hypot(state[2], state[3])
        if speed > speed_limit:
            raise SimulationDiverged(
                f"integration produced a speed of {speed:.4g} m/s, more than "
                f"{self.divergence_speed_factor:g}x the launch speed; "
                f"the timestep is too coarse for this scenario"
            )

    def result(self) -> FlightResult:
        """Snapshot of the current state as a :class:`FlightResult`."""
        return FlightResult(
            ground_range=self.state[0],
            flight_time=self.t,
            impact_speed=math.hypot(self.state[2], self.state[3]),
            landed=self.landed,
            timed_out=self.timed_out,
            steps=self.steps,
            timestep_min=self.timestep_min,
            timestep_max=self.timestep_max,
        )

    @staticmethod
    def _rk4_step(state: State, dt: float, k: float, gravity: float) -> State:
        k1 = derivatives(state, k, gravity)
        s2 = _advance(state, k1, dt / 2)
        k2 = derivatives(s2, k, gravity)
        s3 = _advance(state, k2, dt / 2)
        k3 = derivatives(s3, k, gravity)
        s4 = _advance(state, k3, dt)
        k4 = derivatives(s4, k, gravity)
        return tuple(
            state[i] + dt * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) / 6
            for i in range(4)
        )

    @staticmethod
    def _interpolate_ground_crossing(
        state: State, next_state: State, t: float, dt: float
    ) -> tuple[State, float]:
        """Interpolate the exact y = 0 crossing inside a timestep.

        Returns the crossing state together with its time.
        """
        span = state[1] - next_state[1]
        ratio = state[1] / span if span != 0.0 else 1.0
        ratio = min(max(ratio, 0.0), 1.0)
        crossed: State = (
            state[0] + ratio * (next_state[0] - state[0]),
            0.0,
            state[2] + ratio * (next_state[2] - state[2]),
            state[3] + ratio * (next_state[3] - state[3]),
        )
        return crossed, t + ratio * dt


def _advance(state: State, derivative: State, h: float) -> State:
    return tuple(state[i] + h * derivative[i] for i in range(4))


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value}")
    return float(value)


def _positive(name: str, value: Any) -> float:
    number = _finite(name, value)
    if number <= 0.0:
        raise ValueError(f"{name} must be greater than 0, got {number}")
    return number