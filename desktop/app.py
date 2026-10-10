"""Desktop GUI for the projectile simulator (Tkinter + ttk).

The layout mirrors ``webapp/src/App.tsx``: launch-condition controls on the
left, result metrics on the right, and the trajectory chart below. All physics
and formatting live in :mod:`gui_model`; this module only wires widgets to it.

Run it with::

    python3 desktop/app.py
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

import errors
import gui_model
from gui_model import LaunchConditions, SimulationOutcome
from trajectory_chart import TrajectoryChart

POLL_INTERVAL_MS = 50
INITIAL_RUN_DELAY_MS = 150

METRIC_ROWS = (
    ("ideal_range", "理想射程（抗力なし）"),
    ("ground_range", "実射程（抗力あり）"),
    ("reduction", "到達距離の低減率"),
    ("flight_time", "飛行時間"),
    ("impact_speed", "着弾速度"),
    ("steps", "積分ステップ数"),
    ("timestep", "刻み幅"),
    ("landed", "着弾"),
)


def _preset_label(value: float) -> str:
    for preset_value, preset_label in gui_model.DRAG_PRESETS:
        if preset_value == value:
            return f"{preset_label}（Cd={preset_value}）"
    return f"Cd={value}"


class RangeCalculatorApp(tk.Tk):
    """The application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Range Calculator Desktop")
        self.geometry("1020x780")
        self.minsize(780, 620)

        self._results: queue.Queue[tuple[str, object]] = queue.Queue()
        self._running = False

        self._velocity_var = tk.DoubleVar(value=gui_model.DEFAULT_VELOCITY_KMPH)
        self._angle_var = tk.DoubleVar(value=gui_model.DEFAULT_ANGLE_DEG)
        self._dt_var = tk.StringVar(value=str(gui_model.DEFAULT_TIMESTEP))
        self._adaptive_var = tk.BooleanVar(value=gui_model.DEFAULT_ADAPTIVE)
        self._cd_var = tk.StringVar(
            value=_preset_label(gui_model.DRAG_COEFFICIENT_DEFAULT)
        )
        self._metric_vars: dict[str, tk.StringVar] = {
            key: tk.StringVar(value="-") for key, _ in METRIC_ROWS
        }
        self._timestep_label_var = tk.StringVar(value="刻み幅")
        self._error_var = tk.StringVar(value="")
        self._warning_var = tk.StringVar(value="")

        self._build_ui()
        self.after(POLL_INTERVAL_MS, self._poll_results)
        self.after(INITIAL_RUN_DELAY_MS, self._run)

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, padding=(20, 16, 20, 8))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            header, text="Range Calculator Desktop", font=("", 16, "bold")
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="弾道シミュレーション（抗力あり RK4）をデスクトップで可視化します。",
        ).pack(anchor="w")

        body = ttk.Frame(self, padding=(20, 8, 20, 8))
        body.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        self._build_controls(body)
        self._build_results(body)

        chart_frame = ttk.Frame(self, padding=(20, 8, 20, 20))
        chart_frame.grid(row=2, column=0, sticky="nsew")
        chart_frame.columnconfigure(0, weight=1)
        chart_frame.rowconfigure(1, weight=1)
        ttk.Label(chart_frame, text="Trajectory", font=("", 11, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self._chart = TrajectoryChart(chart_frame, width=940, height=380)
        self._chart.grid(row=1, column=0, sticky="nsew")

    def _build_controls(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Launch conditions", padding=14)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self._add_scale(
            panel,
            "初速",
            "km/h",
            self._velocity_var,
            gui_model.VELOCITY_MIN,
            gui_model.VELOCITY_MAX,
            digits=1,
        )
        self._add_scale(
            panel,
            "発射角",
            "deg",
            self._angle_var,
            gui_model.ANGLE_MIN,
            gui_model.ANGLE_MAX,
            digits=1,
        )

        cd_row = ttk.Frame(panel)
        cd_row.pack(fill="x", pady=(8, 0))
        ttk.Label(cd_row, text="抗力係数 Cd").pack(side="left")
        cd_values = [
            _preset_label(value) for value, _ in gui_model.DRAG_PRESETS
        ]
        cd_box = ttk.Combobox(
            cd_row,
            textvariable=self._cd_var,
            values=cd_values,
            state="readonly",
            width=28,
        )
        cd_box.pack(side="right")

        dt_row = ttk.Frame(panel)
        dt_row.pack(fill="x", pady=(10, 0))
        ttk.Label(dt_row, text="刻み幅 dt (s)").pack(side="left")
        dt_entry = ttk.Entry(dt_row, textvariable=self._dt_var, width=14)
        dt_entry.pack(side="right")
        dt_entry.bind("<Return>", lambda _event: self._run())

        ttk.Checkbutton(
            panel,
            text="adaptive 刻み（安定性上限で自動短縮）",
            variable=self._adaptive_var,
        ).pack(anchor="w", pady=(10, 0))

        self._run_button = ttk.Button(
            panel, text="シミュレーション実行", command=self._run
        )
        self._run_button.pack(fill="x", pady=(14, 0))

        ttk.Label(
            panel,
            textvariable=self._error_var,
            foreground="#b91c1c",
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(10, 0))

    def _add_scale(
        self,
        parent: ttk.Frame,
        title: str,
        unit: str,
        variable: tk.DoubleVar,
        minimum: float,
        maximum: float,
        digits: int,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 8))
        value_label = ttk.Label(row, text="")
        value_label.pack(anchor="w")

        def update_label(_value: str | None = None) -> None:
            value_label.configure(
                text=f"{title} {variable.get():.{digits}f} {unit}"
            )

        update_label()
        scale = ttk.Scale(
            row,
            from_=minimum,
            to=maximum,
            orient="horizontal",
            variable=variable,
            command=update_label,
        )
        scale.pack(fill="x")

    def _build_results(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Result", padding=14)
        panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        panel.columnconfigure(1, weight=1)

        ttk.Label(
            panel,
            textvariable=self._warning_var,
            foreground="#92400e",
            wraplength=340,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        row_index = 1
        for key, label in METRIC_ROWS:
            label_var = self._timestep_label_var if key == "timestep" else None
            if label_var is not None:
                ttk.Label(panel, textvariable=label_var).grid(
                    row=row_index, column=0, sticky="w", pady=2
                )
            else:
                ttk.Label(panel, text=label).grid(
                    row=row_index, column=0, sticky="w", pady=2
                )
            ttk.Label(
                panel,
                textvariable=self._metric_vars[key],
                font=("", 11, "bold"),
            ).grid(row=row_index, column=1, sticky="w", padx=(16, 0), pady=2)
            row_index += 1

    # ------------------------------------------------------------------ actions

    def _read_conditions(self) -> LaunchConditions:
        return LaunchConditions(
            velocity_kmph=round(self._velocity_var.get()),
            angle_deg=round(self._angle_var.get()),
            dt=float(self._dt_var.get()),
            adaptive=bool(self._adaptive_var.get()),
            drag_coefficient=self._selected_cd(),
        )

    def _selected_cd(self) -> float:
        selected = self._cd_var.get()
        for value, _label in gui_model.DRAG_PRESETS:
            if _preset_label(value) == selected:
                return value
        return gui_model.DRAG_COEFFICIENT_DEFAULT

    def _run(self) -> None:
        if self._running:
            return
        message = gui_model.validate_dt(self._dt_var.get())
        if message is not None:
            self._error_var.set(message)
            return
        self._error_var.set("")
        self._warning_var.set("")
        conditions = self._read_conditions()

        self._running = True
        self._run_button.configure(text="計算中...", state="disabled")
        threading.Thread(
            target=self._worker, args=(conditions,), daemon=True
        ).start()

    def _worker(self, conditions: LaunchConditions) -> None:
        try:
            outcome = gui_model.simulate(conditions)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user as text
            self._results.put(("error", f"エラー: {errors.localize_error(str(exc))}"))
        else:
            self._results.put(("ok", outcome))

    def _poll_results(self) -> None:
        try:
            while True:
                status, payload = self._results.get_nowait()
                if status == "ok":
                    self._apply_outcome(payload)  # type: ignore[arg-type]
                else:
                    self._error_var.set(str(payload))
                    self._set_idle()
        except queue.Empty:
            pass
        self.after(POLL_INTERVAL_MS, self._poll_results)

    def _set_idle(self) -> None:
        self._running = False
        self._run_button.configure(text="シミュレーション実行", state="normal")

    def _apply_outcome(self, outcome: SimulationOutcome) -> None:
        result = outcome.result
        metrics = self._metric_vars
        metrics["ideal_range"].set(f"{gui_model.format_number(result.ideal_range)} m")
        metrics["ground_range"].set(
            f"{gui_model.format_number(result.ground_range)} m"
        )
        metrics["reduction"].set(
            f"{gui_model.format_number(outcome.reduction_percent, 1)} %"
        )
        metrics["flight_time"].set(
            f"{gui_model.format_number(result.flight_time)} s"
        )
        metrics["impact_speed"].set(
            f"{gui_model.format_number(result.impact_speed)} m/s"
        )
        metrics["steps"].set(str(result.steps))
        self._timestep_label_var.set(
            "最短刻み" if outcome.conditions.adaptive else "刻み幅"
        )
        if result.timestep_min is not None:
            metrics["timestep"].set(
                f"{gui_model.format_decimal(result.timestep_min)} s"
            )
        metrics["landed"].set("yes" if result.landed else "no")

        self._warning_var.set(
            "時間上限に達しました。着弾前に計算が終了しています。"
            if result.timed_out
            else ""
        )
        self._chart.show(outcome)
        self._set_idle()


def main() -> None:
    app = RangeCalculatorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
