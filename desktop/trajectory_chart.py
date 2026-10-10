"""Trajectory chart drawn on a Tk canvas.

This is the desktop counterpart of ``webapp/src/components/TrajectoryChart.tsx``:
the same axis/grid layout, the same "nice" tick spacing, and the same colours.
No chart library is used, matching the web app's hand-rolled SVG.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import Sequence

from gui_model import SimulationOutcome, TrajectoryPoint

MARGIN = {"top": 28, "right": 28, "bottom": 52, "left": 68}

COLOR_GRID = "#e5edf5"
COLOR_AXIS = "#9fb3c8"
COLOR_TICK = "#7b8794"
COLOR_AXIS_LABEL = "#52606d"
COLOR_TRAJECTORY = "#2f80ed"
COLOR_IDEAL = "#f2994a"
COLOR_IDEAL_LABEL = "#b45309"
COLOR_LAUNCH = "#27ae60"
COLOR_LANDING = "#eb5757"
COLOR_BACKGROUND = "#ffffff"
COLOR_BORDER = "#d9e2ec"


def nice_step(value_range: float, count: int) -> float:
    """A round tick spacing close to ``value_range / count``.

    Port of ``niceStep`` in ``TrajectoryChart.tsx``.
    """
    if value_range <= 0:
        return 1.0
    raw = value_range / count
    magnitude = 10.0 ** math.floor(math.log10(raw))
    normalized = raw / magnitude
    if normalized <= 1:
        nice = 1
    elif normalized <= 2:
        nice = 2
    elif normalized <= 5:
        nice = 5
    else:
        nice = 10
    return nice * magnitude


def ticks(maximum: float, count: int) -> list[float]:
    """Tick values from 0 up to ``maximum`` (inclusive where it lands on a step)."""
    step = nice_step(maximum, count)
    values: list[float] = []
    value = 0.0
    while value <= maximum + step / 2:
        values.append(round(value, 6))
        value += step
    return values


class TrajectoryChart(tk.Canvas):
    """A canvas that renders one simulation's trajectory and ideal-range line."""

    def __init__(self, master: tk.Misc, **kwargs: object) -> None:
        super().__init__(
            master,
            background=COLOR_BACKGROUND,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            **kwargs,
        )
        self._trajectory: Sequence[TrajectoryPoint] = []
        self._ideal_range = 0.0
        self._ground_range = 0.0
        self.bind("<Configure>", lambda _event: self._redraw())

    def show(self, outcome: SimulationOutcome) -> None:
        """Render the trajectory and markers for a completed simulation."""
        self._trajectory = outcome.trajectory
        self._ideal_range = outcome.result.ideal_range
        self._ground_range = outcome.result.ground_range
        self._redraw()

    def clear(self) -> None:
        """Remove the current drawing."""
        self._trajectory = []
        self._ideal_range = 0.0
        self._ground_range = 0.0
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        plot_width = width - MARGIN["left"] - MARGIN["right"]
        plot_height = height - MARGIN["top"] - MARGIN["bottom"]
        if plot_width <= 1 or plot_height <= 1:
            return

        points = self._trajectory
        max_x = max(
            [self._ideal_range, self._ground_range]
            + [point.x for point in points]
            + [1.0]
        )
        max_y = max([point.y for point in points] + [1.0])
        x_domain = max_x * 1.05
        y_domain = max_y * 1.15

        def sx(x: float) -> float:
            return MARGIN["left"] + x / x_domain * plot_width

        def sy(y: float) -> float:
            return MARGIN["top"] + plot_height - y / y_domain * plot_height

        left = MARGIN["left"]
        top = MARGIN["top"]
        right = left + plot_width
        bottom = top + plot_height

        for value in ticks(y_domain, 5):
            y = sy(value)
            self.create_line(left, y, right, y, fill=COLOR_GRID)
            self.create_text(
                left - 10, y, text=f"{value:.0f}", fill=COLOR_TICK, anchor="e"
            )

        for value in ticks(x_domain, 6):
            x = sx(value)
            self.create_line(x, top, x, bottom, fill=COLOR_GRID)
            self.create_text(
                x, bottom + 20, text=f"{value:.0f}", fill=COLOR_TICK, anchor="n"
            )

        self.create_line(left, top, left, bottom, fill=COLOR_AXIS, width=2)
        self.create_line(left, bottom, right, bottom, fill=COLOR_AXIS, width=2)

        if self._ideal_range > 0:
            x = sx(self._ideal_range)
            self.create_line(
                x, top, x, bottom, fill=COLOR_IDEAL, dash=(6, 5)
            )
            self.create_text(
                x - 6,
                top + 14,
                text=f"ideal {self._ideal_range:.1f} m",
                fill=COLOR_IDEAL_LABEL,
                anchor="e",
            )

        if points:
            coords: list[float] = []
            for point in points:
                coords.extend((sx(point.x), sy(point.y)))
            if len(coords) >= 4:
                self.create_line(*coords, fill=COLOR_TRAJECTORY, width=3)

            launch = points[0]
            landing = points[-1]
            self.create_oval(
                sx(landing.x) - 5,
                sy(landing.y) - 5,
                sx(landing.x) + 5,
                sy(landing.y) + 5,
                fill=COLOR_LANDING,
                outline=COLOR_BACKGROUND,
            )
            self.create_oval(
                sx(launch.x) - 5,
                sy(launch.y) - 5,
                sx(launch.x) + 5,
                sy(launch.y) + 5,
                fill=COLOR_LAUNCH,
                outline=COLOR_BACKGROUND,
            )

        self.create_text(
            left + plot_width / 2,
            height - 10,
            text="horizontal distance x (m)",
            fill=COLOR_AXIS_LABEL,
            anchor="s",
        )
        self.create_text(
            16,
            top + plot_height / 2,
            text="height y (m)",
            fill=COLOR_AXIS_LABEL,
            angle=90,
            anchor="center",
        )
