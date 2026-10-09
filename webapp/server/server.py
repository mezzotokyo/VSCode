#!/usr/bin/env python3
"""JSON API for the projectile simulator, built on the standard library only.

The server reuses the tested physics in ``range_calculator`` (``ballistics`` and
``physics_config``) instead of re-implementing it. It exposes three endpoints on
top of that core (two read-only GET and one POST):

    GET  /api/health    liveness probe
    GET  /api/config    built-in defaults for the launch scenario
    POST /api/simulate  run one launch and return the summary plus trajectory

Run it with::

    python3 webapp/server/server.py --port 8000

The response is JSON; ``Access-Control-Allow-Origin`` is permissive so the Vite
dev server can talk to it directly (a dev proxy is also configured, so CORS is
not strictly required).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RANGE_CALCULATOR = REPO_ROOT / "range_calculator"
if str(RANGE_CALCULATOR) not in sys.path:
    sys.path.insert(0, str(RANGE_CALCULATOR))

from ballistics import ProjectileSimulator, SimulationDiverged  # noqa: E402
from physics_config import DEFAULT_PARAMETERS  # noqa: E402

KMPH_TO_MPS = 1000 / 3600

DEFAULT_VELOCITY_KMPH = 170.0
DEFAULT_ANGLE_DEG = 35.0
DEFAULT_TIMESTEP = 0.01

PARAMETER_FIELDS = (
    "max_time",
    "gravity",
    "air_density",
    "mass",
    "diameter",
    "drag_coefficient",
)

MAX_TRAJECTORY_POINTS = 2000

_TOO_COARSE_RE = re.compile(
    r"timestep dt=(?P<dt>\S+) is too coarse: an upward launch reached the "
    r"ground within the first step\. Reduce dt below (?P<stable>\S+)\."
)


class BadRequest(ValueError):
    """Raised when the request payload cannot be turned into a scenario."""


def localize_error(message: str) -> str:
    """Translate the physics core's timestep errors into Japanese for the UI.

    The core (:mod:`ballistics`) keeps its messages in English because they are
    asserted by the unit tests. This adapter is the presentation boundary, so
    only user-facing timestep failures are rewritten here; anything that does not
    match a known pattern is returned unchanged.
    """
    match = _TOO_COARSE_RE.search(message)
    if match:
        return (
            f"刻み幅 dt={match['dt']} は粗すぎます。上方向への発射が最初のステップで"
            f"地面に到達しました。dt を {match['stable']} 未満にしてください。"
        )
    if "non-finite state" in message:
        return (
            "刻み幅 dt が大きすぎて計算が発散しました（非有限値）。"
            "dt を小さくしてください。"
        )
    if "more than" in message and "launch speed" in message:
        return (
            "刻み幅 dt が大きすぎて計算速度が発散しました。dt を小さくしてください。"
        )
    return message


def _number(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BadRequest(f"{key} must be a number")
    if not math.isfinite(value):
        raise BadRequest(f"{key} must be finite")
    return float(value)


def _boolean(payload: dict[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise BadRequest(f"{key} must be a boolean")
    return value


def _parameter_overrides(payload: dict[str, Any]) -> dict[str, float] | None:
    raw = payload.get("parameters")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise BadRequest("parameters must be an object")
    unknown = set(raw) - set(PARAMETER_FIELDS)
    if unknown:
        raise BadRequest(f"unknown parameters: {sorted(unknown)}")
    return {key: _number(raw, key, 0.0) for key in raw}


def simulate(payload: dict[str, Any]) -> dict[str, Any]:
    velocity_kmph = _number(payload, "velocity_kmph", DEFAULT_VELOCITY_KMPH)
    angle_deg = _number(payload, "angle_deg", DEFAULT_ANGLE_DEG)
    dt = _number(payload, "dt", DEFAULT_TIMESTEP)
    adaptive = _boolean(payload, "adaptive", False)
    if dt <= 0.0:
        raise BadRequest("dt must be greater than 0")

    constants = _parameter_overrides(payload)
    simulator = ProjectileSimulator(
        velocity_kmph * KMPH_TO_MPS,
        math.radians(angle_deg),
        constants,
        dt=dt,
        adaptive=adaptive,
    )

    trajectory: list[dict[str, float]] = []

    def record(t: float, state: tuple[float, float, float, float]) -> None:
        x, y, vx, vy = state
        trajectory.append(
            {"t": t, "x": x, "y": y, "vx": vx, "vy": vy, "speed": math.hypot(vx, vy)}
        )

    ideal_range = simulator.calculate_ideal_range()
    ground_range, flight_time = simulator.run_simulation(on_step=record)
    result = simulator.result()

    return {
        "input": {
            "velocity_kmph": velocity_kmph,
            "angle_deg": angle_deg,
            "dt": dt,
            "adaptive": adaptive,
        },
        "result": {
            "ideal_range": ideal_range,
            "ground_range": ground_range,
            "flight_time": flight_time,
            "impact_speed": result.impact_speed,
            "landed": result.landed,
            "timed_out": result.timed_out,
            "steps": result.steps,
            "timestep_min": result.timestep_min,
            "timestep_max": result.timestep_max,
        },
        "trajectory": _downsample(trajectory, MAX_TRAJECTORY_POINTS),
    }


def _downsample(points: list[dict[str, float]], limit: int) -> list[dict[str, float]]:
    if len(points) <= limit:
        return points
    step = math.ceil(len(points) / limit)
    sampled = points[::step]
    if sampled[-1] is not points[-1]:
        sampled.append(points[-1])
    return sampled


def default_config() -> dict[str, Any]:
    return {
        "defaults": {
            "velocity_kmph": DEFAULT_VELOCITY_KMPH,
            "angle_deg": DEFAULT_ANGLE_DEG,
            "dt": DEFAULT_TIMESTEP,
            "adaptive": False,
        },
        "parameters": {
            field: getattr(DEFAULT_PARAMETERS, field) for field in PARAMETER_FIELDS
        },
    }


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "RangeCalcAPI/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        sys.stderr.write(f"[api] {self.address_string()} {format % args}\n")

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(204, {})

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            self._send_json(200, {"status": "ok"})
        elif path == "/api/config":
            self._send_json(200, default_config())
        else:
            self._send_json(404, {"error": f"not found: {path}"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/api/simulate":
            self._send_json(404, {"error": f"not found: {path}"})
            return
        try:
            payload = self._read_json()
            self._send_json(200, simulate(payload))
        except (TypeError, ValueError) as exc:
            # BadRequest is a ValueError subclass, so malformed input and
            # validation failures share the same 400 response.
            self._send_json(400, {"error": localize_error(str(exc))})
        except SimulationDiverged as exc:
            self._send_json(422, {"error": localize_error(str(exc))})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BadRequest(f"invalid JSON body: {exc}") from exc
        if not isinstance(payload, dict):
            raise BadRequest("request body must be a JSON object")
        return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Projectile simulator JSON API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), ApiHandler)
    print(f"RangeCalc API listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
