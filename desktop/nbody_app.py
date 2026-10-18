"""Desktop GUI for mutual-gravity N-body systems.

This is the third desktop entry point (see :mod:`app_common`). It shows the
scenario preset (Sun-centred or Earth-centred), the per-body inputs (name,
bulk density, radius, state) which stay freely editable after a preset is
loaded, and the timestep / time span. A preset starts from its central body
alone at the origin at rest; from the second body on, each body can be loaded
from a catalogue of the Sun, the planets, and the Moon, which seeds a circular
orbit about the central body. Each body's ``mu`` is derived from its density
and radius (``mu = G * density * 4/3 pi r^3``) and shown read-only. A run is
recorded frame by frame and played back with a slider under the chart.

Run it with::

    python3 desktop/nbody_app.py
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

import errors
import gui_model
from app_common import BaseApp
from gui_model import NBodyConditions, NBodyOutcome
from trajectory_chart import NBodyChart

# Playback length in wall-clock seconds; the slider advances
# ``frame_count / (PLAY_SECONDS * PLAY_FPS)`` frames per tick.
PLAY_SECONDS = 12.0
PLAY_FPS = 30

# The UI row order must match gui_model.NBodyRow (name, density, radius,
# then the six state components).
NBODY_ROW_ORDER: tuple[str, ...] = (
    "name", "density", "radius", "x", "y", "z", "vx", "vy", "vz",
)

BODY_FIELD_LABELS: dict[str, str] = {
    "name": "名前",
    "density": "体積密度 (kg/m^3)",
    "radius": "半径 (m)",
    "x": "x (m)",
    "y": "y (m)",
    "z": "z (m)",
    "vx": "vx (m/s)",
    "vy": "vy (m/s)",
    "vz": "vz (m/s)",
}

# Entry rows inside one body group; the mu line below them is read-only.
BODY_ENTRY_ROWS: tuple[tuple[str, ...], ...] = (
    ("name", "density", "radius"),
    ("x", "y", "z"),
    ("vx", "vy", "vz"),
)

# Per-body catalogue dropdown: the catalogue names plus a sentinel that leaves
# the hand-entered values untouched (used by the central body and by "add").
CUSTOM_CATALOG_LABEL = "（カスタム）"
CATALOG_LABELS: tuple[str, ...] = tuple(
    name for name, _density, _radius, _orbit in gui_model.NBODY_CATALOG
) + (CUSTOM_CATALOG_LABEL,)


class _ScrolledFrame(ttk.Frame):
    """A vertically scrollable container: canvas + scrollbar + inner frame.

    The body-input column grows with every added body; without scrolling it
    would eventually push the chart out of the window. The inner frame is the
    public surface: widgets are packed into ``self.inner`` as usual. The canvas
    keeps a small requested height so the frame stretches to the space it is
    given (via grid ``weight``) instead of demanding a fixed block that would
    push the fixed controls below it off-screen.
    """

    def __init__(self, master: tk.Misc, height: int = 160) -> None:
        super().__init__(master)
        self.canvas = tk.Canvas(
            self, highlightthickness=0, borderwidth=0, height=height
        )
        scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.inner = ttk.Frame(self.canvas)
        window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.inner.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            ),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(window, width=event.width),
        )
        # Windows / macOS send MouseWheel; some X11 builds send Button-4/5.
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind(
            "<Button-4>", lambda _event: self.canvas.yview_scroll(-1, "units")
        )
        self.canvas.bind(
            "<Button-5>", lambda _event: self.canvas.yview_scroll(1, "units")
        )

    def _on_mousewheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")


class NBodyApp(BaseApp):
    """The mutual-gravity N-body window."""

    def __init__(self) -> None:
        super().__init__(
            title="Range Calculator Desktop — 多体 (N-body)",
            geometry="1200x800",
            minsize=(900, 650),
        )

        self._preset_var = tk.StringVar(value=gui_model.NBODY_PRESETS[0][1])
        self._dt_var = tk.StringVar()
        self._time_var = tk.StringVar()
        self._frame_var = tk.DoubleVar(value=0.0)
        self._body_vars: list[dict[str, tk.StringVar]] = []
        self._last_outcome: NBodyOutcome | None = None
        self._playing = False
        self._play_after_id: str | None = None

        self._build_ui()
        self._load_preset()
        self.activate()

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        # Side-by-side layout: the input / result column is scrollable on the
        # left, so the chart on the right always keeps its height no matter
        # how many bodies are configured.
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(20, 16, 20, 8))
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(
            header,
            text="Range Calculator Desktop — 多体 (N-body)",
            font=("", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header, text="相互重力（点質量）の多体シミュレーション"
        ).pack(anchor="w")

        body = ttk.Frame(self, padding=(20, 8, 20, 12))
        body.grid(row=1, column=0, columnspan=2, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        self._build_controls(left)
        self._build_results(left)

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self._chart = NBodyChart(right)
        self._chart.grid(row=0, column=0, sticky="nsew")
        self._build_playback(right)

    def _build_controls(self, parent: ttk.Frame) -> None:
        # Only the body groups scroll. The preset, the timestep / time span,
        # the add/remove buttons, and the run button stay pinned in the panel
        # so they never scroll out of reach however many bodies are configured.
        # Grid (not pack) keeps the pinned rows at their natural height and
        # lets the body list absorb any resizing, so shrinking the window
        # never clips the run button or the error message.
        panel = ttk.LabelFrame(parent, text="N-body conditions", padding=14)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)

        top = ttk.Frame(panel)
        top.grid(row=0, column=0, sticky="ew")

        preset_row = ttk.Frame(top)
        preset_row.pack(fill="x", pady=(0, 8))
        ttk.Label(preset_row, text="プリセット").pack(side="left")
        preset_box = ttk.Combobox(
            preset_row,
            textvariable=self._preset_var,
            values=[label for _value, label in gui_model.NBODY_PRESETS],
            state="readonly",
            width=28,
        )
        preset_box.pack(side="right")
        preset_box.bind("<<ComboboxSelected>>", self._load_preset)

        dt_row = ttk.Frame(top)
        dt_row.pack(fill="x")
        ttk.Label(dt_row, text="刻み幅 dt (s)").pack(side="left")
        dt_entry = ttk.Entry(dt_row, textvariable=self._dt_var, width=14)
        dt_entry.pack(side="right")
        dt_entry.bind("<Return>", lambda _event: self._run())

        time_row = ttk.Frame(top)
        time_row.pack(fill="x", pady=(6, 0))
        ttk.Label(time_row, text="最大時間 (s)").pack(side="left")
        time_entry = ttk.Entry(time_row, textvariable=self._time_var, width=14)
        time_entry.pack(side="right")
        time_entry.bind("<Return>", lambda _event: self._run())

        ttk.Label(
            panel, text="天体（天体 1 が中心。2 つ目以降はカタログから選択）"
        ).grid(row=1, column=0, sticky="w", pady=(10, 4))

        self._controls_scroll = _ScrolledFrame(panel)
        self._controls_scroll.grid(row=2, column=0, sticky="nsew")
        self._bodies_container = self._controls_scroll.inner

        bottom = ttk.Frame(panel)
        bottom.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        buttons = ttk.Frame(bottom)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="天体を追加", command=self._add_body).pack(
            side="left"
        )
        ttk.Button(
            buttons, text="最後の天体を削除", command=self._remove_body
        ).pack(side="left", padx=(8, 0))

        self._run_button = ttk.Button(
            bottom, text=self.run_label, command=self._run
        )
        self._run_button.pack(anchor="w", pady=(12, 0))

        ttk.Label(
            bottom,
            textvariable=self._error_var,
            foreground="#b91c1c",
            wraplength=340,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

    def _build_results(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Result", padding=14)
        panel.grid(row=1, column=0, sticky="new", pady=(12, 0))
        panel.columnconfigure(1, weight=1)
        self._metrics_panel = panel

        ttk.Label(
            panel,
            textvariable=self._warning_var,
            foreground="#92400e",
            wraplength=340,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self._render_metric_rows(gui_model.DEFAULT_NBODY_METRIC_ROWS)

    def _build_playback(self, parent: ttk.Frame) -> None:
        row = ttk.Frame(parent)
        row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        row.columnconfigure(1, weight=1)

        self._play_button = ttk.Button(
            row, text="再生", command=self._toggle_playback, width=6
        )
        self._play_button.grid(row=0, column=0, sticky="w")

        self._frame_scale = ttk.Scale(
            row,
            from_=0,
            to=0,
            orient="horizontal",
            variable=self._frame_var,
            command=self._on_frame_change,
        )
        self._frame_scale.grid(row=0, column=1, sticky="ew", padx=12)

        self._time_label = ttk.Label(row, text="t = -", width=26, anchor="e")
        self._time_label.grid(row=0, column=2, sticky="e")

    # ------------------------------------------------------------------ helpers

    def _load_preset(self, *_args: object) -> None:
        value = self._selected_value(self._preset_var, gui_model.NBODY_PRESETS)
        conditions = gui_model.nbody_preset_conditions(value)
        self._dt_var.set(f"{conditions.dt:g}")
        self._time_var.set(f"{conditions.max_time:.0f}")
        self._body_vars = [
            self._fields_from_spec(spec) for spec in conditions.bodies
        ]
        self._rebuild_body_groups()

    @staticmethod
    def _fields_from_spec(spec: gui_model.NBodySpec) -> dict[str, tk.StringVar]:
        fields = {
            "name": tk.StringVar(value=spec.name),
            "density": tk.StringVar(value=repr(spec.density)),
            "radius": tk.StringVar(value=repr(spec.radius)),
            # Per-body catalogue selector (index >= 1); the sentinel keeps the
            # hand-entered values, which is also the initial state.
            "catalog": tk.StringVar(value=CUSTOM_CATALOG_LABEL),
            # Read-only display of the derived mu; kept in sync by traces.
            "mu_display": tk.StringVar(value=f"μ = {spec.mu:.6e} m^3/s^2"),
        }
        for key, value in zip(gui_model.NBODY_STATE_FIELDS, spec.state):
            fields[key] = tk.StringVar(value=repr(value))

        def sync_mu(
            *_args: object, density=fields["density"], radius=fields["radius"],
            display=fields["mu_display"],
        ) -> None:
            try:
                mu = gui_model.nbody_mu(
                    float(density.get()), float(radius.get())
                )
            except ValueError:
                display.set("μ = -")
            else:
                display.set(f"μ = {mu:.6e} m^3/s^2")

        fields["density"].trace_add("write", sync_mu)
        fields["radius"].trace_add("write", sync_mu)
        return fields

    def _rebuild_body_groups(self) -> None:
        for child in self._bodies_container.winfo_children():
            child.destroy()
        for index, fields in enumerate(self._body_vars):
            title = "天体 1（中心）" if index == 0 else f"天体 {index + 1}"
            group = ttk.LabelFrame(
                self._bodies_container, text=title, padding=8
            )
            group.pack(fill="x", pady=(0, 6))
            if index == 0:
                ttk.Label(
                    group,
                    text="中心天体（初期値は座標原点・静止）",
                    font=("", 9),
                ).pack(anchor="w", pady=(0, 4))
            else:
                self._build_catalog_row(group, index, fields)
            for row_fields in BODY_ENTRY_ROWS:
                entry_row = ttk.Frame(group)
                entry_row.pack(fill="x", pady=(0, 4))
                for field in row_fields:
                    cell = ttk.Frame(entry_row)
                    cell.pack(side="left", expand=True, fill="x", padx=(0, 6))
                    ttk.Label(
                        cell, text=BODY_FIELD_LABELS[field], font=("", 9)
                    ).pack(anchor="w")
                    entry = ttk.Entry(cell, textvariable=fields[field], width=13)
                    entry.pack(fill="x")
                    entry.bind("<Return>", lambda _event: self._run())
            ttk.Label(
                group, textvariable=fields["mu_display"], font=("", 9)
            ).pack(anchor="w", pady=(2, 0))

    def _build_catalog_row(
        self, group: ttk.LabelFrame, index: int, fields: dict[str, tk.StringVar]
    ) -> None:
        row = ttk.Frame(group)
        row.pack(fill="x", pady=(0, 4))
        ttk.Label(row, text="天体カタログ", font=("", 9)).pack(side="left")
        catalog_box = ttk.Combobox(
            row,
            textvariable=fields["catalog"],
            values=list(CATALOG_LABELS),
            state="readonly",
            width=12,
        )
        catalog_box.pack(side="right")
        catalog_box.bind(
            "<<ComboboxSelected>>",
            lambda _event, i=index: self._on_catalog_selected(i),
        )

    def _on_catalog_selected(self, index: int) -> None:
        """Load a catalogue body's density/radius and a circular orbit state.

        The body is placed in a circular orbit about the central body (天体 1),
        whose mu comes from the current density and radius, so an edited centre
        is honoured. The ``（カスタム）`` sentinel leaves the inputs untouched.
        """
        fields = self._body_vars[index]
        label = fields["catalog"].get()
        if label == CUSTOM_CATALOG_LABEL or index == 0:
            return
        central = self._body_vars[0]
        try:
            central_radius = float(central["radius"].get())
            central_density = float(central["density"].get())
        except ValueError:
            self._error_var.set(
                "天体 1（中心）の体積密度と半径を先に数値で入力してください。"
            )
            return
        _name, _density, body_radius, _orbit = next(
            entry for entry in gui_model.NBODY_CATALOG if entry[0] == label
        )
        central_mu = gui_model.nbody_mu(central_density, central_radius)
        spec = gui_model.nbody_catalog_spec(
            label, central_mu, central_radius + body_radius
        )
        self._error_var.set("")
        fields["name"].set(spec.name)
        fields["density"].set(repr(spec.density))
        fields["radius"].set(repr(spec.radius))
        for key, value in zip(gui_model.NBODY_STATE_FIELDS, spec.state):
            fields[key].set(repr(value))

    def _add_body(self) -> None:
        # A blank, editable body; the per-body catalogue dropdown then seeds its
        # density/radius and a circular orbit about the centre on selection.
        spec = gui_model.NBodySpec(
            name=f"天体{len(self._body_vars) + 1}",
            density=1000.0,
            radius=1.0,
            state=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
        self._body_vars.append(self._fields_from_spec(spec))
        self._rebuild_body_groups()

    def _remove_body(self) -> None:
        if len(self._body_vars) <= 1:
            return
        self._body_vars.pop()
        self._rebuild_body_groups()

    def _update_time_label(self, index: int) -> None:
        outcome = self._last_outcome
        if outcome is None or not outcome.frames:
            self._time_label.configure(text="t = -")
            return
        frame = outcome.frames[min(max(index, 0), len(outcome.frames) - 1)]
        days = frame.t / 86400.0
        self._time_label.configure(
            text=f"t = {frame.t:,.0f} s（{days:.2f} 日）"
        )

    # ----------------------------------------------------------------- playback

    def _on_frame_change(self, value: str) -> None:
        try:
            index = int(round(float(value)))
        except ValueError:
            return
        index = self._chart.set_frame(index)
        if abs(self._frame_var.get() - index) > 0.5:
            self._frame_var.set(index)
        self._update_time_label(index)

    def _toggle_playback(self) -> None:
        if self._playing:
            self._stop_playback()
        else:
            self._start_playback()

    def _start_playback(self) -> None:
        frame_count = self._chart.frame_count
        if frame_count < 2:
            return
        self._playing = True
        self._play_button.configure(text="停止")
        step = max(1, math.ceil(frame_count / (PLAY_SECONDS * PLAY_FPS)))

        def tick() -> None:
            if not self._playing:
                return
            index = (self._chart.current_index + step) % frame_count
            self._frame_var.set(index)
            self._chart.set_frame(index)
            self._update_time_label(index)
            self._play_after_id = self.after(int(1000 / PLAY_FPS), tick)

        tick()

    def _stop_playback(self) -> None:
        self._playing = False
        if self._play_after_id is not None:
            try:
                self.after_cancel(self._play_after_id)
            except tk.TclError:
                pass
            self._play_after_id = None
        if hasattr(self, "_play_button"):
            self._play_button.configure(text="再生")

    # ------------------------------------------------------------------ actions

    def _read_conditions(self) -> NBodyConditions:
        rows = [
            tuple(fields[key].get() for key in NBODY_ROW_ORDER)
            for fields in self._body_vars
        ]
        return gui_model.nbody_conditions_from_rows(
            rows, self._dt_var.get(), self._time_var.get()
        )

    def _run(self) -> None:
        try:
            conditions = self._read_conditions()
        except ValueError as exc:
            self._error_var.set(str(exc))
            return
        message = gui_model.validate_nbody_conditions(conditions)
        if message is not None:
            self._error_var.set(message)
            return
        self._error_var.set("")
        self._warning_var.set("")
        self._begin_run(conditions)

    def _worker(self, conditions: NBodyConditions) -> None:
        try:
            outcome = gui_model.run_nbody(conditions)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user as text
            self._results.put(
                ("error", f"エラー: {errors.localize_error(str(exc))}")
            )
        else:
            self._results.put(("ok", outcome))

    def _apply_outcome(self, outcome: NBodyOutcome) -> None:
        self._stop_playback()
        self._last_outcome = outcome
        self._render_metric_rows(gui_model.nbody_result_metrics(outcome))
        self._warning_var.set("")
        self._chart.show(outcome)
        self._frame_scale.configure(to=max(len(outcome.frames) - 1, 0))
        self._frame_var.set(0)
        self._update_time_label(0)
        self._set_idle()
        # Start the playback automatically so the run animates on arrival.
        self._start_playback()


def main() -> None:
    app = NBodyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
